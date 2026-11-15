# Tasks

## 1. Repositório e fluxo de branches

- [x] 1.1 Criar as branches `dev` e `hml` a partir de `main` e passar a trabalhar em `dev`; verificar com `git branch -a` e `git rev-parse --abbrev-ref HEAD` = `dev`
- [x] 1.2 Criar as pastas `ml/`, `airflow/`, `infra/mlflow/`, `platform/` e `deploy/` em `atlas_epidemiologia/`; ampliar o `.gitignore` (`.env`, `*.json` de service account, `mlruns/`, `.venv/`, `__pycache__/`, `extra_ca.pem`); verificar que `git check-ignore platform/.env chave-sa.json` ignora os dois
- [x] 1.3 Criar `platform/.env.example` com todas as variáveis (`GCP_PROJECT`, `MLFLOW_ARTIFACTS_BUCKET`, `MLFLOW_SA_KEY_PATH`, `TRAINING_SA_KEY_PATH`, `POSTGRES_PASSWORD`, `AIRFLOW_ADMIN_PASSWORD`, `EXTRA_CA_PATH`) e documentar o fluxo dev → hml → main e as tags `dev`/`hml`/`X.Y` em `platform/README.md`; verificar que o README lista cada variável do `.env.example`
- [x] 1.4 Commit do módulo em `dev` (`chore(platform): estrutura e fluxo de branches`); verificar com `git log -1 --stat`

## 2. Pacote `atlas_ml`

- [x] 2.1 Criar `ml/pyproject.toml` (uv, Python 3.12, `mlflow-skinny`, `scikit-learn`, `pandas`, `pyarrow`, `pydantic-settings`, `google-cloud-bigquery`, `db-dtypes`, `typer`; dev: `pytest`, `ruff`) e o pacote `src/atlas_ml/`; verificar que `uv sync` e `uv run atlas-ml --help` funcionam
- [x] 2.2 Implementar `config.py` (ambiente restrito a `dev|hml|prod`, URL do MLflow obrigatória, commit e tag da imagem com fallback local `git rev-parse` + `local`); verificar com testes de variável ausente, ambiente inválido e falta de commit
- [x] 2.3 Implementar `tracking.atlas_run()`, que exige `atlas.env`, `atlas.git_sha`, `atlas.image_tag` e `atlas.data_version` e falha antes de treinar; verificar com teste usando MLflow em diretório temporário (`file:` URI)
- [x] 2.4 Implementar `experiments/example.py` (dados sintéticos com semente, split temporal, HistGradientBoosting, MAE/RMSE, modelo com assinatura, artefato `data_summary.json`) e `atlas-ml train example [--register]`; verificar com teste de que duas execuções com a mesma semente registram a mesma métrica e de que a run contém parâmetros, métricas, modelo e resumo
- [x] 2.5 Implementar `data/bigquery.read_features()` com `DataSummary` e `data_version` = `<tabela>@<last_modified>`; verificar com teste usando cliente BigQuery simulado
- [x] 2.6 Implementar `registry.promote()` e `atlas-ml promote` com as regras (hml exige run com `atlas.env=hml`; prod exige `atlas.hml_at` e métricas; grava autor e data); verificar com testes de promoção direta recusada, promoção válida e rollback para versão que já teve `@prod`
- [x] 2.7 Criar `ml/Dockerfile` (imagem de treino, usuário não root, build args `ATLAS_GIT_SHA`/`ATLAS_IMAGE_TAG`) e `ml/README.md` (uso do CLI, variáveis, convenção de tags `atlas.*`); verificar `docker build` e `docker run … atlas-ml train example` contra um MLflow `file:` no container
- [x] 2.8 Commit do módulo em `dev` (`feat(ml): pacote atlas_ml, experimento de exemplo e promoção`); verificar `uv run pytest` verde antes do commit

## 3. Servidor MLflow

- [x] 3.1 Criar `infra/mlflow/Dockerfile` (`python:3.12-slim`, `mlflow` 3.x fixado, `psycopg2-binary`, `google-cloud-storage`, usuário não root) e `entrypoint.sh` que monta o comando com `--backend-store-uri`, `--artifacts-destination gs://$BUCKET/mlflow/$MLFLOW_INSTALLATION`, `--serve-artifacts` e `--app-name basic-auth` quando `MLFLOW_AUTH=true`; verificar `docker build` e `mlflow --version` na imagem
- [x] 3.2 Criar `infra/mlflow/basic_auth.ini.tmpl` (banco `mlflow_auth`, admin a partir de variáveis) e documentar a criação dos usuários `airflow-hml` e `airflow-prod`; verificar subindo a imagem com `MLFLOW_AUTH=true` contra um Postgres local e recebendo HTTP 401 sem credenciais
- [x] 3.3 Commit do módulo em `dev` (`feat(mlflow): imagem do servidor MLflow`); verificar com `git log -1`

