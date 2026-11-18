# Plataforma local — Postgres, MLflow, Airflow e API gold

Este diretório guarda o compose de **desenvolvimento local** da plataforma de ML. As stacks da VPS (hml e prod) ficam em [`../deploy/`](../deploy/).

| Serviço | Endereço | Para quê |
|---|---|---|
| MLflow | <http://127.0.0.1:5000> | experimentos, métricas, artefatos e registro de modelos |
| Airflow | <http://127.0.0.1:8080> | DAGs (treinos agora; ingestão e dbt depois) |
| API gold (`backend/`) + Redis | <http://127.0.0.1:8000> | dados das tabelas gold para o site (`/gold/*`, `/health`) |
| JupyterLab (opcional) | <http://127.0.0.1:8888> | exploração com o pacote `atlas_ml` já instalado |
| Postgres | só na rede interna | bancos `mlflow`, `mlflow_auth` e `airflow`, cada um com o seu usuário |

Todas as portas escutam só em `127.0.0.1`.

## Passo a passo (dev)

**Pré-requisitos:** Docker Desktop com WSL2, Git e PowerShell. Para rodar o pacote `ml/` fora do container, também o [uv](https://docs.astral.sh/uv/).

1. **Configuração**
   ```powershell
   ./platform/dev.ps1 up        # na 1ª vez, cria o .env da raiz (a partir do .env.example) e para; edite as senhas
   ```
   Preencha `POSTGRES_PASSWORD` e `AIRFLOW_ADMIN_PASSWORD` no `.env` da raiz. O arquivo é ignorado pelo git.
2. **Subir**
   ```powershell
   ./platform/dev.ps1 up        # build das imagens + sobe tudo
   ./platform/dev.ps1 status    # aguarde todos "healthy" (cerca de 1 min)
   ```
3. **Usar**
   - Abra o Airflow (usuário `admin`, senha do `.env`), despause e dispare `atlas_dengue_forecast_br`.
   - A run aparece no MLflow em `atlas/example`, com as tags `atlas.*`, métricas, modelo e `data_summary.json`. O modelo `atlas-example` ganha o alias `@dev`.
   - Para notebooks: `./platform/dev.ps1 notebook` e abra o link impresso. Os arquivos ficam em `ml/notebooks/`.
4. **Editar código**
   - DAGs em `airflow/dags/` aparecem no Airflow em cerca de 30 s.
   - Mudanças em `ml/src/` valem na próxima tarefa ou no próximo kernel, sem rebuild, porque o pacote é instalado em modo editável dentro dos containers.
   - Mudou dependências (`ml/pyproject.toml`) ou um Dockerfile? Rode `./platform/dev.ps1 up` de novo.
5. **Parar e limpar**
   ```powershell
   ./platform/dev.ps1 logs airflow-scheduler   # depurar
   ./platform/dev.ps1 down      # para tudo e mantém dados (runs, histórico, artefatos)
   ./platform/dev.ps1 reset     # para e APAGA os volumes (pede confirmação)
   ```

O `dev.ps1` define `ATLAS_GIT_SHA` com o commit atual. Esse valor vai para a tag `atlas.git_sha` das runs. Para chamar o `docker compose` direto, exporte antes: `$env:ATLAS_GIT_SHA = git rev-parse HEAD`.

### Artefatos no GCS (opcional)

Sem bucket, os artefatos ficam no volume `mlartifacts`. Para usar o bucket do projeto:
1. Coloque a chave da service account do MLflow em `platform/secrets/mlflow-sa.json`. Ela precisa de acesso a objetos no bucket.
2. No `.env`, defina `MLFLOW_ARTIFACTS_BUCKET=ppgcc-bucket`.
3. Rode `./platform/dev.ps1 up`.

Os novos artefatos passam a ir para `gs://ppgcc-bucket/mlflow/dev/`. Quem treina continua sem precisar de credencial: o MLflow faz o upload.

Para ler features do BigQuery nos treinos e notebooks, coloque a chave de treino em `platform/secrets/training-sa.json`.

### Rede da empresa (inspeção TLS)

Se as chamadas ao GCS ou ao BigQuery falharem com erro de certificado, salve a CA da inspeção (ex.: `platform/certs/cloudflare-gateway-ca.pem`) e defina `EXTRA_CA_PATH=certs/cloudflare-gateway-ca.pem` no `.env`. O `dev.ps1` monta um bundle (CAs públicas + a corporativa) e aplica `compose.ca.yml` em todos os serviços.

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
- Modelos seguem a mesma ordem no registro do MLflow: `@dev` (MLflow local) → `@hml` → `@prod` (MLflow da VPS). Veja [`../ml/README.md`](../ml/README.md).

### Proteção das branches e CI

`hml` e `main` são protegidas no GitHub:
- mudanças só entram por pull request;
- o check **`ci-ok`** do workflow [`ci.yml`](../.github/workflows/ci.yml) precisa estar verde, com a branch atualizada em relação ao destino;
- push direto e force-push são recusados, inclusive para administradores;
- 0 aprovações obrigatórias, porque há um único mantenedor e o GitHub não permite aprovar o próprio PR.

O `ci.yml` roda em todo PR para `hml`/`main` e em todo push nelas, sem segredos:
- lint;
- testes do `ml`;
- builds das imagens;
- integridade das DAGs;
- teste de ponta a ponta;
- frontend;
- validação OpenSpec.

O teste de ponta a ponta também roda localmente com `bash platform/ci/e2e.sh`, em portas separadas da plataforma de dev. Em falha, os logs ficam em `e2e-logs/`.

Para conferir ou reaplicar a regra: `gh api repos/cnx-anselmooliveira/atlas_epidemiologico/branches/<hml|main>/protection`.

## Variáveis (`.env` da raiz)

O `.env.example` da raiz lista todas as variáveis do projeto (dev local e stack de hml/prod), com comentários. As de dev local:

| Variável | Para que serve |
|---|---|
| `GCP_PROJECT` | Projeto GCP com o BigQuery |
| `MLFLOW_ARTIFACTS_BUCKET` | Opcional. Bucket GCS dos artefatos (`ppgcc-bucket`); vazio = volume local |
| `POSTGRES_PASSWORD` | Senha do superusuário do Postgres local; em dev, também a dos usuários `mlflow` e `airflow` |
| `AIRFLOW_ADMIN_PASSWORD` | Senha do usuário `admin` do Airflow local |
| `JUPYTER_TOKEN` | Token do JupyterLab (padrão `atlas`) |
| `EXTRA_CA_PATH` | Opcional. CA da inspeção TLS da rede corporativa |

As chaves de service account ficam em `platform/secrets/`, que é ignorado pelo git:
- `mlflow-sa.json`: SA do MLflow, só o bucket;
- `training-sa.json`: SA de treino, leitura no BigQuery.

## Arquivos

| Arquivo | O quê |
|---|---|
| `compose.dev.yml` | Postgres, MLflow, `airflow-init`, api-server, scheduler, dag-processor, triggerer e Jupyter (profile `notebook`) |
| `compose.ca.yml` | Sobreposição da CA corporativa (aplicada pelo `dev.ps1` quando `EXTRA_CA_PATH` está definido) |
| `postgres/init-databases.sh` | Cria bancos e usuários na 1ª subida (volume vazio) |
| `dev.ps1` | `up`, `status`, `logs`, `notebook`, `down`, `reset` |
