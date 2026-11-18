# Proposal

## Why

Hoje o pipeline diário está numa DAG só, a `process_etl_atlas` (`@daily`, meia-noite UTC): o grupo `sinan` (sensor de diferenças no OpenDataSUS, landing no bucket, carga na bronze) e, se algum ano mudou, o dbt pelo Cosmos. O treino dos modelos de previsão do Brasil (`atlas_dengue_forecast_br`) não tem agendamento: roda à mão e, nos testes rápidos, foi rodado com a amostra ad hoc (`adhoc.gold_dengue_casos_provaveis_uf_semanal_amostra`, 4 UFs desde 2016). O site de hml mostra previsões dessa amostra. O usuário quer um fluxo diário único, às 03h00, que ingira o SINAN, refaça a modelagem só quando os dados mudarem e treine os modelos com a base inteira (todas as UFs e todo o período) também só quando os dados mudarem, na própria VPS de hml (4 CPUs, 8 GB de RAM, nó único).

## What Changes

- **DAG orquestradora `etl_brasil`**, agendada todos os dias às 03h00 de Brasília (`America/Sao_Paulo`), que dispara em sequência e espera cada etapa: ingestão do SINAN → modelagem dbt → treino do Brasil. Cada etapa é uma DAG própria, que também roda sozinha à mão.
- **DAG `ingestao_sinan_brasil`** (extraída do grupo `sinan` da `process_etl_atlas`, mesmo código de `atlas_ingest/sinan.py`): sensor que compara o OpenDataSUS com o landing no bucket, sync do landing (baixar o que mudou, apagar o que sumiu), carga e validação na bronze por ano. Disparada pela orquestradora, o sensor espera por uma janela limitada e, sem diferença, termina como "sem dados novos".
- **DAG `dbt_brasil`** (Cosmos, seed → bronze → silver → gold, extraída da `process_etl_atlas`), que só roda quando a bronze do SINAN mudou depois da última gold (ou com `forcar_dbt`).
- **Treino só quando a gold mudar:** antes de disparar `atlas_dengue_forecast_br`, a orquestradora compara a versão atual da gold com a `data_version` dos modelos vigentes no MLflow. O treino usa a base inteira (`fonte` vazio), e a exportação para o BigQuery continua sendo disparada pelo próprio treino.
- **Recursos intermediários na VPS:** pool do Airflow para o treino, `ATLAS_THREADS` e `max_active_tasks` menores, tempo máximo por tarefa e limites de memória e CPU no `docker-compose.yml` para os serviços do Airflow, para o treino não derrubar o resto do stack nem outros stacks do nó.
- **Fim da `process_etl_atlas`** (substituída pelas duas DAGs novas) e dos agendamentos soltos, para nada rodar duas vezes. **BREAKING** para quem dispara `process_etl_atlas` à mão: passa a ser `ingestao_sinan_brasil` + `dbt_brasil`, ou a `etl_brasil`.
- **Agendamento só em hml e prod:** em `dev` a `etl_brasil` fica sem agendamento (roda à mão), para não treinar todo dia na máquina local.

## Capabilities

### New Capabilities
- `etl-brasil-orchestration`: o fluxo diário do Brasil (ingestão do SINAN, dbt condicional, treino condicional), as DAGs que o compõem, as regras de "dados mudaram", o comportamento em falha e os limites de recurso do treino na VPS.

### Modified Capabilities
<!-- Nenhuma spec principal existe em openspec/specs/. Substitui a DAG process_etl_atlas descrita em add-sinan-opendatasus-ingestion (concluída) e add-cosmos-dbt-dags, sem mudar o que a ingestão e o dbt fazem; não muda o treino nem a exportação (add-dengue-forecast-models, add-forecast-page), só quando e com que fonte rodam. -->

## Impact

- `airflow/dags/`: novas `etl_brasil.py`, `ingestao_sinan_brasil.py` e `dbt_brasil.py`; remoção de `process_etl_atlas.py`; `atlas_dengue_forecast_br.py` com pool e limites; `atlas_ingest/` ganha a verificação de versão da gold e do MLflow.
- `airflow/tests/`: testes de DAG (estrutura, agendamento, encadeamento, regras de decisão) no lugar dos da `process_etl_atlas`.
- `docker-compose.yml` (limites de recurso do Airflow), `.env.example` (variáveis novas, se houver), `platform/compose.dev.yml` (dev sem agendamento).
- Documentação: `airflow/README.md` e `deploy/README.md`.
- Operação: a primeira execução na VPS treina a base inteira (horas); o site de hml passa a mostrar previsões da base inteira depois dela.
