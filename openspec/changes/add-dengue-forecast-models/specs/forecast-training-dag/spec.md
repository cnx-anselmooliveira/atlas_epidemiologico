# Spec Delta

## Purpose

Orquestrar no Airflow o treino dos modelos de previsão de dengue do Brasil, do snapshot dos dados até a comparação final no MLflow, numa única execução rastreável.

## ADDED Requirements

### Requirement: Ordem das tarefas
A DAG `atlas_dengue_forecast_br` SHALL executar nesta ordem:
1. preparação do snapshot;
2. os cinco modelos-base em paralelo (baseline bayesiano, CatBoost, LSTM, SVR, Chronos);
3. o ensemble, depois de CatBoost, SVR e LSTM;
4. a comparação final.

#### Scenario: Dependências do ensemble
- **WHEN** a tarefa da LSTM falha definitivamente
- **THEN** a tarefa do ensemble não é executada
- **AND** os demais modelos-base que terminaram mantêm suas runs registradas

### Requirement: Mesmo snapshot em toda a execução
Todas as tarefas de modelo de uma execução SHALL usar o snapshot gerado pela tarefa de preparação daquela execução, identificado pela run de dataset no MLflow, e não reler o BigQuery.

#### Scenario: Gold atualizada no meio da execução
- **WHEN** a tabela gold é reconstruída enquanto os modelos treinam
- **THEN** todos os modelos daquela execução continuam usando o snapshot original

### Requirement: Execução rastreável no MLflow
Todas as runs de uma execução SHALL ficar no experimento `atlas/dengue-forecast-br` com a tag `atlas.pipeline_run` igual ao identificador da execução da DAG.

#### Scenario: Filtrar uma execução
- **WHEN** se busca no MLflow por `tags.atlas.pipeline_run = '<id>'`
- **THEN** aparecem a run de dataset, as runs dos seis modelos e a run de comparação daquela execução

### Requirement: Comparação final
A última tarefa SHALL registrar uma run de comparação com a tabela das métricas de teste de todos os modelos que terminaram. Ela SHALL indicar o modelo com menor `test_nrmse_mean` e listar os modelos que faltaram.

#### Scenario: Modelo ausente
- **WHEN** o Chronos falhou e os demais terminaram
- **THEN** a run de comparação lista os cinco modelos com métricas e registra o Chronos como ausente

### Requirement: Execução manual e sem sobreposição
A DAG SHALL ser disparada manualmente, sem agendamento, com no máximo uma execução ativa por vez, e permitir sobrescrever a configuração (janela, horizonte, semente) nos parâmetros do disparo.

#### Scenario: Horizonte diferente
- **WHEN** a DAG é disparada com o parâmetro `horizon=4`
- **THEN** todas as runs daquela execução registram `horizon=4`

### Requirement: Artefatos no bucket
No ambiente dev conectado ao bucket, os artefatos das runs SHALL ser gravados em `gs://ppgcc-bucket/mlflow/dev/` sem que as tarefas do Airflow tenham credencial do bucket.

#### Scenario: Verificação de artefato
- **WHEN** a execução termina
- **THEN** os artefatos de previsões de cada run existem sob `gs://ppgcc-bucket/mlflow/dev/`
