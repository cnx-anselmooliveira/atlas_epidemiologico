# Deploy: stack, imagens e credenciais

**Regra:** nenhuma senha, token ou arquivo de credencial do Google vai para o Git (nem em branch `dev`, `hml` ou `main`), para o compose versionado ou para uma imagem. O repositório é público. O stack (`docker-compose.yml`, na raiz) só tem **referências** a variáveis (`${NOME}`); o valor é digitado na interface de quem executa.

## Visão geral

- **Um stack para os dois ambientes:** o `docker-compose.yml` da raiz sobe Postgres, MLflow, Airflow (init, api-server, scheduler, dag-processor, triggerer), API, site e Redis, em formato Swarm. `atlas-hml` lê a branch `hml`; `atlas-prod` lê a `main`. A diferença está só nas variáveis.
- **Variáveis:** todas estão listadas e comentadas no `.env.example` da raiz (grupo "Stack de hml e prod"). No Portainer, use "Load variables from .env file" com esse arquivo e preencha os valores.
- **Sem portas no host:** o site, a API, o Airflow e o MLflow saem pelo Traefik; Postgres e Redis só na rede interna.

| Credencial | Onde fica | Quem usa |
|---|---|---|
| Chave da service account de **leitura** (BigQuery `gold` e `forecast`, prefixo `forecast/` do bucket) | **Docker secret** `atlas_<ambiente>_backend_sa` | `backend` |
| Chave da service account de treino e do dbt | **Docker secret** `atlas_<ambiente>_training_sa` | Airflow (tarefas, dbt via Cosmos) |
| Chave da service account do MLflow (só o bucket) | **Docker secret** `atlas_<ambiente>_mlflow_sa` | MLflow |
| Senhas do Postgres (`POSTGRES_PASSWORD`, `MLFLOW_DB_PASSWORD`, `AIRFLOW_DB_PASSWORD`) | variáveis do stack no Portainer | Postgres, MLflow, Airflow |
| `AIRFLOW_ADMIN_PASSWORD`, `AIRFLOW_JWT_SECRET`, `AIRFLOW_FERNET_KEY` | variáveis do stack | Airflow |
| `MLFLOW_ADMIN_USERNAME`, `MLFLOW_ADMIN_PASSWORD`, `MLFLOW_FLASK_SECRET_KEY` | variáveis do stack | MLflow e tarefas de treino |
| Hosts, tag, bucket, limites (`FRONTEND_HOST`, `IMAGE_TAG`, `ATLAS_BUCKET`…) | variáveis do stack (não são segredo) | `docker-compose.yml` |
| Acesso do Airflow ao GCP (GCS dos docs, cache do Cosmos) | Connection `google_cloud_default`, já montada pelo stack com o caminho do secret | tarefas do Airflow |
| `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN` | **secrets do repositório** no GitHub | workflows de imagem |
| `PORTAINER_WEBHOOK_STACK` | **secret de cada Environment** (`hml` e `prod`) do GitHub | job de deploy |

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

**Tags:** push em `dev` → `dev`; push em `hml` → `hml`; tag `vX.Y` em `main` → `X.Y` (imutável: falha se a versão já existe). Nunca há `latest`: o stack recebe a tag em `IMAGE_TAG` e recusa subir sem ela. Para publicar a primeira tag `hml` de uma imagem sem mexer em arquivo dela, abra Actions › workflow da imagem › **Run workflow** na branch `hml`.

A imagem do Airflow tem mais de 10 GB em camadas (venvs do ML e do dbt); o primeiro push e o primeiro pull na VPS demoram.

## Passo a passo: criar o stack de hml

### 1. DockerHub e GitHub

1. Use uma conta com escrita no namespace `anselmomendes`. Em Account settings › Personal access tokens, gere um token **Read & Write** (`atlas-github-ci`) e copie-o na hora: ele só aparece uma vez.
2. No GitHub, em Settings › Secrets and variables › Actions, crie os secrets do repositório `DOCKERHUB_USERNAME` e `DOCKERHUB_TOKEN`. Sem eles, o primeiro job de cada workflow de imagem (`secrets-check`) falha em segundos listando o que falta.
3. Em Settings › Environments, crie `hml` e `prod`. Em `prod`, ative **Required reviewers**: o deploy de versão espera aprovação.

### 2. Service accounts

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

A condição de IAM exige acesso uniforme no nível do bucket. As contas de treino (leitura e escrita no BigQuery) e do MLflow (só o bucket) são as mesmas do desenvolvimento ou contas próprias do ambiente. Gere cada chave fora do repositório e **apague o arquivo local** depois de colá-la no Portainer.

### 3. Docker secrets no Portainer

Em Secrets › Add secret, crie os três do ambiente, colando o JSON de cada chave:

