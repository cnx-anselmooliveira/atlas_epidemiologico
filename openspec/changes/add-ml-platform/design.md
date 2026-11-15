# Design

## Context

- **Repositório.** O git tem raiz em `atlas_epidemiologia/` (`cnx-anselmooliveira/atlas_epidemiologico`, privado, só `main` hoje). Os workflows do GitHub Actions ficam em `atlas_epidemiologia/.github/workflows/`. `frontend/design-system/` não é versionado.
- **Dados.** O BigQuery `ppgcc-dengue-project` já tem raw/bronze/silver/gold. Variáveis ambientais ainda não foram ingeridas; só o DEM existe em raw.
- **Infra.** Uma VPS com Portainer (Swarm) e Traefik (`network_public`, certresolver `letsencryptresolver`). Mais nada roda para ML.
- **Rede corporativa.** A máquina de dev passa por inspeção TLS (Cloudflare Gateway). O projeto antigo já precisava montar `cloudflare-gateway-ca.pem` nos containers.
- **Decisões do usuário:**
  - escopo só de infra + esqueleto;
  - artefatos no GCS;
  - MLflow de dev local e um compartilhado na VPS para hml e prod;
  - Airflow no mesmo compose;
  - tags de imagem `dev`/`hml`/`X.Y`;
  - um commit por módulo.

## Goals / Non-Goals

**Goals:**
- `docker compose up` local sobe Postgres + MLflow + Airflow (+ Jupyter opcional) e roda a DAG de exemplo de ponta a ponta.
- Na VPS, o mesmo desenho em stacks Portainer: plataforma (Postgres + MLflow + backup), Airflow hml e Airflow prod.
- A promoção de código e de modelo segue a mesma ordem, dev → hml → prod, e é verificada por ferramenta, não só por convenção.

**Non-Goals:**
- Executor distribuído (Celery/Kubernetes). O LocalExecutor basta para o volume previsto.
- Servir o modelo online. O consumo previsto é batch: o Airflow escreve previsões no BigQuery numa mudança futura.
- Infra como código do GCP. Bucket e service accounts são criados por runbook documentado.

## Decisions

### 1. Estrutura de pastas
```
atlas_epidemiologia/
├── ml/                     # pacote atlas_ml (uv, Python 3.12) + testes + Dockerfile da imagem de treino
├── airflow/                # Dockerfile do Airflow, dags/, config
├── infra/mlflow/           # Dockerfile do servidor MLflow
├── platform/               # compose.dev.yml, .env.example, init do Postgres, scripts
└── deploy/                 # platform.stack.yml, airflow.stack.yml (VPS)
.github/workflows/          # ml.yml, airflow.yml, mlflow-server.yml, promotion-guard.yml
```
`platform/` reúne o compose de dev. `deploy/` segue o padrão já previsto na `decouple-architecture-bigquery`.

### 2. Um Postgres, um banco por serviço
Um container Postgres 16 por instalação:
- **dev:** bancos `mlflow`, `mlflow_auth` (não usado em dev) e `airflow`;
- **VPS:** bancos `mlflow`, `mlflow_auth`, `airflow_hml` e `airflow_prod`.

Cada serviço tem o próprio usuário, com acesso só ao seu banco. Um script em `docker-entrypoint-initdb.d` cria os bancos e usuários. Isso economiza memória na VPS e mantém o isolamento exigido entre hml e prod. Postgres separado por serviço foi rejeitado: triplicaria memória e backups.

### 3. Servidor MLflow
Imagem `atlas-epidemiologia-mlflow`, construída sobre `python:3.12-slim` com `mlflow` (3.x, versão exata fixada), `psycopg2-binary` e `google-cloud-storage`. O comando é:

`mlflow server --backend-store-uri postgresql://… --artifacts-destination gs://<bucket>/mlflow/<instalação> --serve-artifacts --host 0.0.0.0 --port 5000`

