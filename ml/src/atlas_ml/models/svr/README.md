# SVR

Support Vector Regression sobre as janelas de incidência. Modelo-base do ensemble.

- **Referência:** notebook de SVC/SVR do ESA-UNICEF Dengue Forecast ([levantamento](../../../../../docs/referencias/esa-unicef-dengue-forecast.md)). O original chamava de SVC, mas o alvo é contínuo, então aqui é regressão.
- **Pipeline:** `OneHotEncoder(uf_code)` + `StandardScaler`, seguidos de `SVR`.
- **Entrada:** a janela achatada de incidência e dos canais de `cfg.features` (padrão: 8 canais do SINAN mais relevo), sazonalidade e UF. A run registra `model.channels` e `model.n_input_columns`.
- **Busca:** `RandomizedSearchCV` com `TimeSeriesSplit(3)`, só no treino, no espaço do original:
  - `kernel` ∈ {rbf, poly, sigmoid};
  - `C` log-uniforme em 0,01 a 10;
  - `gamma` ∈ {scale, auto};
  - `epsilon`.

## O que mudou em relação ao original

- Validação cruzada temporal (`TimeSeriesSplit`) no lugar de folds embaralhados.
- Aumento de dados (ruído gaussiano, `cfg.augment` cópias) **só no treino**. O original aumentava também a validação.
- Escalonamento ajustado só no treino.
- **Custo O(n²):** o SVR usa as `max_train_rows` janelas de treino mais recentes (padrão 8.000), e `max_iter` limita kernels que não convergem. Os dois valores ficam registrados na run.
- Previsões out-of-fold (`oof_predictions.parquet`) para o ensemble.

## Hiperparâmetros

| Parâmetro | Valor |
|---|---|
| `n_iter` | 10 |
| `cv` | `TimeSeriesSplit(3)` |
| `max_train_rows` | 8000 |
| `max_iter` | 50000 |

Os melhores parâmetros da busca entram na run como `model.best_*`.

Registro: `mlflow.sklearn`, em formato skops, com os tipos confiáveis declarados, como `atlas-br-svr`.

## Tempo esperado em CPU

Alguns minutos por busca. Com os 3 blocos OOF, são 4 buscas.
