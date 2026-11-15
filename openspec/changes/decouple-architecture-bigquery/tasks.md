# Tasks

## 1. Estrutura do monorepo

- [ ] 1.1 Garantir acesso de leitura a `../projeto_epidemiologia` (ex.: `/add-dir`) e criar as pastas `pipelines/`, `dbt/`, `backend/`, `frontend/`, `airflow/`, `deploy/`, `.github/workflows/`; verificar com `ls` que existem
- [ ] 1.2 Criar `.gitignore` raiz (chaves `*.json` de service account, `.env*`, `target/`, `dbt_packages/`, `node_modules/`, `dist/`, `.venv/`) e `.env.example` com todas as variáveis usadas (`GCP_PROJECT`, `BQ_LOCATION`, `GOOGLE_APPLICATION_CREDENTIALS_JSON`, `ATLAS_LANDING_URI`, `REDIS_URL`, `ADMIN_TOKEN`, `CORS_ALLOWED_ORIGINS`, `CACHE_TTL_SECONDS`, `API_BASE_URL`); verificar que `git check-ignore` ignora um arquivo `chave.json` de teste
- [ ] 1.3 Escrever `README.md` raiz com o diagrama da nova arquitetura e o papel de cada pasta; verificar que os links para cada componente resolvem

## 2. Modelagem (dbt)

- [ ] 2.1 Copiar `utfpr_dengue/` (models, macros, seeds, docs, `dbt_project.yml`, `packages.yml` se houver) para `dbt/`, sem `target/`, `logs/` e `dbt_packages/`; verificar com `dbt parse` que o projeto compila
- [ ] 2.2 Criar `dbt/profiles.yml` versionado com `env_var('GCP_PROJECT')`, `env_var('BQ_LOCATION')` e `method: service-account-json` a partir de `GOOGLE_APPLICATION_CREDENTIALS_JSON`; verificar `dbt debug --profiles-dir dbt` com as variáveis exportadas e sem `~/.dbt/profiles.yml`
- [ ] 2.3 Adicionar `cluster_by: ['country_iso3']` (e partição por ano onde houver coluna de data) às tabelas gold que filtram por país; verificar com `dbt build --select gold` e conferir no BigQuery que as tabelas estão clusterizadas
- [ ] 2.4 Adicionar testes `not_null`/`unique` nas chaves das tabelas gold e em `silver_dengue_weekly_cases`; verificar que `dbt test` passa e que um teste quebrado propositalmente faz `dbt build` sair com código ≠ 0
- [ ] 2.5 Documentar em `dbt/README.md` como rodar build completo e seleção parcial (`--select +source:raw_uftpr_microdados.raw_uftpr_microdados_colombia+`); verificar executando o comando documentado

## 3. Ingestão (`pipelines`)

- [ ] 3.1 Criar o pacote `pipelines` (Python 3.12, `pyproject.toml` com uv) com CLI `pipelines load <fonte>` e `pipelines download <fonte>`, registry de fontes e erro com lista de fontes válidas para nome desconhecido; verificar com teste pytest do CLI
- [ ] 3.2 Implementar leitura de entrada via `ATLAS_LANDING_URI` aceitando caminho local e `gs://`; verificar com teste usando diretório temporário local
- [ ] 3.3 Migrar a lógica de `carregar_bigquery.py` para um módulo por fonte (brasil-CTAS, paho, colombia, argentina, equador, peru, bolivia, municipios), com `WRITE_TRUNCATE`, tudo STRING e colunas `_source_file`/`_loaded_at`; verificar com testes unitários do empilhamento de cada fonte usando amostras pequenas
- [ ] 3.4 Fazer cada fonte falhar com mensagem do caminho esperado quando a entrada não existir, sem tocar na tabela raw; verificar com teste (caso Bolívia sem arquivo)
- [ ] 3.5 Migrar os downloaders existentes (`baixar_paho_dengue.py`, `baixar_bolivia_dengue.py`, `baixar_microdados_sivigila.py`) para `pipelines download <fonte>` gravando em `ATLAS_LANDING_URI`; verificar baixando uma fonte para diretório local
- [ ] 3.6 Criar o bucket GCS de landing e subir os arquivos sem downloader (Argentina, Equador, Peru, SINAN/municípios); verificar com `gcloud storage ls`
- [ ] 3.7 Ajustar `dbt/models/sources.yaml` e models bronze se as novas colunas de proveniência exigirem; verificar com `dbt build --select bronze`
- [ ] 3.8 Documentar em `pipelines/README.md` cada fonte, sua origem e o comando de carga; verificar executando um comando documentado

