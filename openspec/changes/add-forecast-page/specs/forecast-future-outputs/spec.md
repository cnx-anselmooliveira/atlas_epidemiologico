# Spec Delta

## Purpose

Fazer cada modelo de previsão registrar, nas runs do MLflow, a previsão das próximas semanas, as métricas por horizonte e as figuras que explicam o modelo, para que possam ser exibidas no site.

## ADDED Requirements

### Requirement: Horizontes de 1 a 4 semanas
Cada modelo SHALL poder ser treinado e avaliado para os horizontes de 1, 2, 3 e 4 semanas, cada um como um ajuste próprio (estratégia direta), e cada run SHALL registrar o horizonte. A versão registrada de cada horizonte SHALL ter nome próprio, `atlas-br-<modelo>-h<horizonte>`, com o alias do ambiente apontando para a versão vigente.

#### Scenario: Horizonte 3
- **WHEN** o CatBoost é treinado com `horizon=3`
- **THEN** a run registra `horizon=3`, o alvo é a incidência três semanas após a origem da janela e a versão vai para `atlas-br-catboost-h3`

#### Scenario: Ensemble por horizonte
- **WHEN** o Ensemble é treinado para um horizonte
- **THEN** ele usa só as runs dos modelos-base do mesmo horizonte e do mesmo snapshot, e recusa treinar se faltar alguma

### Requirement: Previsão do futuro por UF
Cada run de modelo SHALL registrar a previsão da incidência por 100 mil habitantes para a semana alvo seguinte à última semana madura do snapshot, em cada UF, no artefato `future_predictions.parquet`. Cada linha SHALL ter `uf`, `origin_date`, `target_date`, `horizon`, `y_pred`, `lower` e `upper` (nulos quando o modelo não produz intervalo). A previsão SHALL estar na escala de incidência, sem valores negativos, e SHALL usar apenas dados anteriores à data de origem.

#### Scenario: Quatro semanas à frente
- **WHEN** os quatro horizontes de um modelo terminam sobre o mesmo snapshot
- **THEN** as quatro runs juntas cobrem as quatro semanas seguintes à última semana madura, para as 27 UFs

#### Scenario: Previsão negativa
- **WHEN** um modelo produz um valor negativo para uma semana futura
- **THEN** o valor registrado é 0

### Requirement: Métricas por horizonte
As métricas de validação e teste (NRMSE, MAE, RMSE, R² e cobertura do intervalo) SHALL ser registradas por run, portanto por horizonte, e as métricas por UF SHALL ser registradas no artefato `metrics_by_uf.csv` com a coluna do horizonte.

#### Scenario: Comparar horizontes
- **WHEN** se consultam as métricas de teste do mesmo modelo nos horizontes 1 e 4
- **THEN** cada horizonte tem seus próprios valores, calculados só sobre as previsões daquele horizonte

### Requirement: Figuras por modelo
Cada run de modelo SHALL registrar figuras PNG na pasta `figures/` do artefato, com título e legenda em português, sem dados pessoais e com tamanho de até 500 KB cada:
- `forecast_vs_observed.png`: previsto × observado no teste, no Brasil;
- `error_by_uf.png`: erro por UF;
- uma figura da família do modelo: importância das variáveis (CatBoost e Ensemble), curva de aprendizado (LSTM), erro por semana (SVR), distribuição posterior dos parâmetros (Bayesiano) ou cobertura do intervalo (Chronos).

#### Scenario: Figuras de um modelo
- **WHEN** a run do LSTM termina
- **THEN** `figures/` tem as duas figuras comuns e a curva de aprendizado

#### Scenario: Figura que falha
- **WHEN** a geração de uma figura levanta erro
- **THEN** a run continua e termina com sucesso, registra a tag `atlas.figures_failed` com o nome da figura e não grava a figura quebrada