## 4. Airflow

- [x] 4.1 Criar `airflow/Dockerfile` (`apache/airflow:3.x-python3.12` fixado, venv `/opt/atlas-ml` com o pacote `ml/`, CLI `atlas-ml` no PATH, `apache-airflow-providers-fab`, DAGs copiadas para a imagem, build args de commit e tag); verificar `docker build` e `docker run … atlas-ml --help` e `airflow version` na mesma imagem
- [x] 4.2 Escrever a DAG `atlas_ml_example_training` (sem agendamento, `BashOperator` com `atlas-ml train example --register`, `retries=2`, falha se a run não for registrada); verificar com teste `DagBag` (sem erros de import, sem schedule, tarefa e retentativas esperadas)
- [x] 4.3 Criar `airflow/config/` com as variáveis de execução (LocalExecutor, `parallelism=4`, sem exemplos, auth manager por ambiente: Simple em dev, FAB na VPS) e o script do `airflow-init` (migração e admin); verificar `airflow config get-value core executor` = `LocalExecutor` na imagem
- [x] 4.4 Documentar em `airflow/README.md` como adicionar DAGs, testar localmente e a regra de que DAGs só mudam via repositório; verificar seguindo o passo "adicionar DAG" com uma DAG vazia de teste (removida depois)
- [x] 4.5 Commit do módulo em `dev` (`feat(airflow): imagem do Airflow e DAG de treino de exemplo`); verificar o teste `DagBag` verde antes do commit

## 5. Compose de dev (plataforma local)

- [ ] 5.1 Criar `platform/postgres/init.sql` (bancos `mlflow`, `mlflow_auth` e `airflow`, cada um com o seu usuário e acesso só ao próprio banco); verificar com `psql` que o usuário do MLflow não acessa o banco `airflow`
- [ ] 5.2 Criar `platform/compose.dev.yml` com `postgres`, `mlflow`, `airflow-init`, `airflow-api-server`, `airflow-scheduler`, `airflow-dag-processor` e `airflow-triggerer` (portas em `127.0.0.1`, volume `pgdata`, bind de `ml/` e `airflow/dags/`, health checks, `depends_on` com condição de saúde) e `jupyter` no profile `notebook`; verificar `docker compose -f platform/compose.dev.yml config` sem erros
- [ ] 5.3 Adicionar a montagem opcional da CA corporativa (`EXTRA_CA_PATH`, `SSL_CERT_FILE`, `REQUESTS_CA_BUNDLE`, `GRPC_DEFAULT_SSL_ROOTS_FILE_PATH`) em MLflow, Airflow e Jupyter; verificar com o bucket configurado um upload de artefato para o GCS a partir da rede corporativa (pendente até o bucket existir — tarefa 7.1)
- [ ] 5.4 Criar `platform/dev.ps1` (`up`, `down`, `logs`, `reset`, `notebook`); verificar que `./platform/dev.ps1 up` sobe tudo saudável (`docker compose ps` com todos `healthy`)
- [ ] 5.5 Teste de ponta a ponta local: disparar a DAG `atlas_ml_example_training` pela UI (`127.0.0.1:8080`) e confirmar no MLflow (`127.0.0.1:5000`) a run com as tags `atlas.*`, o modelo registrado e o artefato no volume local de artefatos (ou em `gs://<bucket>/mlflow/dev/` com bucket); verificar também que reiniciar a stack mantém runs e histórico de DAG
- [ ] 5.6 Atualizar `platform/README.md` com o passo a passo de dev (pré-requisitos Docker Desktop, `.env`, chaves, CA, comandos); verificar seguindo o README do zero (`reset` + `up`)
- [ ] 5.7 Commit do módulo em `dev` (`feat(platform): compose de dev com Postgres, MLflow e Airflow`); verificar com `git log -1 --stat`

## 6. CI e promoção de imagens

