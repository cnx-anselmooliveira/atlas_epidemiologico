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

## Previsão de dengue por UF

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
uv sync --extra models        # CatBoost, PyTorch CPU, PyMC/nutpie, Chronos e papermill
```

O pipeline roda pelo notebook (seção "Notebook do pipeline", abaixo). O CLI `atlas-ml forecast` e o módulo `forecast/pipeline.py` foram removidos; os demais comandos (`train example`, `promote`) continuam.

Use sempre `--extra models` no `uv run`. Sem ele, o `uv` sincroniza o ambiente sem o grupo e remove os pacotes.

### Notebooks dos modelos

Cada modelo é um notebook autocontido em [`notebooks/<modelo>/`](notebooks/README.md), com o código do modelo, o `requirements.txt` e as saídas impressas, que roda na mão (célula por célula) ou pelo Airflow. O código comum (dados, janelas, métricas, MLflow) é idêntico nos seis, e três verificações rodam no CI e à mão (em `ml/`, com `--extra models`):

```sh
uv run --extra models python notebooks/_ferramentas/sincronizar_comum.py            # propaga o código comum
uv run --extra models python notebooks/_ferramentas/verificar_comum.py              # células comuns idênticas e sem import proibido
uv run --extra models python notebooks/_ferramentas/verificar_requirements.py       # requirements × uv.lock × imports
```

Detalhes (estrutura, parâmetros, como rodar na mão e como alterar o código comum): [`notebooks/README.md`](notebooks/README.md).

**No Airflow:** cada tarefa de modelo da DAG executa o notebook do modelo com `atlas_ml.forecast.notebook.run_model_notebook` (papermill, resultado em `result.json` por tarefa, notebook executado anexado à run). A versão da gold e a do notebook ficam fixas durante a execução, e a comparação dos modelos é código da própria DAG.

### Notebook único do pipeline (transitório)

> **Transitório.** A DAG `atlas_dengue_forecast_br` já executa os notebooks por modelo (seção anterior) e não usa mais este notebook único. Ele e o código do pacote que ele chama ficam até a validação em hml, quando saem (change `self-contained-model-notebooks`, grupo 10).

O pipeline é o notebook [`notebooks/forecast_pipeline.ipynb`](notebooks/forecast_pipeline.ipynb): as células são finas e chamam o pacote `atlas_ml`. O Airflow o executa com papermill, uma tarefa por passo, e passa os parâmetros de cada uma.

| Parâmetro | Para quê |
|---|---|
| `step` | `prepare` (snapshot dos dados), `train` (um modelo num horizonte) ou `compare` (junta as runs de uma execução) |
| `model`, `horizon`, `window`, `seed` | só no `train` (e `horizon` também no `compare`; 0 compara todos) |
| `dataset_run` | `train`: a run `dataset` criada pelo `prepare` |
| `base_runs` | só ensemble: `{"catboost": "<run_id>", "svr": "…", "lstm": "…"}` |
| `pipeline_run` | valor da tag `atlas.pipeline_run` (a DAG passa o `run_id` dela) |
| `features` | vazio = canais do SINAN + relevo; `-` = só a incidência; ou a lista separada por vírgulas |
| `painel_parquet` | `prepare`: usa um painel pronto em vez de ler o BigQuery (testes e reprocessamento) |
| `fonte` | `prepare`: tabela `projeto.dataset.tabela` no lugar da gold do ambiente |
| `register` | `train`: registra o modelo (`atlas-br-<modelo>-h<H>` com o sufixo do ambiente) |
| `result_path`, `out_dir` | definidos por quem executa; o notebook grava aí o JSON do passo (`dataset_run_id` ou `run_id`) |

Um passo ou modelo inexistente, ou um `train` sem `dataset_run`, falha na primeira célula, antes de criar qualquer run. O notebook declara a versão do contrato do pacote de que precisa (`REQUIRES_API`, comparada com `atlas_ml.forecast.NOTEBOOK_API`) e falha, também antes de criar run, se a imagem for mais antiga.

**Rodar à mão** (MLflow em arquivo local, painel sintético, sem BigQuery):

```sh
export MLFLOW_ALLOW_FILE_STORE=true MLFLOW_TRACKING_URI=./mlruns ATLAS_GIT_SHA=local
uv run --extra models python -c "from atlas_ml.forecast.synthetic import synthetic_panel as s; s(n_weeks=320).to_parquet('painel.parquet', index=False)"
uv run --extra models papermill notebooks/forecast_pipeline.ipynb saida-prepare.ipynb -p step prepare -p painel_parquet painel.parquet
# o dataset_run_id sai no fim da execução; use-o no treino:
uv run --extra models papermill notebooks/forecast_pipeline.ipynb saida-train.ipynb -p step train -p model catboost -p dataset_run <dataset_run_id>
```

Contra a gold real, omita `painel_parquet` e configure as credenciais do BigQuery (`GOOGLE_APPLICATION_CREDENTIALS`) e do MLflow. Sem `result_path`, o notebook só imprime o resultado.

**Migrar scripts que usavam `atlas-ml forecast` ou `atlas_ml.forecast.pipeline`** (por exemplo um script local fora do Git): cada comando virou um passo do notebook, e `run_step` o executa como o Airflow faz.

| Antes | Agora |
|---|---|
| `atlas-ml forecast prepare` / `prepare_snapshot(fonte)` | passo `prepare` (`fonte`, ou `painel_parquet`) → `dataset_run_id` |
| `atlas-ml forecast train <modelo> --dataset-run ID --horizon H` / `train(...)` | passo `train` (`model`, `horizon`, `dataset_run`, `base_runs` no ensemble) → `run_id` |
| `atlas-ml forecast compare --pipeline-run X` / `compare_horizon(...)` | passo `compare` (`pipeline_run`, `horizon`) → `run_id` |

```python
import os

