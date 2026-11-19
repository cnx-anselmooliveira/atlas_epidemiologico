# Proposal

## Why

Os ambientes não estão separados nos dados. O landing do SINAN é um caminho só (`gs://ppgcc-bucket/landing/sinan/dengue/`) e os datasets do BigQuery (`bronze`, `silver`, `gold`, `forecast`) são os mesmos para dev e hml. Na primeira execução da `etl_brasil` em hml, o sensor não viu nada novo, porque o dev já tinha sincronizado o mesmo landing; e, se tivesse visto, a ETL de hml teria sobrescrito a bronze e a gold do dev (e a exportação de hml, a previsão que o site de dev mostra). Só o MLflow, o cache do Cosmos e os docs do dbt já separam por ambiente. A `etl_brasil` está pausada em hml até isso ser resolvido.

## What Changes

- **Um só ponto de verdade, `ATLAS_ENV`:** cada componente deriva do ambiente onde ler e escrever. Em `dev` nada muda (mesmos caminhos e datasets de hoje); em `hml` e `prod` os dados ficam separados.
- **Cloud Storage com prefixo por ambiente** (decisão do usuário, mesmo bucket `ppgcc-bucket`): landing do SINAN em `landing/<ambiente>/sinan/dengue/` em hml e prod; dev mantém `landing/sinan/dengue/` (os arquivos e o estado de dev já estão lá). As figuras da previsão já usam `forecast/<ambiente>/`.
- **BigQuery com datasets por ambiente** (decisão do usuário): hml escreve em `bronze_hml`, `silver_hml`, `gold_hml` e `forecast_hml`; prod em `*_prod`; dev continua em `bronze`, `silver`, `gold` e `forecast`. Os datasets de origem só de leitura (`microdados` e afins) continuam compartilhados. Location `US`, como os atuais.
- **O que passa a seguir o ambiente:** o landing e a bronze da ingestão (`atlas_ingest/sinan.py`), as decisões da `etl_brasil` (`atlas_ingest/etl_brasil.py`), os schemas do dbt (macro `generate_schema_name`, seeds e a fonte `sinan_opendatasus`), a gold lida pelo treino (`ml/.../forecast/dataset.py`), o dataset da exportação (`ATLAS_FORECAST_DATASET`) e os datasets lidos pelo backend (`BQ_DATASET_GOLD`, `BQ_DATASET_FORECAST`).
- **Datasets criados sem intervenção:** a ingestão cria a bronze do ambiente se não existir; o dbt e a exportação criam os seus.
- **Docs do dbt depois da modelagem** (decisão do usuário): a `process_dbt_docs_atlas` é mantida e disparada ao fim da `dbt_brasil`, só quando o dbt rodou.
- **Primeira carga de hml:** ingestão de todos os anos no prefixo novo, dbt completo em `*_hml` (cerca de 9 GiB processados) e treino da base inteira; o site de hml passa a ler `gold_hml` e `forecast_hml`.

## Capabilities

### New Capabilities
- `env-data-isolation`: como cada ambiente resolve o prefixo do landing e os datasets do BigQuery, o que é compartilhado, a criação dos datasets, a primeira carga e a garantia de que um ambiente nunca escreve nos dados de outro.

### Modified Capabilities
<!-- Nenhuma spec principal existe em openspec/specs/. Complementa add-etl-brasil-orchestration (as DAGs e decisões passam a usar o ambiente; a docs do dbt entra no fim da dbt_brasil) e add-hml-stack (variáveis do stack), sem repetir os requisitos delas. -->

## Impact

- `airflow/dags/atlas_ingest/` (novo `ambiente.py`; `sinan.py`, `etl_brasil.py`), `airflow/dags/dbt_brasil.py` (dispara a docs), `airflow/dags/utfpr_dengue/` (`macros/generate_schema_name.sql`, `models/sources.yaml`).
- `ml/src/atlas_ml/forecast/dataset.py` (gold do ambiente).
- `docker-compose.yml` (`ATLAS_FORECAST_DATASET`, `BQ_DATASET_GOLD`, `BQ_DATASET_FORECAST` por ambiente) e `.env.example`.
- Testes: `airflow/tests/` (ambiente, decisões, DAGs), `ml/tests` (tabela da gold), compilação do dbt com e sem sufixo.
- Operação: datasets `*_hml` novos no projeto; primeira carga de hml com custo de BigQuery e download do OpenDataSUS; dev intocado.