| Nome | Conteúdo |
|---|---|
| `atlas_hml_backend_sa` | chave da conta de leitura do backend |
| `atlas_hml_training_sa` | chave da conta de treino e dbt |
| `atlas_hml_mlflow_sa` | chave da conta do MLflow |

O nome leva o ambiente porque os secrets são do cluster inteiro; em produção, `atlas_prod_...`. **Rotação:** um Docker secret não pode ser alterado. Remova o stack, apague o secret, crie-o de novo com o mesmo nome e crie o stack outra vez; os volumes (banco, logs) são mantidos.

### 4. O stack no Portainer, pelo GitHub

1. Stacks › Add stack › **Repository**. Nome `atlas-hml`.
2. Repository URL `https://github.com/cnx-anselmooliveira/atlas_epidemiologico`, **Repository reference** `refs/heads/hml`, **Compose path** `docker-compose.yml`. O repositório é público: não há credencial de acesso. Se um dia ele ficar privado, guarde um token de leitura em **Authentication** no próprio Portainer, nunca no Git.
3. **Environment variables › Load variables from .env file** com o `.env.example`; depois preencha: `ATLAS_ENV=hml`, `IMAGE_TAG=hml`, os hosts (`FRONTEND_HOST`, `FRONTEND_PUBLIC_URL`, `API_HOST`, `AIRFLOW_HOST`, `MLFLOW_HOST`), `ADMIN_ALLOWED_CIDRS` e todas as senhas (troque cada `troque-esta-senha`; a Fernet key vem de `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`; senhas distintas para Postgres, MLflow e Airflow).
4. **GitOps updates:** desligue a sincronização por intervalo (ela poderia implantar antes de a imagem existir) e ative o **webhook do stack**, com a opção de baixar as imagens de novo (*re-pull image*). Copie a URL do webhook.
5. No GitHub, em Settings › Environments › `hml`, crie o secret `PORTAINER_WEBHOOK_STACK` com essa URL. O de `prod` é outro, do stack `atlas-prod`.

Depois de cada imagem publicada em `hml`, o CI chama o webhook e o Portainer refaz o deploy. Se o secret não existir, a imagem é publicada e o job avisa "deploy não acionado" sem falhar. Mudando só o `docker-compose.yml` em `hml` (sem imagem nova), faça o redeploy à mão no Portainer.

### 5. Primeiro boot

1. O Postgres cria os bancos `airflow`, `mlflow` e `mlflow_auth` e os usuários `airflow` e `mlflow` (cada um só conecta nos próprios bancos). Isso só acontece com o volume vazio; para trocar uma senha depois, use `ALTER ROLE ... PASSWORD ...` no Postgres e atualize a variável.
2. O serviço `airflow-init` roda uma vez (migra o banco e cria o admin) e aparece como concluído; o scheduler, o dag-processor, o triggerer e o api-server esperam a migração e ficam saudáveis sozinhos. A cada novo deploy o init roda de novo, sem efeito (é idempotente).
3. Confira no Portainer, ou na VPS, com `docker service ls`: todos `1/1`, o `airflow-init` como concluído. O site em `FRONTEND_HOST`, a API em `API_HOST`, o Airflow (usuário `admin`, senha `AIRFLOW_ADMIN_PASSWORD`) e o MLflow (usuário e senha de `MLFLOW_ADMIN_*`) respondem; os dois últimos só a partir das origens de `ADMIN_ALLOWED_CIDRS`.
4. Para conferir a leitura do backend: `GET /forecast/figures/<modelo>/<arquivo>.png` devolve 200 `image/png`.

### 6. Produção

O stack `atlas-prod` é o mesmo arquivo lido da branch `main`, com `ATLAS_ENV=prod`, `IMAGE_TAG=X.Y` (a versão publicada, **nunca** a tag móvel `hml`), os hosts e secrets `atlas_prod_...` próprios. O deploy de produção só é acionado por tag `vX.Y` em `main`, depois da aprovação do Environment `prod`. Conferência: `docker service ls --format '{{.Name}} {{.Image}}'` deve mostrar só tags de versão nos serviços do `atlas-prod`.

## Fluxo de promoção dev → hml → main

A produção é a **`main`** (não existe branch `prod`): `atlas-hml` lê a branch `hml` e `atlas-prod` lê a `main`, as duas com o caminho `docker-compose.yml`.

1. Trabalho em `dev`; cada push publica as imagens com tag `dev` (sem deploy). O `ci.yml` roda nos PRs e nos pushes para `hml` e `main`, e antes de qualquer publicação de imagem.
2. **Promover para hml:** PR `dev` → `hml`. No merge, os workflows das imagens alteradas publicam `hml` e chamam o webhook do Environment `hml`.
3. **Versão:** PR `hml` → `main`, depois a tag `vX.Y` em `main`. O workflow publica `X.Y` (imutável), espera a aprovação do Environment `prod` e chama o webhook de prod. Uma tag fora de `main` é recusada.
4. **Merge com commit de merge**, nunca squash nem rebase: o squash cria commits novos que não são ancestrais de `dev`, e o PR seguinte volta a listar tudo como diferença.

