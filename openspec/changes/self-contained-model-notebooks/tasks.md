# Tasks

## 1. Estrutura, convenções e verificações

- [x] 1.1 Definir o padrão dos notebooks em `ml/notebooks/README.md`: pasta `ml/notebooks/<modelo>/`, ordem das seções (0 parâmetros a 8 registro), tags `parameters` e `comum`, parâmetros com padrões que rodam sozinhos (`horizon`, `window`, `seed`, `features`, `pipeline_run`, `data_version_esperada`, `painel_parquet`, `result_path`, `out_dir`) e como rodar na mão; verificar que o texto lista as seis pastas e as nove seções
- [x] 1.2 Criar `ml/notebooks/_ferramentas/comum.py` (fonte única das células comuns, um bloco por seção) e `sincronizar_comum.py`, que reescreve as células `comum` nos notebooks existentes sem tocar nas demais; verificar com teste em notebooks de exemplo: alterar a fonte e sincronizar muda só as células `comum`, e rodar duas vezes não muda nada
- [x] 1.3 Criar `verificar_comum.py` (as células `comum` são idênticas nos seis notebooks e à fonte) e o teste estático de imports (nenhum notebook de modelo importa `atlas_ml.models` nem `atlas_ml.forecast`, só `config`, `tracking`, `registry` e `data/bigquery` entre os de plataforma); verificar com testes: uma célula alterada em um só notebook falha apontando a célula e o notebook, e um import proibido falha apontando o notebook
- [x] 1.4 Criar `verificar_requirements.py` (cada `requirements.txt` é satisfeito pelas versões do `ml/uv.lock`, e os imports de cada notebook, lidos com `ast`, são da biblioteca padrão, do `requirements.txt` ou da plataforma permitida); verificar com testes: um import não declarado falha apontando o notebook e o pacote, e uma versão fora do lock falha apontando o modelo e o pacote
- [x] 1.5 Ligar as três verificações ao CI (`ci.yml`) e à seção de desenvolvimento do `ml/README.md`; verificar rodando os três comandos localmente (devem passar quando houver os seis notebooks; antes disso, passam sobre os notebooks existentes)

## 2. Notebook do CatBoost (piloto das células comuns)

- [x] 2.1 Criar `ml/notebooks/catboost/catboost.ipynb` e `requirements.txt` com as seções 0 a 8 (leitura da gold e `painel_parquet`, janelas e divisão, `CatBoostRegressor` com `uf_code` categórico e parada antecipada na validação, avaliação por UF, out-of-fold, futuro, figuras comuns e importância de variáveis, registro `atlas-br-catboost-h<H>`), com saídas impressas em cada seção e as células comuns marcadas; verificar executando as células em ordem num painel sintético e conferindo a run, as tags `atlas.*`, as métricas, os cinco artefatos e o `result.json`
- [x] 2.2 Rodar `sincronizar_comum.py` para fixar as células comuns do piloto como fonte e `verificar_comum.py` sobre ele; verificar que a fonte (`comum.py`) tem exatamente as células `comum` do notebook do CatBoost
- [x] 2.3 Criar `ml/tests/notebooks/test_modelos.py` com o teste de execução (painel sintético, MLflow em arquivo, sem BigQuery, falha se uma célula levantar erro) e o de equivalência com o pacote (mesmo painel, configuração e semente: `test_nrmse_mean` com diferença de no máximo 1e-6); verificar `uv run pytest ml/tests/notebooks -k catboost` verde
- [x] 2.4 Garantir o contrato do MLflow no notebook (`atlas.data_version` no formato `<tabela>@<modificação>`, `data_version_esperada` que falha antes de criar a run, sem a tag `atlas.dataset_run`); verificar com testes: gold simulada com versão diferente falha sem criar run, e a tag aparece no formato esperado pelo `etl_brasil`

## 3. Notebook do SVR