os.environ["ATLAS_NOTEBOOKS_DIR"] = "notebooks"  # onde está forecast_pipeline.ipynb
from atlas_ml.forecast.notebook import run_step

out = "/tmp/atlas/minha-execucao"  # um diretório por execução
ds = run_step("prepare", {"pipeline_run": "manual"}, out, "prepare")["dataset_run_id"]
run = run_step(
    "train",
    {"model": "catboost", "horizon": 1, "dataset_run": ds, "pipeline_run": "manual"},
    out,
    "train-catboost-h1",
)["run_id"]
```

**Versões gravadas em cada run:** `atlas.git_sha` (a imagem, onde está o pacote) e `atlas.notebook_sha` (o notebook). Em hml e prod, o `atlas.notebook_sha` é o commit que o `git-sync` clonou; fora disso vale `local`. O notebook executado, com as saídas de cada célula, fica como artefato `notebook/` da run.

**Como cada modelo é treinado** (`forecast/base.py`, `run_model`):

1. **Snapshot:** baixa o snapshot da run `dataset`. O BigQuery nunca é relido.
2. **Janelas:** descarta as 8 semanas imaturas e monta janelas N→H em `log1p(incidência)`. Cada passo da janela leva também os **canais do SINAN** como taxa por 100 mil em `log1p` (`notified_cases`, `discarded_cases`, `confirmed_cases`, `alarm_cases`, `severe_cases`, `inconclusive_cases`, `investigation_cases`, `deaths`) e o relevo da UF (`mean_elevation_m`, `mean_slope_deg`), só com semanas até a origem. `--features` troca a lista (separada por vírgula); `--features -` volta a só a incidência. CatBoost, SVR, LSTM e Ensemble usam todos os canais; Chronos e o baseline bayesiano seguem só com a incidência.
3. **Divisão:** pela data do alvo, com teste = últimas 52 semanas, validação = 52 anteriores e treino = o resto. O `TrainOnlyScaler` é ajustado só no treino.
4. **Ajuste:** `fit` com o treino; validação só para early stopping e seleção.
5. **Previsões:** de validação e teste, com corte em 0. Para CatBoost, SVR e LSTM, também as previsões out-of-fold (3 blocos rolling origin de 52 semanas).
6. **Registro:** métricas por UF e médias (NRMSE, MAE, RMSE, R², cobertura do intervalo), artefatos `predictions.parquet`, `metrics_by_uf.csv` e `oof_predictions.parquet`, e o modelo como `atlas-br-<modelo>-h<H>` com o sufixo do ambiente: `_dev` em dev (alias `@dev` automático), `_hml` em hml e sem sufixo em prod. Assim os três ambientes podem dividir um MLflow sem misturar versões; a exportação e a decisão de treino da `etl_brasil` usam o mesmo nome.

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
