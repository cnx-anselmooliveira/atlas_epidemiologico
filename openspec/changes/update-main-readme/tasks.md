# Tasks

## 1. Levantamento dos fatos

- [ ] 1.1 Levantar no repositório o que o README precisa afirmar: seções do site, serviços e portas do `platform/compose.dev.yml`, comandos de teste de `ml/`, `backend/`, `frontend/` e de `airflow/tests`, imagens publicadas e workflows, nomes dos Environments e do secret; verificar com uma tabela "afirmação → arquivo de origem" anexada ao rascunho
- [ ] 1.2 Executar na máquina cada comando que entrará no README (`./platform/dev.ps1 status`, testes de cada parte) e anotar o resultado; verificar que nenhum comando listado falha

## 2. Reescrita (primeira passada)

- [ ] 2.1 Reescrever o início do `README.md`: badges (ci, release, license e DockerHub por imagem ou link do namespace, mantendo o comentário sobre badges vazios), resumo do Atlas, o que o site mostra e as fontes de dados (SINAN pelo OpenDataSUS); verificar lendo o texto contra o site rodando (seções e rotas) e contra `docs/referencias/sinan-opendatasus.md`
- [ ] 2.2 Atualizar a arquitetura (diagrama e parágrafo): BigQuery com dbt, Airflow (ETL, ingestão do SINAN, treino e exportação do MLflow), MLflow, API com Redis e rotas `/forecast`, site; verificar o diagrama renderizando e cada componente contra a pasta correspondente
- [ ] 2.3 Escrever a seção "Rodar localmente": pré-requisitos, `.env.example` → `.env`, `./platform/dev.ps1`, tabela de portas de todos os serviços, testes por parte e links para `platform/README.md`; verificar seguindo os passos em um clone limpo
- [ ] 2.4 Escrever a seção "Implantar": imagens publicadas, fluxo `dev` → `hml` → `main` com tags `dev`, `hml` e `X.Y`, stack único `docker-compose.yml` da raiz no Portainer, Environments e webhook do stack, com links para `deploy/README.md`; verificar cada nome contra os workflows e contra as mudanças `add-hml-stack`, `add-hml-cicd-images` e `add-branch-promotion`
- [ ] 2.5 Escrever as seções "Segurança" (tabela tipo de segredo → onde entra) e "OpenSpec", atualizar "Estrutura do repositório" (incluindo `backend/` e a nova descrição de `deploy/` e `platform/`) e remover as referências obsoletas; verificar com `grep` que nenhum termo obsoleto resta

## 3. Verificação automática

- [ ] 3.1 Criar `platform/ci/check-readme.sh` (links relativos existentes, termos obsoletos ausentes, pastas de primeiro nível citadas); verificar com o README novo passando e com três casos que falham (link quebrado, termo obsoleto, pasta não citada)
- [ ] 3.2 Chamar o script no job `lint` do `ci.yml`; verificar com `actionlint` e a execução do passo no CI

## 4. Fechamento (segunda passada)

- [ ] 4.1 Depois de `add-hml-stack` 2.7 e 2.8, `add-branch-promotion` 1 e 2 e da primeira publicação das imagens, reler o README contra o repositório real (caminho e nome do stack, fluxo de promoção, secrets, badges) e ajustar; verificar com `check-readme.sh` e `grep` pelos nomes finais
- [ ] 4.2 Conferir o tamanho (cerca de 150 linhas), a ausência de procedimento repetido dos READMEs das pastas e o português do Brasil; verificar com `wc -l` e uma leitura completa
- [ ] 4.3 Registrar no `CHANGELOG.md` a atualização do README e commitar por assunto; verificar `git log` e o `ci-ok` do PR
