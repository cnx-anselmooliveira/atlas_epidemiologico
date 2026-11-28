# Spec Delta

## MODIFIED Requirements

### Requirement: Um notebook por tarefa de modelo
Cada tarefa de treino de uma DAG de modelo (`atlas_forecast_<modelo>`) SHALL executar o notebook do respectivo modelo, com os parâmetros da tarefa (horizonte, janela, semente, `pipeline_run`, versão da gold esperada e, no ensemble, `base_runs`). O pool de treino, os tempos máximos, os quatro horizontes e a regra de o ensemble usar CatBoost, SVR e LSTM SHALL permanecer como na DAG única que esta forma substitui.

#### Scenario: Mesma forma da DAG
- **WHEN** o orquestrador roda depois da mudança
- **THEN** as bases (`baseline_bayes`, `chronos`, `catboost`, `svr`, `lstm`) rodam nas suas DAGs em paralelo e o `ensemble` só depois que as cinco terminam
- **AND** as tarefas de treino continuam no pool `atlas_treino`, com os mesmos tempos máximos

#### Scenario: Falha de um modelo
- **WHEN** o notebook de um modelo falha
- **THEN** a tarefa e a DAG daquele modelo falham
- **AND** os outros modelos e horizontes não são interrompidos

### Requirement: Sem tarefa de snapshot
Nenhuma DAG de previsão SHALL ter tarefa de preparação de snapshot. Uma tarefa de início SHALL registrar a versão atual da gold e a dos notebooks e passá-las a todos os notebooks da execução. No processo completo essa tarefa é do orquestrador; numa DAG de modelo disparada sozinha, da própria DAG.

#### Scenario: Início da execução
- **WHEN** o orquestrador começa
- **THEN** a tarefa de início registra a versão da gold e a dos notebooks
- **AND** cada notebook de modelo, em todas as DAGs disparadas, recebe a versão da gold como `data_version_esperada`

#### Scenario: Gold alterada durante a execução
- **WHEN** a gold é reconstruída enquanto os modelos treinam
- **THEN** os notebooks que começarem depois da mudança falham indicando as duas versões, sem criar run

### Requirement: Comparação como código da DAG
A comparação final SHALL ser uma tarefa Python do orquestrador `atlas_dengue_forecast_br`, sem notebook, que junta as runs de uma execução e de um horizonte, registra a run `compare` com a tabela das métricas de teste e o melhor modelo, e lista os modelos ausentes. Ela SHALL rodar mesmo quando modelos ou DAGs de modelo falharem.

#### Scenario: Modelo ausente
- **WHEN** a DAG do Chronos falhou e as demais terminaram
- **THEN** a run `compare` lista os cinco modelos com métricas e registra o Chronos como ausente

### Requirement: Resultado, notebook executado e limpeza
Cada execução de notebook SHALL gravar o arquivo de resultado do passo (identificador da run e métricas principais) no diretório da execução da DAG de modelo, e a tarefa SHALL tratar a ausência dele como falha. O notebook executado, com as saídas, SHALL ser anexado à run. Cada DAG de modelo SHALL remover o seu diretório no fim, com sucesso ou falha.

#### Scenario: Notebook sem resultado
- **WHEN** o notebook termina sem gravar o arquivo de resultado
- **THEN** a tarefa falha indicando o arquivo esperado

#### Scenario: Notebook executado na run
- **WHEN** uma tarefa de treino termina
- **THEN** a run do modelo tem o notebook executado como artefato

#### Scenario: Limpeza por modelo
- **WHEN** a DAG do SVR termina, com sucesso ou falha
- **THEN** o diretório da execução do SVR não existe mais, e os das outras DAGs de modelo em andamento continuam
