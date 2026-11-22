# Proposal

## Why

O notebook de previsão atual (`ml/notebooks/forecast_pipeline.ipynb`) só orquestra: quem treina é o pacote `atlas_ml`, importado como modelo pronto. Quem quer entender um modelo, mudar um passo ou acompanhar o treino precisa abrir código Python dentro do pacote, e não consegue rodar o modelo "na mão", célula por célula, vendo o que acontece em cada etapa.

Queremos que cada modelo seja um notebook que se lê de cima para baixo e roda passo a passo: o código do modelo, as dependências dele e as saídas impressas ficam no próprio notebook. O Airflow executa esses mesmos notebooks.

## What Changes

- **Um notebook por modelo**, em `ml/notebooks/<modelo>/<modelo>.ipynb`: `baseline_bayes`, `catboost`, `svr`, `lstm`, `chronos` e `ensemble`. Cada um é **autocontido**: lê a gold, monta as janelas, divide treino/validação/teste, define e treina o modelo, avalia por UF, gera as previsões (validação, teste, out-of-fold e futuro), as figuras e registra tudo no MLflow, com as saídas impressas em cada etapa (tamanhos, cortes, hiperparâmetros, métricas, caminhos, `run_id`). Nenhuma célula importa a implementação do modelo pronta de `atlas_ml`.
- **Roda na mão e pelo Airflow.** Os parâmetros ficam numa célula `parameters` com valores padrão que funcionam sozinhos (horizonte 1, janela 12, semente 42); o papermill os sobrescreve. Sem Airflow, basta executar as células em ordem.
- **Requirements por modelo.** Cada pasta tem um `requirements.txt` com o que o notebook usa. A imagem continua com um venv comum (a união), e o CI confere que o venv satisfaz cada lista e que os imports do notebook estão declarados.
- **Código comum duplicado de propósito.** Dados, janelas, divisão, métricas e MLflow aparecem em cada notebook, em células marcadas como `comum`. Para a duplicação não divergir, uma ferramenta de desenvolvimento sincroniza essas células e o CI falha se elas diferirem entre os seis notebooks. Os notebooks não dependem dessa ferramenta para rodar.
- **Sem passo de snapshot.** Cada notebook lê a gold direto. A execução da DAG registra a versão da gold no início e cada notebook falha se ela mudar no meio (substitui a garantia do snapshot único).
- **DAG.** A forma de `atlas_dengue_forecast_br` não muda (bases em paralelo, ensemble depois de catboost, svr e lstm, comparação com `all_done`, 4 horizontes, pool `atlas_treino`). Cada tarefa de modelo executa o notebook do modelo; a tarefa `prepare` some; a comparação passa a ser código Python da própria DAG.
- **Mesmo contrato com quem consome as runs.** Experimento, tags `atlas.*`, parâmetros, métricas, artefatos e nomes registrados continuam como estão, para a comparação, a exportação para o BigQuery e a decisão de treino do `etl_brasil` seguirem funcionando.
- **Transição segura.** Os notebooks entram ao lado do pacote atual e são validados contra ele (mesmas métricas com a mesma semente). Só depois de validados em hml, num último grupo de tarefas, saem o código dos modelos em `atlas_ml`, o `forecast_pipeline.ipynb` e os testes unitários antigos.
- Fora de escopo: mudar métodos, hiperparâmetros ou features dos modelos; o serviço Jupyter de exploração e a entrega das DAGs por `git-sync` (da change `move-forecast-to-notebook-pipeline`); mexer nos módulos de plataforma de `atlas_ml` (`config`, `tracking`, `registry`, `data/bigquery`), que os notebooks podem importar.

## Capabilities

### New Capabilities
- `model-notebooks`: o notebook autocontido de cada modelo (parâmetros, passos, saídas impressas, requirements, contrato com o MLflow e equivalência com o pacote durante a transição).
- `notebook-pipeline-execution`: a DAG executando os notebooks dos modelos, a versão da gold fixada na execução, a comparação como código da DAG e a leitura dos notebooks do clone.

### Modified Capabilities
<!-- Nenhuma em openspec/specs/ (ainda não há specs arquivadas). Substitui, nas changes em andamento, o notebook único e o `run_step` da `move-forecast-to-notebook-pipeline` e o requisito de "mesmo snapshot" da `forecast-training-dag` (`add-dengue-forecast-models`). -->

## Impact

- **Código**:
  - novos `ml/notebooks/<modelo>/<modelo>.ipynb` e `requirements.txt` (6 modelos);
  - ferramenta de desenvolvimento para sincronizar e verificar as células comuns, e verificação dos requirements;
  - `airflow/dags/atlas_dengue_forecast_br.py` (executa o notebook de cada modelo, sem `prepare`, comparação interna) e `airflow/tests/test_dags.py`;
  - `ml/src/atlas_ml/forecast/notebook.py` ganha a execução por modelo; no fim, saem `forecast/{dataset,windows,splits,evaluate,base,compare,figures,export_read,synthetic,config}.py` e `models/*` do pacote, junto dos testes que cobriam esse código.
- **Imagem e CI**: o venv comum do `atlas_ml` não muda de conteúdo; `ml.yml` e `ci.yml` ganham a execução de cada notebook num painel sintético e as duas verificações.
- **Notebooks no Git**: continuam sem saídas (`nbstripout`); as saídas impressas aparecem quando o notebook roda (à mão ou no notebook executado que a DAG guarda na run).
- **Contrato**: sem mudança em quem consome as runs (MLflow, exportação, `etl_brasil`).
- **Sobreposição**: reabre a `move-forecast-to-notebook-pipeline` (grupos 2 e 3 e a decisão 1 do design), que deve ser atualizada depois com `openspec-update-change`; mantém intactos o `git-sync`, o filtro de caminhos do CI e o Jupyter dela.
