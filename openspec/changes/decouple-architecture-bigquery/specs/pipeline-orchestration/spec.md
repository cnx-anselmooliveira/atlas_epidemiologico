# Spec Delta

## Purpose

Encadear e agendar ingestão, modelagem dbt, modelo de AI e atualização do cache da API com o Airflow, substituindo a execução manual dessas etapas depois que elas estiverem estáveis.

## ADDED Requirements

### Requirement: Ordem das etapas
O pipeline SHALL executar, nesta ordem, ingestão das fontes, build da modelagem, etapa do modelo de AI e invalidação do cache da API, e uma etapa só SHALL iniciar após o sucesso das etapas das quais depende.

#### Scenario: Ingestão falha
- **WHEN** a ingestão de alguma fonte falha numa execução
- **THEN** o build da modelagem não é iniciado nessa execução
- **AND** a execução é marcada como falha

### Requirement: Ingestão por fonte em paralelo
Cada fonte SHALL ser uma tarefa separada, permitindo reexecutar somente a fonte que falhou.

#### Scenario: Reprocessar uma fonte
- **WHEN** a tarefa da fonte `colombia` falha e é reexecutada com sucesso
- **THEN** as demais fontes não são recarregadas e o pipeline continua para a modelagem

### Requirement: Agendamento configurável
Cada pipeline SHALL ter agendamento configurável e também poder ser disparado manualmente; execuções sobrepostas do mesmo pipeline SHALL NOT ocorrer.

#### Scenario: Disparo manual durante execução
- **WHEN** um disparo manual ocorre enquanto uma execução do mesmo pipeline está em andamento
- **THEN** a nova execução só começa após o término da anterior

### Requirement: Mesmos artefatos da execução manual
As tarefas SHALL executar os mesmos comandos e imagens usados na execução manual de ingestão e modelagem, sem lógica de negócio duplicada nas DAGs.

#### Scenario: Comparação manual vs orquestrado
- **WHEN** a ingestão da fonte `peru` roda pelo Airflow
- **THEN** o resultado no BigQuery é o mesmo que o da execução manual do mesmo comando

### Requirement: Etapa do modelo de AI como contrato
A etapa do modelo de AI SHALL ser uma tarefa que executa um comando/imagem configurável, lendo da gold e escrevendo resultados no BigQuery; enquanto não configurada, SHALL ser pulada sem falhar o pipeline.

#### Scenario: Modelo ainda não configurado
- **WHEN** o pipeline roda sem comando do modelo de AI configurado
- **THEN** a tarefa do modelo é marcada como pulada e a invalidação do cache executa normalmente

### Requirement: Retentativas e alerta de falha
Tarefas SHALL ter retentativas configuráveis e uma falha definitiva SHALL ficar visível na interface do Airflow com os logs da tarefa.

#### Scenario: Erro transitório do BigQuery
- **WHEN** uma tarefa falha por erro transitório e a retentativa seguinte tem sucesso
- **THEN** a execução do pipeline termina com sucesso
