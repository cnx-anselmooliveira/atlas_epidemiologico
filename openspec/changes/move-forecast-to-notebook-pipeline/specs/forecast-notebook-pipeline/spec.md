# Spec Delta

## Purpose

Executar o pipeline de previsão de dengue por um notebook parametrizado, chamado pelo Airflow, de modo que cada passo seja revisável em PR, rastreável no MLflow e sem um CLI paralelo que repita a orquestração.

## ADDED Requirements

### Requirement: Pipeline definido por notebook
O pipeline de previsão (preparar o snapshot, treinar um modelo num horizonte e comparar os modelos de um horizonte) SHALL ser definido por notebook em `ml/notebooks/`, versionado no repositório. O notebook SHALL receber seus parâmetros por uma célula marcada como parâmetros e SHALL chamar o pacote `atlas_ml` para o trabalho de dados, janelas, modelos e avaliação.

#### Scenario: Parâmetros do passo
- **WHEN** o notebook é executado com o passo `train`, o modelo `catboost`, o horizonte 2 e a semente 7
- **THEN** a run registrada no MLflow tem o horizonte 2 e a semente 7 nos parâmetros
- **AND** o modelo treinado é o CatBoost

#### Scenario: Passo desconhecido
- **WHEN** o notebook recebe um passo ou um modelo que não existe
- **THEN** a execução falha com mensagem que lista os valores aceitos
- **AND** nenhuma run é criada

### Requirement: Execução pelo Airflow com os mesmos resultados
As tarefas da DAG `atlas_dengue_forecast_br` SHALL executar o notebook com os parâmetros da tarefa. A ordem das tarefas, o pool de treino, os quatro horizontes, a tag `atlas.pipeline_run` e o registro dos modelos SHALL permanecer como na DAG atual.

#### Scenario: Mesma forma da DAG
- **WHEN** a DAG é carregada depois da mudança
- **THEN** tem as mesmas tarefas, dependências, pools e regras de disparo de antes
- **AND** só mudam o que cada tarefa executa

#### Scenario: Falha de um modelo
- **WHEN** a execução do notebook de um modelo falha
- **THEN** a tarefa correspondente falha e as dependências seguem as regras de disparo da DAG
- **AND** os demais modelos e horizontes não são interrompidos

### Requirement: Resultado do passo devolvido à DAG
Cada execução do notebook SHALL gravar um arquivo de resultado com o identificador da run criada e as métricas principais, que a tarefa SHALL ler para passá-los adiante. Uma execução que termina sem gravar esse arquivo SHALL ser tratada como falha.

#### Scenario: Passagem do identificador da run
- **WHEN** o passo de preparação termina
- **THEN** o arquivo de resultado traz o identificador da run `dataset`
- **AND** as tarefas de treino usam esse identificador como snapshot

#### Scenario: Notebook sem resultado
- **WHEN** o notebook chega ao fim sem gravar o arquivo de resultado
- **THEN** a tarefa falha com mensagem que indica o arquivo esperado

### Requirement: Arquivos de uma execução em diretório próprio
Os arquivos que o notebook entrega a tarefas seguintes (tabelas e parâmetros extensos) SHALL ficar num diretório próprio de cada execução da DAG, de modo que execuções simultâneas ou repetidas não se misturem. O diretório SHALL ser removido ao fim da execução, com sucesso ou falha, e o local-base SHALL ser configurável.

#### Scenario: Duas execuções seguidas
- **WHEN** a DAG é executada duas vezes
- **THEN** cada execução lê só os arquivos do próprio diretório

#### Scenario: Limpeza ao final
- **WHEN** a execução da DAG termina, com sucesso ou com falha
- **THEN** o diretório dos arquivos daquela execução não existe mais

### Requirement: Ingestão do arquivo por tarefa própria
Quando o notebook entregar uma tabela, uma tarefa seguinte do Airflow SHALL lê-la e gravá-la no MLflow ou no BigQuery, conforme o destino. A ingestão SHALL ser idempotente: repetir a tarefa para a mesma execução não duplica linhas nem versões.

#### Scenario: Reexecução da ingestão
- **WHEN** a tarefa de ingestão é repetida para a mesma execução
- **THEN** o destino contém as mesmas linhas de antes, sem duplicatas

#### Scenario: Arquivo ausente
- **WHEN** a tarefa de ingestão não encontra o arquivo esperado
- **THEN** ela falha sem gravar nada no destino

### Requirement: Notebook executado como artefato
O notebook de cada execução, com as saídas das células, SHALL ser guardado como artefato da run correspondente no MLflow, para auditar o que rodou com quais parâmetros.

#### Scenario: Auditoria de uma run
- **WHEN** se abre a run de um modelo treinado pela DAG
- **THEN** ela tem o notebook executado como artefato
- **AND** os parâmetros do passo aparecem na célula de parâmetros injetados

### Requirement: Código executado rastreável
Cada run SHALL registrar a versão do código do `atlas_ml` que treinou e a versão do notebook que a orquestrou, de modo que se saiba qual código gerou o modelo mesmo quando o notebook e o pacote mudam em momentos diferentes.

#### Scenario: Versões nas tags
- **WHEN** uma run termina
- **THEN** ela tem as tags `atlas.git_sha` (pacote) e `atlas.notebook_sha` (notebook)

#### Scenario: Notebook incompatível com o pacote
- **WHEN** o notebook exige uma versão do contrato do pacote maior do que a instalada
- **THEN** a execução falha antes de criar qualquer run, indicando que a imagem precisa ser atualizada

### Requirement: Experimento do MLflow configurável
O experimento em que as runs do pipeline são gravadas SHALL poder ser trocado por variável de ambiente, mantendo o experimento oficial como padrão. A leitura das runs (comparação e exportação) SHALL usar o mesmo experimento configurado.

#### Scenario: Padrão
- **WHEN** a variável não está definida
- **THEN** as runs vão para o experimento oficial `atlas/dengue-forecast-br`

#### Scenario: Experimento de exploração
- **WHEN** a variável aponta para um experimento sandbox
- **THEN** as runs do notebook vão para esse experimento
- **AND** o experimento oficial não recebe nenhuma run

### Requirement: Sem CLI de previsão
O pacote `atlas_ml` SHALL NOT oferecer comandos de previsão (`atlas-ml forecast …`) nem um módulo de orquestração paralelo ao notebook. Os demais comandos do CLI (`train example`, `promote` e afins) SHALL permanecer.

#### Scenario: Comando removido
- **WHEN** alguém executa `atlas-ml forecast prepare`
- **THEN** o CLI informa que o comando não existe
- **AND** `atlas-ml promote` continua funcionando

### Requirement: Notebook testado no CI
O notebook SHALL ser executado nos testes sobre um painel sintético, com MLflow temporário e sem acesso ao BigQuery, cobrindo ao menos o passo de preparação, o de treino de um modelo leve e o de comparação.

#### Scenario: Teste do notebook
- **WHEN** a suíte de testes roda
- **THEN** o notebook executa os três passos sobre o painel sintético
- **AND** o teste falha se alguma célula levantar erro
