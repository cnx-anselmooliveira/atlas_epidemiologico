# Tasks

## 1. Projeto dbt dentro das DAGs

- [x] 1.1 Registrar a mudança de pasta no git (`utfpr_dengue/` → `airflow/dags/utfpr_dengue/`), confirmando que `target/`, `logs/` e `dbt_packages/` seguem ignorados; verificar com `git status` que o git detecta como renomeação (sem conteúdo novo)
- [x] 1.2 Criar `airflow/dags/utfpr_dengue/pyproject.toml` (dbt-core + dbt-bigquery, Python 3.12) com `uv.lock`, e `profiles.yml` por variáveis de ambiente; verificar `uv run --project airflow/dags/utfpr_dengue dbt debug --project-dir … --profiles-dir …` com `DBT_BQ_KEYFILE=platform/secrets/training-sa.json` e sem `~/.dbt/profiles.yml`
- [x] 1.3 Criar `airflow/dags/.airflowignore` (`utfpr_dengue/`) e acrescentar ao `airflow/Dockerfile.dockerignore` os diretórios gerados do dbt; verificar com `docker build` que a imagem não contém `utfpr_dengue/target`
- [x] 1.4 Commits por assunto em `dev` (`refactor(dbt): projeto dbt junto das DAGs`; `build(dbt): dependências fixadas e profile por ambiente`; `chore(airflow): ignorar projeto dbt no processador e na imagem`); verificar `git log --oneline -3`

## 2. Imagem e compose

- [x] 2.1 Instalar o dbt no `airflow/Dockerfile` num venv `/opt/dbt` a partir do `pyproject`/`uv.lock` do projeto e expor o CLI `dbt`; verificar `docker run … dbt --version` e `airflow version` na mesma imagem
- [x] 2.2 Acrescentar ao `platform/compose.dev.yml` as variáveis `DBT_BQ_KEYFILE=/secrets/training-sa.json` e `DBT_PARTIAL_PARSE=false` e o volume `dbt-artifacts` em `/opt/airflow/dbt-artifacts`; verificar `docker compose config` e a stack saudável depois do `dev.ps1 up`
- [x] 2.3 Commit em `dev` (`build(airflow): dbt na imagem e variáveis do compose`); verificar `git log -1 --stat`

## 3. DAG

- [x] 3.1 Escrever `airflow/dags/process_etl_atlas.py` (sem agendamento, `max_active_runs=1`, parâmetros `select`/`exclude`/`full_refresh`, `dbt_debug → dbt_deps → dbt_seed → dbt_bronze → dbt_silver → dbt_gold → dbt_report` com `trigger_rule=all_done` e sentinela `dbt_status` (`one_failed`), artefatos em `/opt/airflow/dbt-artifacts/<run_id>`, `retries=0`); verificar com `ruff` e com o teste de integridade
- [x] 3.2 Ampliar `airflow/tests/test_dags.py` com os testes da nova DAG (agendamento, ordem, trigger rule, caminhos fora da pasta de DAGs, parâmetros) e com a garantia de que o `DagBag` não traz nada de `utfpr_dengue/`; verificar rodando o teste dentro da imagem
- [x] 3.3 Rodar a DAG no compose de dev com uma seleção pequena e depois com o build completo; conferir debug e build verdes, o relatório (contagens, nós lentos), os artefatos em `dbt-artifacts/<run_id>/` e nenhum arquivo novo em `airflow/dags/utfpr_dengue/`; registrar tempo e bytes processados do build completo no `README.md` do projeto dbt
- [x] 3.4 Forçar uma falha (ex.: `select` com um teste que falha ou chave inválida) e conferir que a tarefa certa falha e o relatório ainda roda listando o erro; verificar pelos logs das tarefas
- [x] 3.5 Commits por assunto em `dev` (`feat(airflow): DAG process_etl_atlas`; `test(airflow): integridade da DAG do dbt`; `docs(dbt): execução pela DAG e custo do build`); verificar `git log --oneline -3`

## 4. Alinhamento

- [x] 4.1 Atualizar a `add-gold-casos-provaveis-uf` (proposta, design e tarefas 1.2, 3.x e 4.1) para o caminho `airflow/dags/utfpr_dengue/`, o profile e a execução desta mudança (o job `dbt parse` do CI aponta para o novo caminho); verificar `openspec validate add-gold-casos-provaveis-uf --strict`
- [x] 4.2 Atualizar `airflow/README.md` (nova DAG, como disparar com `select`, onde ficam os artefatos) e o `README.md` raiz (projeto dbt dentro de `airflow/dags/`); verificar links com lychee
- [x] 4.3 Commits por assunto em `dev` (`docs(openspec): projeto dbt dentro das DAGs`; `docs: DAG de atualização do dbt`); verificar `git log --oneline -2`

## 5. Credencial do BigQuery por Connection do Airflow

- [ ] 5.1 Ler a credencial de uma Connection do Airflow (`atlas_gcp`, tipo Google Cloud, campo Keyfile JSON) cadastrada pela UI e cifrada com a Fernet key: um helper das DAGs grava o JSON num arquivo temporário `0600` só durante a tarefa, aponta `DBT_BQ_KEYFILE`/`GOOGLE_APPLICATION_CREDENTIALS` para ele e apaga no fim; sem a Connection, cai para o arquivo montado (dev). Nenhuma chave em imagem, git, variável do compose ou log; verificar com teste do helper (arquivo `0600`, removido mesmo com falha) e uma execução com a Connection cadastrada
- [ ] 5.2 Exigir `AIRFLOW__CORE__FERNET_KEY` (segredo da stack) nas stacks de hml/prod e documentar no `airflow/README.md` o cadastro da Connection pela UI (Admin → Connections) e a rotação da chave; verificar que a Connection aparece cifrada no banco (`is_extra_encrypted=true`)
- [ ] 5.3 Commit (`feat(airflow): credencial do BigQuery por Connection`); verificar `git log -1 --stat`

## Workflow follow-up

- Promover para `hml` por PR com o CI verde e arquivar a mudança depois de a DAG rodar em hml.
