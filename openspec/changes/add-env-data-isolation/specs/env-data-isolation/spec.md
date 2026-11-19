# Spec Delta

## Purpose

Garantir que cada ambiente (dev, hml, prod) leia e escreva só os seus dados, no Cloud Storage e no BigQuery, a partir de uma única configuração.

## ADDED Requirements

### Requirement: Ambiente como única configuração
Todos os componentes que leem ou escrevem dados do Atlas SHALL derivar o prefixo do landing e os datasets do BigQuery de `ATLAS_ENV` (`dev`, `hml` ou `prod`). Um valor de ambiente desconhecido SHALL interromper a execução com erro, sem escrever nada.

#### Scenario: Ambiente inválido
- **WHEN** um componente roda com `ATLAS_ENV=teste`
- **THEN** ele falha antes de ler ou escrever dados, dizendo que o ambiente é inválido

### Requirement: Landing por ambiente
O landing do SINAN SHALL ficar em `gs://ppgcc-bucket/landing/<ambiente>/sinan/dengue/` em hml e prod. Em dev SHALL continuar em `gs://ppgcc-bucket/landing/sinan/dengue/`.

#### Scenario: Ingestão em hml
- **WHEN** a `ingestao_sinan_brasil` roda em hml
- **THEN** ela compara o OpenDataSUS com `landing/hml/sinan/dengue/` e só escreve nesse prefixo

#### Scenario: Dev intocado
- **WHEN** a ingestão roda em dev depois desta mudança
- **THEN** ela usa o mesmo caminho e o mesmo estado de antes, sem baixar tudo de novo

### Requirement: Datasets do BigQuery por ambiente
As camadas escritas pelo Atlas SHALL usar o sufixo do ambiente: `bronze`, `silver`, `gold` e `forecast` em dev; `bronze_hml`, `silver_hml`, `gold_hml` e `forecast_hml` em hml; `bronze_prod`, `silver_prod`, `gold_prod` e `forecast_prod` em prod. Os datasets de origem só de leitura SHALL continuar compartilhados. Os datasets novos SHALL ter location `US`.

#### Scenario: dbt em hml
- **WHEN** a `dbt_brasil` roda em hml
- **THEN** seeds e models são escritos em `bronze_hml`, `silver_hml` e `gold_hml`, e a fonte do SINAN é lida de `bronze_hml`

#### Scenario: Treino e site de hml
- **WHEN** o treino e o backend rodam em hml
- **THEN** o treino lê `gold_hml.gold_dengue_casos_provaveis_uf_semanal`, a exportação escreve em `forecast_hml` e o backend lê `gold_hml` e `forecast_hml`

### Requirement: Um ambiente não escreve nos dados de outro
Nenhuma execução em hml ou prod SHALL escrever nos caminhos ou datasets de dev, e vice-versa.

#### Scenario: ETL completa em hml
- **WHEN** a `etl_brasil` roda em hml do começo ao fim
- **THEN** a última modificação de `bronze`, `silver`, `gold` e `forecast` (dev) e do landing de dev não muda

### Requirement: Datasets criados sem intervenção
A primeira execução em um ambiente SHALL criar os datasets que faltarem (a ingestão cria a bronze; o dbt, a silver e a gold; a exportação, o forecast), sem passo manual.

#### Scenario: Primeira carga de hml
- **WHEN** a `etl_brasil` roda em hml sem nenhum dataset `*_hml` existente
- **THEN** os quatro datasets são criados, a bronze recebe todos os anos e a gold e as previsões são geradas

### Requirement: Documentação do dbt depois da modelagem
A `process_dbt_docs_atlas` SHALL ser disparada ao fim da `dbt_brasil` sempre que o dbt rodar, e não SHALL ser disparada quando o dbt for pulado.

#### Scenario: dbt rodou
- **WHEN** a `dbt_brasil` termina o grupo `gold` com sucesso
- **THEN** a documentação do dbt do ambiente é gerada e publicada em `dbt_docs/<ambiente>/`
