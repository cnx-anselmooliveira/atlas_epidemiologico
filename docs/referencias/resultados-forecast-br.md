# Resultados: previsão de dengue por UF (primeira execução)

Primeira execução de ponta a ponta da DAG `atlas_dengue_forecast_br` em dev, em 16/11/2026, disparada sem configuração (janela 12, horizonte 1 semana, semente 42).

- **Execução:** `manual__2026-11-16T14:56:03.101095+00:00`, que é também a tag `atlas.pipeline_run` das 8 runs.
- **Dados:** `gold_dengue_casos_provaveis_uf_semanal@2026-11-16T04:27:11`, a mesma `atlas.data_version` em todas as runs.
- **Painel:** 27 UFs, alvo = incidência de casos prováveis por 100 mil habitantes na semana seguinte.
- **Janelas:**
  - treino: 33.993;
  - validação: últimas 52 semanas antes do teste;
  - teste: 1.404 (27 UFs × 52 semanas mais recentes, depois de descartar as 8 semanas imaturas).

## Métricas de teste (média entre UFs)

| Modelo | NRMSE | MAE | RMSE | R² | Cobertura do intervalo | NRMSE validação |
|---|---:|---:|---:|---:|---:|---:|
| **CatBoost** | **0,0892** | 0,786 | 1,243 | **0,787** | — | 0,0977 |
| SVR | 0,0893 | **0,781** | **1,200** | 0,785 | — | 0,0974 |
| LSTM | 0,0912 | 0,787 | 1,238 | 0,777 | — | 0,0970 |
| Ensemble (OOF) | 0,0961 | 0,839 | 1,318 | 0,750 | 56% (alvo 95%) | 0,1057 |
| Chronos-Bolt (zero-shot) | 0,1235 | 1,211 | 1,738 | 0,523 | 91% (alvo 80%) | 0,1077 |
| Baseline bayesiano | 0,1404 | 1,806 | 2,810 | 0,570 | 92% (alvo 95%) | 0,1593 |

- A run `compare` aponta `atlas.best_model=catboost` e nenhum modelo ausente. A tabela completa está em `comparison.csv`.
- MAE e RMSE estão em casos por 100 mil habitantes por semana.

## Leitura

- **Modelos-base:** CatBoost, SVR e LSTM ficam praticamente empatados (NRMSE entre 0,089 e 0,091). Com janela de 12 semanas e só a série de casos, a informação disponível limita o resultado mais que o algoritmo.
- **Ensemble:** ficou abaixo dos modelos-base. O meta-modelo aprende com só 4.212 linhas OOF, os blocos finais do treino, e as previsões dos três modelos são muito correlacionadas.
- **Intervalo do ensemble:** os percentis entre árvores medem a discordância das árvores, não a incerteza da previsão. Por isso cobrem só 56%.
- **Chronos:** sem nenhum treino, fica a 0,03 de NRMSE dos modelos treinados e tem o intervalo mais bem calibrado (91% para 80% nominal, ou seja, conservador).
- **Baseline bayesiano: não convergiu.** R̂ máximo 1,21 e ESS mínimo 16, com 2 cadeias × 500 draws (tag `atlas.converged=false`). As métricas dele não devem ser usadas para conclusões até a correção.

## Tempo por tarefa (CPU do notebook, até 3 tarefas em paralelo)

| Tarefa | Duração | Detalhe |
|---|---:|---|
| prepare | 35 s | leitura da gold e snapshot no MLflow |
| CatBoost | 13 min | modelo final 517 s (melhor iteração 2.327) + OOF 246 s |
| Baseline bayesiano | 8 min | amostragem NUTS (nutpie) 448 s |
| Chronos | 11,5 min | inclui o download do checkpoint para o `hf-cache` |
| SVR | 46 min | busca final 778 s (melhor: rbf, C≈0,71) + OOF 1.886 s |
| LSTM | 1 h 34 min | modelo final 3.472 s (melhor época 9 de 21) + OOF 2.070 s |
| Ensemble | 1 min | 300 árvores sobre as OOF |
| compare | 5 s | |
| **Total** | **1 h 35 min** | |

Os artefatos estão em `gs://ppgcc-bucket/mlflow/dev/2/` (62 objetos) e os seis modelos estão registrados como `atlas-br-<modelo>` v1, com `@dev`.

## Próximos passos

- **Baseline bayesiano:** parametrização não centrada dos efeitos de UF e ano, mais tune e draws, e conferência dos diagnósticos antes de comparar.
- **Ensemble:** mais blocos OOF, ou incluir Chronos e o bayesiano como meta-features. Para o intervalo, considerar quantis por árvore (quantile regression forest) ou conformal.
- **Covariáveis:** clima (temperatura, chuva, umidade) e as já disponíveis na gold (`mean_elevation_m`, `mean_slope_deg`) via `--features`.
- **Horizonte de 4 semanas** (tarefa 9.3): repetir com `horizon=4`.
