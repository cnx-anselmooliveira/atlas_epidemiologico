# Tasks

## 1. Workflows de imagem

- [x] 1.1 Estender o `_image.yml` com a entrada `target` (alvo do Dockerfile) e acrescentar `workflow_dispatch` nos chamadores; verificar com `actionlint` sem erros
- [x] 1.2 Criar `.github/workflows/airflow.yml` (contexto `.`, `file: airflow/Dockerfile`, caminhos `airflow/**` e `ml/**`), `mlflow.yml` (`infra/mlflow/**`) e `ml.yml` (`context: ml`, alvo `runtime`); verificar que cada um passa o secret `PORTAINER_WEBHOOK_<IMAGEM>`
- [x] 1.3 Adicionar `workflow_dispatch` e os caminhos de dependência a `frontend.yml` e `backend.yml`; verificar que uma alteração só em `ml/src/` dispara `ml` e `airflow` e não `frontend`
- [ ] 1.4 Conferir os `.dockerignore` das cinco imagens (`.env`, chaves JSON, `platform/secrets/`, certificados); verificar construindo cada imagem e listando o contexto enviado
- [ ] 1.5 Verificar o build local das três imagens novas (`airflow`, `mlflow`, `ml` alvo `runtime`) com os mesmos build args do workflow

## 2. Secrets e Environments

- [ ] 2.1 Criar o job `secrets-check` no início do `_image.yml`, com os demais dependendo dele; verificar a execução sem o secret: falha em segundos, lista o nome que falta e não imprime valor
- [ ] 2.2 Escolher o `environment` pela origem no job de publicação (`hml` para a branch, `prod` para tag, nenhum para `dev`) e ler `PORTAINER_WEBHOOK` do Environment; verificar que um push em `hml` não usa o webhook de `prod`
- [ ] 2.3 Registrar no job, sem falhar, quando não há webhook ("deploy não acionado"); verificar numa execução sem o secret
- [ ] 2.4 Criar a regra de `deploy/` no `platform/ci/check-secrets.sh` (campos de credencial só com `${...}`, `/run/secrets/...` ou vazios); verificar com um caso que falha, um que passa e `check-secrets --all` limpo

## 3. Stacks

- [x] 3.1 Tags obrigatórias e variáveis do bucket de figuras no stack: absorvido pela mudança `add-hml-stack` (tarefa 2.1), que substitui o `deploy/app.stack.yml`
- [x] 3.2 Stack da plataforma de dados (Postgres, MLflow, Airflow): absorvido pela mudança `add-hml-stack` (tarefas 2.1 a 2.5), em um único `deploy/atlas.stack.yml`
- [ ] 3.3 Documentar a criação da service account de leitura do backend e o acesso ao prefixo `forecast/` por condição IAM, com comandos sem valores; verificar, com o usuário, o PNG de uma figura servido por essa conta e anotar o resultado no README

## 4. Documentação

- [ ] 4.1 Reescrever a tabela de `deploy/README.md` como inventário (nome, onde cria, quem usa, ambiente, rotação), incluindo DockerHub, Environments, webhooks, Docker secrets e Connection do Airflow
- [ ] 4.2 Escrever o passo a passo da primeira configuração de hml e o roteiro dev → hml → main, com proteção de branch e tags; verificar os nomes de workflows e variáveis contra o código com `grep`
- [ ] 4.3 Atualizar os comentários do `_image.yml` e o `CHANGELOG.md`

## 5. Verificação e publicação

- [ ] 5.1 Rodar o `ci.yml` completo e `check-secrets --all`; verificar tudo verde
- [ ] 5.2 Promover `dev` para `hml`, disparar os cinco workflows e conferir as tags `hml` no DockerHub com `docker manifest inspect`
- [ ] 5.3 Com o usuário, criar os stacks no Portainer, acionar os webhooks de hml e verificar `/previsao`, o MLflow e o Airflow na VPS; anotar os ajustes no design
