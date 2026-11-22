# Notebooks dos modelos de previsão

Cada modelo de previsão de dengue por UF é um notebook **autocontido**: lê a gold, monta as janelas, define e treina o modelo, avalia por UF, gera as previsões e registra a run no MLflow, com a saída impressa em cada etapa. Dá para rodar **na mão**, célula por célula, ou pelo Airflow (papermill), que só troca os valores da célula de parâmetros.

| Pasta | Modelo | Família | Previsões out-of-fold (ensemble) |
|---|---|---|---|
| [`catboost/`](catboost/catboost.ipynb) | CatBoost | gbm | sim |
| [`svr/`](svr/svr.ipynb) | SVR | kernel | sim |
| [`lstm/`](lstm/lstm.ipynb) | LSTM (PyTorch) | rnn | sim |
| [`baseline_bayes/`](baseline_bayes/baseline_bayes.ipynb) | Baseline bayesiano (PyMC) | bayes | não (comparador) |
| [`chronos/`](chronos/chronos.ipynb) | Chronos-Bolt zero-shot | foundation | não (comparador) |
| [`ensemble/`](ensemble/ensemble.ipynb) | Random Forest sobre as OOF de catboost, svr e lstm | stacking | — |

Cada pasta tem o notebook (`<modelo>.ipynb`) e o `requirements.txt` dele. Os notebooks ficam no Git **sem saídas**; as saídas impressas aparecem quando o notebook roda (e o Airflow guarda o notebook executado como artefato da run).

## Estrutura de cada notebook

As seções aparecem na mesma ordem nos seis notebooks. Só a seção 4 muda de um para outro.

| # | Seção | O que faz | Tag |
|---|---|---|---|
| 0 | Parâmetros | valores padrão que bastam para rodar na mão; o papermill os sobrescreve | `parameters` |
| – | Requisitos | lista `PACOTES` (o mesmo conteúdo do `requirements.txt`) | `pacotes` |
| 1 | Ambiente | imprime as versões dos pacotes, define threads, configuração e MLflow | `comum` |
| 2 | Dados | lê a gold (ou `painel_parquet`), monta o painel e registra a versão dos dados | `comum` |
| 3 | Janelas e divisão | descarta semanas imaturas, janelas N→H, cortes treino/validação/teste, escala só no treino | `comum` |
| 4 | **Modelo** | definição e treino do modelo (**só deste notebook**) | `modelo` |
| 5 | Avaliação | previsões de validação e teste, métricas por UF, cobertura do intervalo | `comum` |
| 6 | Out-of-fold | blocos rolling origin (só catboost, svr e lstm) | `comum` |
| 7 | Futuro e figuras | previsão das próximas semanas e figuras da run | `comum` |
| 8 | Registro | run no MLflow, modelo registrado e o resultado do passo | `comum` |

O MLflow só é aberto na seção 8: as seções 1 a 7 acumulam tudo em variáveis, então quem explora na mão não deixa runs pela metade.

## Parâmetros

| Parâmetro | Para quê |
|---|---|
| `horizon`, `window`, `seed` | semanas à frente (1 a 4), semanas de histórico (12) e semente (42) |
| `features` | vazio usa os canais do SINAN e o relevo; `-` usa só a incidência; ou uma lista separada por vírgula |
| `pipeline_run` | valor da tag `atlas.pipeline_run` (a DAG passa o `run_id` dela) |
| `data_version_esperada` | a DAG passa a versão da gold do início da execução; se a gold mudou, o notebook falha antes de criar a run |
| `painel_parquet` | usa um painel salvo (parquet) em vez de ler o BigQuery |
| `fonte` | tabela `projeto.dataset.tabela` no lugar da gold do ambiente |
| `register` | registra o modelo como `atlas-br-<modelo>-h<horizonte>` (com o sufixo do ambiente) |
| `result_path`, `out_dir` | definidos pelo Airflow; o notebook grava o resultado (`run_id` e métricas) em `result_path` |
| hiperparâmetros | cada modelo acrescenta os seus (`iterations`, `n_iter`, `max_epochs`, `draws`…) |