## 4. Imagem `pipelines` (ingestão + dbt)

- [ ] 4.1 Criar `pipelines/Dockerfile` (Python 3.12 slim, pacote `pipelines`, `dbt-bigquery`, projeto `dbt/` com `dbt deps` no build) e `.dockerignore`; verificar `docker build` e que `docker run … pipelines --help` e `docker run … dbt --version` funcionam
- [ ] 4.2 Executar manualmente no container a carga de todas as fontes e `dbt build` completo contra o BigQuery; verificar comparando contagens de linhas das tabelas raw e gold com as atuais (registrar o resultado em `pipelines/README.md`)
- [ ] 4.3 Verificar que a imagem não contém chave nem `.env` (`docker run --rm <img> sh -c 'find / -name "*.json" -path "*service*" -o -name ".env"'` vazio)

## 5. Backend (BigQuery + Redis)

- [ ] 5.1 Copiar `infra/api/app` para `backend/app`, remover `gold_sync.py`, DuckDB e o loop do lifespan; criar `backend/pyproject.toml` com `fastapi`, `uvicorn`, `google-cloud-bigquery`, `redis`, `pytest`, `ruff`; verificar que `ruff check` passa e a app importa
- [ ] 5.2 Implementar o repositório BigQuery com whitelist de tabela/colunas por rota, `ScalarQueryParameter` para filtros, `LIMIT/OFFSET` parametrizados e `maximum_bytes_billed`; verificar com teste que um filtro `' OR 1=1 --` vira parâmetro e não SQL
- [ ] 5.3 Adaptar os 14 routers ao novo repositório mantendo rotas, filtros e campos; verificar com testes de contrato (cliente BigQuery mockado) comparando campos com os tipos de `frontend/src/lib/api.ts`
- [ ] 5.4 Implementar cache Redis com chave por geração (`tables.get` → `last_modified`, cacheado 5 min) e TTL máximo configurável; verificar com testes (fakeredis) que requisição repetida não chama o BigQuery e que mudança de `last_modified` gera miss
- [ ] 5.5 Implementar `POST /admin/cache/invalidate` com `ADMIN_TOKEN`; verificar com testes: 401 sem token, cache vazio após chamada com token
- [ ] 5.6 Implementar degradação sem Redis (timeout curto + fallback direto); verificar com teste em que o Redis levanta erro e a rota responde 200
- [ ] 5.7 Implementar `/health` com status de BigQuery e Redis (503 se BigQuery inacessível) e CORS via `CORS_ALLOWED_ORIGINS`, apenas GET; verificar com testes
- [ ] 5.8 Criar `backend/Dockerfile` (Python 3.12 slim, usuário não-root, `HEALTHCHECK` em `/health`) e `.dockerignore`; verificar `docker build` e subida local com Redis (`docker compose -f backend/compose.dev.yml up`) respondendo uma rota `/gold/*` real
- [ ] 5.9 Atualizar `backend/README.md` (variáveis, rotas, cache, invalidação); verificar que o exemplo de `curl` documentado funciona localmente

## 6. Frontend (configuração em runtime)

- [ ] 6.1 Copiar `front/` para `frontend/` sem `dist/`, `node_modules/`, `.env` e logs; verificar `npm ci && npm run build`
- [ ] 6.2 Adicionar `/config.js` carregado no `index.html` e ajustar `src/lib/api.ts` para usar `window.__ATLAS_CONFIG__.apiBaseUrl` com fallback para `VITE_API_BASE_URL`; verificar com `npm run build` e `tsc --noEmit`
- [ ] 6.3 Criar script em `/docker-entrypoint.d/` que gera `config.js` a partir de `API_BASE_URL` e regra nginx `no-cache` para `config.js`; verificar subindo a imagem com dois valores de `API_BASE_URL` e conferindo o `config.js` servido
- [ ] 6.4 Atualizar `frontend/README.md` (dev local, variável `API_BASE_URL`); verificar seguindo o passo a passo

## 7. CI no GitHub Actions

