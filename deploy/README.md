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
