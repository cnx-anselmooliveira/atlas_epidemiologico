# Proposal

## Why

Hoje os seis modelos de previsão são tarefas de uma DAG só (`atlas_dengue_forecast_br`), então não dá para treinar, depurar ou repetir um modelo sem rodar a execução inteira (até 12 h na VPS de hml). Além disso, cada ajuste numa DAG ou num notebook espera o CI completo no PR `dev` → `hml` (~8 min: build das seis imagens, e2e da plataforma, frontend, backend). Mudar um notebook ainda dispara o `ml.yml` (~20 min, build das imagens `ml` e `ml-notebook`). Isso tudo para um código que chega ao Airflow pelo git-sync, sem imagem nova.

## What Changes

- **Uma DAG por modelo:** `atlas_forecast_baseline_bayes`, `atlas_forecast_chronos`, `atlas_forecast_catboost`, `atlas_forecast_svr`, `atlas_forecast_lstm` e `atlas_forecast_ensemble`. Cada uma treina os horizontes pedidos com o notebook do modelo e registra no MLflow. Todas têm os mesmos parâmetros (horizontes, janela, semente, fonte) e os parâmetros de execução opcionais (`pipeline_run`, versão da gold, versão dos notebooks).
- **Disparada sozinha** (decisão do usuário), a DAG de um modelo treina e registra; não compara nem exporta. O ensemble sozinho usa as runs concluídas mais recentes de CatBoost, SVR e LSTM com a mesma versão da gold, e falha no horizonte em que faltar alguma.
- **`atlas_dengue_forecast_br` vira o orquestrador** do processo completo: fixa as versões da gold e dos notebooks, dispara as cinco DAGs de base, depois a do ensemble, e então compara os modelos por horizonte e dispara a exportação. Cada DAG de modelo é disparada individualmente e acompanhada até o fim, sem ocupar vaga de worker enquanto espera. **BREAKING** para quem lê a estrutura da DAG: as tarefas `horizonte.train_*` saem dela. O `dag_id`, os parâmetros e o disparo pela `etl_brasil` não mudam.
- **CI com via rápida** (decisão do usuário): um PR ou push que muda só DAGs (e os testes delas), notebooks, documentação ou OpenSpec roda lint, verificação dos notebooks, integridade das DAGs, segredos, OpenSpec, stack e promoção. Ficam de fora o build das imagens, o e2e da plataforma, o frontend, o backend e os testes do pacote `ml`. O check `ci-ok` aceita esses pulos só na via rápida. Mudanças em dependências (`pyproject.toml`/`uv.lock` do dbt), em `ml/src`, nos Dockerfiles ou nos workflows continuam no pipeline completo.
- **`ml.yml` deixa de rodar por notebook:** as imagens `ml` e `ml-notebook` não são reconstruídas por mudanças só em `ml/notebooks/**`.
- **Teste rápido local das DAGs:** um comando que roda os testes de DAG na imagem local do Airflow com as DAGs do disco, em segundos, antes de abrir o PR.

## Capabilities

### New Capabilities
- `forecast-model-dags`: as DAGs independentes por modelo (parâmetros, horizontes, recursos, execução sozinha e pelo orquestrador, resolução das runs de base do ensemble) e a orquestração do processo completo pela `atlas_dengue_forecast_br`.

### Modified Capabilities
- `notebook-pipeline-execution`: a execução de cada notebook deixa de ser tarefa da DAG única e passa para a DAG do modelo. A tarefa de início e a fixação das versões ficam no orquestrador, e a comparação continua como código da DAG orquestradora. Vem da `self-contained-model-notebooks`, ainda não arquivada.
- `ci-test-pipeline`: a cobertura completa deixa de ser obrigatória em toda execução; entra a via rápida para mudanças só em DAGs, notebooks e documentação. Vem da `add-ci-test-pipeline`, ainda não arquivada.
- `airflow-dag-delivery`: a regra "imagem não precisa reconstruir por DAG ou notebook" passa a valer também para as imagens `ml` e `ml-notebook`. Vem da `move-forecast-to-notebook-pipeline`, ainda não arquivada.

## Impact

- DAGs: `airflow/dags/atlas_dengue_forecast_br.py` (orquestrador), seis arquivos novos `airflow/dags/atlas_forecast_<modelo>.py` e um módulo comum novo em `airflow/dags/atlas_ingest/` com a fábrica das DAGs de modelo.
- Testes: `airflow/tests/test_dags.py` (estrutura nova, parâmetros, pools, regras de disparo).
- CI: `.github/workflows/ci.yml` (detecção da via rápida, jobs condicionais, `ci-ok`), `.github/workflows/ml.yml` (paths), script novo em `platform/ci/` para o teste local das DAGs.
- Docs: `airflow/README.md`, `ml/README.md`, `deploy/README.md`, `CHANGELOG.md`.
- Operação: em hml aparecem seis DAGs novas. Elas nascem despausadas (`is_paused_upon_creation=False`; não têm agendamento, então só rodam por disparo), senão o orquestrador esperaria para sempre por runs na fila. O pool `atlas_treino` continua limitando os treinos. Antes disso, o `airflow-dag-processor` de hml precisa estar na imagem atual (incidente de 28/11: ele ainda serializava a DAG antiga com `prepare`).
- Fora do escopo: o Jupyter de hml continua com os notebooks da última imagem `ml-notebook` até o próximo build dela; nenhuma mudança nos notebooks, na exportação ou na `etl_brasil`.
