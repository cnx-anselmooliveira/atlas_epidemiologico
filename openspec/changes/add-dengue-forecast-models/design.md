# Design

## Context

- **Plataforma pronta** (`add-ml-platform`, módulos 1–5 em `dev`):
  - pacote `atlas_ml` com CLI `atlas-ml`;
  - contrato de tags `atlas.*` (`atlas_run`);
  - `read_features` do BigQuery com versão `<tabela>@<última modificação>`;
  - promoção de modelos;
  - imagem do Airflow 3.3.2 com `atlas_ml` num venv separado chamado via `BashOperator`;
  - compose de dev (Postgres + MLflow 3.18 + Airflow) com MLflow servindo artefatos (`--serve-artifacts`).
- **Dados disponíveis** (BigQuery `ppgcc-dengue-project.gold`):
  - `gold_dengue_epi_curve_weekly`: `country_iso3`, `admin1_name`, `year`, `epi_week`, `epi_week_start_date`, `total_cases`;
  - `gold_dim_populacao_admin1`: `country_iso3`, `admin1_name`, `population`, `population_year`.
  - O Brasil vem do SINAN. Ainda não há covariáveis ambientais.
  - **Conferido no BigQuery (tarefa 1.3):** as colunas batem; as tabelas estão em `US`.
    - **Período e volume:** 27 UFs, semanas de 2000-01-01 a 2026-06-18, 36.110 linhas e 33,4 milhões de casos. Uma série completa teria cerca de 37,3 mil linhas, então há semanas faltantes a preencher.
    - **População:** um único ano (2022) para as 27 UFs, todas com valor. A incidência dos anos antigos fica levemente subestimada.
    - **Semanas recentes:** as últimas semanas são subnotificadas por atraso de digitação.
- **Referência:** `docs/referencias/esa-unicef-dengue-forecast.md`. Os modelos, os hiperparâmetros originais e os problemas a corrigir estão lá.
- **Ambiente:** notebook Windows na rede corporativa, com inspeção TLS e CPU sem GPU. Isso limita o custo de LSTM, MCMC e Chronos.

## Goals / Non-Goals

**Goals:**
- Seis modelos comparáveis sobre o mesmo snapshot, com metodologia sem vazamento e métricas por UF.
- Uma pasta por modelo, com contrato comum, para que o próximo modelo, ou a troca de dados por satélite e clima, não mexa nos outros.
- Execução completa pela DAG em dev, com artefatos no `gs://ppgcc-bucket`.

**Non-Goals:**
- Otimização exaustiva de hiperparâmetros. Os valores iniciais vêm do original e podem ser ajustados depois.
- Fine-tuning do Chronos.
- Servir previsões online ou gravá-las no BigQuery.
- GPU.

## Decisions

### 1. Estrutura
```
ml/src/atlas_ml/
├── forecast/
│   ├── config.py      # ForecastConfig: window=12, horizon=1, test_weeks=52, val_weeks=52, oof_folds=3, seed=42, features
│   ├── dataset.py     # gold → painel UF×semana (casos, população, incidência, filled); snapshot → MLflow
│   ├── windows.py     # janelas (X, y) por UF; transformações ajustadas só no treino (TrainOnlyScaler)
│   ├── splits.py      # treino/validação/teste por data; blocos temporais para out-of-fold
│   ├── evaluate.py    # NRMSE, MAE, RMSE, R² por UF + médias; metrics_by_uf.csv; predictions.parquet
│   ├── base.py        # ForecastModel (Protocol): fit(train, val) / predict(windows) / log_model(); run_model()
│   └── compare.py     # run de comparação da execução
└── models/
    ├── baseline_bayes/  model.py · README.md
    ├── catboost/        model.py · README.md
    ├── lstm/            model.py · README.md
    ├── svr/             model.py · README.md
    ├── chronos/         model.py · README.md
    └── ensemble/        model.py · README.md
```

Cada `README.md` de modelo traz:
- a referência ao original;
- o que mudou na correção da metodologia;
- os hiperparâmetros;
- o tempo esperado em CPU.

`base.run_model(name, cfg, dataset_run_id)` faz o trabalho comum a todos os modelos:
1. baixa o snapshot;
2. monta as janelas;
3. chama `fit` e `predict`;
4. avalia;
5. registra parâmetros, métricas, artefatos e o modelo.

