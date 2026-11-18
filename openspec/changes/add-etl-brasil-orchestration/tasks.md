# Tasks

## 1. Pré-requisito

- [x] 1.1 Com a aprovação do usuário, mergear o PR #5 (chave de treino como `training_sa.json`) e reimplantar o stack de hml; verificar que a Connection `google_cloud_default` carrega (a DAG de ETL sai da lista de erros de import)

## 2. DAGs extraídas da process_etl_atlas

- [x] 2.1 Criar `ingestao_sinan_brasil.py` com o grupo `sinan` atual (mesmo `atlas_ingest/sinan.py`), sem agendamento, com o parâmetro `janela_horas` no sensor (padrão: uma verificação à mão) e um resultado final "sem dados novos" ou a lista de anos carregados e removidos; verificar com os testes de `test_sinan_ingest.py` e um teste de DAG (carrega, sem agendamento, sensor com a janela do `conf`)
- [x] 2.2 Criar `dbt_brasil.py` com os quatro `DbtTaskGroup` (`BUILDABLE`), sem agendamento, precedidos de uma decisão `@task.short_circuit` que roda o dbt se a bronze do SINAN for mais nova que a gold ou com `forcar_dbt`; verificar com teste unitário da decisão (bronze mais nova, igual, forçado) e teste de DAG
- [x] 2.3 Remover `process_etl_atlas.py` e migrar seus testes; verificar com `git grep process_etl_atlas` só em documentação histórica e os testes de DAG verdes

## 3. Treino condicional e com recursos limitados

- [x] 3.1 Criar em `atlas_ingest/` a verificação "gold mudou desde o treino vigente" (versão da gold × `atlas.data_version` dos modelos no alias do ambiente; sem modelo vigente = treinar; `forcar_treino`); verificar com testes unitários usando versões falsas e um MLflow simulado
- [x] 3.2 Na `atlas_dengue_forecast_br`: pool `atlas_treino` (2 vagas; peso 2 para LSTM, Bayesiano e Chronos, 1 para os demais), `max_active_tasks=2`, `execution_timeout` de 3 h por tarefa de treino e de 12 h na DAG; verificar com teste de DAG lendo pool, pesos e tempos
- [x] 3.3 Criar o pool `atlas_treino` na inicialização (`airflow/config/init.sh`, idempotente) e `ATLAS_THREADS=2` no stack; verificar rodando o `init.sh` duas vezes num Postgres local e listando o pool

## 4. Orquestradora

- [x] 4.1 Criar `etl_brasil.py`: `TriggerDagRunOperator` com `wait_for_completion=True` e `deferrable=True` para `ingestao_sinan_brasil` (janela de 3 h) e `dbt_brasil`, depois a decisão do treino (3.1) e o disparo de `atlas_dengue_forecast_br` com `fonte` vazio; parâmetros `forcar_dbt` e `forcar_treino` repassados; `max_active_runs=1`, sem catchup; verificar com teste de DAG (ordem das tarefas, `conf` enviado, `failed_states`)
- [x] 4.2 Agendamento `0 3 * * *` no fuso `America/Sao_Paulo` só quando `ATLAS_ENV` for `hml` ou `prod`, `None` em `dev`; verificar com teste de DAG carregando a DAG com cada `ATLAS_ENV`
- [x] 4.3 Teste de que só a `etl_brasil` tem agendamento entre as DAGs do fluxo; verificar com `test_dags.py`

## 5. Stack e documentação

- [ ] 5.1 Limites de recurso no `docker-compose.yml` (scheduler até 3 CPUs e 5 GB; api-server, dag-processor e triggerer menores; reservas para Postgres, backend e frontend) e variáveis novas no `.env.example`; verificar com `check-stack.sh`, `check-secrets --all` e um deploy no Swarm local
- [ ] 5.2 Atualizar `airflow/README.md` (fluxo diário, como rodar cada DAG à mão, parâmetros `forcar_*`) e `deploy/README.md` (horário, recursos, como acompanhar a primeira execução); verificar os nomes de DAG e parâmetros contra o código com `git grep`

## 6. Verificação em hml

- [ ] 6.1 Promover pelo fluxo de PR e, com a aprovação do usuário, disparar a `etl_brasil` à mão na VPS com `forcar_treino`, para a primeira execução completa da base inteira; verificar no Airflow as três etapas, no MLflow os 24 runs (6 modelos × 4 horizontes) com `data_version` da gold completa, no BigQuery o ponteiro atualizado e no site as previsões das 27 UFs
- [ ] 6.2 Medir tempo e pico de memória por tarefa na VPS e registrar em `docs/referencias/resultados-forecast-br.md`; ajustar pool e limites se houver pressão; verificar que o site e a API responderam durante o treino
- [ ] 6.3 Conferir no dia seguinte a execução agendada das 03h00: sem dados novos, dbt e treino pulados; verificar o estado das tarefas no Airflow
