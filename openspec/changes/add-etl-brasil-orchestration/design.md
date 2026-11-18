# Design

## Context

Observado no código:

- `process_etl_atlas.py` (`@daily`, `max_active_runs=1`, `retries=0`): grupo `sinan` com o sensor `detectar_diferencas` (`@task.sensor`, `mode="reschedule"`, `poke_interval` 30 min, `timeout` 20 h, `soft_fail=True`), `baixar`/`apagar` mapeados, `carga_ano` (carregar, validar, marcar o `bronze_etag`) e `remover_da_bronze`; depois `decidir_dbt` (dados novos ou o parâmetro `forcar_dbt`) e quatro `DbtTaskGroup` do Cosmos (seed, bronze, silver, gold, com `TestIndirectSelection.BUILDABLE`). A lógica de rede e de bronze está em `atlas_ingest/sinan.py`.
- `atlas_dengue_forecast_br.py`: `schedule=None`, `max_active_runs=1`, `max_active_tasks=3`, parâmetros `window`, `horizons`, `seed` e `fonte` (vazio = gold completa, `ml/src/atlas_ml/forecast/dataset.py`). Grupo mapeado `horizonte` (seis modelos por horizonte, `@task.external_python` no venv `/opt/atlas-ml`), `comparar` e, no fim, `TriggerDagRunOperator` para `process_forecast_export_atlas`. Cada run grava a tag `atlas.data_version` com a tabela e o `last_modified` da gold.
- Airflow com `LocalExecutor`, `PARALLELISM=4` e `MAX_ACTIVE_TASKS_PER_DAG=4` (Dockerfile): as tarefas rodam dentro do container do scheduler. `ATLAS_THREADS` limita as threads de cada treino (padrão: um terço dos núcleos).
- VPS de hml: nó único, 4 CPUs, 8 GB de RAM, Docker 29.5.2, dividida com outros stacks do usuário. O `docker-compose.yml` não tem limites de recurso hoje.
- O treino completo nunca rodou do começo ao fim: com a amostra (cerca de 2,3 mil linhas, 4 UFs) levou cerca de 21 minutos em 8 CPUs locais; a base inteira tem cerca de 37,8 mil linhas (27 UFs desde 2000).
- O PR #5 (aberto) monta a chave de treino como `training_sa.json`, sem a qual a Connection do Google não carrega no hml; as DAGs novas dependem dele.

## Goals / Non-Goals

**Goals:**
- Um disparo diário único, às 03h00 de Brasília, do SINAN às previsões.
- dbt e treino só quando os dados mudarem, com a decisão baseada em estado (e não em memória da execução anterior).
- Treino da base inteira caber na VPS sem derrubar o stack.

**Non-Goals:**
- Mudar o que a ingestão, o dbt, os modelos ou a exportação fazem.
- Alertas por e-mail ou Slack (o estado de falha fica visível no Airflow); fica como evolução.
- Treinar fora da VPS (máquina dedicada, GPU) ou escalar o Airflow para outro executor.
- Agendar a `process_dbt_docs_atlas` (continua manual).

## Decisions

1. **Orquestradora com `TriggerDagRunOperator(wait_for_completion=True, deferrable=True)`.** A espera fica no triggerer e não ocupa uma das 4 vagas do `LocalExecutor` durante horas. Cada filho recebe um `conf` explícito (por exemplo, a janela do sensor) e continua disparável à mão. Alternativa descartada: Assets (datasets) do Airflow 3, porque o encadeamento ficaria implícito, a ordem "ingestão → dbt → treino" num só dia não teria uma execução que a represente, e a falha de uma etapa não apareceria como falha de um fluxo.

2. **Decisões por estado, não por XCom entre DAGs.**
   - *dbt:* roda se o `last_modified` da tabela `bronze.sinan_dengue_opendatasus` for posterior ao da gold `gold_dengue_casos_provaveis_uf_semanal`, ou com `forcar_dbt`. Assim uma ingestão de ontem que não chegou ao dbt (falha) é recuperada hoje.
   - *treino:* roda se a versão da gold (tabela e `last_modified`) for diferente da `atlas.data_version` dos modelos vigentes no MLflow do ambiente (alias do ambiente), ou com `forcar_treino`. Se não houver modelo vigente, treina.
   Ambas as verificações são tarefas `@task.short_circuit` (Python) em `atlas_ingest/`, testáveis com dados falsos. Alternativa descartada: ler o XCom da execução filha, porque não sobrevive a reexecuções isoladas e quebra a idempotência.

