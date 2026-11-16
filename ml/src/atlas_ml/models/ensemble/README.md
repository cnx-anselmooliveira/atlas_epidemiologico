# Ensemble (stacking out-of-fold)

Meta-modelo sobre as previsões de CatBoost, SVR e LSTM.

- **Referência:** o ensemble do ESA-UNICEF Dengue Forecast ([levantamento](../../../../../docs/referencias/esa-unicef-dengue-forecast.md)): Random Forest sobre previsões dos modelos-base e extrapolações polinomiais.
- **Meta-features por janela:**
  - as previsões de CatBoost, SVR e LSTM;
  - extrapolações polinomiais de graus 0, 1 e 2 da janela de incidência até t + `horizon`.
- **Meta-modelo:** `RandomForestRegressor(n_estimators=300, max_depth=8)`.

## O que mudou em relação ao original

- **Sem previsões in-sample:** o original treinava o meta-modelo com previsões dos modelos-base nos próprios dados de treino, o que superestima os modelos que decoram. Aqui o treino usa só as **previsões out-of-fold** (`oof_predictions.parquet`), em blocos rolling origin: cada linha foi prevista por um ajuste que nunca viu aquele alvo.
- **Validação e teste:** usam as previsões dos modelos-base finais (`predictions.parquet`).
- **`max_depth=8`:** aplicado; no original estava desativado.
- **Intervalo:** percentis 2,5 e 97,5 **entre as árvores**, usados diretamente como limites (o original os desenhava como desvios).
- **Recusa a treinar** se faltar a run ou a OOF de algum modelo-base.

## Uso

```
atlas-ml forecast train ensemble --dataset-run ID --base-runs catboost=ID,svr=ID,lstm=ID
```

As runs dos modelos-base precisam ser do mesmo snapshot e da mesma configuração (`window`, `horizon`). Na DAG, os IDs vêm por XCom.

## Registro

`mlflow.sklearn` em formato skops, como `atlas-br-ensemble`. O tipo `sklearn.tree._tree.Tree` é declarado confiável porque o arquivo é gerado pela própria run.

## Tempo esperado em CPU

Segundos: o custo dos re-treinos está nas tarefas dos modelos-base.