Assim cada `model.py` só contém o que é específico do modelo.

### 2. Dataset e snapshot
- **Consulta:** um `SELECT` simples da `gold_dengue_casos_provaveis_uf_semanal` (mudança `add-gold-casos-provaveis-uf`): `probable_cases` vira `cases`, com a população do ano epidemiológico e o relevo (`mean_elevation_m`, `mean_slope_deg`) como covariáveis estáticas, disponíveis para `cfg.features`. A leitura usa `read_features(query=…, source_tables=[gold])`, então a `data_version` registra a geração da tabela. A curva antiga (`gold_dengue_epi_curve_weekly`) não serve como alvo: soma descartados até 2021 e não depois, o que cria uma quebra de nível em 2022 (`docs/referencias/gold-casos-provaveis-uf.md`).
- **Painel:**
  - semanas faltantes completadas com zero e `filled=true`;
  - `incidence = cases / population × 1e5`;
  - uma chave estável por UF, `uf_code`, com índice 0–26 em ordem alfabética.
- **Snapshot:** `atlas-ml forecast prepare` cria uma run `dataset` com `panel.parquet` e `data_summary.json` (período, UFs, linhas, semanas preenchidas) e imprime `dataset_run_id=<id>`. Os modelos baixam esse artefato com `mlflow.artifacts.download_artifacts` e nunca releem o BigQuery. Isso cumpre a spec `forecast-training-dag`.

### 3. Janelas, alvo e divisão
- **Alvo:** a incidência da semana t+H (H=1). Os modelos treinam sobre `log1p(incidence)`, que reduz a assimetria das epidemias. O `TrainOnlyScaler`, um `StandardScaler` ajustado só no treino, padroniza tanto o histórico quanto o alvo. A previsão volta à escala original com `expm1` e é fixada em ≥ 0. O MinMax global do original foi descartado porque vazava informação.
- **Features por janela:**
  - as últimas N incidências transformadas;
  - `sin` e `cos` da semana do ano do alvo;
  - `uf_code`: categórica no CatBoost, one-hot no SVR, embedding na LSTM;
  - as covariáveis listadas em `cfg.features`, nenhuma por enquanto, como janelas de N semanas. É por esse ponto que temperatura, vento e chuva vão entrar.
- **Semanas imaturas:** `drop_recent_weeks` (padrão 8) descarta as últimas semanas do painel antes da divisão. Por causa do atraso de notificação, elas seriam um "observado" subestimado e contaminariam o teste. O valor é registrado como parâmetro.
- **Divisão por data do alvo:**
  - teste = últimas 52 semanas;
  - validação = as 52 semanas anteriores;
  - treino = o restante.
  - As janelas de validação e teste podem usar semanas anteriores como histórico, mas os alvos nunca se sobrepõem.
- **Aumento de dados:** ruído gaussiano com σ = 0,01 na escala padronizada, 3 cópias, **só no treino** e só nos modelos que se beneficiam dele (LSTM e SVR). O original aplicava o aumento também na validação.
- **Out-of-fold:** o período de treino é dividido em `oof_folds=3` blocos finais de 52 semanas. Para cada bloco, o modelo-base é treinado com tudo antes dele e prevê o bloco. Esse esquema é rolling origin, nunca `KFold` embaralhado.

### 4. Modelos

