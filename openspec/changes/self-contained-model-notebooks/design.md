# Design

## Context

Motivação e escopo: ver `proposal.md`. Estado atual relevante:

- **O modelo vive no pacote.** `ml/src/atlas_ml/forecast/` (≈1.700 linhas: `dataset`, `windows`, `splits`, `evaluate`, `base`, `compare`, `figures`, `export_read`, `config`, `synthetic`, `threads`, `notebook`) e `ml/src/atlas_ml/models/<modelo>/model.py` (86 a 224 linhas cada) têm todo o código. `base.run_model` faz o fluxo comum: snapshot → janelas → divisão → ajuste → previsões de validação e teste → OOF → métricas → artefatos → futuro → figuras → modelo → registro.
- **O notebook atual só chama.** `ml/notebooks/forecast_pipeline.ipynb` (passos `prepare`, `train`, `compare`) executa `atlas_ml`, e `notebook.run_step` o roda pelo Airflow (papermill, `result.json`, notebook executado anexado à run, diretório por execução, conferência da versão do notebook).
- **Quem consome as runs.** A comparação lê `atlas.pipeline_run` e `atlas.horizon`; a exportação lê `atlas.model_family`, `atlas.data_version`, parâmetros, métricas e os artefatos (`predictions.parquet`, `future_predictions.parquet`, `metrics_by_uf.csv`, `figures/`); o `etl_brasil` decide o retreino pela `atlas.data_version` (a versão `<tabela>@<modificação>` da gold aparece nela); o ensemble lê `oof_predictions.parquet`, `predictions.parquet` e `future_predictions.parquet` das três bases.
- **Dependências por modelo (hoje no grupo `models`):** `baseline_bayes` (PyMC, nutpie, h5netcdf, h5py), `catboost`, `svr` (scikit-learn, scipy, skops), `lstm` (PyTorch), `chronos` (PyTorch, chronos-forecasting), `ensemble` (scikit-learn). Todas num só venv (`/opt/atlas-ml`), travado por `ml/uv.lock`.
- **Plataforma que não é modelo.** `atlas_ml.config` (configuração por ambiente), `tracking.atlas_run` (tags `atlas.*` obrigatórias), `registry` (registro e promoção) e `data/bigquery` servem também a outros comandos (`train example`, `promote`).

## Goals / Non-Goals

**Goals:**
- Cada modelo é um notebook que se lê e roda passo a passo na mão, com o código, os requirements e as saídas.
- O Airflow executa esse mesmo notebook, e quem consome as runs não percebe diferença.
- A duplicação do código comum não vira divergência.

**Non-Goals:**
- Mudar métodos, hiperparâmetros ou features.
- Reescrever a plataforma (`config`, `tracking`, `registry`, `data/bigquery`).
- Um venv por modelo (decisão: venv comum).

## Decisions

### 1. Layout e estrutura de cada notebook
`ml/notebooks/<modelo>/<modelo>.ipynb` e `ml/notebooks/<modelo>/requirements.txt`, para os seis modelos. Todos seguem a mesma ordem de seções (cabeçalhos em markdown), para a duplicação ser previsível:

| # | Seção | Conteúdo | Tag |
|---|---|---|---|
| 0 | Parâmetros | célula `parameters` com padrões que rodam sozinhos | `parameters` |
| 1 | Ambiente | versões dos pacotes do `requirements.txt` impressas; threads; configuração e MLflow | `comum` |
| 2 | Dados | gold do ambiente (ou `painel_parquet`), painel UF × semana, `data_version`, conferência de `data_version_esperada` | `comum` |
| 3 | Janelas e divisão | descarte das semanas imaturas, janelas N→H, cortes treino/validação/teste, escalonador só no treino | `comum` |
| 4 | **Modelo** | definição, treino e previsão do modelo (**só deste notebook**) | — |
| 5 | Avaliação | previsões de validação e teste, métricas por UF e médias, cobertura do intervalo | `comum` |
| 6 | Out-of-fold | blocos rolling origin (só `catboost`, `svr`, `lstm`), reusa a seção 4 | `comum` + 4 |
| 7 | Futuro e figuras | previsão das próximas semanas, figuras comuns e da família | `comum` |
| 8 | Registro | run, parâmetros, métricas, artefatos, modelo registrado, `result.json` | `comum` |

A célula de cada seção imprime o que fez (tamanhos, cortes, métricas). Rodar célula por célula funciona porque as variáveis fluem de uma seção para a seguinte e nada depende de ordem fora da sequência. O MLflow só é aberto na seção 8 (as seções 1 a 7 acumulam parâmetros, métricas e arquivos em variáveis e numa pasta temporária), para quem explora na mão não deixar runs pela metade; o `run_id` é impresso no fim.

