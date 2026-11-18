# Spec Delta

## Purpose

Rodar todo dia, sem intervenção, o caminho do SINAN até as previsões do site, fazendo o trabalho pesado só quando os dados mudarem.

## ADDED Requirements

### Requirement: Orquestradora diária
A DAG `etl_brasil` SHALL ser agendada todos os dias às 03h00 no fuso `America/Sao_Paulo`, sem catchup e com uma execução por vez, e SHALL disparar em sequência `ingestao_sinan_brasil`, `dbt_brasil` e `atlas_dengue_forecast_br`, esperando cada uma terminar antes da próxima. Em `dev` a DAG SHALL existir sem agendamento.

#### Scenario: Execução diária em hml
- **WHEN** chega 03h00 de Brasília em hml
- **THEN** a `etl_brasil` inicia e dispara a ingestão; a etapa seguinte só começa quando a anterior termina

#### Scenario: Ambiente de desenvolvimento
- **WHEN** o Airflow roda com `ATLAS_ENV=dev`
- **THEN** a `etl_brasil` não tem agendamento e só roda quando disparada à mão

### Requirement: Ingestão do SINAN em DAG própria
A DAG `ingestao_sinan_brasil` SHALL comparar os arquivos anuais do OpenDataSUS com o landing do bucket, sincronizar o landing (baixar o que mudou, apagar o que sumiu) e carregar e validar na bronze cada ano alterado, como faz hoje o grupo `sinan`. Disparada pela orquestradora, a espera do sensor SHALL ter janela limitada; sem diferença na janela, a DAG SHALL terminar com sucesso informando que não há dados novos.

#### Scenario: Sem dados novos
- **WHEN** nenhum arquivo do OpenDataSUS mudou em relação ao landing durante a janela
- **THEN** a ingestão termina sem baixar nem carregar nada e a orquestradora registra "sem dados novos"

#### Scenario: Ano alterado
- **WHEN** o arquivo de um ano mudou na origem
- **THEN** o landing recebe a versão nova, a partição do ano na bronze é substituída e validada

### Requirement: dbt só com dados novos
A DAG `dbt_brasil` SHALL rodar a modelagem (seed, bronze, silver, gold, com os testes) somente quando a bronze do SINAN tiver mudado depois da última gold, ou quando disparada com `forcar_dbt`. Caso contrário SHALL terminar sem rodar o dbt.

#### Scenario: Bronze inalterada
- **WHEN** a ingestão não carregou nem removeu ano algum
- **THEN** o dbt não roda e a gold não muda

#### Scenario: Modelagem forçada
- **WHEN** alguém dispara `dbt_brasil` à mão com `forcar_dbt=true`
- **THEN** o dbt roda mesmo sem dados novos

### Requirement: Treino só quando a gold mudar
A orquestradora SHALL disparar o treino somente quando a versão atual da gold (`gold_dengue_casos_provaveis_uf_semanal`) for diferente da `data_version` dos modelos vigentes no MLflow do ambiente, ou quando disparada com `forcar_treino`. O treino SHALL usar a base inteira (todas as UFs e todo o período, sem tabela avulsa) e SHALL disparar a exportação para o BigQuery ao terminar.

#### Scenario: Gold igual à do último treino
- **WHEN** a gold não mudou desde o treino dos modelos vigentes
- **THEN** o treino não roda e as previsões do site continuam as mesmas

#### Scenario: Gold nova
- **WHEN** o dbt atualizou a gold
- **THEN** os seis modelos são treinados com a base inteira, para os horizontes 1 a 4, e a exportação atualiza o BigQuery

### Requirement: Falha interrompe a sequência
Se uma etapa falhar, a orquestradora SHALL não disparar as seguintes e SHALL terminar com falha visível. Uma falha no treino SHALL manter os modelos e as previsões vigentes. Cada DAG SHALL poder ser reexecutada isoladamente, e a reexecução SHALL ser idempotente.

#### Scenario: dbt falhou
- **WHEN** um teste do dbt falha
- **THEN** o treino não é disparado, a `etl_brasil` fica com falha e o site continua com a gold e as previsões anteriores

### Requirement: Recursos do treino na VPS
O treino SHALL respeitar limites que caibam na VPS de hml (4 CPUs, 8 GB de RAM, compartilhada com outros stacks): pool do Airflow para as tarefas de treino, threads por tarefa (`ATLAS_THREADS`), tarefas simultâneas limitadas, tempo máximo por tarefa e limites de CPU e memória nos serviços do Airflow do stack.

#### Scenario: Treino na VPS
- **WHEN** o treino completo roda na VPS
- **THEN** nenhum serviço do stack é morto por falta de memória e o site e a API continuam respondendo durante o treino

### Requirement: Uma só origem de agendamento
Nenhuma outra DAG do fluxo SHALL ter agendamento próprio: a `process_etl_atlas` SHALL ser removida e `ingestao_sinan_brasil`, `dbt_brasil` e `atlas_dengue_forecast_br` SHALL rodar só disparadas pela orquestradora ou à mão.

#### Scenario: Nada roda duas vezes
- **WHEN** o dia vira
- **THEN** só a `etl_brasil` inicia sozinha