### O que o CI barra em um PR para hml ou main

| Job | Regra |
|---|---|
| `promocao` | `hml` só recebe PR de `dev`; `main` só recebe PR de `hml`. Qualquer outra origem falha explicando o fluxo. |
| `stack` | `docker-compose.yml`, `.env.example` e `platform/postgres/init-databases.sh` existem; `docker stack config` valida para hml (tag `hml`) e prod (tag de versão); sem `latest`, sem porta publicada, sem `build`, secrets externos, só imagens do projeto, `postgres` e `redis`. Roda também com `bash platform/ci/check-stack.sh`. |
| `secrets` | nenhum valor literal de credencial no `docker-compose.yml` e em `deploy/`, nenhuma variável do stack fora do `.env.example`. |
| `ci-ok` | passa só se todos os jobs passaram (`promocao` pulado só é aceito fora de PR). É o único check exigido na proteção. |

### Proteção das branches `hml` e `main` (Settings › Branches)

| Configuração | Esperado |
|---|---|
| Exigir PR antes do merge | ligado, **sem** exigir aprovação (um só mantenedor) |
| Check obrigatório | `ci-ok`, com a branch em dia |
| Valer para administradores | ligado |
| Push direto, force-push e exclusão | bloqueados |
| Merge do repositório (Settings › General) | só **Create a merge commit**; squash e rebase desligados; "delete branch on merge" desligado (apagaria `dev` e `hml`) |

Para conferir: `gh api repos/cnx-anselmooliveira/atlas_epidemiologico/branches/<hml|main>/protection` e `gh api repos/cnx-anselmooliveira/atlas_epidemiologico --jq '{merge_commit: .allow_merge_commit, squash: .allow_squash_merge, rebase: .allow_rebase_merge}'`. O `.github/CODEOWNERS` pede o mantenedor para o stack, o `.env.example`, `platform/postgres/`, `deploy/` e os workflows.

### Conferência de produção

Depois de implantar o `atlas-prod`, todos os serviços do stack devem usar tag de versão: `docker service ls --format '{{.Name}} {{.Image}}'` não pode mostrar `:hml` nem `:dev`. O CI já impede um valor fixo no arquivo e só aciona o deploy de produção por tag em `main`; o valor de `IMAGE_TAG` no Portainer só você vê.

### Emergência

Um conserto urgente também passa por `dev` e `hml`. Se for impossível esperar, o administrador pode desligar a proteção da branch por um momento (Settings › Branches), aplicar a mudança e **religar na hora**; registre o motivo no PR seguinte.

## Desenvolvimento local

- Chaves em `platform/secrets/` e senhas no `.env` da raiz: ambos são ignorados pelo Git e entram nos containers só em runtime, como volume somente leitura. Nunca são copiados para uma imagem.
- Não deixe a chave solta na raiz do repositório (`ppgcc-dengue-project.json`): use `platform/secrets/`.
- O `AIRFLOW__API_AUTH__JWT_SECRET` e a senha de dev do `compose.dev.yml` valem **só** para a máquina local.

## Proteções contra vazamento

1. **Hook local** (uma vez por clone): `git config core.hooksPath .githooks`. Ele roda `platform/ci/check-secrets.sh --staged` antes de cada commit.
2. **CI**, job `secrets` (em todo push e PR, e dentro do `ci-ok`):
   - `check-secrets.sh --all` barra nomes proibidos (`.env`, `*.pem`, `*.key`, `secrets/`, chaves de service account), conteúdos com formato de credencial (chave privada, JSON de service account, tokens do GitHub e do DockerHub, URL de webhook do Portainer), valor literal em campo de credencial do `docker-compose.yml` e de `deploy/`, variável de compose ou stack ausente do `.env.example` e valor real no próprio exemplo;
   - gitleaks no histórico inteiro (`.gitleaks.toml`, com as exceções conhecidas).
3. **`.gitignore` e `.dockerignore`:** as mesmas famílias de arquivo ficam fora do Git e fora do contexto de build.
4. **GitHub:** secret scanning e push protection ligados no repositório.

## Se uma credencial vazar

1. Revogue a chave na hora (GCP IAM › Service accounts › Keys, ou o token no DockerHub/GitHub/Portainer). Apagar o commit **não basta**: o repositório é público e a chave já pode ter sido copiada.
2. Crie uma nova e atualize nos lugares da tabela acima.
3. Só depois limpe o histórico, se necessário.
