# atlas-ml — projeto de treino do Atlas da Dengue

Pacote Python (`atlas_ml`) com o CLI `atlas-ml`. O mesmo comando roda na sua máquina, na imagem `atlas-epidemiologia-ml` e nas tarefas do Airflow. Cada treino é registrado no MLflow com os metadados de reprodutibilidade, e os modelos são promovidos na ordem **dev → hml → prod**.

> Este pacote ainda não contém o modelo de nicho ecológico. O experimento `example` usa dados sintéticos para validar a plataforma de ponta a ponta.

## Uso

```sh
cd ml
uv sync                                   # ambiente local (Python 3.12)
export MLFLOW_TRACKING_URI=http://127.0.0.1:5000   # MLflow do compose de dev

uv run atlas-ml info                      # versão, ambiente e destino
uv run atlas-ml train example             # treina e registra a run
uv run atlas-ml train example --register --seed 7   # também registra o modelo (alias @dev no MLflow local)
uv run atlas-ml promote atlas-example --version 3 --to hml   # só no MLflow da VPS
uv run atlas-ml promote atlas-example --version 3 --to prod
```

Na rede da empresa (inspeção TLS), use `uv sync --native-tls`.

## Variáveis de ambiente

| Variável | Obrigatória | Descrição |
|---|---|---|
| `MLFLOW_TRACKING_URI` | sim | URL do servidor MLflow (`http://127.0.0.1:5000` em dev; `https://mlflow.dengue.contovisual.com.br` na VPS) |
| `ATLAS_ENV` | não (padrão `dev`) | `dev`, `hml` ou `prod`; outro valor interrompe a execução |
| `ATLAS_GIT_SHA` | na imagem | Commit do código; localmente vem de `git rev-parse HEAD`. Sem nenhum dos dois, o treino falha |
| `ATLAS_IMAGE_TAG` | não (padrão `local`) | Tag da imagem em uso (`dev`, `hml`, `1.0`…) |
| `GCP_PROJECT` | para BigQuery | Projeto das tabelas de features |
| `MLFLOW_TRACKING_USERNAME` / `MLFLOW_TRACKING_PASSWORD` | na VPS | Credenciais do MLflow com autenticação |
| `GOOGLE_APPLICATION_CREDENTIALS` | para BigQuery | Chave da service account de treino |

## Contrato de cada run

Toda run abre com estas tags. Se alguma estiver vazia, a execução falha antes de treinar.

| Tag | Valor |
|---|---|
| `atlas.env` | ambiente (`dev`, `hml`, `prod`) |
| `atlas.git_sha` | commit do código |
| `atlas.image_tag` | tag da imagem (`local` fora de container) |
| `atlas.data_version` | `synthetic-seed<N>`, `<tabela>@<última modificação>` ou `query:<hash>+<tabela>@<…>` |

Além das tags, cada run registra:
- os hiperparâmetros;
- as métricas de validação `val_*`, sempre num split temporal;
- o modelo com assinatura (`skops`, o formato seguro do MLflow 3);
- o artefato `data_summary.json`.

Experimentos ficam em `atlas/<nome>` no MLflow.

## Promoção de modelos

| Destino | Regra |
|---|---|
| `@dev` | automático ao registrar no MLflow **local** |
| `@hml` | a run da versão precisa ter `atlas.env=hml`, ou seja, ter sido treinada com a imagem `hml` contra o MLflow da VPS |
| `@prod` | a versão precisa ter passado por `@hml` (tag `atlas.hml_at`) e ter métricas `val_*` |

Cada promoção grava `atlas.<destino>_at` e `atlas.<destino>_by` na versão. Para fazer rollback, promova de novo uma versão anterior que já esteve em `@prod`.

## Leitura de features do BigQuery

```python
from atlas_ml.data.bigquery import bigquery_client, read_features

df, summary = read_features(
    bigquery_client(settings),
    table="ppgcc-dengue-project.gold.gold_dengue_epi_curve_weekly",
    date_column="epi_week_start_date",
)
# summary.data_version → "…gold_dengue_epi_curve_weekly@2026-11-14T06:12:00+00:00"
```

