# Tasks

## 1. Ajustes de código para hml e prod

- [ ] 1.1 Fazer o `infra/mlflow/entrypoint.sh` aceitar `MLFLOW_INSTALLATION` `dev|hml|prod` (e `vps` como alias de `prod`); verificar executando o entrypoint com cada valor e com um inválido (mensagem de erro) e o destino `gs://<bucket>/mlflow/<ambiente>` resultante
- [ ] 1.2 Parametrizar por `ATLAS_ENV` o cache do Cosmos e os docs do dbt no `compose.dev.yml` e no stack (`AIRFLOW__COSMOS__REMOTE_CACHE_DIR`, `AIRFLOW__COSMOS__DBT_DOCS_PROJECTS`), sem mudar o caminho de dev; verificar com `docker compose config` que dev segue com `.../dev`
- [ ] 1.3 Revisar `airflow/config/vps.env` para hml e prod (FAB, config não exposta) e conferir que o `init.sh` cria o admin no FAB; verificar subindo o `airflow-init` com `AIRFLOW__CORE__AUTH_MANAGER` do FAB num Postgres local e listando o usuário

## 2. Stack único

- [ ] 2.1 Criar `deploy/atlas.stack.yml` com `postgres`, `mlflow`, `airflow-init`, `airflow-api-server`, `airflow-scheduler`, `airflow-dag-processor`, `airflow-triggerer`, `backend`, `frontend` e `redis`: imagens por `IMAGE_TAG` obrigatória, redes `atlas_internal` e `network_public`, volumes nomeados, health checks, `restart_policy` e `update_config`, sem `build`, volume de código nem porta no host; verificar com `docker stack config -c deploy/atlas.stack.yml` com e sem as variáveis obrigatórias
- [ ] 2.2 Implementar a ordem de subida: `airflow-init` de execução única e espera por `airflow db check-migrations` nos demais componentes; verificar derrubando o scheduler com o banco já migrado (sobe sem rodar o init) e subindo com o volume vazio (tudo saudável sem intervenção)
- [ ] 2.3 Incluir o `init-databases.sh` por Docker config e as senhas distintas de `mlflow` e `airflow`; verificar no Postgres local os papéis, bancos e `REVOKE CONNECT`
- [ ] 2.4 Montar as chaves por Docker secrets (`training_sa`, `mlflow_sa`, `backend_sa`) e apontar `GOOGLE_APPLICATION_CREDENTIALS`, `DBT_BQ_KEYFILE` e a Connection para `/run/secrets/`; verificar que nenhum valor de credencial aparece no arquivo (`check-secrets --all`) e que o backend lê o BigQuery com a chave montada
- [ ] 2.5 Rótulos do Traefik para site, API, Airflow e MLflow com hosts por variável e o middleware de origens permitidas nas duas interfaces administrativas; verificar por `docker stack config` e relendo os rótulos contra o `app.stack.yml`
- [ ] 2.6 Remover o `deploy/app.stack.yml` e atualizar as referências (`deploy/README.md`, `_image.yml`, comentários); verificar com `grep` que nada aponta mais para ele

## 3. Webhooks

- [ ] 3.1 Fazer o job `deploy` do `_image.yml` aceitar várias URLs (uma por linha) no secret e falhar se qualquer chamada falhar; verificar com `actionlint` e um teste do loop de shell com duas URLs, uma delas inválida

## 4. Exemplos de variáveis

- [ ] 4.1 Completar `platform/.env.example` (portas do MLflow, Airflow, backend e site, `GCP_PROJECT`, bucket, Jupyter, CA, chaves em `platform/secrets/`), cada variável comentada; verificar copiando para `platform/.env` e rodando `docker compose config`
- [ ] 4.2 Criar `deploy/hml.env.example` com todas as variáveis do stack agrupadas (obrigatórias, com padrão, segredos) e indicação de Docker secret ou variável de stack; verificar que cada `${NOME}` do stack aparece no exemplo
- [ ] 4.3 Adicionar ao `check-secrets.sh` a conferência de que toda variável de `atlas.stack.yml` e `compose.dev.yml` existe no exemplo correspondente e de que os exemplos só têm valores reconhecíveis; verificar com um caso que passa e dois que falham (variável sem exemplo, senha real no exemplo)
- [ ] 4.4 Criar `backend/.env.example` (e conferir o `frontend/.env.example`) com as variáveis do `config.py` e do `astro.config.mjs`; verificar contra o código

## 5. Validação local

- [ ] 5.1 Subir o stack num Swarm local de um nó (`docker swarm init`, secrets e config de teste, imagens `:local` com `IMAGE_TAG` de teste); verificar todos os serviços saudáveis, `/`, `/previsao`, a API e o MLflow respondendo, e desfazer com `docker stack rm` e `docker swarm leave --force`
- [ ] 5.2 Rodar `actionlint`, `check-secrets --all` e o `ci.yml`; verificar tudo verde

## 6. Documentação e hml

- [ ] 6.1 Escrever em `deploy/README.md` o passo a passo de criação do stack `atlas-hml` (Docker secrets, config, variáveis, deploy a partir do Git, webhooks, primeiro boot, rotação de secret e de senha do Postgres) e o roteiro de promoção para `atlas-prod`; verificar relendo contra os nomes reais do stack e do exemplo
- [ ] 6.2 Atualizar as tarefas 3.1 e 3.2 da `add-hml-cicd-images` para apontar para esta mudança; verificar com `openspec validate` das duas mudanças
- [ ] 6.3 Com o usuário, criar o stack `atlas-hml` no Portainer, acionar os webhooks e verificar site, API, Airflow e MLflow na VPS; anotar os ajustes no design
