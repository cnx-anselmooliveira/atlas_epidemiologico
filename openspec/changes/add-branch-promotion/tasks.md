# Tasks

## 1. Validação do stack no CI

- [x] 1.1 Criar `platform/ci/check-stack.sh`: existência de `docker-compose.yml`, `.env.example` e dos arquivos de `configs.file`; `docker stack config` com as variáveis do `.env.example` para hml (`ATLAS_ENV=hml`, `IMAGE_TAG=hml`) e prod (`ATLAS_ENV=prod`, `IMAGE_TAG=1.0`); na saída resolvida, sem `:latest`, sem `published:`, secrets externos, imagens só do prefixo do projeto, `postgres` e `redis`, e nenhum serviço com tag `hml` quando `IMAGE_TAG=1.0`; verificar rodando o script no stack atual (passa) e com quatro casos que falham (script do Postgres ausente, porta publicada, `latest`, variável obrigatória sem exemplo)
- [ ] 1.2 Acrescentar ao `ci.yml` o job `stack` (checkout e `check-stack.sh`) e incluí-lo no `needs` do `ci-ok`; verificar com `actionlint` e, no PR, o job rodando e o `ci-ok` falhando quando ele é pulado

## 2. Regra de origem da promoção

- [x] 2.1 Acrescentar ao `ci.yml` o job `promocao` (só em `pull_request`: base `hml` exige head `dev`, base `main` exige head `hml`, outras combinações falham com mensagem), no `needs` do `ci-ok` tratando "pulado em push" como sucesso esperado; verificar extraindo o passo e executando-o com as quatro combinações de `base_ref` e `head_ref`
- [x] 2.2 Fazer o `ci-ok` aceitar `promocao` pulado fora de PR sem liberar um pulado dentro de PR; verificar com a lógica do passo agregado testada para push (pulado ok) e para PR (pulado falha)

## 3. Proteção e CODEOWNERS

- [ ] 3.1 Atualizar o `.github/CODEOWNERS` com `docker-compose.yml`, `.env.example`, `platform/postgres/` e `deploy/`; verificar pelo endpoint de erros de CODEOWNERS do GitHub, sem avisos
- [ ] 3.2 Consultar com `gh api` a proteção de `hml` e `main` e as opções de merge do repositório e montar a tabela "esperado × atual" (PR obrigatório, `ci-ok`, sem push direto, force-push e exclusão, administradores incluídos, sem exigir aprovação, só commit de merge); verificar mostrando o diff ao usuário
- [ ] 3.3 Com o usuário, aplicar os ajustes que faltarem (permissão de administrador); verificar de novo com `gh api` que a tabela fecha

## 4. Documentação

- [ ] 4.1 Escrever em `deploy/README.md` o fluxo de promoção e a configuração do Portainer por ambiente (`atlas-hml` em `refs/heads/hml`, `atlas-prod` em `refs/heads/main`, caminho `docker-compose.yml`, sincronização por intervalo desligada, webhook do stack no Environment, sem credencial para repositório público e como guardá-la no Portainer se ele virar privado); verificar relendo contra os nomes reais do stack, dos Environments e dos workflows
- [ ] 4.2 Acrescentar a conferência de produção (`docker service ls` só com tags `X.Y`) e o procedimento de exceção para emergência; verificar que os comandos citados existem

## 5. Primeira promoção

- [ ] 5.1 Abrir o PR `dev` → `hml`, esperar o `ci-ok` e, com a aprovação do usuário, fazer o merge com commit de merge; verificar que `hml` passa a ter `docker-compose.yml`, `.env.example` e `platform/postgres/init-databases.sh` (`git ls-tree`) e que os workflows de imagem de `hml` rodam
- [ ] 5.2 Abrir o PR `hml` → `main`, revisar a lista de commits com o usuário, esperar o `ci-ok` e, com a aprovação dele, fazer o merge; verificar a ancestralidade (`git merge-base --is-ancestor origin/hml origin/main`) e os três arquivos em `main`
- [ ] 5.3 Com o usuário, criar o stack `atlas-hml` no Portainer pela branch `hml` e confirmar o redeploy pelo webhook; a tag de versão e o stack `atlas-prod` ficam para depois, por decisão dele
