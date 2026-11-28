# Tasks

## 1. DAGs de modelo

- [x] 1.1 Criar `airflow/dags/atlas_ingest/forecast_modelo.py` com as tarefas (`configuracao`, `iniciar`, `lista_de_horizontes`, `treinar`, `limpar`, `external_python` literais e autocontidas, levando os logs de hoje) e `criar_dag_modelo(modelo)` (params `horizons`, `window`, `seed`, `fonte`, `pipeline_run`, `data_version`, `notebook_sha`; `max_active_runs=1`, `max_active_tasks=2`, `dagrun_timeout` 8 h, `is_paused_upon_creation=False`, pool e tempos por modelo); verificar com `ruff` e importando o módulo na imagem local
- [x] 1.2 Tarefa `bases` do ensemble (busca no MLflow por `pipeline_run` ou, sem ele, a run concluída mais recente com a mesma `atlas.data_version`; falha no horizonte nomeando o modelo que falta; log das runs escolhidas com janela e semente) ligada a `treinar` como `base_runs`; verificar com teste unitário da função de escolha com runs simuladas (pipeline_run, só data_version, base ausente)
- [x] 1.3 Criar os seis arquivos `airflow/dags/atlas_forecast_<modelo>.py` chamando a fábrica e estender `airflow/tests/test_dags.py`: seis DAGs sem agendamento e despausadas na criação, tarefa de treino mapeada por horizonte, pool, `pool_slots` e `execution_timeout` por modelo, `bases` só no ensemble, `limpar` com `all_done`, horizonte inválido recusado; verificar com `test_dags.py` na imagem local
- [x] 1.4 Documentar as DAGs de modelo em `airflow/README.md` (tabela de DAGs, parâmetros, disparo isolado e o que ele não faz, ensemble sozinho); verificar que o texto bate com as DAGs carregadas (tarefas, parâmetros, regras) pelos testes de DAG. O disparo real do SVR seguindo o texto fica na 4.2, em hml (decisão do usuário: sem execução local)

## 2. Orquestrador

- [x] 2.1 Reescrever `atlas_dengue_forecast_br`: `configuracao`, `lista_de_horizontes`, `iniciar_execucao` (sem pasta), `modelo_<base>` ×5 e `modelo_ensemble` (`TriggerDagRunOperator` com `trigger_run_id` `<run_id>__<modelo>`, `conf` completa, `wait_for_completion`, `deferrable`, `poke_interval=60`, `failed_states=["failed"]`, `reset_dag_run=True`, `retries=0`, `execution_timeout` 8 h), `comparar.expand` (`all_done`), `algum_resultado` e `exportar`; `conf` montada por uma tarefa (`conf_dos_modelos`), com os tipos certos; mesmo `dag_id` e mesmos params; docstring com o novo desenho; verificar com `ruff`
- [x] 2.2 Atualizar os testes do orquestrador em `test_dags.py`: sem `horizonte.train_*` nem `prepare`, cinco disparos de base em paralelo, ensemble depois dos cinco com `all_done`, `conf` com `pipeline_run` e as versões, comparação e exportação com as regras de disparo, `trigger_run_id` por modelo; e conferir que `test_etl_brasil.py` continua passando (o disparo pela `etl_brasil` não muda); verificar com os dois testes na imagem local

## 3. CI com via rápida

- [x] 3.1 Criar `platform/ci/escopo.sh` (lista de arquivos na entrada, `rapido=true|false` na saída, padrões da design) com casos de teste em `platform/ci/test-escopo.sh` (só DAG, DAG + `ml/src`, `uv.lock` do dbt, só notebook, só Markdown, lista vazia, workflow alterado), executados no job `lint` e incluídos no `shellcheck`; verificar rodando os dois scripts localmente
- [ ] 3.2 `ci.yml`: job `escopo` (diff de PR e de push, `false` em `workflow_call`, `workflow_dispatch` e `before` nulo); `if` nos jobs dispensados; passo `pytest -m models` condicional; job `dags` na via rápida com `docker pull` da `:hml` e as pastas do commit montadas; `ci-ok` com a lista de dispensas; verificar com `actionlint` e lendo o plano dos jobs num PR de teste
- [ ] 3.3 `ml.yml` com `"!ml/notebooks/**"` nos `paths`; verificar com `actionlint` e conferindo que o PR da tarefa 4.2 (só notebook ou DAG) não dispara o `ml.yml`
- [x] 3.4 Criar `platform/ci/testar-dags.sh` (imagem local ou `--publicada` para a `:hml`, DAGs e testes do disco montados); documentar a via rápida e o teste local em `deploy/README.md` e `airflow/README.md` e registrar a mudança no `CHANGELOG.md`; verificar rodando o script nos dois modos

## 4. Integração em hml

- [ ] 4.1 Com a aprovação do usuário: conferir o `airflow-dag-processor` de hml na imagem atual (redeploy com *re-pull* se ainda estiver em rollback), promover por PR `dev` → `hml` (pipeline completo, porque muda workflows) e verificar no Airflow de hml as seis DAGs despausadas, o orquestrador com a forma nova e nenhum erro de importação
- [ ] 4.2 Em hml, com a aprovação do usuário (substitui a execução local, por decisão do usuário): disparar `atlas_forecast_svr` sozinha seguindo o `airflow/README.md` (`horizons=[1]`: treina e registra, sem `compare` nem exportação, pasta removida) e depois o orquestrador completo; verificar seis runs de modelo `<run_id>__<modelo>` com o mesmo `atlas.pipeline_run` no MLflow, o ensemble usando as bases desse `pipeline_run`, a `compare` por horizonte, a exportação disparada e as pastas das execuções removidas; depois abrir um PR só com uma docstring de DAG e verificar a via rápida (jobs dispensados pulados, `ci-ok` verde, `ml.yml` não disparado, tempo total registrado no PR)

## Workflow follow-up

- Arquivar `add-ci-test-pipeline`, `move-forecast-to-notebook-pipeline` e `self-contained-model-notebooks` antes desta, para os deltas de `ci-test-pipeline`, `airflow-dag-delivery` e `notebook-pipeline-execution` aplicarem sobre as specs principais.
