# ESA-UNICEF Dengue Forecast Project — modelos e técnicas

> **Origem:** pasta local `drive/ONU/fontes/3 - ESA-UNICEF_DengueForecastProject`, uma cópia do repositório ESA-PhiLab.
> **Método:** leitura estática dos `.ipynb` (JSON, código e saídas gravadas) e dos `.py` de apoio. Nada foi executado.
> O que não aparece explicitamente no código ou nas saídas está marcado como **(inferido)**.

## 1. O projeto

O repositório acompanha dois artigos:
- **Schneider et al. (2021)**, *Climate-based ensemble machine learning model to forecast Dengue epidemics*, ICML 2021 (workshop). Estudo sobre o Peru.
- **Sebastianelli et al. (2024)**, *A reproducible ensemble machine learning approach to forecast dengue outbreaks*, Nature Scientific Reports. Estudo sobre o Brasil, com transferência para o Peru.

**Objetivo:** prever a **taxa de incidência de dengue** (DIR, casos por 100 mil habitantes) **com 1 mês de antecedência, por UF**. São 27 UFs, para a população total e para a de 0 a 19 anos.

**Modelo:** um **ensemble por stacking**. CatBoost, SVR e LSTM geram previsões, e um **Random Forest** atua como meta-modelo. O ensemble é comparado a um baseline estatístico bayesiano.

**Covariáveis:**
- clima: reanálise ERA5;
- satélite: NDVI, elevação, cobertura florestal e urbana;
- socioeconômicas: IVS, IDHM etc.

## 2. Resumo

| Notebook / script | Modelo(s) | Alvo | Métrica |
|---|---|---|---|
| `code/modelling-Brazil.ipynb` | `catboost.CatBoostRegressor` (MultiRMSE); `sklearn.svm.SVR` em `MultiOutputRegressor` + `RandomizedSearchCV`; LSTM empilhada em `tf.keras` (`LSTM(60)`→`LSTM(20)`→`Dense(2)`); meta-modelo `sklearn.ensemble.RandomForestRegressor`. Usa ainda saídas pré-computadas de uma CNN ConvLSTM2D como features e um baseline bayesiano externo (provavelmente INLA, **inferido**) para comparação | DIR do mês t+1 por UF, com 2 saídas: `DengRate_all` e `DengRate_019`, normalizadas por MinMax | NRMSE = RMSE/(máx−mín) e R², por UF, em treino e validação |
| `code/baseline_preprocess.ipynb` / `.py` | Nenhum: só carrega as previsões do baseline | `pred.mean/lci/uci` → taxa por 100 mil | — |
| `main.ipynb` (raiz) | Arquivo vazio (0 bytes) | — | — |
| `code/models.py` (biblioteca) | `CNN` (ConvLSTM2D), `Ensamble` (rede densa), `CatBoostEnsableNet`, `RandomForestEnsableNet`, `LSTMNet`, `CatBoostNet`, `SVMNet` | — | — |

## 3. `code/modelling-Brazil.ipynb` — pipeline completo

**Estado do notebook:**
- 102 células, kernel Python 3.8.
- Foi executado com `TRAINING = False`: as células **carregam modelos já salvos** em `code/saved_models/Brazil/` e só fazem inferência e avaliação.
- O treino aconteceu antes, em outra sessão. O CatBoost rodou 27.000 iterações em cerca de 3.852 s.

### Modelos e hiperparâmetros

| Modelo | Implementação | Hiperparâmetros |
|---|---|---|
| **CatBoost** | `CatBoostRegressor` + `Pool` | `iterations=27000`, `learning_rate=0.001`, `loss_function/eval_metric='MultiRMSE'`, `max_depth=6`, `random_seed=42`, `early_stopping_rounds=300`, `eval_set` = validação. MultiRMSE final: learn 0,0127, test 0,0305 |
| **SVM** | `MultiOutputRegressor(SVR(max_iter=20000))` em `RandomizedSearchCV` | `kernel` ∈ {poly, sigmoid, rbf}; `C` ∈ {0.01, 0.1, 1, 10}; `gamma` ∈ {0.01, 0.1, 1}; `epsilon` ∈ {0.01, 0.1, 1}; `n_iter=5`, `cv=5`, `refit=True` |
| **LSTM** | `tf.keras.Sequential` | `LSTM(60, return_sequences=True, dropout=0.5)` → `LSTM(20, dropout=0.5)` → `Dense(2)`; loss `mae`, `epochs=200`, `batch_size=16`, `EarlyStopping(patience=12)`. **Bug:** o otimizador cai sempre no `adam` padrão; o lr e o `rmsprop` do config são ignorados |
| **Ensemble (meta)** | `RandomForestRegressor` | `n_estimators=100`; o `max_depth` está comentado, então as árvores não têm limite de profundidade |
| Definidos e não usados | `Ensamble` (rede densa), `CatBoostEnsableNet`, `CNN` (ConvLSTM2D) | A CNN tem um bug: a 2ª camada recebe a entrada em vez da saída da 1ª. Só as saídas pré-computadas dela são usadas |
| **Baseline** | Externo, fora do repositório; só os CSVs existem | As colunas `state_index`, `year_index` e `pred.lci/uci` sugerem um modelo bayesiano hierárquico com efeitos de UF e ano, provavelmente INLA (**inferido**) |

