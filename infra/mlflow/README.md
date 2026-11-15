# Servidor MLflow (`atlas-epidemiologia-mlflow`)

Imagem do servidor de rastreamento. Os metadados ficam no Postgres. Os artefatos ficam no GCS e passam pelo próprio servidor (`--serve-artifacts`), então os clientes não precisam de credencial do bucket. Na VPS, a imagem roda com autenticação (`basic-auth`).

## Variáveis

| Variável | Obrigatória | Descrição |
|---|---|---|
| `MLFLOW_BACKEND_STORE_URI` | sim | `postgresql://mlflow:<senha>@postgres:5432/mlflow` |
| `MLFLOW_ARTIFACTS_BUCKET` | sim* | Bucket GCS. Os artefatos vão para `gs://<bucket>/mlflow/<instalação>/` |
| `MLFLOW_INSTALLATION` | sim* | `dev` (compose local) ou `vps` |
| `MLFLOW_ARTIFACTS_DESTINATION` | — | Substitui bucket + instalação (ex.: pasta local em testes) |
| `GOOGLE_APPLICATION_CREDENTIALS` | com GCS | Caminho da chave da SA do MLflow (só acesso ao bucket) |
| `MLFLOW_AUTH` | — | `true` liga a autenticação (exigido na VPS) |
| `MLFLOW_AUTH_DATABASE_URI` | com auth | Banco de usuários/permissões (`…/mlflow_auth`) |
| `MLFLOW_ADMIN_USERNAME` / `MLFLOW_ADMIN_PASSWORD` | com auth | Admin criado no primeiro boot |
| `MLFLOW_FLASK_SERVER_SECRET_KEY` | com auth | Chave fixa do CSRF; tem de ser a mesma entre reinícios |
| `MLFLOW_ALLOWED_HOSTS` | na VPS | Ex.: `mlflow.dengue.contovisual.com.br` (proteção contra DNS rebinding) |
| `MLFLOW_WORKERS` | — | Processos do servidor (padrão 2) |

\* Ou `MLFLOW_ARTIFACTS_DESTINATION`.

Se faltar alguma variável obrigatória, o entrypoint para com uma mensagem que diz qual é. A senha do admin não aparece no comando do processo: ela vai para um `basic_auth.ini` com permissão 600, gerado a partir de `basic_auth.ini.tmpl`.

## Usuários do Airflow (VPS)

Cada Airflow (hml e prod) usa um usuário próprio no MLflow. Crie-os uma vez, como admin:

```sh
docker exec -it <container-mlflow> sh -c '
  MLFLOW_TRACKING_USERNAME=$MLFLOW_ADMIN_USERNAME MLFLOW_TRACKING_PASSWORD=$MLFLOW_ADMIN_PASSWORD python -c "
from mlflow.server import get_app_client
c = get_app_client(\"basic-auth\", tracking_uri=\"http://127.0.0.1:5000\")
c.create_user(username=\"airflow-hml\", password=\"<senha-hml>\")
c.create_user(username=\"airflow-prod\", password=\"<senha-prod>\")
"'
```

- **Permissões:** o padrão (`default_permission = READ`) deixa todo usuário autenticado ler. Quem cria um experimento ou um modelo registrado vira dono dele (`MANAGE`).
- **Experimentos compartilhados:** se hml e prod gravam no mesmo experimento (ex.: `atlas/example`), dê `EDIT` ao outro usuário. Faça o mesmo no modelo registrado:
  ```python
  c.create_experiment_permission(experiment_id="<id>", username="airflow-prod", permission="EDIT")
  c.create_registered_model_permission(name="atlas-example", username="airflow-prod", permission="EDIT")
  ```
- **Credenciais nas stacks:** guarde-as como `MLFLOW_TRACKING_USERNAME` / `MLFLOW_TRACKING_PASSWORD` nas variáveis de cada stack do Airflow no Portainer.

## Build e teste local

```sh
docker build -t atlas-epidemiologia-mlflow:local --build-arg ATLAS_GIT_SHA=$(git rev-parse HEAD) infra/mlflow/
```

Verificado: `/health` → 200; API sem credenciais ou com senha errada → 401; admin → 200; `airflow-hml` criado lê e cria experimentos.