### 2. Código comum duplicado, com ferramenta de sincronização
Escolha do usuário: cada notebook tem o código comum, sem módulo compartilhado. Para a duplicação não divergir:
- as células comuns levam a tag `comum`;
- `ml/notebooks/_ferramentas/sincronizar_comum.py` (desenvolvimento, **não** é dependência de execução) mantém uma fonte única das células comuns (`ml/notebooks/_ferramentas/comum.py`, com um bloco por seção) e as reescreve nos seis notebooks;
- `ml/notebooks/_ferramentas/verificar_comum.py` roda no CI: compara, byte a byte, cada célula `comum` entre os seis notebooks e com a fonte, e falha apontando a célula e os notebooks que divergem.
Quem edita um notebook à mão altera a célula e depois roda a sincronização (ou o CI avisa).

*Alternativas descartadas:* módulo `_comum.py` importado (menos duplicação, mas o notebook deixa de ser autocontido) e manter o código no pacote (é o que o usuário não quer).

### 3. Plataforma importada, modelo não
Os notebooks podem importar só o que não é modelo: `atlas_ml.config.load_settings` (ambiente, `git_sha`, `image_tag`), `atlas_ml.tracking.atlas_run` (tags `atlas.*` obrigatórias, que a spec de ciclo de vida de modelos exige validar antes de abrir a run) e `atlas_ml.registry.register_model`. Janelas, divisão, métricas, figuras, treino e previsão ficam no notebook. O teste estático da tarefa 1.3 falha se um notebook importar `atlas_ml.models` ou `atlas_ml.forecast`.

### 4. Dados e versão da gold, sem snapshot
- Cada notebook lê `gold_dengue_casos_provaveis_uf_semanal` do ambiente (`gold`, `gold_hml`, `gold_prod`, mesma regra do dbt e do Airflow) com `google-cloud-bigquery` e monta o painel (série regular por UF, semanas faltantes com zero e marca `filled`, `incidence`, `uf_code`, canais do SINAN e relevo como na change `add-dengue-forecast-models`).
- `atlas.data_version` = `<tabela>@<última modificação ISO>` (a mesma forma de `table_version`), de modo que o `etl_brasil` reconheça a versão (ele a procura dentro da tag).
- Sem snapshot, a garantia de "todos os modelos da execução veem os mesmos dados" vira uma conferência: a tarefa `iniciar_execucao` lê a versão da gold e a passa como `data_version_esperada`; o notebook falha, antes de criar a run, se a versão atual for outra. A gold só muda quando o dbt roda, e o `etl_brasil` não treina enquanto o dbt roda; o risco é um disparo manual no meio de uma reconstrução.
- `painel_parquet` (opcional) usa um painel salvo no lugar do BigQuery, para testes e reprocessamento; o `data_version` vira `parquet:<hash>`.

### 5. Contrato com o MLflow
Cada notebook grava a run exatamente como `base.run_model` faz hoje: experimento oficial (`atlas/dengue-forecast-br`, ou o configurado por `ATLAS_FORECAST_EXPERIMENT`), tags, parâmetros (`cfg` e `model.*`), métricas (`<split>_<métrica>_mean`, `oof_*`, `fit_seconds`, `oof_seconds`, cobertura), artefatos (`predictions.parquet`, `metrics_by_uf.csv`, `future_predictions.parquet`, `oof_predictions.parquet`, `figures/` com `captions.json`), modelo no formato de cada família e registro `atlas-br-<modelo>-h<H><sufixo>` com o alias do ambiente. `atlas.dataset_run` deixa de existir (não há snapshot); nenhum consumidor a lê. A equivalência é verificada contra o pacote (tarefa de cada modelo).

### 6. Requirements e venv comum
- `requirements.txt` por modelo, com faixa de versão (`catboost>=1.2`, `torch>=2.5` etc.), mais o que todos usam (`mlflow-skinny`, `pandas`, `pyarrow`, `google-cloud-bigquery`, `db-dtypes`, `numpy`, `matplotlib`).
- O venv comum da imagem (`ml/uv.lock`, grupo `models`) não muda; `ml/notebooks/_ferramentas/verificar_requirements.py` roda no CI e confere (a) que cada `requirements.txt` é satisfeito pelas versões do `uv.lock` e (b) que os imports de cada notebook (via `ast`) pertencem à biblioteca padrão, ao `requirements.txt` ou à plataforma permitida.
- A primeira célula imprime a versão instalada de cada pacote da lista, para quem roda na mão saber o ambiente.

*Alternativas descartadas:* venv por modelo na imagem (isolamento, mas +2 GB e seis builds) e `%pip install` no notebook (rede e versões imprevisíveis a cada execução).