### Passo a passo

1. **Dados.**
   - Fonte: `dataset/Brazil_UF_dengue_monthly.csv`, com 27 UFs × 228 meses (2001 a 2019) e 62 colunas.
   - Clima ERA5: temperaturas, ponto de orvalho, precipitação, pressão, umidade e vento.
   - Satélite e geografia: NDVI, elevação (5 estatísticas), cobertura florestal e urbana.
   - População, casos de dengue e cerca de 30 indicadores socioeconômicos.
   - Junta-se `cnn_dataframe.csv`, com as saídas de uma CNN externa.
2. **Limpeza.** Cria `rate_total = casos/pop·1e5` e `rate_019` e descarta as colunas de população e de casos usadas no cálculo. Não há valores nulos.
3. **Agrupamento de variáveis.**
   - CLIMATIC: 4 variáveis.
   - GEO: 8 variáveis.
   - SOCIO: 30 variáveis.
   - AUXILIAR: mês e casos por faixa etária.
   - EXCLUDED: 12 variáveis que não passam pela redução, entre elas precipitação, umidade e as saídas da CNN.
4. **Normalização do alvo.** `MinMaxScaler` nas duas DIR. O mesmo scaler desfaz a escala das previsões.
5. **Redução supervisionada por grupo.** `MinMaxScaler` → `PLSRegression` ajustada contra o alvo → `MinMaxScaler`. São 4 componentes de clima, 6 de geo e 6 dos 10 de socio. O PCA existe como alternativa.
6. **Engenharia de features.** São 38 colunas:
   - as EXCLUDED normalizadas;
   - as variáveis auxiliares;
   - "efeitos aleatórios" sintéticos: `UF×mês`, `UF×ano` e `UF×mês×ano`, normalizados;
   - os componentes PLS;
   - as duas DIR, que funcionam como preditores autorregressivos.
7. **Divisão temporal por ano.**
   - Treino: até 2016, com alvos de 2002 a 2016.
   - Validação: alvos de 2017 a 2019, usando 2016 só como contexto da janela.
   - Não há teste separado nem validação cruzada temporal.
8. **Janelas deslizantes.** Para cada UF, X são os 12 meses anteriores e y é o mês seguinte, nas 2 saídas. Resultado: `x_train (4860, 12, 38)` e `x_val (972, 12, 38)`. `Year` e `dep_id` são removidos, o que deixa 36 features.
9. **Aumento de dados.** 3 cópias com ruído gaussiano N(0; 0,01), aplicado também à validação.
10. **Modelos base.**
    - CatBoost e SVM recebem a janela achatada (12 × 36 = 432 features).
    - A LSTM recebe a entrada 3D `(12, 36)`.
    - Em todos, previsões negativas são fixadas em zero e a escala é desfeita.
11. **Stacking.** O RF recebe 12 features:
    - as previsões dos 3 modelos nas 2 saídas;
    - 3 **extrapolações polinomiais** (graus 0, 1 e 2, ajustadas com `scipy.optimize.curve_fit` sobre os 12 meses) de cada DIR.
12. **Intervalos de previsão.** Percentis 2,5 e 97,5 entre as 100 árvores do RF.
13. **Avaliação.**
    - NRMSE e R² por UF, contra o baseline.
    - Gráficos de barras por UF e diferenças par a par entre modelos (ablação).
    - Métricas gravadas em `metrics/Brazil/*.csv`.

### Resultados (NRMSE médio nas 27 UFs)