**Regra da célula de parâmetros:** os comentários dela não podem ter vírgula nem ponto e vírgula. O papermill usa uma expressão regular que se perde com eles e deixa o parâmetro de fora (um teste confere).

## Rodar na mão

Sem Airflow, abra o notebook (Jupyter, VS Code) e execute as células em ordem. Precisa de:

- as credenciais do BigQuery (`GOOGLE_APPLICATION_CREDENTIALS`) e do MLflow (`MLFLOW_TRACKING_URI`, e usuário e senha se o servidor tiver login), ou `painel_parquet` apontando para um painel salvo;
- o ambiente com os pacotes do `requirements.txt` da pasta (`uv sync --extra models` em `ml/` instala todos).

Para testar sem nenhuma credencial:

```sh
cd ml
export MLFLOW_ALLOW_FILE_STORE=true MLFLOW_TRACKING_URI=./mlruns ATLAS_GIT_SHA=local
uv run --extra models python -c "from atlas_ml.forecast.synthetic import synthetic_panel as s; s(n_weeks=320).to_parquet('painel.parquet', index=False)"
uv run --extra models papermill notebooks/catboost/catboost.ipynb saida.ipynb -p painel_parquet painel.parquet -p iterations 300
```

O ensemble precisa dos `run_id` das três bases (`-p base_runs '{"catboost": "<id>", "svr": "<id>", "lstm": "<id>"}'`), treinadas no mesmo horizonte.

## Código comum e ferramentas

O código das seções comuns é **idêntico nos seis notebooks** (cada um é autocontido, sem módulo compartilhado). Para a duplicação não divergir, `_ferramentas/` guarda a fonte e três verificações. **Os notebooks rodam sem essa pasta**; ela é só de desenvolvimento.

| Comando (em `ml/`, com `uv run --extra models`) | O que faz |
|---|---|
| `python notebooks/_ferramentas/sincronizar_comum.py` | reescreve as células `comum` dos seis notebooks a partir de `_ferramentas/comum.py` |
| `python notebooks/_ferramentas/sincronizar_comum.py --verificar` | só confere (não escreve) |
| `python notebooks/_ferramentas/verificar_comum.py` | CI: as células comuns são idênticas à fonte, e nenhum notebook importa `atlas_ml.models` nem `atlas_ml.forecast` (só `config`, `tracking`, `registry` e `data.bigquery`) |
| `python notebooks/_ferramentas/verificar_requirements.py` | CI: cada `requirements.txt` é satisfeito pelo `ml/uv.lock`, os imports do notebook estão declarados e `PACOTES` bate com o arquivo |

**Alterar o código comum:** edite `_ferramentas/comum.py` e rode `sincronizar_comum.py`. Se editar uma célula `comum` direto no notebook, leve a mudança para o `comum.py` (o CI falha enquanto os dois diferirem).

**Alterar um modelo:** edite as células de tag `modelo` do notebook. Se ele passar a usar um pacote novo, acrescente-o ao `requirements.txt` e à lista `PACOTES` (o CI confere); se o pacote não estiver no `ml/uv.lock`, inclua-o em `ml/pyproject.toml` e atualize o lock.

## Contrato com quem consome as runs

Cada run grava, no experimento `atlas/dengue-forecast-br`: as tags `atlas.env`, `atlas.git_sha`, `atlas.image_tag`, `atlas.data_version`, `atlas.pipeline_run`, `atlas.model_family`, `atlas.forecast_model`, `atlas.horizon` e `atlas.notebook_sha`; os parâmetros (a configuração e os `model.*`); as métricas `<split>_<métrica>_mean`, `oof_*`, `fit_seconds` e a cobertura do intervalo; e os artefatos `predictions.parquet`, `metrics_by_uf.csv`, `future_predictions.parquet`, `oof_predictions.parquet` (modelos-base), `figures/` e o modelo registrado. A comparação, a exportação para o BigQuery e a decisão de treino do `etl_brasil` leem exatamente isso.

`atlas.data_version` tem a forma `query:<hash>+<tabela>@<última modificação>`: o `etl_brasil` procura a versão da gold dentro dela.
