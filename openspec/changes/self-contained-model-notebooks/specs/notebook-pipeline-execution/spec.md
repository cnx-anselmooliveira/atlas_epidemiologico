# Spec Delta

## Purpose

Executar no Airflow os notebooks autocontidos dos modelos de previsão, na mesma forma de DAG de hoje, com a versão da gold e dos notebooks fixada pela execução e a comparação final como código da própria DAG.

## ADDED Requirements

### Requirement: Um notebook por tarefa de modelo
Cada tarefa de modelo da DAG `atlas_dengue_forecast_br` SHALL executar o notebook do respectivo modelo, com os parâmetros da tarefa (horizonte, janela, semente, `pipeline_run`, versão da gold esperada e, no ensemble, `base_runs`). A ordem, as dependências, o pool de treino, os tempos máximos, os quatro horizontes e as regras de disparo SHALL permanecer como na DAG atual.

#### Scenario: Mesma forma da DAG
- **WHEN** a DAG é carregada depois da mudança
- **THEN** as bases (`baseline_bayes`, `chronos`, `catboost`, `svr`, `lstm`) rodam em paralelo por horizonte e o `ensemble` só depois de `catboost`, `svr` e `lstm`
- **AND** as tarefas de modelo continuam no pool `atlas_treino`, com os mesmos tempos máximos

#### Scenario: Falha de um modelo
- **WHEN** o notebook de um modelo falha
- **THEN** a tarefa falha e as demais seguem as regras de disparo
- **AND** os outros modelos e horizontes não são interrompidos

### Requirement: Sem tarefa de snapshot
A DAG SHALL NOT ter tarefa de preparação de snapshot. Uma tarefa de início da execução SHALL registrar a versão atual da gold e a versão dos notebooks, e SHALL passá-las a todos os notebooks da execução.

#### Scenario: Início da execução
- **WHEN** a DAG começa
- **THEN** a tarefa de início registra a versão da gold e a dos notebooks
- **AND** cada notebook de modelo recebe a versão da gold como `data_version_esperada`

#### Scenario: Gold alterada durante a execução
- **WHEN** a gold é reconstruída enquanto os modelos treinam
- **THEN** os notebooks que começarem depois da mudança falham indicando as duas versões, sem criar run

### Requirement: Notebook trocado no meio da execução
Se a versão dos notebooks mudar depois do início da execução (um merge no clone), as tarefas seguintes SHALL falhar com mensagem clara, sem executar um notebook de versão diferente da de partida.

#### Scenario: Merge durante o treino
- **WHEN** um merge muda o notebook do `lstm` enquanto o `catboost` treina
- **THEN** a tarefa do `lstm` falha informando as versões de início e atual
- **AND** a DAG pode ser disparada de novo depois do merge

### Requirement: Comparação como código da DAG
A comparação final SHALL ser uma tarefa Python da DAG, sem notebook, que junta as runs de uma execução e de um horizonte, registra a run `compare` com a tabela das métricas de teste e o melhor modelo, e lista os modelos ausentes. Ela SHALL rodar mesmo quando modelos falharem.

#### Scenario: Modelo ausente
- **WHEN** o Chronos falhou e os demais terminaram
- **THEN** a run `compare` lista os cinco modelos com métricas e registra o Chronos como ausente

### Requirement: Notebooks lidos da pasta configurada
O notebook de cada modelo SHALL ser lido de `<pasta de notebooks>/<modelo>/<modelo>.ipynb`, em que a pasta é a configurada no ambiente (o clone do `git-sync` em hml e prod, a pasta montada em dev, a cópia da imagem como reserva).

#### Scenario: Notebook ausente
- **WHEN** o notebook de um modelo não existe na pasta configurada
- **THEN** a tarefa falha com mensagem que indica o caminho esperado

### Requirement: Resultado, notebook executado e limpeza
Cada execução de notebook SHALL gravar o arquivo de resultado do passo (identificador da run e métricas principais) no diretório da execução, e a tarefa SHALL tratar a ausência dele como falha. O notebook executado, com as saídas, SHALL ser anexado à run, e o diretório da execução SHALL ser removido no fim, com sucesso ou falha.

#### Scenario: Notebook sem resultado
- **WHEN** o notebook termina sem gravar o arquivo de resultado
- **THEN** a tarefa falha indicando o arquivo esperado

#### Scenario: Notebook executado na run
- **WHEN** uma tarefa de modelo termina
- **THEN** a run do modelo tem o notebook executado como artefato
