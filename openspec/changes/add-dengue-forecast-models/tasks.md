# Tasks

## 1. Credenciais e MLflow no bucket

- [x] 1.1 Receber do usuário as chaves das service accounts, salvas como `platform/secrets/mlflow-sa.json` (objetos no `ppgcc-bucket`) e `platform/secrets/training-sa.json` (leitura no BigQuery `ppgcc-dengue-project`); verificar com `git check-ignore` que as duas estão fora do git
- [x] 1.2 Definir `MLFLOW_ARTIFACTS_BUCKET=ppgcc-bucket` no `platform/.env` e reiniciar a stack; verificar com uma run de `atlas-ml train example` que o artefato aparece em `gs://ppgcc-bucket/mlflow/dev/` (listagem com `google-cloud-storage` no container do MLflow) e, se a rede corporativa bloquear, configurar `EXTRA_CA_PATH` e marcar a tarefa 5.3 da `add-ml-platform`
- [x] 1.3 Conferir na gold do BigQuery os nomes e colunas de `gold_dengue_epi_curve_weekly` e `gold_dim_populacao_admin1` para o Brasil (amostra de 5 linhas e contagem de UFs) e ajustar o design se divergirem; verificar 27 UFs com população
- [x] 1.4 Commit do módulo em `dev` (`chore(forecast): MLflow de dev no ppgcc-bucket`); verificar com `git log -1 --stat` que nenhuma chave entrou no commit

## 2. Núcleo de previsão (dados, janelas, divisão, avaliação)

- [x] 2.1 Criar `atlas_ml/forecast/config.py` (`ForecastConfig` com window, horizon, test_weeks, val_weeks, drop_recent_weeks, oof_folds, augment, seed e features) e `splits.py` (treino/validação/teste por data do alvo; blocos OOF rolling-origin); verificar com testes de limites (nenhum alvo de treino nas 52 semanas finais; blocos OOF sempre antes do período previsto)
- [x] 2.2 Criar `forecast/dataset.py`: consulta da `gold_dengue_casos_provaveis_uf_semanal` (casos prováveis, população do ano epidemiológico, relevo), painel UF×semana com semanas faltantes preenchidas (`filled`), `incidence`, `uf_code`; erro listando UFs sem população; verificar com testes sobre um cliente BigQuery simulado
- [x] 2.3 Implementar `atlas-ml forecast prepare` (run `dataset` com `panel.parquet` e `data_summary.json`, `data_version` das duas tabelas, imprime `dataset_run_id=`); verificar com teste em MLflow temporário e uma execução real contra o BigQuery
- [x] 2.4 Criar `forecast/windows.py` (janelas N→H por UF, `log1p` + `TrainOnlyScaler` ajustado só no treino, sazonalidade, covariáveis de `cfg.features`, aumento só no treino); verificar com testes de que o scaler não muda ao alterar dados de validação/teste e de que uma covariável nova entra nas janelas sem mudança no código
- [x] 2.5 Criar `forecast/evaluate.py` (NRMSE/MAE/RMSE/R² por UF e médias; `metrics_by_uf.csv`; `predictions.parquet` com `lower`/`upper` opcionais; previsões negativas → 0) e `forecast/base.py` (`ForecastModel` + `run_model` com tags `atlas.pipeline_run` e `atlas.model_family`); verificar com testes usando um modelo trivial (persistência da última semana)
- [x] 2.6 Commit do módulo em `dev` (`feat(forecast): dataset SINAN-BR, janelas, divisões e avaliação`); verificar `uv run pytest` verde

## 3. Dependências e imagens

- [x] 3.1 Adicionar o grupo opcional `models` (`catboost`, `torch` do índice CPU, `pymc`, `chronos-forecasting`) ao `ml/pyproject.toml` e atualizar o `uv.lock`; verificar `uv sync --extra models` e import dos quatro pacotes
- [x] 3.2 Atualizar `airflow/Dockerfile` (`uv sync --extra models`) e `ml/Dockerfile` (alvo `runtime-models`; Jupyter com os extras); adicionar o volume `hf-cache` com `HF_HOME` no compose de dev; verificar build das imagens e `python -c "import torch, pymc, catboost, chronos"` no venv do Airflow
- [x] 3.3 Commit do módulo em `dev` (`build(ml): dependências dos modelos de previsão`); verificar o tamanho das imagens registrado na mensagem do commit

## 4. CatBoost e SVR

