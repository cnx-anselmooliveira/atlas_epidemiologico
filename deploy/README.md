# Deploy: onde cada credencial entra

**Regra:** nenhuma senha, token ou arquivo de credencial do Google vai para o Git (nem em branch `dev`, `hml` ou `main`), para o compose versionado ou para uma imagem. O repositório é público. Os arquivos em `deploy/` só têm **referências** a variáveis (`${NOME}`); o valor é digitado na interface de quem executa.

| Credencial | Onde fica | Quem usa |
|---|---|---|
| Chave JSON da service account do BigQuery (leitura) | variável de stack `GOOGLE_APPLICATION_CREDENTIALS_JSON` no **Portainer** (stack `atlas-app`) | `backend` |
| `ADMIN_TOKEN` (invalidação de cache) | variável de stack no Portainer | `backend` |
| Hosts e tags (`FRONTEND_HOST`, `API_HOST`, `BACKEND_TAG`…) | variáveis de stack (não são segredo) | `app.stack.yml` |
| Chave da service account do dbt/treino em hml | **Docker secret** do Portainer montado como arquivo, apontado por `DBT_BQ_KEYFILE=/run/secrets/<nome>` | Airflow (dbt via Cosmos) |
| Acesso do Airflow ao GCP (GCS dos docs, cache do Cosmos, BigQuery das tarefas) | **Connection** `google_cloud_default` criada na UI do Airflow (ou `AIRFLOW_CONN_GOOGLE_CLOUD_DEFAULT` como variável de stack) | tarefas do Airflow |
| Fernet key, JWT secret, senhas do Postgres e do admin do Airflow | variáveis da stack de dados no Portainer | Airflow |
| Credenciais do MLflow (usuário/senha, bucket) | variáveis da stack no Portainer / **Variables** do Airflow | MLflow, tarefas de treino |
| `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN`, `PORTAINER_WEBHOOK_*` | **secrets do repositório** no GitHub (Settings › Secrets and variables › Actions) | workflows `_image.yml`, `frontend.yml`, `backend.yml` |

Credenciais próprias de hml (outra service account, outro bucket) entram como variáveis da stack de hml, em Connections e Variables do Airflow de hml. A stack de prod usa valores diferentes.

## Imagens publicadas no DockerHub

Todas saem de `anselmomendes/atlas-epidemiologia-<imagem>`; os repositórios são criados no primeiro push.

| Imagem | Workflow | Muda com | Usada por |
|---|---|---|---|
| `frontend` | `frontend.yml` | `frontend/**` | site |
| `backend` | `backend.yml` | `backend/**` | API gold |
| `airflow` | `airflow.yml` | `airflow/**` e `ml/**` (embute as DAGs, o dbt e o `atlas_ml`) | Airflow (4 serviços) |
| `mlflow` | `mlflow.yml` | `infra/mlflow/**` | servidor MLflow |
| `ml` (alvo `runtime`) | `ml.yml` | `ml/**` | treino avulso em container |

Não são publicadas: `ml-notebook` (só desenvolvimento), `postgres` e `redis` (imagens oficiais).

**Tags:** push em `dev` → `dev`; push em `hml` → `hml`; tag `vX.Y` em `main` → `X.Y` (imutável: falha se a versão já existe). Nunca há `latest`: os stacks recebem a tag por variável. Para publicar a primeira tag `hml` de uma imagem sem mexer em arquivo dela, abra Actions › workflow da imagem › **Run workflow** na branch `hml`.

A imagem do Airflow tem mais de 10 GB em camadas (venvs do ML e do dbt); o primeiro push e o primeiro pull na VPS demoram.

## Secrets do GitHub e do Portainer: passo a passo

### 1. DockerHub

1. Use uma conta com escrita no namespace `anselmomendes`.
2. Account settings › Personal access tokens › Generate new token, permissão **Read & Write**, nome `atlas-github-ci`. Copie o token na hora: ele só aparece uma vez.
3. No GitHub: Settings › Secrets and variables › Actions › **New repository secret**: `DOCKERHUB_USERNAME` (usuário) e `DOCKERHUB_TOKEN` (o token).

Sem eles, o primeiro job de cada workflow de imagem (`secrets-check`) falha em segundos listando o que falta, antes de rodar testes e build.

### 2. Environments e webhooks do Portainer

1. No Portainer, para cada serviço do stack: serviço › **Service webhook** › ative e copie a URL.
2. No GitHub: Settings › Environments › **New environment** `hml` e `prod`. Em `prod`, ative **Required reviewers** (o deploy de versão espera aprovação).
3. Em cada Environment, crie os secrets (mesmo nome nos dois, valores diferentes):