- [x] 3.1 Criar `ml/notebooks/svr/svr.ipynb` e `requirements.txt` (pipeline `OneHotEncoder(uf_code)` + `StandardScaler` + `SVR`, `RandomizedSearchCV` com `TimeSeriesSplit(3)` só no treino, aumento de dados só no treino, `max_train_rows` e `max_iter` registrados, out-of-fold, figura de erro por semana, registro em skops com tipos confiáveis), com as células comuns idênticas às do piloto; verificar executando em ordem num painel sintético e rodando `verificar_comum.py`
- [x] 3.2 Acrescentar ao `test_modelos.py` a execução e a equivalência do SVR (1e-6); verificar `uv run pytest ml/tests/notebooks -k svr` verde

## 4. Notebook da LSTM

- [x] 4.1 Criar `ml/notebooks/lstm/lstm.ipynb` e `requirements.txt` (`Embedding(27, 4)` + `LSTM(60)` + `LSTM(20)` + `Linear`, Adam, parada antecipada na validação restaurando os melhores pesos, sementes e determinismo, aumento só no treino, out-of-fold, curva de aprendizado, modelo em pickle e `input_contract.json`), com as células comuns idênticas; verificar executando em ordem num painel sintético (rápido, com poucas épocas pelos parâmetros) e rodando `verificar_comum.py`
- [x] 4.2 Acrescentar ao `test_modelos.py` a execução e a equivalência da LSTM (2%) e a reprodutibilidade (duas execuções com a mesma semente, variação de no máximo 2%); verificar `uv run pytest ml/tests/notebooks -k lstm` verde

## 5. Notebook do baseline bayesiano

- [x] 5.1 Criar `ml/notebooks/baseline_bayes/baseline_bayes.ipynb` e `requirements.txt` (PyMC com binomial negativa e offset de população, efeitos de UF e de ano, Fourier semanal, termo defasado, NUTS pelo `nutpie`, `rhat_max`, `ess_bulk_min`, tag `atlas.converged`, intervalo de 95%, `idata.nc`, pyfunc), com as células comuns idênticas; verificar executando em ordem num painel sintético com poucos sorteios e rodando `verificar_comum.py`
- [x] 5.2 Acrescentar ao `test_modelos.py` a execução do baseline bayesiano (`lower ≤ previsto ≤ upper`, diagnósticos registrados) e a equivalência com o pacote (2%, porque a amostragem é estocástica com a mesma semente); verificar `uv run pytest ml/tests/notebooks -k bayes` verde

## 6. Notebook do Chronos

- [x] 6.1 Criar `ml/notebooks/chronos/chronos.ipynb` e `requirements.txt` (`chronos-bolt-small` zero-shot em CPU, contexto de até 512 semanas por UF a partir do painel completo, quantis 0,1 e 0,9 como intervalo de 80%, nome e revisão do checkpoint nos parâmetros, pyfunc), com as células comuns idênticas; verificar executando em ordem com um pipeline simulado no painel sintético (sem baixar o checkpoint) e rodando `verificar_comum.py`
- [x] 6.2 Acrescentar ao `test_modelos.py` a execução do Chronos com o pipeline simulado e a equivalência com o pacote (2%, com o mesmo pipeline simulado); verificar `uv run pytest ml/tests/notebooks -k chronos` verde

## 7. Notebook do ensemble

- [x] 7.1 Criar `ml/notebooks/ensemble/ensemble.ipynb` e `requirements.txt` (`RandomForestRegressor` sobre as previsões out-of-fold de `catboost`, `svr` e `lstm`, lidas pelos identificadores em `base_runs`, mais extrapolações polinomiais de graus 0, 1 e 2 da janela; intervalo pelos percentis 2,5 e 97,5 entre as árvores; recusa a treinar sem alguma base ou com horizonte diferente), com as células comuns idênticas; verificar executando em ordem sobre três runs-base geradas pelos notebooks do painel sintético e rodando `verificar_comum.py`
- [x] 7.2 Acrescentar ao `test_modelos.py` a execução do ensemble, a recusa sem uma base (falha antes de criar a run), nenhuma linha de treino do meta-modelo com previsão in-sample e a equivalência com o pacote (1e-6); verificar `uv run pytest ml/tests/notebooks -k ensemble` verde e `verificar_comum.py` e `verificar_requirements.py` verdes com os seis notebooks

## 8. DAG executando os notebooks dos modelos

