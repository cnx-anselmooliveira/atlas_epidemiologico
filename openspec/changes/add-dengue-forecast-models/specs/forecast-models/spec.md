# Spec Delta

## Purpose

Disponibilizar seis modelos de previsão de incidência de dengue (baseline bayesiano, CatBoost, LSTM, SVR, Chronos e Ensemble), com contrato comum, comparáveis entre si e rastreados no MLflow.

## ADDED Requirements

### Requirement: Um módulo por modelo
Cada modelo SHALL ficar em sua própria pasta do pacote (`baseline_bayes`, `catboost`, `lstm`, `svr`, `chronos`, `ensemble`), com o mesmo contrato: treinar com o snapshot e a configuração, prever a incidência das janelas de validação e teste, e registrar a run.

#### Scenario: Treinar um modelo isolado
- **WHEN** `atlas-ml train forecast-catboost` é executado com um snapshot disponível
- **THEN** uma run do CatBoost é registrada sem depender dos outros modelos

### Requirement: Entrada multivariada
CatBoost, SVR, LSTM e Ensemble SHALL consumir todos os canais configurados em cada passo da janela, sem código específico por canal: a LSTM recebe os canais por passo, e CatBoost, SVR e o Ensemble recebem a janela achatada. O baseline bayesiano e o Chronos SHALL continuar univariados (incidência da UF), e essa exceção SHALL constar nos READMEs e nos parâmetros das runs.

#### Scenario: Canais na entrada
- **WHEN** CatBoost, SVR ou LSTM são treinados com a configuração padrão de features
- **THEN** a run registra a lista de canais e o número de entradas por passo
- **AND** os nomes das features do CatBoost incluem cada canal e a defasagem (ex.: `confirmed_cases_t-3`)

#### Scenario: Modelo univariado
- **WHEN** o Chronos ou o baseline bayesiano são treinados
- **THEN** a run registra que a entrada é só a incidência da UF

### Requirement: Capacidade registrada
Cada run SHALL registrar o número de entradas e, quando o modelo tiver parâmetros treináveis (LSTM, CatBoost, SVR), o número de parâmetros, para comparar a capacidade com a do projeto de referência.

#### Scenario: Parâmetros da LSTM
- **WHEN** a LSTM termina
- **THEN** a run tem `n_inputs_per_step` e `n_trainable_params`

### Requirement: Saídas na escala original
As previsões SHALL estar na escala de incidência por 100 mil habitantes, com qualquer escalonamento revertido e valores negativos fixados em zero.

#### Scenario: Previsão negativa
- **WHEN** um modelo produz um valor negativo para uma semana
- **THEN** a previsão registrada é 0

### Requirement: Métricas padronizadas por UF
Cada run SHALL registrar, para validação e teste:
- NRMSE (RMSE dividido pela amplitude observada na UF);
- MAE, RMSE e R²;
- a média dessas métricas entre UFs;
- um artefato com as métricas por UF.

#### Scenario: Métricas de teste
- **WHEN** um modelo termina
- **THEN** a run tem `test_nrmse_mean`, `test_mae_mean`, `test_rmse_mean`, `test_r2_mean` e o artefato `metrics_by_uf.csv`

### Requirement: Previsões registradas como artefato
Cada run SHALL registrar as previsões de validação e teste por UF e semana (observado, previsto e, quando o modelo fornecer, limites inferior e superior).

#### Scenario: Intervalos do baseline
- **WHEN** o baseline bayesiano termina
- **THEN** o artefato de previsões tem colunas `lower` e `upper` do intervalo de credibilidade de 95%

### Requirement: Baseline bayesiano hierárquico
O baseline SHALL ser um modelo bayesiano hierárquico de contagens (binomial negativa com offset de população), com efeitos aleatórios de UF e de ano e sazonalidade semanal, ajustado por amostragem MCMC. Ele SHALL registrar os diagnósticos de convergência (R-hat máximo e tamanho efetivo de amostra mínimo).

#### Scenario: Convergência
- **WHEN** o baseline termina
- **THEN** a run tem as métricas `rhat_max` e `ess_bulk_min`
- **AND** recebe a tag `atlas.converged=false` se `rhat_max` > 1,01

### Requirement: Chronos zero-shot
O Chronos SHALL ser usado como modelo pré-treinado, sem ajuste de pesos. Ele recebe o histórico de incidência de cada UF e prevê H semanas à frente. A identificação e a revisão do checkpoint usado SHALL ser registradas.

#### Scenario: Registro do checkpoint
- **WHEN** a run do Chronos termina
- **THEN** a run tem o parâmetro com o nome do checkpoint (ex.: `amazon/chronos-bolt-small`) e sua revisão

### Requirement: Ensemble com previsões out-of-fold
O Ensemble SHALL ser um meta-modelo Random Forest treinado sobre previsões **out-of-fold** de CatBoost, SVR e LSTM no período de treino, obtidas por validação temporal em blocos. Ele SHALL incluir as tendências locais por extrapolação polinomial (graus 0, 1 e 2) da janela. Previsões in-sample dos modelos-base SHALL NOT ser usadas para treinar o meta-modelo.

#### Scenario: Origem das features do meta-modelo
- **WHEN** o ensemble é treinado
- **THEN** cada linha de treino do meta-modelo usa previsões de modelos-base que não viram o alvo daquela linha

#### Scenario: Intervalo do ensemble
- **WHEN** o ensemble prevê o teste
- **THEN** registra `lower` e `upper` como os percentis 2,5 e 97,5 entre as árvores, em torno da previsão

### Requirement: Registro dos modelos
Cada modelo SHALL ser registrado no registro de modelos com nome próprio (`atlas-br-<modelo>`), com assinatura de entrada e saída, respeitando o contrato de tags `atlas.*` e o ciclo de aliases da plataforma.

#### Scenario: Registro no dev
- **WHEN** a DAG roda no ambiente dev
- **THEN** existem `atlas-br-baseline-bayes`, `atlas-br-catboost`, `atlas-br-lstm`, `atlas-br-svr`, `atlas-br-chronos` e `atlas-br-ensemble`, cada um com alias `@dev` na versão nova

### Requirement: Reprodutibilidade
Com o mesmo snapshot, configuração e semente, CatBoost, SVR, LSTM e Ensemble SHALL produzir as mesmas métricas de teste (tolerância de 1e-6 para os determinísticos e 2% para a LSTM em CPU).

#### Scenario: Reexecução
- **WHEN** o CatBoost é treinado duas vezes com o mesmo snapshot e semente
- **THEN** `test_nrmse_mean` é igual nas duas runs