- `<instalação>` é `dev` ou `vps`.
- **Dev sem bucket:** o padrão do compose de dev é `MLFLOW_ARTIFACTS_DESTINATION=/mlartifacts`, num volume Docker nomeado. Assim a plataforma sobe sem nenhuma chave GCP. Com `MLFLOW_ARTIFACTS_BUCKET` definido no `.env`, o dev passa a usar `gs://<bucket>/mlflow/dev`. Decisão do usuário: começar a estudar antes de o bucket existir.
- Com `--serve-artifacts`, o cliente fala `mlflow-artifacts:/`. Só o servidor tem a credencial do bucket, montada como arquivo de segredo (`GOOGLE_APPLICATION_CREDENTIALS`).
- **VPS:** adiciona `--app-name basic-auth`, com o banco de usuários em `mlflow_auth` configurado via `MLFLOW_AUTH_CONFIG_PATH`. Usuários: `admin`, `airflow-hml` e `airflow-prod`. O host é `mlflow.dengue.contovisual.com.br` no Traefik, e os hosts permitidos são configurados para o domínio.
- **Dev:** sem autenticação, porta publicada só em `127.0.0.1:5000`.
- Health check em `GET /health`.

Alternativa rejeitada: o cliente gravar direto no GCS, que exigiria credencial de bucket em cada notebook e cada Airflow.

### 4. Airflow
Imagem `atlas-epidemiologia-airflow`, construída sobre `apache/airflow:3.x-python3.12` (versão exata fixada):
- **Execução:** LocalExecutor. Componentes `api-server`, `scheduler`, `dag-processor` e `triggerer`, mais um job `airflow-init` (migração do banco e usuário admin).
- **Isolamento de dependências:** o pacote `atlas_ml` é instalado num **venv separado** (`/opt/atlas-ml`), com o CLI `atlas-ml` no PATH. Assim as restrições de versão do Airflow não colidem com as do MLflow e do scikit-learn. As tarefas chamam o CLI via `BashOperator`. Isso cumpre a regra "mesmo comando em todo lugar" e é a mesma abordagem já escolhida na `decouple-architecture-bigquery` (sem DockerOperator nem socket Docker).
- **DAGs:** em dev, `airflow/dags/` é montado como volume e alterações aparecem sem rebuild. Na VPS, as DAGs ficam dentro da imagem.
- **Autenticação:** em dev, o Simple Auth Manager do Airflow 3 com usuário admin local. Na VPS, o FAB Auth Manager (`apache-airflow-providers-fab`) com login e senha, admin criado pelo `airflow-init` a partir de variáveis da stack.
- **Configuração:** URL do MLflow, credenciais (`MLFLOW_TRACKING_USERNAME`/`PASSWORD`) e `ATLAS_ENV` entram como variáveis de ambiente da stack, disponíveis às tarefas.
- **VPS:** duas stacks, `atlas-airflow-hml` (imagem `:hml`, banco `airflow_hml`, host `airflow-hml.…`) e `atlas-airflow-prod` (imagem `:X.Y`, banco `airflow_prod`, host `airflow.…`), geradas do mesmo `deploy/airflow.stack.yml` com variáveis de ambiente.
- **Memória:** `parallelism=4` e `AIRFLOW__CORE__LOAD_EXAMPLES=False`. A stack hml pode ficar com 0 réplicas quando ociosa.