- [x] 4.1 Implementar `models/catboost/` (CatBoost com `uf_code` categórico, early stopping só na validação, OOF por blocos, `mlflow.catboost`, README); verificar com teste no painel sintético (`@pytest.mark.models`): métricas registradas, `oof_predictions.parquet` sem alvos vistos e reprodutibilidade com a mesma semente
- [x] 4.2 Implementar `models/svr/` (one-hot UF + StandardScaler + SVR, `RandomizedSearchCV` com `TimeSeriesSplit` só no treino, aumento só no treino, OOF, skops com tipos confiáveis, README); verificar com teste equivalente ao 4.1
- [x] 4.3 Commit do módulo em `dev` (`feat(models): CatBoost e SVR`); verificar `uv run pytest -m models` verde

## 5. LSTM

- [x] 5.1 Implementar `models/lstm/` (PyTorch: embedding de UF + LSTM 60→20 → Linear, Adam lr de fato aplicado, early stopping na validação com restauração dos melhores pesos, sementes e determinismo, OOF, `mlflow.pytorch`, README); verificar com teste no painel sintético (métricas, OOF e variação ≤ 2% entre duas execuções)
- [x] 5.2 Commit do módulo em `dev` (`feat(models): LSTM em PyTorch`); verificar testes verdes

## 6. Baseline bayesiano

- [x] 6.1 Implementar `models/baseline_bayes/` (PyMC binomial negativa com offset de população, efeitos de UF e ano, Fourier semanal, termo defasado; NUTS configurável; `rhat_max`, `ess_bulk_min`, tag `atlas.converged`; intervalos de 95%; `idata.nc`; pyfunc; README com tempo medido); verificar com teste no painel sintético (draws pequenos) que `lower ≤ previsto ≤ upper` e que os diagnósticos são registrados
- [x] 6.2 Commit do módulo em `dev` (`feat(models): baseline bayesiano em PyMC`); verificar testes verdes

## 7. Chronos

- [ ] 7.1 Implementar `models/chronos/` (`chronos-bolt-small` zero-shot em CPU, previsões em lote por UF e origem, quantis 0,1/0,9 como intervalo de 80%, parâmetros com checkpoint e revisão, pyfunc, README); verificar com teste que usa um pipeline falso (sem download) e uma execução real que baixa o checkpoint para o `hf-cache`
- [x] 7.2 Commit do módulo em `dev` (`feat(models): Chronos zero-shot`); verificar testes verdes

## 8. Ensemble e comparação

- [x] 8.1 Implementar `models/ensemble/` (RF sobre as OOF de CatBoost, SVR e LSTM + extrapolações polinomiais graus 0–2; `max_depth` aplicado; intervalos pelos percentis entre árvores; recusa a treinar se faltar alguma OOF; README); verificar com teste usando runs-base falsas que nenhuma linha de treino do meta-modelo usa previsão in-sample
- [x] 8.2 Implementar `atlas-ml forecast compare` (tabela de métricas de teste por modelo, melhor `test_nrmse_mean`, modelos ausentes); verificar com teste em MLflow temporário com um modelo ausente
- [x] 8.3 Commit do módulo em `dev` (`feat(models): ensemble out-of-fold e comparação`); verificar testes verdes

## 9. DAG e execução de ponta a ponta

- [x] 9.1 Escrever a DAG `atlas_dengue_forecast_br` (prepare → 5 bases em paralelo → ensemble → compare com `all_done`; `max_active_runs=1`, `max_active_tasks=3`, `params` window/horizon/seed, `ATLAS_PIPELINE_RUN`, retries=1); verificar com teste `DagBag` (ordem, regras de disparo, parâmetros)
- [ ] 9.2 Rodar a DAG no compose de dev contra a gold real e registrar o resultado: as 8 runs com a mesma `atlas.pipeline_run` e `atlas.data_version`, os seis modelos `atlas-br-*` com `@dev`, a run de comparação e os artefatos em `gs://ppgcc-bucket/mlflow/dev/`; anotar tempos por tarefa e as métricas de teste em `docs/referencias/resultados-forecast-br.md`
- [ ] 9.3 Rodar de novo com `horizon=4` e verificar que todas as runs registram `horizon=4`
- [x] 9.4 Atualizar `ml/README.md` e `airflow/README.md` (novos comandos `atlas-ml forecast …`, DAG, pastas dos modelos); verificar seguindo os comandos documentados
- [ ] 9.5 Commit do módulo em `dev` (`feat(forecast): DAG atlas_dengue_forecast_br e resultados`); verificar `git log -1 --stat`

## Workflow follow-up

- Promover para hml/prod pelo fluxo da `add-ml-platform` depois da validação em dev.
- Arquivar a mudança quando os modelos estiverem em `@prod`.
