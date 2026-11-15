# Design

## Context

Ponto de partida é o `projeto_epidemiologia` (ver proposal.md - Why):

- **Ingestão**: `scripts/carregar_bigquery.py` (um alvo por país, `WRITE_TRUNCATE`, tudo STRING) lê arquivos de `microdados/` e `dados_paho/` na máquina local; só Colômbia, PAHO e Bolívia têm downloader. Sem argumentos, a carga quebra no alvo `bolivia`.
- **Modelagem**: dbt `utfpr_dengue` em `ppgcc-dengue-project`, raw em `microdados`, camadas `bronze` (views), `silver` e `gold` (14 tabelas, todas com `gold_generated_at`). Profile em `~/.dbt/profiles.yml`, fora do repo.
- **API**: FastAPI com 14 routers `/gold/*`, `limit` 200/1000, filtros por igualdade; `gold_sync.py` copia a gold para parquet a cada 1h e o DuckDB lê os arquivos. CORS `*`.
- **Front**: Vite + React, `VITE_API_BASE_URL` embutido no build, nginx servindo `dist/`.
- **Deploy**: `infra/docker-compose.yaml` em Swarm + Traefik (`network_public`, certresolver `letsencryptresolver`), imagens `anselmomendes/projeto_epidemiologia_{backend,frontend}:1.0` publicadas manualmente.

Restrição: tudo roda numa única VPS gerenciada pelo Portainer (Swarm). O código-fonte a migrar está fora do `atlas_epidemiologia`; a implementação precisa de acesso de leitura a `../projeto_epidemiologia` (ex.: `/add-dir`).

## Goals / Non-Goals

**Goals:**
- Cada componente com build, imagem, ciclo de deploy e configuração próprios.
- Fase 1 entrega CI/CD de backend + frontend e ingestão/dbt executáveis manualmente em container; Airflow é a última fase.
- Zero credenciais no repositório e nas imagens.

**Non-Goals:**
- Ambiente de homologação separado (um só ambiente na VPS).
- Infra como código do GCP (datasets e service accounts continuam criados manualmente; apenas documentados).
- Autenticação de usuários no front/API.

## Decisions

### 1. Monorepo com composes separados
```
atlas_epidemiologia/
├── pipelines/   # pacote Python: CLI de ingestão (download + carga raw)
├── dbt/         # projeto dbt (ex-utfpr_dengue) + profiles.yml por env var
├── backend/     # FastAPI
├── frontend/    # Vite + React + nginx
├── airflow/     # DAGs + Dockerfile do Airflow (última fase)
├── deploy/      # app.stack.yml (front+api+redis) e data.stack.yml (Airflow)
└── .github/workflows/  # backend.yml, frontend.yml, pipelines.yml, airflow.yml
```
Escolhido pelo usuário. Workflows usam `paths:` para isolar componentes. Alternativa (repo por componente) descartada pelo overhead de versionamento entre repos para um projeto de uma pessoa.

### 2. BigQuery: manter projeto e nomes de datasets
Mantém `ppgcc-dengue-project`, raw em `microdados` e `bronze/silver/gold`. Renomear a raw (`raw`) quebraria `sources.yaml` e não traz ganho agora. Gold tables devem ser **clusterizadas por `country_iso3`** (e particionadas por ano quando houver data) para reduzir bytes lidos pela API.

### 3. Ingestão: pacote `pipelines` com CLI por fonte e landing configurável
`python -m pipelines load <fonte>` / `download <fonte>`, reaproveitando a lógica de `carregar_bigquery.py` dividida em um módulo por fonte. Entrada lida de `ATLAS_LANDING_URI`, que aceita caminho local (volume) ou `gs://bucket/landing/` — os arquivos sem downloader (Argentina, Equador, Peru, DuckDB do SINAN) são enviados uma vez ao bucket e lidos de lá. Colunas `_source_file` e `_loaded_at` em toda tabela raw. Carga continua `WRITE_TRUNCATE` (idempotente). Alternativa: volume Docker na VPS — suportado pelo mesmo URI, mas GCS é preferido por não prender os dados à VPS.

