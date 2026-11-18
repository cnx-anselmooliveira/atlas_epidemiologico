# Spec Delta

## Purpose

Levar para o BigQuery e para o bucket o que as runs de previsão registraram no MLflow, de forma idempotente e sem credenciais no código, para que a API e o site leiam só do BigQuery.

## ADDED Requirements

### Requirement: DAG de exportação
Uma DAG do Airflow, escrita em Python (TaskFlow, sem scripts bash), SHALL ler no MLflow, para cada modelo e horizonte, a versão registrada no alias do ambiente e a run de origem dela, e materializar o resultado no BigQuery. Ela SHALL rodar ao fim da DAG de treino e poder ser disparada manualmente, com no máximo uma execução ativa.

#### Scenario: Depois do treino
- **WHEN** a DAG de treino termina
- **THEN** a DAG de exportação é disparada e as tabelas passam a refletir as versões do alias do ambiente

#### Scenario: Disparo manual
- **WHEN** a DAG é disparada à mão sem mudança no MLflow
- **THEN** as tabelas continuam com os mesmos dados, sem linhas duplicadas

### Requirement: Tabelas materializadas
A exportação SHALL manter no dataset `forecast` as tabelas `forecast_model_runs`, `forecast_metrics`, `forecast_metrics_uf`, `forecast_predictions` e `forecast_figures`, e uma visão `forecast_current_*` para cada uma, só com as linhas vigentes de cada modelo e horizonte. Tabelas e visões SHALL ter `exported_at` e a descrição de cada coluna.

#### Scenario: Conteúdo das tabelas
- **WHEN** a exportação termina
- **THEN** `forecast_model_runs` tem a run, a versão registrada, a família, os parâmetros, o `data_version` e o ambiente de cada modelo e horizonte
- **AND** `forecast_predictions` tem as previsões de validação, teste e futuro, com `split`, `y_true`, `y_pred`, `lower` e `upper`
- **AND** `forecast_figures` tem o caminho no bucket e a legenda de cada figura

#### Scenario: Linha por modelo e horizonte
- **WHEN** a exportação termina com seis modelos e quatro horizontes
- **THEN** `forecast_model_runs` vigente tem 24 linhas, uma por modelo e horizonte

### Requirement: Série do Brasil
A exportação SHALL acrescentar às previsões e às métricas as linhas da UF `BR`, calculadas a partir das UFs: a incidência do Brasil é a média das incidências das UFs ponderada pela população, as métricas são recalculadas sobre essa série e o intervalo fica nulo.

#### Scenario: Previsão do Brasil
- **WHEN** a exportação processa as previsões das 27 UFs de uma semana
- **THEN** a linha `BR` dessa semana é a soma dos casos previstos dividida pela população total

### Requirement: Idempotência e versão vigente
Reexecutar a exportação para a mesma versão registrada SHALL sobrescrever as linhas daquela run, sem duplicar. Uma versão nova de um modelo SHALL tornar-se a vigente sem apagar o histórico das anteriores.

#### Scenario: Nova versão do CatBoost
- **WHEN** o CatBoost horizonte 1 ganha uma versão nova e a exportação roda
- **THEN** a visão vigente mostra a versão nova e a tabela mantém as linhas da versão anterior

### Requirement: Figuras no bucket
A exportação SHALL copiar as figuras de cada run para o bucket, em `forecast/<ambiente>/<modelo>/h<horizonte>/<run>/<arquivo>`, e só aceitar arquivos PNG de até 500 KB.

#### Scenario: Arquivo fora do padrão
- **WHEN** um artefato em `figures/` não é PNG ou passa do limite
- **THEN** ele não é copiado e a exportação registra o aviso sem falhar

### Requirement: Credenciais por Connection
A DAG SHALL obter o acesso ao MLflow, ao BigQuery e ao bucket por Connection do Airflow, sem chave em código, imagem ou repositório. Falha de conexão SHALL falhar a tarefa com mensagem que não revele credenciais.

#### Scenario: MLflow sem resposta
- **WHEN** o MLflow não responde
- **THEN** a execução falha, as tabelas anteriores ficam intactas e o site continua mostrando a última exportação

### Requirement: Modelo ausente
Se um modelo ou horizonte não tiver versão no alias do ambiente, a exportação SHALL seguir com os demais, listar os ausentes no resultado da tarefa e marcar a execução com aviso.

#### Scenario: Chronos ainda sem versão em hml
- **WHEN** o alias de hml não existe para o Chronos
- **THEN** os outros modelos são exportados e o Chronos aparece como ausente