### 5. Compose de dev (`platform/compose.dev.yml`)
- **Serviços:** `postgres`, `mlflow`, `airflow-init`, `airflow-api-server`, `airflow-scheduler`, `airflow-dag-processor`, `airflow-triggerer`. O `jupyter` (imagem de treino + JupyterLab) entra no profile `notebook`.
- **Portas:** todas publicadas só em `127.0.0.1`. MLflow em 5000, Airflow em 8080, Jupyter em 8888.
- **Volumes nomeados:** `pgdata`. O código é montado por bind, para editar sem rebuild: `ml/` vira editable install no venv, mais `airflow/dags/`.
- **Arquivo `.env` (fora do git):** `GCP_PROJECT`, `MLFLOW_ARTIFACTS_BUCKET` (opcional; vazio = volume local), caminho da chave do MLflow (só com bucket), caminho da chave de treino (BigQuery) e senha do Postgres.
- **CA corporativa:** um `extra_ca.pem` opcional é montado e apontado por `SSL_CERT_FILE`/`REQUESTS_CA_BUNDLE`/`GRPC_DEFAULT_SSL_ROOTS_FILE_PATH` para atravessar a inspeção TLS da rede da empresa. Se o arquivo não existir, fica vazio e inofensivo.
- **Atalhos:** `make`/script `platform/dev.ps1` com `up`, `down`, `logs`, `reset` e `notebook`, porque o dev é Windows/PowerShell.

### 6. Pacote `atlas_ml`
```
ml/src/atlas_ml/
├── config.py        # pydantic-settings: ATLAS_ENV ∈ {dev,hml,prod}, MLFLOW_TRACKING_URI, GCP_PROJECT, ATLAS_GIT_SHA, ATLAS_IMAGE_TAG
├── tracking.py      # atlas_run(): abre a run e exige as tags atlas.*; falha antes de treinar se faltar alguma
├── data/bigquery.py # read_features(query|table) → (DataFrame, DataSummary{rows, cols, period, data_version})
├── experiments/
│   └── example.py   # dados sintéticos com semente: casos semanais ~ temperatura + chuva + sazonalidade; split temporal; HistGradientBoosting; MAE/RMSE
├── registry.py      # register(), promote(name, version, to=hml|prod) com as regras de ordem
└── cli.py           # atlas-ml train <exp> [--register] | promote … | info
```
- **Dependências:** `mlflow-skinny` (cliente leve), `scikit-learn`, `pandas`, `pyarrow`, `pydantic-settings`, `google-cloud-bigquery`, `db-dtypes` e `typer`.
- **Commit e tag da imagem:** `ATLAS_GIT_SHA` e `ATLAS_IMAGE_TAG` são gravados nas imagens via `--build-arg` no CI. Localmente, o CLI usa `git rev-parse HEAD` e `local`. Sem nenhum dos dois, falha (spec `ml-model-lifecycle`).
- **Versão dos dados:** é `synthetic-seed<N>` no exemplo e `<tabela>@<last_modified ISO>` nas leituras do BigQuery (metadado `tables.get`, sem custo).

### 7. Promoção de modelos
O MLflow não guarda histórico de aliases, então o histórico é gravado em tags da versão do modelo.

- **`atlas-ml promote <nome> --version N --to hml`**:
  - exige que a run da versão tenha `atlas.env=hml` (ou seja, foi treinada no MLflow da VPS com a imagem `hml`);
  - move `@hml`;
  - grava `atlas.hml_at` e `atlas.hml_by`.
- **`atlas-ml promote <nome> --version N --to prod`**:
  - exige a tag `atlas.hml_at` e as métricas de validação presentes;
  - move `@prod`;
  - grava `atlas.prod_at` e `atlas.prod_by`.
  - Recusa qualquer outro caso.
- **`@dev`:** existe só no MLflow local.

### 8. CI e promoção de imagens
- **`ml.yml`, `airflow.yml` e `mlflow-server.yml`:** disparam em push nas branches `dev` e `hml` e em tags `v*`, com filtro de path para os pushes.
  - **Passos:** lint (`ruff`) + testes (`pytest`, sem rede) → build → push com a tag calculada (`dev`, `hml` ou `X.Y`).
  - **`ATLAS_GIT_SHA`:** passado como build arg.
  - **Tags de versão:** antes do push, um passo verifica que o commit está em `origin/main` (`git merge-base --is-ancestor`) e que a tag ainda não existe no DockerHub (`docker manifest inspect`), garantindo a imutabilidade.
  - **Pull requests:** só lint, testes e build, sem push.