### 4. Uma imagem `pipelines` para ingestão + dbt
Imagem Python 3.12 com o pacote `pipelines`, `dbt-bigquery` e o projeto `dbt/` (deps instalados no build). Uso manual: `docker run --env-file … atlas-epidemiologia-pipelines pipelines load colombia` ou `… dbt build --select …`. `dbt/profiles.yml` versionado com `env_var('GCP_PROJECT')`, `env_var('BQ_LOCATION')` e `method: service-account-json` lendo `GOOGLE_APPLICATION_CREDENTIALS_JSON` (mesma convenção que a API já usa). Python 3.12 (e não 3.14 como no projeto antigo) por compatibilidade com dbt e com a imagem do Airflow.

### 5. Backend: BigQuery direto + Redis com chave versionada por geração
- `db.py` substituído por um repositório BigQuery: `SELECT <colunas fixas> FROM gold.<tabela> WHERE col = @p … ORDER BY … LIMIT @limit OFFSET @offset`, com `ScalarQueryParameter`; nome de tabela e colunas vêm de whitelist no código. `maximum_bytes_billed` configurável por query como trava de custo.
- **Cache**: chave `atlas:gold:{tabela}:{geracao}:{sha1(rota+filtros+paginação)}`, valor = JSON da resposta, TTL máximo (`CACHE_TTL_SECONDS`, padrão 24h). `geracao` = `last_modified` da tabela via `tables.get` (metadado, **sem custo de query**), guardado em `atlas:gen:{tabela}` com TTL de 5 min. Quando o dbt reconstrói a tabela a geração muda e as chaves antigas simplesmente param de ser lidas (expiram pelo TTL). Rejeitado: consultar `MAX(gold_generated_at)` a cada checagem (cobra bytes lidos).
- `POST /admin/cache/invalidate` protegido por `ADMIN_TOKEN` (header `Authorization: Bearer`) apaga `atlas:gen:*` e `atlas:gold:*`; é chamado pelo Airflow no fim do pipeline e serve para uso manual.
- Falha de Redis → log de aviso e consulta direta (circuit breaker simples com timeout curto).
- Rotas síncronas continuam na threadpool do FastAPI (cliente BigQuery é thread-safe). Remove `gold_sync.py`, DuckDB, volume `api_data` e o loop de lifespan.
- CORS: `CORS_ALLOWED_ORIGINS` (lista), padrão `https://dengue.contovisual.com.br`.
- Alternativa considerada: manter cópia parquet + DuckDB (custo zero por request). Descartada por decisão do usuário; o custo é controlado pelo cache, clustering e `maximum_bytes_billed`.

### 6. Frontend: configuração em runtime
O nginx da imagem roda um script em `/docker-entrypoint.d/` que gera `/config.js` a partir de `API_BASE_URL` (`window.__ATLAS_CONFIG__ = {apiBaseUrl: …}`); `index.html` carrega `/config.js` antes do bundle e `src/lib/api.ts` usa `window.__ATLAS_CONFIG__?.apiBaseUrl ?? import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000"`. `config.js` servido com `no-cache`. Alternativa (proxy `/api` no nginx do front) descartada porque a API já tem domínio próprio no Traefik.

### 7. CI: GitHub Actions → DockerHub
Por componente: `lint+test` (ruff/pytest no backend e pipelines, `tsc`+`vite build` no front, `dbt parse` no pipelines) → `docker/build-push-action` com cache GHA. Em PR: só valida e builda (`push: false`). Em `main`: publica `anselmomendes/atlas-epidemiologia-<componente>:{sha7,latest}`; em tag `v*`: também `:vX.Y.Z`. Secrets: `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN`, `PORTAINER_WEBHOOK_<COMPONENTE>`.

### 8. CD: webhook de serviço do Portainer com tag imutável
Cada serviço Swarm (`atlas-app_backend`, `atlas-app_frontend`) tem webhook de serviço habilitado no Portainer. O workflow chama `POST <webhook>?tag=<sha7>`, o que atualiza a imagem do serviço para a tag exata publicada (rolling update). `deploy/app.stack.yml` usa `image: …-backend:${BACKEND_TAG:-latest}` para o primeiro deploy. Rollback = chamar o webhook com tag anterior ou editar a variável na stack. Alternativas: GitOps do Portainer (polling do repo) — exigiria commit da tag no compose a cada build; `latest` + pull forçado — sem rastreabilidade. Swarm `update_config: order: start-first` + `healthcheck` no backend para não derrubar tráfego.

