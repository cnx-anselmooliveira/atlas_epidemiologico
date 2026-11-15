# Plataforma de ML — Postgres, MLflow e Airflow

Este diretório guarda o compose de **desenvolvimento local** da plataforma de ML. As stacks da VPS (hml e prod) ficam em [`../deploy/`](../deploy/).

## Fluxo de promoção

O código e as imagens seguem sempre **dev → hml → prod**:

| Etapa | Branch / gatilho | Tag da imagem no DockerHub | Onde roda |
|---|---|---|---|
| Desenvolvimento | commits na branch `dev` (um commit por módulo concluído) | `dev` | localmente (este compose) |
| Homologação | merge `dev → hml` via pull request | `hml` | stacks `hml` na VPS (Portainer) |
| Produção | merge `hml → main` via pull request + tag git `vX.Y` em `main` | `X.Y` (ex.: `1.0`) | stacks `prod` na VPS |

Regras:
- `hml` só recebe merge vindo de `dev`, e `main` só vindo de `hml`.
- Uma tag de versão (`1.0`, `1.1`…) nunca é sobrescrita. As tags `dev` e `hml` são móveis.
- Modelos seguem a mesma ordem no registro do MLflow: aliases `@dev` (MLflow local) → `@hml` → `@prod` (MLflow da VPS).

## Variáveis (`platform/.env`)

Copie `.env.example` para `.env` (ignorado pelo git) e preencha:

| Variável | Para que serve |
|---|---|
| `GCP_PROJECT` | Projeto GCP com o BigQuery e o bucket de artefatos |
| `MLFLOW_ARTIFACTS_BUCKET` | Bucket GCS dos artefatos do MLflow; o dev usa o prefixo `mlflow/dev/` |
| `MLFLOW_SA_KEY_PATH` | Caminho local da chave da service account do MLflow (só acesso ao bucket) |
| `TRAINING_SA_KEY_PATH` | Caminho local da chave da service account de treino (leitura no BigQuery) |
| `POSTGRES_PASSWORD` | Senha do superusuário do Postgres local |
| `AIRFLOW_ADMIN_PASSWORD` | Senha do usuário `admin` do Airflow local |
| `EXTRA_CA_PATH` | Opcional: CA da inspeção TLS da rede corporativa; vazio fora dela |

As chaves ficam em `platform/secrets/`, que também é ignorado pelo git.
