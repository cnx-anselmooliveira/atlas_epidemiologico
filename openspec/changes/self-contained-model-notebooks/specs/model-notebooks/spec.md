# Spec Delta

## Purpose

Dar a cada modelo de previsão de dengue um notebook autocontido, com o código do modelo, as dependências e as saídas impressas, que se lê de cima para baixo e roda passo a passo na mão ou pelo Airflow, registrando as runs no MLflow no mesmo contrato de hoje.

## ADDED Requirements

### Requirement: Um notebook por modelo
Cada um dos seis modelos (`baseline_bayes`, `catboost`, `svr`, `lstm`, `chronos`, `ensemble`) SHALL ter o próprio notebook em `ml/notebooks/<modelo>/<modelo>.ipynb`, versionado sem saídas de células.

#### Scenario: Notebooks existentes
- **WHEN** se lista `ml/notebooks/`
- **THEN** há uma pasta por modelo, cada uma com o notebook de mesmo nome e um `requirements.txt`

### Requirement: Notebook autocontido
O notebook SHALL conter, em células visíveis, a leitura dos dados, a montagem das janelas, a divisão temporal, a definição e o treino do modelo, a avaliação por UF, as previsões e o registro no MLflow. Nenhuma célula SHALL importar a implementação do modelo, das janelas ou da avaliação de pacotes do projeto; só ajudantes de plataforma (configuração, tags `atlas.*` e registro de modelos) podem ser importados.

#### Scenario: Sem modelo pronto
- **WHEN** se analisam os imports de um notebook de modelo
- **THEN** não há import de `atlas_ml.models` nem de `atlas_ml.forecast`

#### Scenario: Código do modelo à vista
- **WHEN** alguém abre o notebook do CatBoost
- **THEN** a criação do `CatBoostRegressor`, o treino e a previsão estão em células do próprio notebook

### Requirement: Roda passo a passo na mão
O notebook SHALL poder ser executado célula por célula, de cima para baixo, sem Airflow e sem editar código, com a célula `parameters` trazendo valores padrão que bastam (horizonte 1, janela 12, semente 42). As células SHALL ser independentes de efeitos de execução fora de ordem além das variáveis das células anteriores.

#### Scenario: Execução manual
- **WHEN** alguém executa as células em ordem com as credenciais do BigQuery e do MLflow configuradas
- **THEN** o notebook termina com a run registrada e o `run_id` impresso

#### Scenario: Painel local
- **WHEN** o parâmetro `painel_parquet` aponta para um painel salvo
- **THEN** o notebook usa esse painel em vez de ler o BigQuery, e o resto do fluxo é igual

### Requirement: Parâmetros sobrescritíveis
A célula `parameters` SHALL listar horizonte, janela, semente, `features`, `pipeline_run`, `data_version_esperada`, `painel_parquet`, `result_path` e `out_dir`, e o papermill SHALL poder sobrescrevê-los. `result_path` e `out_dir` SHALL ser opcionais (vazios = só imprimir).

#### Scenario: Parâmetros do Airflow
- **WHEN** o Airflow executa o notebook com `horizon=3`, `seed=7` e `pipeline_run=<id>`
- **THEN** a run registrada tem horizonte 3, semente 7 e a tag `atlas.pipeline_run` com esse identificador

### Requirement: Saídas impressas em cada etapa
Cada etapa do notebook SHALL imprimir o que aconteceu: dados lidos (período, UFs, linhas, versão da gold), janelas e cortes (treino, validação, teste), hiperparâmetros, andamento do treino quando o modelo informa, métricas por UF e as médias, cobertura do intervalo quando houver, artefatos gravados e o `run_id`.

#### Scenario: Notebook executado
- **WHEN** o Airflow guarda o notebook executado de uma run
- **THEN** ele mostra, em cada etapa, as saídas impressas descritas acima

### Requirement: Requirements por modelo
Cada pasta de modelo SHALL ter um `requirements.txt` com os pacotes que o notebook importa, com faixa de versão. O venv comum da imagem SHALL satisfazer todas as listas, e o CI SHALL falhar se um import do notebook não estiver declarado ou se o venv não atender a lista.

#### Scenario: Dependência não declarada
- **WHEN** um notebook passa a importar um pacote que não está no `requirements.txt` dele
- **THEN** o CI falha apontando o notebook e o pacote

#### Scenario: Lista fora do venv
- **WHEN** um `requirements.txt` pede uma versão que o venv comum não instala
- **THEN** o CI falha apontando o modelo e o pacote

### Requirement: Primeira célula mostra o ambiente
O notebook SHALL imprimir, logo no começo, as versões instaladas dos pacotes do seu `requirements.txt`, para quem roda na mão saber em que ambiente está.

#### Scenario: Versões impressas
- **WHEN** o notebook começa
- **THEN** imprime o nome e a versão de cada pacote do `requirements.txt` do modelo

