# Proposal

## Why

O objetivo científico do Atlas é um modelo de AI: uma "impressão digital ambiental" por região, que cruza relevo, clima e uso do solo com a modelagem de nicho ecológico do *Aedes*, para estimar o risco de dengue sem depender só das notificações oficiais. Antes de construir esse modelo, é preciso a plataforma que o torna reprodutível, orquestrável e promovível:
- experimentos rastreados;
- artefatos guardados fora da máquina de quem treinou;
- um registro de modelos;
- um orquestrador para disparar treinos e, depois, ingestão e dbt;
- um caminho controlado dev → homologação → produção.

Nada disso existe hoje.

## What Changes

- **Um compose de plataforma de ML** com **MLflow + Airflow + Postgres** (um banco por serviço). Ele é usado em dois lugares:
  - **dev local** (no notebook do usuário), com Jupyter opcional;
  - **VPS** (Portainer): MLflow compartilhado por hml e prod; Airflow em duas stacks, `hml` e `prod`, cada uma com a imagem da sua tag, apontando para o mesmo MLflow e o mesmo Postgres (bancos separados).
- **MLflow**:
  - artefatos no **Google Cloud Storage**, com o servidor fazendo proxy do upload e do download (quem treina não precisa de credencial do bucket);
  - metadados no Postgres;
  - na VPS, HTTPS via Traefik e autenticação.
- **Airflow**:
  - executor local, metadados no Postgres e DAGs versionadas no repositório;
  - conexão pronta com o MLflow;
  - uma **DAG de exemplo** que dispara o treino do experimento de exemplo e registra o resultado no MLflow;
  - na VPS, UI com HTTPS e login.
- **Projeto `ml/`** (esqueleto, sem modelo real ainda):
  - pacote Python com configuração por ambiente;
  - CLI de treino que registra parâmetros, métricas, artefatos e metadados de reprodutibilidade;
  - leitor de features do BigQuery (interface);
  - experimento de exemplo com dados sintéticos;
  - testes.
- **Registro de modelos com aliases `@dev`, `@hml`, `@prod`** e regra de promoção: só chega a `@prod` uma versão que passou por `@hml`.
- **Convenção de promoção para todas as imagens**:
  - branch `dev` publica a tag `dev`;
  - branch `hml` publica a tag `hml`;
  - a tag git `vX.Y` em `main` publica a tag `X.Y` (ex.: `1.0`).
  - Prod nunca recebe uma imagem que não passou por hml.
- **Imagens novas** publicadas pelo GitHub Actions no DockerHub: `atlas-epidemiologia-mlflow` (servidor), `atlas-epidemiologia-airflow` (Airflow + DAGs + pacote `ml`) e `atlas-epidemiologia-ml` (treino isolado).
- **Fluxo de trabalho**: um commit ao concluir cada módulo da lista de tarefas.

## Capabilities

### New Capabilities
- `ml-experiment-tracking`: servidor de rastreamento de experimentos com metadados persistentes, artefatos no GCS via proxy, autenticação na VPS e health check.
- `ml-model-lifecycle`: registro de modelos, aliases por ambiente, regras de promoção dev → hml → prod e metadados obrigatórios de reprodutibilidade de cada run.
- `ml-training-pipeline`: projeto de treino executável localmente, em container e pelo Airflow, configurado por ambiente, com contrato de registro no MLflow e experimento de exemplo.
- `orchestration-runtime`: o Airflow como serviço da plataforma, com persistência, autenticação, DAGs vindas do repositório, isolamento entre hml e prod, integração com o MLflow e health check.
- `release-promotion`: convenção de branches e tags de imagem (`dev`, `hml`, `X.Y`) e ordem obrigatória de promoção para as imagens do projeto.

### Modified Capabilities
<!-- Nenhuma: openspec/specs/ ainda está vazio. -->

## Impact

- **Código novo**:
  - `atlas_epidemiologia/ml/`;
  - `atlas_epidemiologia/airflow/` (imagem e DAGs);
  - `atlas_epidemiologia/infra/mlflow/` (imagem);
  - `atlas_epidemiologia/platform/compose.dev.yml`;
  - `atlas_epidemiologia/deploy/` (`mlflow.stack.yml`, `airflow.stack.yml`);
  - workflows em `.github/workflows/` na raiz do repositório git (`PPGCC/`).
- **GCP**:
  - um bucket GCS para artefatos;
  - uma service account do MLflow só com acesso ao bucket;
  - uma service account de treino com leitura no BigQuery.
- **VPS**: Postgres, MLflow e duas stacks Airflow (hml pode ser desligada quando ociosa). DNS e roteadores Traefik para `mlflow.`, `airflow-hml.` e `airflow.dengue.contovisual.com.br`.
- **Outras mudanças**:
  - A `decouple-architecture-bigquery` previa o Airflow numa `data.stack.yml` própria (grupo 10) e tags `sha7`/`latest` em `container-delivery`. Ela deve passar a **reutilizar o Airflow desta plataforma** para as DAGs de ingestão e dbt e adotar a convenção `release-promotion`, via `openspec-update-change`.
  - O requisito "Ordem das etapas" de `pipeline-orchestration` (decouple) continua valendo: as DAGs serão escritas nesta plataforma.
- **Fora de escopo**:
  - o modelo de nicho e as features ambientais (ERA5, CHIRPS, MODIS…);
  - as DAGs de ingestão e dbt (ficam na `decouple-architecture-bigquery`);
  - servir o modelo pela API;
  - monitoramento de drift.
