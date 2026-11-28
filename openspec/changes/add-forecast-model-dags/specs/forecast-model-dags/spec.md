# Spec Delta

## Purpose

Treinar cada modelo de previsão de dengue numa DAG própria, que pode rodar sozinha ou ser disparada pelo orquestrador `atlas_dengue_forecast_br`, responsável pelo processo completo (treino de todos os modelos, comparação e exportação).

## ADDED Requirements

### Requirement: Uma DAG por modelo
O Airflow SHALL ter uma DAG por modelo de previsão: `atlas_forecast_baseline_bayes`, `atlas_forecast_chronos`, `atlas_forecast_catboost`, `atlas_forecast_svr`, `atlas_forecast_lstm` e `atlas_forecast_ensemble`. Cada uma SHALL treinar o seu modelo em cada horizonte pedido, executando o notebook do modelo, e registrar a run e o modelo no MLflow.

#### Scenario: Seis DAGs carregadas
- **WHEN** as DAGs são carregadas
- **THEN** existem as seis DAGs de modelo, sem agendamento, cada uma com uma tarefa de treino por horizonte

#### Scenario: Um horizonte falha
- **WHEN** o treino do horizonte 3 do LSTM falha
- **THEN** os horizontes 1, 2 e 4 do LSTM continuam e a run da DAG termina com falha

### Requirement: Parâmetros das DAGs de modelo
Cada DAG de modelo SHALL aceitar `horizons` (1 a 4, padrão todos), `window` (padrão 12), `seed` (padrão 42) e `fonte` (padrão a gold do ambiente). Também SHALL aceitar, opcionais, `pipeline_run`, a versão da gold esperada e a versão dos notebooks. Sem esses três, a DAG SHALL usar o próprio `run_id` como `pipeline_run` e registrar as versões atuais no início.

#### Scenario: Disparo sem configuração
- **WHEN** a DAG do CatBoost é disparada sem `conf`
- **THEN** ela treina os horizontes 1 a 4 com janela 12 e semente 42 na gold do ambiente, e as runs levam `atlas.pipeline_run` igual ao `run_id` da DAG

#### Scenario: Horizonte inválido
- **WHEN** a DAG é disparada com `horizons=[5]`
- **THEN** ela falha antes de treinar, dizendo que os horizontes vão de 1 a 4

### Requirement: DAG de modelo sozinha não compara nem exporta
Disparada fora do orquestrador, uma DAG de modelo SHALL só treinar e registrar. Ela SHALL NOT criar a run `compare` nem disparar a exportação.

#### Scenario: SVR sozinho
- **WHEN** a DAG do SVR termina com sucesso sem ter sido disparada pelo orquestrador
- **THEN** há runs e versões novas do SVR no MLflow, e nenhuma run `compare` nem execução da `process_forecast_export_atlas` foi criada por ela

### Requirement: Runs de base do ensemble
A DAG do ensemble SHALL buscar no MLflow, para cada horizonte, as runs concluídas de CatBoost, SVR e LSTM: as do mesmo `pipeline_run`, quando ele é informado; senão, as mais recentes com a mesma versão da gold. Um horizonte sem alguma das três runs SHALL falhar indicando o modelo que falta.

#### Scenario: Ensemble pelo orquestrador
- **WHEN** o orquestrador dispara o ensemble com o seu `pipeline_run`
- **THEN** o ensemble de cada horizonte usa as runs de CatBoost, SVR e LSTM daquele `pipeline_run` e daquele horizonte

#### Scenario: Ensemble sozinho
- **WHEN** a DAG do ensemble é disparada sem `pipeline_run`
- **THEN** ela usa as runs concluídas mais recentes de CatBoost, SVR e LSTM com a versão atual da gold

#### Scenario: Base ausente
- **WHEN** não há run concluída do LSTM no horizonte 2 com a versão da gold
- **THEN** o horizonte 2 do ensemble falha dizendo que falta o LSTM, e os outros horizontes seguem

### Requirement: Recursos dos treinos
As tarefas de treino de todas as DAGs de modelo SHALL usar o pool `atlas_treino`, ocupando as duas vagas nos modelos pesados (LSTM, bayesiano e Chronos) e uma nos demais, com o mesmo tempo máximo por treino de hoje. Cada DAG de modelo SHALL ter no máximo uma execução ativa.

#### Scenario: Dois modelos pesados ao mesmo tempo
- **WHEN** as DAGs do LSTM e do Chronos estão com treinos prontos para rodar
- **THEN** só um treino pesado ocupa o pool por vez

### Requirement: DAGs de modelo prontas para disparo
As DAGs de modelo SHALL ser criadas despausadas, para que o orquestrador consiga dispará-las logo depois do primeiro deploy.

#### Scenario: Primeiro deploy em hml
- **WHEN** as DAGs de modelo aparecem pela primeira vez no Airflow de hml
- **THEN** elas estão despausadas e um disparo do orquestrador começa a treinar sem passo manual

### Requirement: Orquestração do processo completo
A `atlas_dengue_forecast_br` SHALL fixar as versões da gold e dos notebooks e disparar cada DAG de base individualmente com o seu `pipeline_run`, os parâmetros e essas versões. Depois que as cinco terminarem, com sucesso ou falha, SHALL disparar a do ensemble e, ao fim dela, comparar os modelos de cada horizonte e disparar a exportação. O `dag_id`, os parâmetros e o disparo pela `etl_brasil` SHALL continuar os mesmos.

#### Scenario: Execução completa
- **WHEN** a `etl_brasil` dispara a `atlas_dengue_forecast_br`
- **THEN** são criadas seis execuções de DAG de modelo com o mesmo `pipeline_run`, uma run `compare` por horizonte e uma execução da `process_forecast_export_atlas`

#### Scenario: Um modelo falha
- **WHEN** a DAG do Chronos falha e as demais terminam
- **THEN** o ensemble roda, a `compare` de cada horizonte registra o Chronos como ausente e a exportação é disparada

#### Scenario: Nenhum modelo conclui
- **WHEN** todas as DAGs de modelo falham
- **THEN** a exportação não é disparada e a execução do orquestrador termina com falha

### Requirement: Espera sem ocupar worker
O orquestrador SHALL acompanhar as DAGs de modelo sem ocupar vaga de execução de tarefa enquanto espera, e cada execução disparada SHALL ter um identificador que leva o da execução do orquestrador e o nome do modelo.

#### Scenario: Acompanhamento das execuções
- **WHEN** o orquestrador está esperando as DAGs de base
- **THEN** as vagas de execução ficam livres para os treinos, e cada execução de modelo tem um `run_id` que identifica a execução do orquestrador e o modelo
