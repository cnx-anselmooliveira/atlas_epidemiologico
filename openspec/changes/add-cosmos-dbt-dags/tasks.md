# Tasks

## 1. Imagem e compose

- [x] 1.1 Instalar `astronomer-cosmos==1.16.0` no ambiente do Airflow (`airflow/Dockerfile`, `USER airflow`, com `apache-airflow==` fixo) e tirar o diretório `dbt-artifacts` da imagem; verificar com `pip check`, `airflow version` e `python -c "import cosmos; print(cosmos.__version__)"` na imagem
- [x] 1.2 Conferir qual service account escreve no `ppgcc-bucket` (gravar e apagar um objeto de teste em `dbt_docs/dev/` com a `training-sa`; se negar, usar a `mlflow-sa`) e registrar a escolha no design
- [x] 1.3 Atualizar `platform/compose.dev.yml`:
  - `AIRFLOW_CONN_GOOGLE_CLOUD_DEFAULT`, só com `key_path` da SA escolhida;
  - `AIRFLOW__COSMOS__DBT_DOCS_PROJECTS` apontando para `gs://ppgcc-bucket/dbt_docs/dev`;
  - `AIRFLOW__CORE__DAGBAG_IMPORT_TIMEOUT=120` (acabou na imagem, para valer em todo ambiente);
  - remover o volume `dbt-artifacts`.

  Verificar com `docker compose config`, `airflow connections get google_cloud_default` e a stack saudável.
- [x] 1.4 Commit em `dev` (`build(airflow): Cosmos na imagem e configuração do dbt docs`); verificar `git log -1 --stat` e que nenhuma chave entrou

## 2. ETL com Cosmos

- [x] 2.1 Reescrever `airflow/dags/process_etl_atlas.py` com um `DbtTaskGroup` por camada (`seed → bronze → silver → gold`, mesmos seletores de hoje), `ProjectConfig(install_dbt_deps=True)`, `ProfileConfig` com o `profiles.yml` do projeto, `ExecutionConfig(dbt_executable_path="/opt/dbt/bin/dbt")`, `schedule=None`, `max_active_runs=1`, `retries=0`, sem parâmetros; remover `dbt_report`/`dbt_status`; verificar com `ruff` e com a DAG sem erro de importação no dag-processor (tempo de leitura anotado)
- [x] 2.2 Trocar os testes da ETL em `airflow/tests/test_dags.py`:
  - grupos em cadeia;
  - cada model de `models/` em exatamente um grupo (lista tirada do próprio projeto);
  - tarefa de `gold_dengue_casos_provaveis_uf_semanal` presente;
  - `retries=0`;
  - nenhum parâmetro obrigatório.

  Verificar rodando o teste dentro da imagem com a pasta de DAGs somente leitura e `DBT_BQ_KEYFILE` fictício.
- [x] 2.3 Commit em `dev` (`feat(airflow): process_etl_atlas com Cosmos`); verificar `git log -1 --stat`

## 3. Docs no bucket e no Airflow

- [x] 3.1 Criar `airflow/dags/process_dbt_docs_atlas.py` com um `DbtDocsGCSOperator`:
  - `connection_id="google_cloud_default"`;
  - bucket de `ATLAS_DBT_DOCS_BUCKET` (padrão `ppgcc-bucket`);
  - `folder_dir=dbt_docs/<ATLAS_ENV>`;
  - `schedule=None` e `retries=0`.

  Verificar com `ruff`.
- [x] 3.2 Adicionar o teste da DAG de docs (uma tarefa, operador, bucket e pasta por ambiente); verificar dentro da imagem
- [ ] 3.3 Rodar no compose de dev:
  1. a `process_etl_atlas` completa: todas as tarefas verdes e nada novo em `airflow/dags/utfpr_dengue/`; anotar o tempo total contra os 128 s da versão anterior no README do dbt;
  2. uma falha forçada: um teste de dados com `severity: error` temporário, conferindo que só a tarefa do model falha, as dependentes ficam `upstream_failed` e a execução fica vermelha; reverter o teste depois;
  3. a `process_dbt_docs_atlas`: conferir `index.html`, `manifest.json` e `catalog.json` em `gs://ppgcc-bucket/dbt_docs/dev/` com o tipo de conteúdo certo, e o menu de docs no Airflow mostrando `gold_dengue_casos_provaveis_uf_semanal` com linhagem.
- [x] 3.4 Commits em `dev` (`feat(airflow): DAG process_dbt_docs_atlas`; `test(airflow): DAGs do Cosmos`); verificar `git log --oneline -2`

## 4. Documentação e alinhamento

- [x] 4.1 Atualizar a `add-dbt-refresh-dag`:
  - spec `dbt-orchestration`: os requisitos de relatório, sentinela, parâmetros e artefatos por execução passam a apontar para esta mudança;
  - design: nota sobre o Cosmos;
  - seção 5: a Connection `google_cloud_default` e o `DBT_DOCS_PROJECTS` das stacks hml/prod.

  Verificar com `openspec validate add-dbt-refresh-dag --strict` e `openspec validate add-cosmos-dbt-dags --strict`.
- [ ] 4.2 Atualizar:
  - `airflow/README.md`: as duas DAGs, como refazer parte da modelagem com clear e onde ver o dbt docs;
  - `airflow/dags/utfpr_dengue/README.md`: a execução pelo Cosmos e o novo tempo medido.

  Verificar links com lychee.
- [ ] 4.3 Commit em `dev` (`docs: ETL e dbt docs com Cosmos`); verificar `git log -1 --stat` e `git push`

## Workflow follow-up

- Promover para `hml` por PR com o CI verde, cadastrar a Connection `google_cloud_default` pela UI e o `DBT_DOCS_PROJECTS` com `dbt_docs/hml` na stack, e arquivar a mudança depois de rodar em hml.
