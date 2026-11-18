# Proposal

## Why

Os seis modelos de previsão (Ensemble, CatBoost, LSTM, SVR, Bayesiano PyMC e Chronos) já treinam e se registram no MLflow, mas só quem abre o MLflow vê o resultado, e ele guarda apenas previsões de **avaliação** (validação e teste, com o valor observado ao lado, a 1 semana). Não há previsão do futuro em nenhum artefato. A seção "Previsão" do site está como "em breve". Esta mudança leva os modelos ao site: gráfico com a série e as próximas semanas previstas, escolha do modelo, métricas de erro e uma explicação de como cada modelo funciona.

## What Changes

- **Previsão do futuro nos modelos.** Cada modelo passa a ser treinado e avaliado para os horizontes de **1 a 4 semanas** (estratégia direta) e a registrar, além das previsões de validação e teste, a **previsão das próximas 4 semanas por UF**, com intervalo quando o modelo o produz. As métricas passam a ser por horizonte.
- **Figuras no treino.** Cada run grava figuras PNG por modelo (previsto × observado, erro por UF e um gráfico próprio da família: importância das variáveis, convergência ou distribuição posterior) como artefatos do MLflow.
- **DAG que puxa do MLflow e materializa no BigQuery.** Uma DAG Python do Airflow (TaskFlow, sem scripts bash) lê, para cada modelo registrado no alias do ambiente, a run, as métricas, os parâmetros, as previsões e as figuras, e escreve tabelas no dataset `forecast` do BigQuery e as figuras no bucket. Roda ao fim da DAG de treino e pode ser disparada à mão, de forma idempotente.
- **API com cache Redis.** O backend ganha rotas `/forecast/*` que leem essas tabelas, com a mesma paginação, parâmetros de consulta e cache por geração da tabela das rotas gold. As figuras são servidas por uma rota própria, com cache HTTP.
- **Página de previsão no site** (`/previsao`, seção que passa de "em breve" a disponível):
  - gráfico com a série observada, a previsão de teste e as 4 semanas seguintes à última semana consolidada, com faixa de intervalo; como os modelos descartam as 8 últimas semanas (atraso de notificação), essas semanas ficam antes do dado mais recente e a página as rotula como **previsão retroativa** (decisão do usuário);
  - seletor de modelo com ícones próprios e botão de informação em cada um;
  - seletor de UF (Brasil por padrão) e de horizonte;
  - cartões de métricas (NRMSE, MAE, RMSE, R², cobertura do intervalo e tempo de treino), comparação entre os modelos e a data e a versão dos dados do treino.
- **Documentação de cada modelo** (`/previsao/modelos/<modelo>`): como funciona em poucas linhas, entradas e hiperparâmetros, métricas por horizonte e por UF e as figuras vindas do MLflow. O botão de informação da página de previsão leva até ela.
- **Credenciais** só por Connection e Variables do Airflow e variáveis de stack. Nada vai para o Git, para o bucket público nem para o navegador.

## Capabilities

### New Capabilities
- `forecast-future-outputs`: previsão das próximas 4 semanas, métricas por horizonte e figuras por modelo gravadas nas runs do MLflow.
- `forecast-mlflow-export`: DAG que materializa no BigQuery e no bucket o que as runs registraram.
- `forecast-data-api`: rotas `/forecast/*` do backend, com cache Redis.
- `forecast-page`: a página de previsão e a documentação dos modelos no site.

### Modified Capabilities
<!-- Nenhuma spec principal existe em openspec/specs/. Os requisitos de treino (forecast-models e forecast-training-dag, da add-dengue-forecast-models) são ajustados no design e nas tarefas desta mudança. -->

## Impact

- **ML (`ml/`):** os modelos e o `run_model` aceitam horizonte 1 a 4 e a previsão do futuro; as figuras ficam num módulo novo; o CLI ganha `forecast predict-future` ou equivalente. A `add-dengue-forecast-models` fica com a tarefa 9.3 (horizonte 4) coberta por esta mudança.
- **Airflow:** DAG nova de exportação e ajuste na `atlas_dengue_forecast_br` (um treino por horizonte e disparo da exportação ao fim). Connection do MLflow e do BigQuery por Connection, sem chave na imagem.
- **BigQuery:** dataset `forecast` novo, mantido pela DAG (não pelo dbt), com tabelas e uma visão do que está vigente.
- **Backend:** rotas novas, registro das tabelas na whitelist e rota de figuras lendo do bucket.
- **Frontend:** a seção "Previsão" no registro de seções, a página, a documentação, componentes novos (`ModelSwitcher`, `ForecastChart`, `MetricCard`, `ModelDoc`) e um sprite de ícones dos modelos.
- **Dependências:** as runs precisam existir no MLflow do ambiente (dev hoje; hml depois), com o alias do ambiente apontando para a versão a exibir.
- **Fora de escopo:** previsão em nível de município, retreino agendado, comparação entre ambientes na mesma página, autenticação de usuários e explicabilidade por caso.