3. **Sensor com janela limitada quando disparado pela orquestradora.** A `ingestao_sinan_brasil` recebe `janela_horas` no `conf` (padrão 3 h na orquestradora; à mão, uma verificação). Sem diferença na janela, o sensor termina como pulado (`soft_fail`) e a DAG termina com sucesso, informando "sem dados novos". A espera de 20 h atual some: ela prenderia a orquestradora o dia inteiro.

4. **DAGs com os nomes do fluxo.** `ingestao_sinan_brasil` e `dbt_brasil` são extraídas da `process_etl_atlas` (mesmas tarefas e mesmo `atlas_ingest/sinan.py`), que é removida. O treino mantém o nome `atlas_dengue_forecast_br`, porque o MLflow, a exportação e o site já o usam. A orquestradora chama `atlas_dengue_forecast_br` com `fonte` vazio, o que garante a base inteira.

5. **Agendamento só em hml e prod.** `schedule` da `etl_brasil` vem de `ATLAS_ENV`: `hml` e `prod` usam o cron `0 3 * * *` com `pendulum.timezone("America/Sao_Paulo")` na `start_date`; `dev` usa `None`. Evita que a máquina local treine todo dia.

6. **Recursos intermediários (primeira configuração, ajustável depois de medir):**
   - pool `atlas_treino` com 2 vagas; tarefas pesadas (LSTM, Bayesiano, Chronos) pesam 2, as leves (SVR, CatBoost, ensemble) pesam 1: no máximo um treino pesado por vez;
   - `max_active_tasks=2` na `atlas_dengue_forecast_br` e `ATLAS_THREADS=2` no stack;
   - `execution_timeout` por tarefa de treino (3 h) e da DAG de treino (12 h), para uma tarefa travada não segurar o fluxo para sempre;
   - limites no `docker-compose.yml`, revistos depois de medir a VPS (18/11/2026: cerca de 5,7 GB em uso **sem treino**, 2,2 GB só no MLflow com 2 workers e cerca de 2 GB de outros stacks): MLflow com **1 worker** (`MLFLOW_WORKERS`, limite de 2 GB); scheduler, onde o treino roda, com até 3 CPUs e **3,5 GB**; dag-processor 1 GB; api-server e triggerer 768 MB; backend 512 MB; frontend e Redis 384 MB; Postgres 1 GB. Os 5 GB previstos para o scheduler não cabiam no nó.
   Os valores são o ponto de partida; a primeira execução completa mede tempo e memória por tarefa e a tabela vai para `docs/referencias/resultados-forecast-br.md`.

7. **Falha:** cada `TriggerDagRunOperator` falha se a filha falhar (`failed_states=["failed"]`), e as etapas seguintes não rodam (dependência normal). A exportação só roda depois de um treino bem-sucedido, então o ponteiro de modelos vigentes e as previsões do site não mudam numa falha. `retries=0` no fluxo, como já é na ETL; a reexecução é manual e idempotente.

8. **Testes.** `airflow/tests/test_dags.py` passa a conferir: as três DAGs novas carregam sem erro de import; só a `etl_brasil` tem agendamento (e nenhum em dev); a ordem dos disparos; as funções de decisão do dbt e do treino com `last_modified` e `data_version` falsos (mudou, não mudou, sem modelo vigente, forçado). Os testes da `process_etl_atlas` migram para a `dbt_brasil` e a `ingestao_sinan_brasil`.

## Risks / Trade-offs

- **Tempo do treino completo na VPS é desconhecido** (estimativa: algumas horas com um treino pesado por vez). Mitigação: tempos máximos por tarefa, a medição da primeira execução e a decisão "só quando a gold mudar", que deixa a maioria dos dias sem treino.
- **Memória:** LSTM, PyMC (compilação do nutpie) e Chronos podem passar de 2 GB cada; com o limite do scheduler em 5 GB e um pesado por vez, a folga é pequena. Se a primeira medição mostrar pressão, a segunda configuração reduz a 1 vaga no pool.
- **Outros stacks no mesmo nó** competem por CPU e memória; os limites protegem os outros, mas deixam o treino mais lento.
- **Decisão pelo `last_modified`:** uma alteração manual na gold (por exemplo, um `dbt run` fora do fluxo) também dispara treino; é o comportamento desejado ("dados mudaram").
- **Sensor de 3 h às 03h00:** se o OpenDataSUS publicar depois das 06h00, os dados entram só no dia seguinte. Aceitável para uma série semanal.
- **Dependência do PR #5:** sem a chave `.json`, a Connection do Google não carrega nas DAGs novas; o merge do PR #5 vem antes.