| Pasta | Implementação | Ajuste inicial | Registro no MLflow |
|---|---|---|---|
| `baseline_bayes` | **PyMC** com binomial negativa: `log μ = log(pop/1e5) + α + u_uf + v_ano + Σ Fourier(semana, 2 harmônicos) + β·log1p(incid_{t−H})`, com `u_uf` e `v_ano` normais hierárquicos. Para o ano do teste, que não foi visto no treino, `v_ano` vem da priori. | NUTS: 2 cadeias, 500 de tune e 500 de draws (configurável); `target_accept=0.9` | `pyfunc` com o resumo do posterior (`idata.nc` como artefato); métricas `rhat_max` e `ess_bulk_min`; intervalo de credibilidade de 95% |
| `catboost` | `CatBoostRegressor`, perda RMSE, `cat_features=[uf_code]` | `iterations=5000`, `learning_rate=0.03`, `depth=6`, early stopping na validação (300), `random_seed` | `mlflow.catboost` |
| `svr` | `Pipeline(OneHot(uf) + StandardScaler, SVR)` com `RandomizedSearchCV(cv=TimeSeriesSplit(3))` só no treino | espaço do original: `kernel` ∈ {rbf, poly, sigmoid}, `C` ∈ {0.01…10}, `gamma`, `epsilon`; `n_iter=10` | `mlflow.sklearn` (skops, tipos confiáveis declarados) |
| `lstm` | **PyTorch**: `Embedding(27, 4)` + `LSTM(60)` → `LSTM(20)` → `Linear(1)`, dropout 0,5 | Adam `lr=1e-3` (o otimizador do original era ignorado por bug); `batch=64`; até 200 épocas; early stopping na validação (paciência 12, restaura os melhores pesos); `torch.manual_seed` e `use_deterministic_algorithms` | `mlflow.pytorch` |
| `chronos` | `chronos-forecasting` com `BaseChronosPipeline.from_pretrained("amazon/chronos-bolt-small")`, zero-shot, CPU. Para cada origem de validação e teste, o contexto é o histórico de incidência da UF (até 512 semanas). | sem treino; previsões em lote (27 UFs × 104 origens) | `pyfunc` que carrega o checkpoint; parâmetros com o nome e a revisão (commit do Hugging Face); quantis 0,1 e 0,9 como `lower`/`upper` (intervalo de 80%, explicitado na run) |
| `ensemble` | `RandomForestRegressor` sobre as previsões OOF de CatBoost, SVR e LSTM + extrapolações polinomiais (graus 0, 1, 2) da janela | `n_estimators=300`, `max_depth=8` (desativado no original), `random_state` | `mlflow.sklearn`; intervalos pelos percentis 2,5 e 97,5 entre árvores, usados diretamente como limites (o original os desenhava como desvios) |

O baseline bayesiano e o Chronos ficam fora do stacking, como comparadores, para manter a configuração do artigo. Incluí-los depois só exige que também produzam previsões OOF.

### 5. Previsões OOF produzidas pelos modelos-base
CatBoost, SVR e LSTM registram, além do modelo final treinado no treino completo, o artefato `oof_predictions.parquet`, com a previsão de cada janela de treino coberta pelos blocos OOF. O ensemble lê:
- os artefatos OOF das três runs, para treinar o meta-modelo;
- os artefatos `predictions.parquet`, com validação e teste dos modelos finais, para prever.

Isso paraleliza o custo dos re-treinos dentro das tarefas de cada modelo e deixa o ensemble leve. Os IDs das runs vêm da DAG via XCom.

### 6. CLI e DAG
```
atlas-ml forecast prepare [--window 12 --horizon 1 --seed 42]           → dataset_run_id=…
atlas-ml forecast train <baseline_bayes|catboost|lstm|svr|chronos> --dataset-run ID   → run_id=…
atlas-ml forecast train ensemble --dataset-run ID --base-runs catboost=ID,svr=ID,lstm=ID
atlas-ml forecast compare --pipeline-run RUN_ID
```

A DAG `atlas_dengue_forecast_br`:
- **Agendamento e execução:** `schedule=None`, `max_active_runs=1` e `max_active_tasks=3`, porque MCMC, LSTM e Chronos em paralelo saturam a CPU do notebook.
- **Parâmetros:** `params` com `window`, `horizon` e `seed`.
- **Passagem de IDs:** cada `BashOperator` executa o CLI e devolve a última linha (`…=ID`) por XCom.
- **Identificação da execução:** `ATLAS_PIPELINE_RUN={{ run_id }}` vai no ambiente da tarefa, e o `atlas_run` grava a tag `atlas.pipeline_run`.
- **Comparação final:** usa `trigger_rule="all_done"` para registrar os modelos ausentes.
- **Retentativas:** `retries=1`. MCMC e LSTM são caros, então uma falha não deve repetir várias vezes.

### 7. Dependências e imagens
- **Grupo opcional** em `ml/pyproject.toml`: `models = ["catboost", "torch", "pymc", "chronos-forecasting"]`. O `torch` vem do índice CPU do PyTorch, via `[tool.uv.sources]` com índice explícito `pytorch-cpu`, para não baixar CUDA (cerca de 2 GB a menos).
- **Imagens:**
  - Airflow: `uv sync --extra models`;
  - treino: novo alvo `runtime-models`;
  - a imagem `runtime` atual continua leve.
