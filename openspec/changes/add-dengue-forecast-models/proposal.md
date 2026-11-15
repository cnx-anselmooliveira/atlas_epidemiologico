# Proposal

## Why

A plataforma de ML (`add-ml-platform`) já roda localmente, mas só com um experimento sintético. O levantamento do ESA-UNICEF Dengue Forecast Project ([docs/referencias/esa-unicef-dengue-forecast.md](../../../docs/referencias/esa-unicef-dengue-forecast.md)) mostrou um conjunto de modelos de previsão de incidência que vale reproduzir. Ele também mostrou falhas de metodologia (vazamento de dados, stacking sem out-of-fold) que devem ser corrigidas.

Antes de chegar ao modelo de nicho com dados de satélite e clima, precisamos dos modelos de referência rodando de ponta a ponta sobre dados reais do Atlas, rastreados e comparáveis no MLflow.

## What Changes

- **Seis modelos em Python, cada um em sua pasta** dentro do pacote `atlas_ml`:
  - **Baseline bayesiano**: PyMC hierárquico;
  - **CatBoost**;
  - **LSTM** (PyTorch);
  - **SVR**;
  - **Chronos**: modelo fundacional de séries temporais, zero-shot;
  - **Ensemble**: meta-modelo Random Forest sobre CatBoost, SVR e LSTM.

  Cada modelo tem a mesma interface de treino e previsão e é registrado no MLflow como modelo próprio.
- **Dataset de teste: a gold do Brasil (SINAN) no BigQuery.**
  - Casos semanais por UF, convertidos em **incidência por 100 mil habitantes** com a população da UF.
  - Por enquanto só o histórico de casos, a sazonalidade e a identidade da UF. As variáveis de satélite e clima (temperatura, vento, chuva, NDVI…) entram depois, sem mudar a interface.
- **Metodologia corrigida** em relação ao original:
  - divisão temporal treino / validação / teste, com o teste nunca usado em ajuste ou seleção;
  - escalonamento e aumento de dados ajustados só no treino;
  - stacking com previsões out-of-fold;
  - métricas por UF: NRMSE, MAE, RMSE e R².
- **DAG `atlas_dengue_forecast_br`** no Airflow:
  - prepara um snapshot versionado dos dados;
  - treina os cinco modelos-base em paralelo;
  - treina o ensemble;
  - registra uma comparação final.
  - Tudo no experimento `atlas/dengue-forecast-br` do MLflow.
- **MLflow de dev conectado ao bucket `gs://ppgcc-bucket`** (prefixo `mlflow/dev/`), com a chave da SA do MLflow.
- **Dependências novas no `atlas_ml`**, num grupo opcional `models` para não pesar quem só usa o núcleo: `catboost`, `torch` (CPU), `pymc`, `chronos-forecasting`. A imagem do Airflow passa a instalar esse grupo.

## Capabilities

### New Capabilities
- `forecast-dataset`: montagem do painel UF × semana de incidência a partir da gold do SINAN, com snapshot versionado, divisões temporais sem vazamento e janelas de entrada/alvo extensíveis a novas covariáveis.
- `forecast-models`: contrato comum dos seis modelos (treino, previsão, intervalos quando houver), registro no MLflow, métricas por UF e regras do ensemble (out-of-fold).
- `forecast-training-dag`: a DAG que orquestra dados → modelos-base → ensemble → comparação, com isolamento entre execuções e falha explícita.

### Modified Capabilities
<!-- Nenhuma em openspec/specs/. Depende da mudança add-ml-platform (ainda não arquivada): plataforma, CLI atlas-ml, tags atlas.* e imagem do Airflow. -->

## Impact

- **Código**:
  - `ml/src/atlas_ml/forecast/`: dados, features, divisões e avaliação;
  - `ml/src/atlas_ml/models/<modelo>/`: uma pasta por modelo;
  - `airflow/dags/atlas_dengue_forecast_br.py`;
  - testes em `ml/tests/forecast/`.
- **Imagens**: a imagem do Airflow cresce (torch CPU, PyMC, CatBoost; estimativa de mais 1,5 GB). A imagem de treino ganha o alvo com o grupo `models`.
- **GCP**:
  - leitura da gold do Brasil no BigQuery, com a chave de treino em `platform/secrets/training-sa.json`;
  - escrita de artefatos em `gs://ppgcc-bucket/mlflow/dev/`, com a chave da SA do MLflow em `platform/secrets/mlflow-sa.json`.
  - As duas chaves ainda **precisam ser fornecidas**.
- **Rede**: o Chronos baixa os pesos do Hugging Face na primeira execução. Na rede corporativa, isso pode exigir a CA da inspeção TLS (`EXTRA_CA_PATH`).
- **Fora de escopo**:
  - covariáveis de satélite e clima;
  - outros países;
  - previsão por município;
  - publicar as previsões em tabela gold para a API;
  - agendamento automático;
  - promoção para hml/prod (segue o fluxo da `add-ml-platform` depois de validado em dev).