- [ ] 6.1 Criar o workflow reutilizável `.github/workflows/_image.yml` na raiz do repositório (calcula a tag pela origem: branch `dev` → `dev`, `hml` → `hml`, tag `vX.Y` → `X.Y`; verifica que a tag de versão está em `origin/main` e ainda não existe no DockerHub; build com `ATLAS_GIT_SHA`/`ATLAS_IMAGE_TAG`; push; webhook do Portainer para `hml` e `X.Y`); verificar com `actionlint`
- [ ] 6.2 Criar `ml.yml` (paths `ml/**`: ruff + pytest → `_image.yml`), `airflow.yml` (paths `airflow/**` e `ml/**`: teste `DagBag` → `_image.yml`) e `mlflow-server.yml` (paths `infra/mlflow/**`); pull requests só validam; verificar com um PR (sem push) e um push em `dev` publicando as três imagens `:dev`
- [ ] 6.3 Criar `promotion-guard.yml` (PR com base `hml` exige head `dev`; base `main` exige head `hml`); verificar com um PR `dev → main` falhando e um PR `dev → hml` passando
- [ ] 6.4 Configurar no GitHub os secrets (`DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN`, `PORTAINER_WEBHOOK_*`) e a proteção das branches `hml` e `main` (sem push direto, check `promotion-guard` obrigatório); documentar em `platform/README.md`; verificar que um push direto em `hml` é rejeitado
- [ ] 6.5 Commit do módulo em `dev` (`ci: publicação de imagens dev/hml/X.Y e guarda de promoção`); verificar o workflow verde no GitHub para o próprio commit

## 7. GCP e VPS — homologação

- [ ] 7.1 Criar o bucket de artefatos (região `US`, ciclo de vida de 30 dias em `backups/`), a SA do MLflow (só `storage.objectAdmin` no bucket) e a SA de treino (leitura no BigQuery) e documentar o runbook em `platform/README.md`; verificar com `gcloud storage ls` e uma tentativa negada da SA do MLflow ao BigQuery
- [ ] 7.2 Criar `deploy/platform.stack.yml` (Postgres com init dos bancos da VPS, MLflow com `MLFLOW_AUTH=true` e Traefik em `mlflow.dengue.contovisual.com.br`, `pg-backup` diário para `gs://…/backups/postgres/`, rede overlay `atlas_platform` anexável) e `deploy/airflow.stack.yml` parametrizado por `ATLAS_ENV`/`IMAGE_TAG`/`AIRFLOW_DB`/host; verificar com `docker stack config` para hml e prod
- [ ] 7.3 Medir a RAM livre na VPS, criar os DNS e subir a stack `atlas-platform` no Portainer com as variáveis secretas; verificar `https://mlflow.…/health` = 200, HTTP 401 sem login e Postgres sem porta pública
- [ ] 7.4 Testar o backup: forçar uma execução do `pg-backup`, restaurar o dump num Postgres temporário e listar os experimentos; verificar o arquivo no bucket e a restauração bem-sucedida
- [ ] 7.5 Merge `dev → hml` por PR, conferir a publicação das imagens `:hml` e subir a stack `atlas-airflow-hml` (webhooks registrados nos secrets); verificar o login em `https://airflow-hml.…` e o health dos componentes
- [ ] 7.6 Rodar a DAG de exemplo no Airflow hml e promover a versão registrada com `atlas-ml promote atlas-example --version N --to hml`; verificar no MLflow da VPS a run com `atlas.env=hml` e `atlas.image_tag=hml`, e o alias `@hml`
- [ ] 7.7 Registrar o resultado da homologação (prints/links) no PR `hml → main`; verificar que o PR passa no `promotion-guard`

## 8. Produção

- [ ] 8.1 Merge `hml → main`, criar a tag `v1.0` em `main` e conferir a publicação das imagens `:1.0` (e a recusa de republicar `1.0`); verificar no DockerHub
- [ ] 8.2 Subir a stack `atlas-airflow-prod` (imagem `:1.0`, banco `airflow_prod`, host `airflow.…`); verificar o login, os componentes saudáveis e que o histórico de hml não aparece em prod
- [ ] 8.3 Promover a versão homologada com `atlas-ml promote atlas-example --version N --to prod`; verificar `@prod` no MLflow e a recusa ao tentar promover para prod uma versão sem `@hml`
- [ ] 8.4 Documentar o rollback (stack com tag anterior, alias `@prod` anterior) em `platform/README.md` e ensaiá-lo uma vez; verificar a stack de prod de volta na versão corrente ao fim do ensaio

## 9. Alinhamento com as outras mudanças

- [ ] 9.1 Atualizar a `decouple-architecture-bigquery` via `openspec-update-change`: Airflow passa a ser o desta plataforma (remover `data.stack.yml` do grupo 10), tags `dev`/`hml`/`X.Y` em `container-delivery`, branches `dev`/`hml`/`main`; verificar `openspec validate decouple-architecture-bigquery --strict`
- [ ] 9.2 Alinhar a `rebuild-frontend-astro` à convenção de tags (`frontend.yml` usando `_image.yml`); verificar `openspec validate rebuild-frontend-astro --strict`

## Workflow follow-up

- Arquivar a mudança depois que prod estiver rodando com `@prod` atribuído.