| Secret do Environment | Serviço atualizado |
|---|---|
| `PORTAINER_WEBHOOK_FRONTEND` | site |
| `PORTAINER_WEBHOOK_BACKEND` | API |
| `PORTAINER_WEBHOOK_AIRFLOW` | Airflow |
| `PORTAINER_WEBHOOK_MLFLOW` | MLflow |
| `PORTAINER_WEBHOOK_ML` | (opcional) treino avulso |

Push em `hml` usa só o Environment `hml`; tag `vX.Y` usa só o `prod`. Se o secret não existir, a imagem é publicada e o job avisa "deploy não acionado" sem falhar.

### 3. Service account de leitura do backend

O backend lê o BigQuery (datasets `gold` e `forecast`) e o prefixo `forecast/` do bucket de figuras. Use uma conta **só de leitura**, nunca a de treino:

```bash
P=ppgcc-dengue-project
gcloud iam service-accounts create atlas-backend-ro --project "$P" --display-name "Atlas backend (leitura)"
SA="atlas-backend-ro@${P}.iam.gserviceaccount.com"
# executar consultas no projeto
gcloud projects add-iam-policy-binding "$P" --member "serviceAccount:${SA}" --role roles/bigquery.jobUser
# leitura nos dois datasets: console BigQuery › dataset gold (e forecast) › Compartilhar › adicionar
#   o principal ${SA} com o papel "Leitor de dados do BigQuery" (roles/bigquery.dataViewer)
# figuras: só o prefixo forecast/ do bucket
gcloud storage buckets add-iam-policy-binding gs://ppgcc-bucket \
  --member "serviceAccount:${SA}" --role roles/storage.objectViewer \
  --condition 'expression=resource.name.startsWith("projects/_/buckets/ppgcc-bucket/objects/forecast/"),title=forecast-figuras'
```

A condição de IAM exige acesso uniforme no nível do bucket. Gere a chave fora do repositório, cole-a no Portainer (variável do stack `GOOGLE_APPLICATION_CREDENTIALS_JSON` ou Docker secret) e **apague o arquivo local**. Para conferir: com a conta, `GET /forecast/figures/<modelo>/<arquivo>.png` do backend devolve 200 `image/png`, e uma consulta a outro prefixo do bucket é negada.

### 4. Outras credenciais

A tabela do início lista o resto (chaves de treino e do dbt como Docker secret, Connection `google_cloud_default`, senhas do Postgres e do Airflow, MLflow). Valores só no Portainer ou na UI do Airflow.

## Fluxo de promoção dev → hml → main

1. Trabalho em `dev`; cada push roda o `ci.yml` e publica as imagens com tag `dev` (sem deploy).
2. **Promover para hml:** PR `dev` → `hml`, com o `ci-ok` obrigatório; no merge, os workflows das imagens alteradas publicam `hml` e chamam o webhook do Environment `hml`.
3. **Versão:** PR `hml` → `main`, depois a tag `vX.Y` em `main`. O workflow publica `X.Y` (imutável), espera a aprovação do Environment `prod` e chama o webhook de prod. Uma tag fora de `main` é recusada.
4. Proteção de branch (feita no GitHub, em Settings › Branches): `hml` e `main` exigem o check `ci-ok` e PR.

## Desenvolvimento local

- Chaves em `platform/secrets/` e senhas em `platform/.env`: ambos são ignorados pelo Git e entram nos containers só em runtime, como volume somente leitura. Nunca são copiados para uma imagem.
- Não deixe a chave solta na raiz do repositório (`ppgcc-dengue-project.json`): use `platform/secrets/`.
- O `AIRFLOW__API_AUTH__JWT_SECRET` e a senha de dev do `compose.dev.yml` valem **só** para a máquina local.

## Proteções contra vazamento

1. **Hook local** (uma vez por clone): `git config core.hooksPath .githooks`. Ele roda `platform/ci/check-secrets.sh --staged` antes de cada commit.
2. **CI**, job `secrets` (em todo push e PR, e dentro do `ci-ok`):
   - `check-secrets.sh --all` barra nomes proibidos (`.env`, `*.pem`, `*.key`, `secrets/`, chaves de service account) e conteúdos com formato de credencial (chave privada, JSON de service account, tokens do GitHub e do DockerHub, URL de webhook do Portainer);
   - gitleaks no histórico inteiro (`.gitleaks.toml`, com as exceções conhecidas).
3. **`.gitignore` e `.dockerignore`:** as mesmas famílias de arquivo ficam fora do Git e fora do contexto de build.
4. **GitHub:** secret scanning e push protection ligados no repositório.

## Se uma credencial vazar

1. Revogue a chave na hora (GCP IAM › Service accounts › Keys, ou o token no DockerHub/GitHub/Portainer). Apagar o commit **não basta**: o repositório é público e a chave já pode ter sido copiada.
2. Crie uma nova e atualize nos lugares da tabela acima.
3. Só depois limpe o histórico, se necessário.