### Requirement: Código comum idêntico nos seis notebooks
As células de código comum (leitura da gold, janelas, divisão, métricas, MLflow) SHALL ser marcadas com a tag `comum` e SHALL ser idênticas nos seis notebooks. O CI SHALL falhar se divergirem, e uma ferramenta de desenvolvimento SHALL poder sincronizá-las a partir de uma única fonte. A execução do notebook SHALL NOT depender da ferramenta.

#### Scenario: Célula comum alterada em um só notebook
- **WHEN** uma célula `comum` é alterada em um notebook e não nos outros
- **THEN** o CI falha apontando a célula e os notebooks que divergem

#### Scenario: Sincronização
- **WHEN** a fonte das células comuns é alterada e a ferramenta é executada
- **THEN** os seis notebooks passam a ter as mesmas células `comum`

### Requirement: Dados da gold com versão registrada
O notebook SHALL ler `gold_dengue_casos_provaveis_uf_semanal` do ambiente (`ATLAS_ENV`) e SHALL registrar `atlas.data_version` contendo `<tabela>@<última modificação>`, o formato que a decisão de treino do `etl_brasil` já usa. Se `data_version_esperada` for informada e diferir da versão atual da gold, o notebook SHALL falhar antes de criar a run.

#### Scenario: Gold atualizada no meio da execução
- **WHEN** a gold é reconstruída depois do início da execução da DAG e um notebook começa com `data_version_esperada` da versão antiga
- **THEN** o notebook falha antes de criar a run, indicando as duas versões

#### Scenario: Versão para o etl_brasil
- **WHEN** a run termina
- **THEN** a tag `atlas.data_version` contém a versão da gold lida, e o `etl_brasil` a reconhece como já treinada

### Requirement: Metadados da run no MLflow
Cada run SHALL ficar no experimento oficial de previsão, com as tags `atlas.env`, `atlas.git_sha`, `atlas.image_tag`, `atlas.data_version`, `atlas.pipeline_run`, `atlas.model_family`, `atlas.horizon` e `atlas.notebook_sha`, os parâmetros da configuração e os `model.*`, e as métricas de validação e teste por UF e as médias.

#### Scenario: Consumidores das tags
- **WHEN** a comparação e a exportação leem as runs treinadas pelos notebooks
- **THEN** encontram as mesmas tags, parâmetros e métricas que liam das runs do pacote

### Requirement: Artefatos e registro do modelo
Cada run SHALL gravar `predictions.parquet`, `metrics_by_uf.csv`, `future_predictions.parquet` e `figures/` (com `captions.json`), e SHALL registrar o modelo como `atlas-br-<modelo>-h<horizonte>` com o sufixo do ambiente e o alias do ambiente.

#### Scenario: Exportação inalterada
- **WHEN** a DAG de exportação lê as runs treinadas pelos notebooks
- **THEN** encontra os mesmos artefatos e nomes registrados de antes e exporta sem alteração

### Requirement: Previsões out-of-fold dos modelos-base
Os notebooks de `catboost`, `svr` e `lstm` SHALL gravar `oof_predictions.parquet` por blocos rolling origin, sem nenhum alvo previsto por um ajuste que o tenha visto. O notebook do `ensemble` SHALL ler as previsões dos três pelos identificadores em `base_runs`, recusar-se a treinar se faltar qualquer um e SHALL NOT usar previsões in-sample.

#### Scenario: Ensemble sem uma base
- **WHEN** o notebook do ensemble recebe `base_runs` sem o `lstm`
- **THEN** falha antes de criar a run, indicando o modelo ausente

### Requirement: Sem vazamento de dados
O escalonamento SHALL ser ajustado só no treino, o teste SHALL NOT ser usado em ajuste nem em parada antecipada, e as janelas SHALL usar só semanas até a origem. As semanas imaturas SHALL ser descartadas antes da divisão.

#### Scenario: Escalonamento
- **WHEN** os dados de validação e teste mudam
- **THEN** os parâmetros do escalonador do treino não mudam

### Requirement: Equivalência com o pacote na transição
Enquanto o pacote `atlas_ml` ainda tiver o código dos modelos, o notebook de cada modelo SHALL produzir, no mesmo painel, na mesma configuração e com a mesma semente, a mesma `test_nrmse_mean` do pacote (tolerância de 1e-6 nos determinísticos e de 2% na LSTM e no Chronos).

#### Scenario: CatBoost
- **WHEN** o notebook do CatBoost e o pacote treinam o mesmo painel sintético com a mesma semente
- **THEN** a diferença de `test_nrmse_mean` entre eles é de no máximo 1e-6

### Requirement: Notebook executado no CI
Cada notebook SHALL ser executado nos testes sobre um painel sintético, com MLflow temporário e sem BigQuery, e o teste SHALL falhar se qualquer célula levantar erro.

#### Scenario: Teste de um modelo
- **WHEN** a suíte de testes roda
- **THEN** cada um dos seis notebooks executa de ponta a ponta no painel sintético e registra a run
