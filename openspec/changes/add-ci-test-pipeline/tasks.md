# Tasks

## 1. Preparação dos testes

- [ ] 1.1 Registrar o marcador `models` no `ml/pyproject.toml` e conferir que `uv run pytest -m "not models"` roda os 23+ testes leves e `uv run pytest -m models` termina com código 0 ou 5; verificar os dois comandos localmente
- [ ] 1.2 Corrigir o que `shellcheck` apontar em `infra/mlflow/entrypoint.sh`, `airflow/config/init.sh` e `platform/postgres/init-databases.sh` e o que `ruff` apontar em `airflow/dags/`; verificar os dois sem avisos (rodando via container `koalaman/shellcheck` e `uv run ruff`)
- [ ] 1.3 Criar `platform/ci/e2e.sh` (`.env` temporário, compose com projeto `atlas-ci`, espera por health, token, despausa e dispara `atlas_ml_example_training`, asserções de estado, tags `atlas.*` e alias `@dev`, logs em `e2e-logs/` em falha, `down -v` no `trap`); verificar rodando-o localmente no Git Bash até passar, e forçando uma falha (DAG com comando inválido) para ver os logs gerados
- [ ] 1.4 Commit por assunto em `dev` (`test(ml): marcador models`, `fix(scripts): ajustes do shellcheck`, `test(platform): script de ponta a ponta`); verificar com `git log --oneline -3`

## 2. Workflow de CI

- [ ] 2.1 Criar `.github/workflows/ci.yml` com gatilhos (push e PR para `hml`/`main`, `workflow_dispatch`, `workflow_call`), `concurrency` e `permissions: contents: read`, mais os jobs `lint`, `ml-tests`, `ml-models-tests`, `frontend` e `openspec`; verificar com `actionlint` sem erros
- [ ] 2.2 Adicionar os jobs `images` (buildx, `push: false`, cache GHA por imagem, `ATLAS_GIT_SHA`), `dags` (rebuild com cache + `test_dags.py`) e `platform-e2e` (chama `platform/ci/e2e.sh`, publica `e2e-logs/` em falha); verificar com `actionlint`
- [ ] 2.3 Adicionar o job `ci-ok` (`needs` de todos, `if: always()`, falha se algum resultado não for `success`); verificar com `actionlint` e com um teste mental das combinações `success`/`failure`/`skipped` documentado no comentário do job
- [ ] 2.4 Commit em `dev` (`ci: pipeline de testes para hml e main`); verificar com `git log -1 --stat`

## 3. Primeira execução e proteção

- [ ] 3.1 Abrir o PR `dev → hml` e acompanhar o `ci.yml` até todos os jobs ficarem verdes, corrigindo o que falhar no runner (com um commit por assunto); verificar o check `ci-ok` verde no PR
- [ ] 3.2 Provar que o portão funciona: numa branch temporária com um teste quebrado de propósito, abrir PR para `hml` e ver o `ci-ok` vermelho apontando o job; fechar o PR e apagar a branch; verificar pelo link da execução
- [ ] 3.3 Configurar a proteção de `hml` e `main` via `gh api` (check `ci-ok` obrigatório e `strict`, PR obrigatório com 0 aprovações, `enforce_admins`, sem force-push) e documentar em `platform/README.md`; verificar com `gh api …/protection` e com um `git push` direto em `hml` sendo rejeitado
- [ ] 3.4 Fazer o merge do PR `dev → hml` com o CI verde; verificar que o push resultante em `hml` dispara o `ci.yml` e termina verde

## 4. Alinhamento com as outras mudanças

- [ ] 4.1 Atualizar as tarefas 6.1 e 6.2 da `add-ml-platform`: os workflows de publicação chamam `./.github/workflows/ci.yml` como primeiro job e só publicam com `needs: tests`, sem repetir ruff/pytest/DagBag; verificar `openspec validate add-ml-platform --strict`
- [ ] 4.2 Commit em `dev` (`docs(openspec): publicação de imagens depende do CI`); verificar `git log -1`

## Workflow follow-up

- Arquivar a mudança depois que a proteção estiver ativa e o CI verde em `hml` e `main`.