### 7. Execução pelo Airflow
- `atlas_ml/forecast/notebook.py` ganha `run_model_notebook(model, params, out_dir, name, expected_sha)`, que escolhe `<ATLAS_NOTEBOOKS_DIR>/<modelo>/<modelo>.ipynb`, confere a versão do notebook, executa (papermill, `result.json`, `cwd` do chamador) e anexa o notebook executado à run. O resto (`run_notebook`, `run_dir`, `clean_dir`, `check_notebook_version`, `attach_executed_notebook`, `notebook_sha`) já existe e é reaproveitado.
- DAG: `iniciar_execucao` cria o diretório e registra a versão do notebook **e a da gold**; as tarefas de modelo recebem `out_dir`, `notebook_sha` e `data_version`; sem `prepare`; `comparar` vira função Python da DAG (corpo autocontido, porque roda no venv do `atlas_ml` como `external_python`), com a lógica de `forecast/compare.py` copiada; `limpar` e `exportar` ficam.

### 8. Testes e transição
- **Execução:** `ml/tests/notebooks/test_modelos.py` executa cada notebook no painel sintético (`painel_parquet`), MLflow em arquivo e sem BigQuery, e confere run, tags, métricas, artefatos e `result.json`.
- **Equivalência:** durante a transição, o mesmo teste treina o mesmo painel pelo pacote e compara `test_nrmse_mean` (1e-6; 2% para LSTM e Chronos).
- **Estáticos:** imports proibidos (tarefa 1.3), células comuns idênticas e requirements.
- Os testes unitários do pacote (janelas, divisão, métricas, modelos) ficam até o último grupo; ao remover o código, saem junto, e a cobertura passa a ser a execução dos notebooks.

### 9. Remoção do código antigo (último grupo, depois de validar em hml)
Saem de `atlas_ml`: `forecast/{dataset,windows,splits,evaluate,base,compare,figures,export_read,config,synthetic}.py`, `models/*` e os testes que cobriam esse código; o `forecast_pipeline.ipynb` e `notebook.run_step`. Ficam: `forecast/notebook.py` (executor), `forecast/threads.py`, `config`, `tracking`, `registry`, `data/bigquery` e o CLI. A exportação (`process_forecast_export_atlas`) lê as runs por `forecast/export_read.py`: esse arquivo precisa mover para a DAG antes de sair (tarefa 10.2).

## Risks / Trade-offs

- **[Duplicação do código comum nos seis notebooks]** → células `comum` idênticas, ferramenta de sincronização e verificação no CI; revisão de PR olha a diferença só do bloco do modelo.
- **[Sem unit tests do código comum depois da remoção do pacote]** → o teste de execução dos seis notebooks cobre o fluxo; a equivalência com o pacote antes da remoção garante que não houve regressão.
- **[Notebook longo é difícil de revisar em PR (diff de JSON)]** → ferramenta `verificar_comum` aponta só o que diverge; notebooks sem saídas (`nbstripout`) mantêm o diff pequeno.
- **[Gold muda durante a execução e quebra a garantia de dados únicos]** → conferência de `data_version_esperada` falha antes da run.
- **[Treino longo (LSTM, Chronos, Bayes) na mão]** → ok para quem escolhe rodar; na DAG nada muda (tempos máximos e pool iguais).
- **[Regressão numérica ao reescrever]** → equivalência com o pacote na semente fixa, por modelo, antes de remover o código antigo.
- **[Consumidor depende de um detalhe do contrato (tag, artefato)]** → teste que lê a run como a exportação e a comparação leem; o contrato da spec lista tudo.
- **[Sobreposição com `move-forecast-to-notebook-pipeline`]** → esta mudança supersede os grupos 2 e 3 dela e a decisão 1 do design; atualizar aquela change com `openspec-update-change` depois (ver o follow-up em `tasks.md`).

## Migration Plan

1. Criar a estrutura e as ferramentas (grupo 1); fazer o `catboost` como piloto, que fixa as células comuns (grupo 2); depois `svr`, `lstm`, `baseline_bayes`, `chronos` e `ensemble`, cada um com seus testes e a equivalência.
2. Trocar a DAG para executar os notebooks (grupo 8), ainda com o pacote no lugar.
3. Validar em hml: um modelo leve, depois os seis; conferir que a exportação e o `etl_brasil` leem as runs sem mudança; rodar um notebook na mão no Jupyter de hml.
4. Remover o código antigo (grupo 10).
5. **Reversão:** até a remoção, voltar a DAG ao commit anterior (o pacote ainda tem o código); depois da remoção, `git revert` do commit do grupo 10.

## Open Questions

- **Figuras:** manter as três figuras por modelo como estão (duas comuns e uma da família) ou mostrá-las também inline no notebook; as duas coisas são compatíveis e a segunda não muda o contrato.
- **Tamanho do notebook executado no MLflow:** se as saídas impressas ficarem grandes (treinos com muito log), limitar a verbosidade do treino (ex.: CatBoost de 100 em 100 iterações).