- [ ] 7.1 Criar `.github/workflows/backend.yml` (paths `backend/**`): ruff + pytest → build; em `main` push para `anselmomendes/atlas-epidemiologia-backend:{sha7,latest}` e `:vX.Y.Z` em tags; verificar com um PR (só build) e um push em `main` (imagem no DockerHub)
- [ ] 7.2 Criar `.github/workflows/frontend.yml` (paths `frontend/**`): `npm ci`, `tsc`, `vite build` → build/push da imagem do frontend; verificar como em 7.1
- [ ] 7.3 Criar `.github/workflows/pipelines.yml` (paths `pipelines/**`, `dbt/**`): ruff + pytest + `dbt parse` → build/push da imagem `pipelines`; verificar como em 7.1
- [ ] 7.4 Configurar secrets `DOCKERHUB_USERNAME` e `DOCKERHUB_TOKEN` no repositório GitHub e documentar em `deploy/README.md`; verificar que um workflow em `main` faz login no DockerHub com sucesso

## 8. Stack da aplicação no Portainer

- [ ] 8.1 Criar `deploy/app.stack.yml` com `frontend`, `backend` e `redis` (sem porta publicada, rede interna), labels Traefik em hosts temporários (`next.dengue.contovisual.com.br`, `api-next.dengue.contovisual.com.br`), `restart_policy`, `update_config: order: start-first` e imagens `${BACKEND_TAG:-latest}`/`${FRONTEND_TAG:-latest}`; verificar com `docker stack config -c deploy/app.stack.yml`
- [ ] 8.2 Criar a stack `atlas-app` no Portainer com as variáveis secretas (`GOOGLE_APPLICATION_CREDENTIALS_JSON`, `ADMIN_TOKEN`, `CORS_ALLOWED_ORIGINS`, `API_BASE_URL`); verificar `https://api-next.dengue.contovisual.com.br/health` = 200 e porta do Redis fechada no IP público
- [ ] 8.3 Habilitar webhooks de serviço do backend e do frontend no Portainer, salvar como secrets `PORTAINER_WEBHOOK_BACKEND`/`PORTAINER_WEBHOOK_FRONTEND` e adicionar o passo `curl -fsS -X POST "$WEBHOOK?tag=$SHA7"` após o push em 7.1/7.2; verificar que um push em `main` atualiza o serviço para a tag do commit
- [ ] 8.4 Documentar em `deploy/README.md` deploy, variáveis e rollback por tag; verificar fazendo um rollback do backend para a tag anterior

## 9. Corte para produção

- [ ] 9.1 Comparar respostas da API nova e da antiga para as rotas e filtros usados pelo front (script de comparação em `backend/scripts/`); verificar diferenças zero (salvo `gold_generated_at`)
- [ ] 9.2 Validar o front novo em `next.dengue.contovisual.com.br` (mapa, curvas, KPIs, qualidade de dados); verificar navegação sem erros no console
- [ ] 9.3 Trocar os hosts Traefik para `dengue.contovisual.com.br`/`api.dengue.contovisual.com.br`, remover a stack antiga e restringir CORS ao domínio final; verificar os dois domínios com HTTPS válido e manter as instruções de rollback para as imagens `:1.0`

## 10. Orquestração com Airflow (última fase)

- [ ] 10.1 Criar `airflow/Dockerfile` (`apache/airflow` + pacote `pipelines` + `dbt-bigquery` + `dbt/` + `airflow/dags/`) e workflow `.github/workflows/airflow.yml` publicando `atlas-epidemiologia-airflow`; verificar build no CI
- [ ] 10.2 Escrever a DAG `atlas_dengue_pipeline`: task group de ingestão (uma task por fonte com `pipelines load`), `dbt build`, tarefa do modelo de AI (`AI_MODEL_COMMAND`, skip se vazio), invalidação do cache (`trigger_rule=none_failed`), `max_active_runs=1`, `retries=2`; verificar com teste `DagBag` sem erros de import e ordem das dependências
- [ ] 10.3 Criar `deploy/data.stack.yml` (Airflow LocalExecutor + Postgres de metadados, UI em `airflow.dengue.contovisual.com.br` via Traefik) e stack `atlas-data` no Portainer com webhook; verificar RAM livre na VPS antes e depois e acesso à UI com login
- [ ] 10.4 Disparar a DAG manualmente e conferir: tabelas raw/gold com nova geração, tarefa do modelo pulada, cache invalidado (próxima chamada à API reflete a nova geração); verificar pelos logs das tarefas
- [ ] 10.5 Habilitar agendamento conforme a frequência de cada fonte e documentar em `airflow/README.md` como reprocessar uma fonte; verificar a primeira execução agendada com sucesso

## Workflow follow-up

- Revisar os artefatos e iniciar a implementação com o workflow de apply.
- Arquivar a mudança após a fase de Airflow (ou dividir a fase 10 em outra mudança, se for adiada por muito tempo).