- [x] 8.1 Acrescentar `run_model_notebook(model, params, out_dir, name, expected_sha)` a `atlas_ml/forecast/notebook.py` (escolhe `<ATLAS_NOTEBOOKS_DIR>/<modelo>/<modelo>.ipynb`, confere a versão do notebook, executa, anexa o notebook executado à run); verificar com testes: notebook ausente falha indicando o caminho, versão trocada falha antes de executar e o notebook executado vira artefato
- [ ] 8.2 Trocar `treinar` de `atlas_dengue_forecast_br.py` para executar o notebook do modelo (mesmo `external_python`, pool, tempos máximos, retentativas e regras de disparo), remover a tarefa `prepare` e fazer `iniciar_execucao` registrar também a versão da gold e passá-la como `data_version_esperada`; verificar com `airflow/tests/test_dags.py` atualizado (mesmas tarefas de modelo, dependências e pools, sem `prepare`) e com teste da falha por gold alterada
- [ ] 8.3 Mover a comparação para uma tarefa Python da DAG (corpo autocontido no `external_python`, com a lógica de `forecast/compare.py`: junta as runs por `atlas.pipeline_run` e `atlas.horizon`, registra a run `compare`, lista os ausentes); verificar com teste que usa MLflow em arquivo e um modelo ausente
- [ ] 8.4 Atualizar `airflow/README.md`, a docstring da DAG e o `ml/README.md` (notebooks por modelo, sem `prepare`, como rodar na mão, requirements, células comuns e as três verificações); verificar seguindo os comandos documentados com o painel sintético

## 9. Validação em hml e prod

- [ ] 9.1 Disparar `atlas_dengue_forecast_br` em hml com um modelo leve e um horizonte; verificar as runs com `atlas.pipeline_run`, `atlas.data_version` no formato esperado, o notebook executado como artefato, o diretório da execução removido ao final e a exportação disparada
- [ ] 9.2 Disparar a DAG completa em hml (seis modelos, quatro horizontes) e comparar as métricas de teste com as da última execução pelo pacote; verificar que a exportação e o `etl_brasil` leem as runs sem mudança e registrar as diferenças em `docs/referencias/resultados-forecast-br.md`
- [ ] 9.3 Rodar um notebook de modelo na mão no ambiente de exploração de hml, célula por célula, e conferir as saídas impressas e a run no experimento de exploração; verificar que não é preciso editar nada no notebook para isso
- [ ] 9.4 Repetir a validação em prod depois de aprovada em hml; verificar `git log -1 --stat` dos commits sem chaves ou credenciais

## 10. Remoção do código antigo (só depois da validação em hml)

- [ ] 10.1 Mover para o `process_forecast_export_atlas` a leitura das runs que hoje está em `forecast/export_read.py`, em função autocontida do `external_python`; verificar com `airflow/tests/test_forecast_export.py` e uma exportação em hml com as runs dos notebooks
- [ ] 10.2 Remover de `ml/src/atlas_ml`: `forecast/{dataset,windows,splits,evaluate,base,compare,figures,export_read,config,synthetic}.py`, `models/*` e `forecast/notebook.run_step`; remover o `ml/notebooks/forecast_pipeline.ipynb` e os testes unitários que cobriam esse código; verificar `uv run pytest` verde (a cobertura passa a ser a execução dos seis notebooks), `uv run ruff check` limpo e que `atlas-ml promote` e `atlas-ml train example` continuam funcionando
- [ ] 10.3 Remover do teste de execução a parte de equivalência com o pacote e atualizar `ml/README.md` e os READMEs (um por pasta de notebook, no lugar dos READMEs de `models/*`); verificar com `grep` que nenhum documento aponta para código removido

## Workflow follow-up

- Atualizar a `move-forecast-to-notebook-pipeline` com `openspec-update-change`: esta mudança supersede os grupos 2 e 3 dela (notebook único e `run_step`) e a decisão 1 do design; as partes de `git-sync`, filtro de caminhos do CI, `aguardar-clone.sh` e Jupyter de exploração continuam valendo.
- Aplicar o grupo 9 depois que o `git-sync` e a imagem com `papermill` estiverem em hml (tarefas 5 e 8 da `move-forecast-to-notebook-pipeline`).
- Arquivar a mudança quando hml e prod estiverem treinando pelos notebooks e o código antigo tiver saído.