| Modelo | 0-19 treino | Total treino | **0-19 validação** | **Total validação** |
|---|---|---|---|---|
| Ensemble (RF) | 0,0286 | 0,0295 | **0,1157** | **0,1158** |
| CatBoost | 0,0375 | 0,0380 | 0,1173 | 0,1181 |
| LSTM | 0,0842 | 0,0868 | 0,1598 | 0,1791 |
| SVM | 0,0551 | 0,0549 | 0,1863 | 0,1823 |
| Baseline bayesiano | 0,1207 | 0,1214 | 0,2067 | 0,2078 |

O R² por UF varia muito, com valores negativos na validação em algumas UFs no CatBoost e na SVM.

### Pontos de atenção metodológicos

- **Vazamento de dados:**
  - o `MinMaxScaler` é ajustado no período inteiro;
  - a PLS é supervisionada com o alvo de todo o período, validação incluída;
  - a validação, já com o aumento de dados, serve para early stopping e também para a avaliação final.
- **Stacking sem out-of-fold:** o RF aprende a partir de previsões in-sample, o que superestima o desempenho no treino.
- **Bugs de hiperparâmetro:** o otimizador e o lr da LSTM são ignorados, e o `max_depth` do RF está desativado.
- **Validação cruzada da SVR:** usa `KFold` padrão sobre amostras aumentadas, sem respeitar a ordem temporal (**inferido**).
- **Features da CNN:** vêm de um modelo externo com janela de treino desconhecida, o que pode introduzir vazamento (**inferido**).

## 4. Técnicas reaproveitáveis para o Atlas

1. **Multi-saída:** prever a DIR total e a de 0 a 19 anos no mesmo modelo.
2. **Janela de 12 meses → 1 passo** por unidade espacial, num **modelo global** que empilha todas as unidades, com o histórico do alvo como preditor.
3. **Alvo como taxa por 100 mil**, com escala MinMax revertida antes das métricas e previsões negativas fixadas em zero.
4. **Redução supervisionada por grupo temático** (clima, geo, socio) com PLS. Ajustar **só no treino**.
5. **Efeitos espaço-temporais sem one-hot**: produtos UF×mês, UF×ano e UF×mês×ano.
6. **Aumento com ruído gaussiano pequeno**, aplicado **só no treino**.
7. **Divisão temporal por ano**, com o último ano de treino como contexto das janelas de validação.
8. **Stacking heterogêneo** (boosting + kernel + recorrente) com meta-RF, mais extrapolações polinomiais como features de tendência. Usar previsões **out-of-fold**.
9. **Intervalos de previsão** a partir da dispersão entre as árvores do RF.
10. **Avaliação por unidade espacial** com NRMSE normalizado pela amplitude, mais R², sempre contra um baseline estatístico e com ablação entre modelos.
11. **Modelos e métricas versionados**, com uma flag que alterna entre treinar e só avaliar. No Atlas, esse papel cabe ao MLflow: runs, registro e aliases.

## 5. Arquivos relevantes

| Arquivo | Tamanho | Descrição |
|---|---|---|
| `code/dataset/Brazil_UF_dengue_monthly.csv` | 3,7 MB | Dataset principal: 27 UFs × 228 meses, 62 colunas |
| `code/saved_models/cnn_dataframe.csv` | 248 KB | Saídas da CNN externa por UF e mês |
| `baseline_models/Brazil/Baseline_fitted_predicted_*.csv` | cerca de 800 KB cada | Ajuste e previsão do baseline bayesiano (população total e 0 a 19) |
| `code/saved_models/Brazil/` | cerca de 192 MB | CatBoost (43 MB), SVM (29 MB), LSTM (0,4 MB) e RF (121 MB) treinados |
| `code/metrics/Brazil/*.csv` | cerca de 2,5 KB cada | NRMSE por UF de cada modelo |
| `code/requirements.txt` | — | numpy 1.19.5, catboost 1.0.0, scikit-learn 1.0, pandas 1.3.4, tensorflow 2.6.0 |
| `README.md`, `guide/*.md`, `artigo_traduzido.md`, `paper.pdf` | — | Documentação, dicionário de dados e artigos |

Os outros arquivos da pasta (`ingest.py`, `br_ms_sinan.duckdb`, mapas, `dbt/`, `ppgcc-dengue-project-poc/`) são trabalho de ingestão e visualização do SINAN e não contêm modelos de ML.