## Previsão de dengue por UF (`atlas-ml forecast`)

Seis modelos sobre o mesmo painel de casos prováveis por UF e semana, lido da `gold_dengue_casos_provaveis_uf_semanal`:

| Modelo | Pasta | Família | No ensemble |
|---|---|---|---|
| Baseline bayesiano (PyMC) | [`models/baseline_bayes`](src/atlas_ml/models/baseline_bayes/README.md) | bayes | não (comparador) |
| Chronos-Bolt zero-shot | [`models/chronos`](src/atlas_ml/models/chronos/README.md) | foundation | não (comparador) |
| CatBoost | [`models/catboost`](src/atlas_ml/models/catboost/README.md) | gbm | sim |
| SVR | [`models/svr`](src/atlas_ml/models/svr/README.md) | kernel | sim |
| LSTM (PyTorch) | [`models/lstm`](src/atlas_ml/models/lstm/README.md) | rnn | sim |
| Ensemble (RandomForest sobre OOF) | [`models/ensemble`](src/atlas_ml/models/ensemble/README.md) | stacking | — |

```sh
uv sync --extra models                                   # CatBoost, PyTorch CPU, PyMC/nutpie, Chronos
uv run --extra models atlas-ml forecast prepare          # gold → run `dataset`  → dataset_run_id=…
uv run --extra models atlas-ml forecast train catboost --dataset-run ID [--window 12 --horizon 1 --seed 42]
uv run --extra models atlas-ml forecast train ensemble --dataset-run ID --base-runs catboost=ID,svr=ID,lstm=ID
uv run --extra models atlas-ml forecast compare --pipeline-run <atlas.pipeline_run>
```

Use sempre `--extra models` no `uv run`. Sem ele, o `uv` sincroniza o ambiente sem o grupo e remove os pacotes.

**Como cada modelo é treinado** (`forecast/base.py`, `run_model`):

1. **Snapshot:** baixa o snapshot da run `dataset`. O BigQuery nunca é relido.
2. **Janelas:** descarta as 8 semanas imaturas e monta janelas N→H em `log1p(incidência)`.
3. **Divisão:** pela data do alvo, com teste = últimas 52 semanas, validação = 52 anteriores e treino = o resto. O `TrainOnlyScaler` é ajustado só no treino.
4. **Ajuste:** `fit` com o treino; validação só para early stopping e seleção.
5. **Previsões:** de validação e teste, com corte em 0. Para CatBoost, SVR e LSTM, também as previsões out-of-fold (3 blocos rolling origin de 52 semanas).
6. **Registro:** métricas por UF e médias (NRMSE, MAE, RMSE, R², cobertura do intervalo), artefatos `predictions.parquet`, `metrics_by_uf.csv` e `oof_predictions.parquet`, e o modelo como `atlas-br-<modelo>` (`@dev` em dev).

Todas as runs ficam no experimento `atlas/dengue-forecast-br`, com as tags `atlas.pipeline_run`, `atlas.dataset_run` e `atlas.model_family`. Pelo Airflow, a DAG `atlas_dengue_forecast_br` roda tudo em sequência.

## Imagem

```sh
docker build -t atlas-epidemiologia-ml:local --build-arg ATLAS_GIT_SHA=$(git rev-parse HEAD) ml/
docker run --rm -e MLFLOW_TRACKING_URI=http://host.docker.internal:5000 atlas-epidemiologia-ml:local train example
```

A imagem roda como usuário `atlas` (uid 1000), não contém credenciais e recebe `ATLAS_GIT_SHA` e `ATLAS_IMAGE_TAG` como build args no CI. Para incluir os modelos de previsão, use `--build-arg ATLAS_ML_EXTRAS=models`. A imagem do Airflow e o Jupyter do compose já os incluem.

## Testes

```sh
uv run pytest                      # sem rede: MLflow em diretório temporário e BigQuery simulado
uv run --extra models pytest       # inclui os testes @models (painel sintético; Chronos com pipeline falso)
uv run ruff check . && uv run ruff format --check .
```