- **Testes:**
  - os rápidos (dataset, janelas, divisões, métricas, ensemble com modelos-base falsos) rodam sem os extras;
  - os testes de cada modelo usam um painel sintético pequeno (3 UFs × 3 anos) e ficam marcados com `@pytest.mark.models`, rodando quando os extras estão instalados.

### 8. Compose de dev: bucket e cache
- **Bucket:** o `.env` passa a ter `MLFLOW_ARTIFACTS_BUCKET=ppgcc-bucket`, e a chave da SA do MLflow vai em `platform/secrets/mlflow-sa.json` (`roles/storage.objectAdmin` só nesse bucket). Os artefatos novos vão para `gs://ppgcc-bucket/mlflow/dev/`.
- **Runs antigas:** as runs do volume local continuam no Postgres, mas os artefatos delas ficam inacessíveis depois da troca. Isso é aceitável em dev. Se quiser zerar, use `dev.ps1 reset`.
- **Cache do Hugging Face:** um volume `hf-cache` com `HF_HOME=/opt/airflow/hf-cache` (e o equivalente no Jupyter) evita baixar o Chronos a cada execução.
- **Rede corporativa:** se o download do Hugging Face ou o acesso ao BigQuery falhar por TLS, use `EXTRA_CA_PATH`. Essa é a tarefa 5.3 da `add-ml-platform`, que passa a ser verificada aqui.

### 9. Organização no MLflow
- **Experimento:** `atlas/dengue-forecast-br`.
- **Runs:** `dataset`, um por modelo (`run_name=<modelo>`) e `compare`.
- **Tags:** além das `atlas.*`, cada run grava `atlas.pipeline_run` e `atlas.model_family` (`bayes`, `gbm`, `kernel`, `rnn`, `foundation`, `stacking`).
- **Modelos registrados:** `atlas-br-<modelo>`, com `@dev` automático em dev.

## Risks / Trade-offs

- **[Tempo de MCMC em CPU (cerca de 27 × 700 semanas de observações)]** → draws baixos por padrão e configuráveis; tempo registrado; fallback documentado para ADVI (`pm.fit`) se passar de 20 min.
- **[Imagem do Airflow pesada (torch + PyMC + CatBoost)]** → torch CPU; o grupo `models` só entra nas imagens que treinam; build cacheado.
- **[Download do Chronos bloqueado pela inspeção TLS ou sem rede]** → cache em volume; CA corporativa; se o modelo não carregar, a tarefa falha com mensagem clara e a comparação registra o Chronos como ausente.
- **[População de um único ano (2022) aplicada a 2000–2026]** → a incidência de anos antigos fica subestimada, mas as métricas por UF no teste (2024–2026) quase não são afetadas. Trocar por população anual quando a gold tiver a série.
- **[Gold do Brasil com mudanças de definição ao longo dos anos (SINAN)]** → por ora o dado é tratado como está. O `data_summary.json` mostra o período e as semanas preenchidas para inspeção.
- **[Aumento de dados distorce a LSTM em séries com muitos zeros]** → aumento configurável (`augment=0` desliga) e registrado como parâmetro.
- **[Chaves GCP ainda não fornecidas]** → as primeiras tarefas checam as chaves e falham cedo com instruções. Os testes e o desenvolvimento usam o painel sintético.

## Migration Plan

1. **Dev:** módulos implementados com testes, DAG rodando no compose local com artefatos no bucket. Um commit por módulo em `dev`.
2. **Promoção:** depois da validação, seguir o fluxo da `add-ml-platform`. A imagem `hml` roda a DAG no Airflow de hml, e `atlas-ml promote` leva cada `atlas-br-<modelo>` para `@hml` e `@prod`.

## Open Questions

- Revisão fixa do checkpoint do Chronos (`chronos-bolt-small` vs `-base`): começar pelo `small` por causa da CPU e reavaliar depois de medir o tempo.
- O tamanho do teste (52 semanas) cobre um único ciclo sazonal. Avaliar uma validação rolling-origin adicional quando houver mais anos e covariáveis.
