# CatBoost

Gradient boosting sobre as janelas de incidência. Modelo-base do ensemble.

- **Referência:** notebook de CatBoost do ESA-UNICEF Dengue Forecast ([levantamento](../../../../../docs/referencias/esa-unicef-dengue-forecast.md)).
- **Entrada por janela:**
  - as últimas `window` incidências em `log1p`, padronizadas pelo `TrainOnlyScaler`;
  - `sin`/`cos` da semana do alvo;
  - covariáveis de `cfg.features`;
  - `uf_code` como **categórica**.
- **Alvo:** incidência da semana t + `horizon` (mesma transformação). A previsão volta com `expm1` e nunca fica negativa.

## O que mudou em relação ao original

- Divisão por data do alvo (treino → validação → teste), sem embaralhar o tempo.
- Early stopping só na validação (`od_wait`); o teste nunca entra no ajuste.
- Escalonamento ajustado só no treino. O original usava MinMax global, que vazava informação.
- Previsões out-of-fold por blocos rolling origin (`oof_predictions.parquet`), usadas pelo ensemble no lugar de previsões in-sample.

## Hiperparâmetros

| Parâmetro | Valor |
|---|---|
| `iterations` | 5000 (com early stopping) |
| `learning_rate` | 0,03 |
| `depth` | 6 |
| `od_wait` | 300 |
| perda | RMSE |
| `random_seed` | `cfg.seed` |

Registro: `mlflow.catboost`, como `atlas-br-catboost`.

## Tempo esperado em CPU

Painel real (27 UFs, cerca de 34 mil janelas de treino): poucos minutos para o modelo final, mais 3 ajustes OOF.