### 9. Stack da aplicação
`deploy/app.stack.yml`: `frontend`, `backend`, `redis` (redis:7-alpine, `maxmemory 256mb`, `allkeys-lru`, sem porta publicada, só rede interna `atlas_internal`). Front e API na `network_public` com os mesmos labels Traefik atuais. Segredos (`GOOGLE_APPLICATION_CREDENTIALS_JSON`, `ADMIN_TOKEN`) como env vars da stack no Portainer.

### 10. Airflow (última fase)
`deploy/data.stack.yml`: Airflow 2.x (LocalExecutor) com `postgres` de metadados, imagem `atlas-epidemiologia-airflow` = `apache/airflow` + pacote `pipelines` + `dbt-bigquery` + projeto `dbt/` + DAGs. Tarefas via `BashOperator` executando os **mesmos comandos** da imagem `pipelines` (`pipelines load <fonte>`, `dbt build`), um task por fonte (task group), `max_active_runs=1`, `retries=2`. Tarefa do modelo de AI executa `AI_MODEL_COMMAND` (Variable); vazio → `AirflowSkipException`; trigger rule da invalidação = `none_failed`. Última tarefa chama `/admin/cache/invalidate`. UI exposta em `airflow.dengue.contovisual.com.br` via Traefik com login do Airflow. Alternativa `DockerOperator` descartada: exige montar o socket do Docker no worker (risco de segurança) e não combina bem com Swarm.

## Risks / Trade-offs

- [Custo BigQuery por request sem cache] → clustering das gold, `maximum_bytes_billed`, TTL longo, chave por geração; acompanhar `INFORMATION_SCHEMA.JOBS` na primeira semana.
- [Latência de cold cache (~1–2 s por query BigQuery)] → aquecimento opcional: o Airflow pode, após invalidar, chamar as rotas usadas pela página inicial.
- [Memória da VPS com Airflow + Postgres + Redis + app] → Airflow só entra na última fase; medir RAM livre antes; LocalExecutor com `parallelism` baixo.
- [Tabelas raw grandes (Brasil ~33M linhas) em CTAS] → manter CTAS dentro do BigQuery (já é o padrão hoje), nunca baixar para o container.
- [Webhook do Portainer exposto na internet] → URL tratada como secret; webhook só aceita atualizar imagem do serviço.
- [Front antigo usa hosts iguais aos novos] → migração com hosts temporários (abaixo).
- [Python 3.12 vs 3.14 do projeto antigo] → rodar a carga de todas as fontes no container antes de desligar os scripts antigos.

## Migration Plan

1. Criar `pipelines/` e `dbt/` a partir do projeto antigo; rodar manualmente em container contra o mesmo BigQuery e comparar contagens das tabelas raw/gold.
2. Backend novo + Redis com testes; publicar via CI; subir stack `atlas-app` com hosts temporários (`next.dengue…`, `api-next.dengue…`).
3. Validar o front novo contra a API nova (mesmas respostas das rotas `/gold/*` da API antiga para os filtros usados pelo front).
4. Trocar os hosts do Traefik para `dengue.contovisual.com.br` / `api.dengue.contovisual.com.br` e remover a stack antiga. **Rollback**: redeploy da stack antiga (imagens `:1.0` continuam no DockerHub).
5. Última fase: stack `atlas-data` com Airflow; executar DAG manualmente, depois habilitar agendamento e aposentar a execução manual.

## Open Questions

- Namespace do DockerHub: assumido `anselmomendes` (o mesmo das imagens atuais).
- Bucket GCS do landing: nome e região (mesma localização do dataset, `US`).
- Frequência de agendamento de cada fonte (semanal na maioria, diária no Brasil segundo `sources.yaml`).
- TTL padrão do cache e `maximum_bytes_billed` exatos — ajustar após medir.