- **`promotion-guard.yml`:** em `pull_request`, falha se a base for `hml` e o head não for `dev`, ou se a base for `main` e o head não for `hml`. A proteção de branch no GitHub (exigir esse check, bloquear push direto em `hml` e `main`) é configurada manualmente e documentada.
- **Deploy:**
  - publicar `hml` chama os webhooks do Portainer dos serviços das stacks hml;
  - publicar `X.Y` chama os webhooks de prod com `?tag=X.Y`;
  - publicar `dev` não implanta nada.
  - Mesmo mecanismo da `decouple-architecture-bigquery`.
- **Branches:** `dev` e `hml` são criadas a partir de `main`, e o trabalho diário acontece em `dev`.

### 9. Backup
Um serviço `pg-backup` na stack de plataforma, com imagem `postgres:16-alpine` + `gcloud` CLI mínima ou `google-cloud-storage` em Python, roda um laço diário:
- `pg_dumpall` comprimido para `gs://<bucket>/backups/postgres/AAAA-MM-DD.sql.gz`;
- regra de ciclo de vida do bucket apaga com 30 dias, o que cobre o mínimo de 14.

A restauração fica documentada e testada uma vez (tarefa).

### 10. Um commit por módulo
Cada grupo de `tasks.md` é um módulo e termina com uma tarefa de commit em `dev`, com mensagem `feat(<módulo>): …` e o rodapé de coautoria. A promoção para `hml` e `main` só acontece nos grupos finais, depois de tudo verificado em dev.

## Risks / Trade-offs

- **[Conflito de dependências Airflow × MLflow × sklearn]** → venv separado para `atlas_ml` dentro da imagem do Airflow; testes de import no CI.
- **[Memória da VPS: Postgres ~0,3 GB + MLflow ~0,4 GB + 2× Airflow ~1,3 GB]** → medir RAM livre antes do deploy; `parallelism` baixo; hml escalável a 0; se faltar memória, prod e hml compartilham uma única instância (decisão a revisar com dados).
- **[Inspeção TLS na rede corporativa quebra chamadas ao GCS/BigQuery no dev]** → montagem opcional da CA (decisão 5) e teste explícito de upload de artefato no grupo do compose.
- **[Airflow 3 e MLflow 3 mudam rápido]** → versões exatas fixadas, atualização só via PR que passa por dev e hml.
- **[Webhook e senhas expostos]** → GitHub Secrets e variáveis de stack no Portainer; `.env` no `.gitignore`; nenhuma chave nas imagens (verificado no CI).
- **[Promoção manual de modelo sujeita a erro humano]** → a ferramenta recusa ordem inválida e grava autor e data; o registro do MLflow fica como trilha de auditoria.

## Migration Plan

1. **dev local:** compose completo e DAG de exemplo rodando. Commit por módulo em `dev`.
2. **VPS hml:** criar bucket/SAs, DNS e stack de plataforma, publicar imagens `hml` e implantar a stack Airflow hml. Rodar a DAG, registrar a versão e promover para `@hml`.
3. **VPS prod:** merge `hml` → `main`, tag `v1.0`, publicar `1.0` e implantar a stack Airflow prod. Promover a versão validada para `@prod`.
4. **Rollback:** reimplantar a stack com a tag `X.Y` anterior; mover `@prod` para a versão anterior (`atlas-ml promote` aceita versão que já teve `@prod`).

## Open Questions

- Nome do bucket (sugestão `ppgcc-dengue-ml-artifacts`, região `US`, igual ao dataset).
- Subdomínios finais (`mlflow.`, `airflow-hml.`, `airflow.dengue.contovisual.com.br`) e criação dos registros DNS.
- RAM disponível na VPS, para confirmar as duas stacks Airflow simultâneas.
