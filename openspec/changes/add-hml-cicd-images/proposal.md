# Proposal

## Why

A esteira de hml está pela metade. Só `frontend` e `backend` têm workflow de publicação no DockerHub; `airflow`, `mlflow` e `ml` (treino) são só construídas no CI e nunca chegam ao DockerHub, então o Portainer da VPS não tem como subir a plataforma de dados. Os secrets também não estão inventariados: o repositório não tinha nenhum quando se tentou publicar, o job de imagens só descobre isso no login do DockerHub (depois de rodar todos os testes), e o mesmo secret de webhook do Portainer é chamado em hml e em versão (prod), o que implantaria uma versão de produção no ambiente errado. Vale fechar isso antes do primeiro push para hml.

## What Changes

- **Publicar todas as imagens implantáveis:** `airflow`, `mlflow` e `ml` (alvo `runtime`) passam a ter workflow de publicação, pelo mesmo `_image.yml` do `frontend` e do `backend` (tags `dev`, `hml` e `X.Y`). `ml-notebook` e `postgres`/`redis` ficam de fora (só desenvolvimento ou imagem oficial).
- **Disparo manual e por caminho:** os workflows de imagem ganham `workflow_dispatch`, para publicar a primeira tag `hml` de uma imagem sem precisar mexer em arquivo dela, e passam a observar também os arquivos de que cada imagem depende (o `airflow` depende de `airflow/**` e do `ml/**`).
- **Verificação prévia de secrets:** um job inicial confere que os secrets obrigatórios existem (sem imprimir valor) e falha na hora com mensagem clara, antes dos testes e do build.
- **Webhooks por ambiente:** `PORTAINER_WEBHOOK_*` de hml e de prod passam a ser secrets de **GitHub Environments** (`hml` e `prod`), de modo que hml nunca acione o stack de prod. Prod pode exigir aprovação.
- **Stack no repositório, sem valores:** o `docker-compose.yml` da raiz (definido na mudança `add-hml-stack`, que substituiu o `app.stack.yml` e o `platform.stack.yml` previstos aqui) lê só variáveis e Docker secrets do Portainer, sem tag `latest` e com as variáveis do bucket de figuras.
- **Inventário de credenciais:** a tabela de `deploy/README.md` vira o contrato (nome, onde mora, quem usa, de qual ambiente) e um passo a passo para criar cada item, incluindo DockerHub, GitHub Environments, Portainer, Connection do Airflow e a conta de leitura do backend.
- **Sem credencial no Git:** o `check-secrets.sh` passa a conferir que o `docker-compose.yml` da raiz e os `deploy/*.yml` não têm valores literais nos campos de credencial, só referências.

## Capabilities

### New Capabilities
- `image-publishing`: publicação no DockerHub de todas as imagens implantáveis, por origem (branch ou tag), com tag imutável de versão e verificação prévia dos secrets.
- `hml-deploy-pipeline`: promoção dev → hml → main até o Portainer, com webhooks por ambiente, stacks versionados sem valores e inventário de credenciais.

### Modified Capabilities
<!-- Nenhuma spec principal existe em openspec/specs/; os ajustes em ci-test-pipeline e repo-governance (add-ci-test-pipeline, add-repo-governance) entram aqui como requisitos novos. -->

## Impact

- `.github/workflows/`: novos `airflow.yml`, `mlflow.yml`, `ml.yml`; `_image.yml` (job de verificação, uso de Environment), `frontend.yml` e `backend.yml` (`workflow_dispatch`, caminhos).
- `deploy/README.md` com o passo a passo; o stack em si fica no `docker-compose.yml` da raiz (mudança `add-hml-stack`).
- `platform/ci/check-secrets.sh`: regra de credencial para o `docker-compose.yml` da raiz e para `deploy/`.
- GitHub (feito pelo usuário na interface): secrets `DOCKERHUB_*` (já criados), Environments `hml` e `prod` com os webhooks.
- Portainer/VPS: criação do stack (`atlas-hml` e `atlas-prod`, ver `add-hml-stack`) e dos Docker secrets; credenciais nunca entram em imagem, XCom, navegador ou Git.
