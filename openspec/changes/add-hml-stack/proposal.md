# Proposal

## Why

Hoje não existe um compose de hml. O repositório tem `platform/compose.dev.yml` (build local, DAGs e código montados por volume, portas no host) e `deploy/app.stack.yml` (só site, API e Redis, em Swarm/Portainer). Nada sobe Postgres, MLflow e Airflow a partir das imagens publicadas, então hml não pode existir na VPS. Além disso, as variáveis de que cada ambiente precisa estão espalhadas em vários exemplos (`platform/.env.example` cobre só parte do dev, `frontend/.env.example`, nada para o backend) e para hml não há nada que diga o que preencher no Portainer. A mudança em andamento `add-hml-cicd-images` prevê um `deploy/platform.stack.yml` (tarefa 3.2) separado do `app.stack.yml`; manter dois arquivos duplicaria rede, hosts e credenciais.

## What Changes

- **Um stack único, `deploy/atlas.stack.yml`, para hml e prod**, em formato Swarm (a VPS usa Traefik e a rede pública `network_public`), com Postgres, MLflow, Airflow (init, api-server, scheduler, dag-processor, triggerer), backend, frontend e Redis. As imagens vêm do DockerHub (`anselmomendes/atlas-epidemiologia-*`) pela variável de tag, sem `build` e sem volume de código. A mesma definição vira `atlas-hml` (tag `hml`) e `atlas-prod` (tag `X.Y`), só trocando as variáveis. Ele **absorve** as tarefas 3.1 e 3.2 da `add-hml-cicd-images` e substitui o `deploy/app.stack.yml`.
- **Subida sem `depends_on`** (o Swarm o ignora): o `airflow-init` roda como serviço de execução única e os demais componentes esperam a migração do banco (`airflow db check-migrations`); health checks por serviço; Postgres criado por um Docker config com o script de bancos.
- **Credenciais só por variáveis de stack e Docker secrets**, com as chaves das service accounts montadas em `/run/secrets/`; nenhum valor no arquivo.
- **MLflow e artefatos por ambiente:** o entrypoint do MLflow passa a aceitar `hml` e `prod` (hoje só `dev` e `vps`, o que faria hml e prod escreverem no mesmo prefixo do bucket), e os caminhos de cache do Cosmos e dos docs do dbt deixam de ser fixos em `dev`.
- **Portainer sincroniza o stack pelo GitHub:** o stack `atlas-hml` é criado no Portainer **a partir do repositório** (branch `hml`, arquivo `deploy/atlas.stack.yml`) e os valores (senhas, hosts, tag) são digitados nas variáveis do stack no Portainer. Depois de publicar as imagens, o CI chama o **webhook do stack** (um por Environment), que refaz o deploy baixando as imagens de novo. Isso substitui os webhooks por serviço e dispensa a lista de URLs do Airflow.
- **Um único `.env.example` e um `.env` local:** o `.env.example` da raiz lista todas as variáveis do projeto (dev local e stack de hml/prod), agrupadas e comentadas, só com valores de exemplo. Cada pessoa o copia para `.env` (ignorado pelo Git) para rodar localmente, e no Portainer as mesmas variáveis são preenchidas pela interface. Substitui `platform/.env.example`, `frontend/.env.example` e o exemplo previsto para o backend. O `check-secrets.sh` confere que o exemplo só tem valores de exemplo e que toda variável do compose e do stack está nele.
- **Validação:** `docker stack config`, subida real num Swarm local de um nó e verificação do site, da API e do MLflow antes de levar à VPS.

## Capabilities

### New Capabilities
- `hml-stack`: stack único em Swarm que sobe o Atlas completo a partir das imagens publicadas, para hml e prod, com a ordem de subida, os health checks, os hosts no Traefik e as credenciais por secrets.
- `env-examples`: um único `.env.example` na raiz, com todas as variáveis de dev e de hml/prod, e um `.env` local ignorado pelo Git.

### Modified Capabilities
<!-- Nenhuma spec principal existe em openspec/specs/. Ajusta a add-hml-cicd-images (tarefas 3.1 e 3.2 passam para esta mudança; o webhook multi-URL altera a tarefa 2.2). -->

## Impact

- `deploy/`: novo `atlas.stack.yml`; remoção de `app.stack.yml`; `README.md` com o passo a passo.
- `.env.example` na raiz (novo e único) e remoção de `platform/.env.example` e `frontend/.env.example`; `platform/dev.ps1`, `platform/ci/e2e.sh` e os scripts do site passam a ler o `.env` da raiz; `infra/mlflow/entrypoint.sh` (instalações `hml` e `prod`); `airflow/config/` (arquivo de ambiente de hml/prod); `.github/workflows/_image.yml` (webhook do stack); `platform/ci/check-secrets.sh`.
- `openspec/changes/add-hml-cicd-images/tasks.md`: tarefas 3.1 e 3.2 apontam para esta mudança.
- Portainer/VPS: criação do stack `atlas-hml` a partir do repositório (branch `hml`), variáveis do stack, Docker secrets, Docker config e o webhook do stack; credenciais nunca entram em imagem, XCom, navegador ou Git.
