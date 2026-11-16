# Proposal

## Why

Hoje os casos de dengue do Brasil chegam ao BigQuery por uma cópia manual da tabela pública da Base dos Dados (`microdados.raw_uftpr_microdados_brasil`, copiada em 20/09/2026, com notificações só até 29/06/2026), feita por um script que não está no repositório. O OpenDataSUS publica os mesmos microdados do SINAN direto do Ministério da Saúde e está bem mais atualizado: em 16/11/2026, o arquivo de 2026 já tinha 489 mil notificações, até 02/11/2026. Os arquivos ficam num endereço público com `ETag` e `Last-Modified`, o que permite detectar mudança sem baixar nada.

## What Changes

- **Nova DAG de ingestão com sensor**, `process_sinan_ingest_atlas`, quebrada em etapas explícitas:
  1. **Sensor:** consulta `ETag`/`Last-Modified` dos 27 arquivos anuais (`DENGBR00` a `DENGBR26`) e compara com a tabela de controle. Libera a execução só quando algum ano mudou e devolve a lista desses anos. Roda diariamente, em modo reschedule. Sem mudança, a execução termina como pulada.
  2. **Landing:** para cada ano alterado, baixa o `.csv.zip` original e grava sem alteração em `gs://ppgcc-bucket/landing/sinan/dengue/ano=<AAAA>/<etag>/DENGBR<aa>.csv.zip`, mantendo o histórico de versões, e também o CSV descompactado ao lado.
  3. **Tabela bronze:** carrega o CSV do landing numa tabela BigQuery materializada, `bronze.sinan_dengue_opendatasus`.
     - Sem transformação: todas as colunas de origem como texto, mais `ano_arquivo`, `arquivo_etag`, `arquivo_uri` e `carregado_em`.
     - Particionada por `ano_arquivo`; cada ano é substituído por inteiro (idempotente).
  4. **Validação:** confere se as linhas carregadas batem com as linhas do CSV e se as colunas obrigatórias existem. Grava o ano na tabela de controle (`bronze.sinan_dengue_opendatasus_controle`).
  5. **Modelagem:** dispara a `process_etl_atlas`, que roda o dbt.
- **dbt:**
  - a tabela bronze vira `source` (`sinan_opendatasus`);
  - o model `bronze_dengue_brasil` passa a mapear os códigos do DATASUS para as colunas que o resto do projeto já usa:
    - UF por código do IBGE → sigla;
    - município de 6 dígitos → código de 7 dígitos;
    - datas em ISO;
  - silver e gold não mudam de contrato.
- **Fallback:** a fonte antiga (Base dos Dados) continua disponível pela variável dbt `sinan_source` (`opendatasus`, o padrão, ou `basedosdados`), para rollback sem mudar código.
- **Imagem/compose:** nenhum pacote novo. Os providers Google e o Cosmos já estão na imagem. A DAG usa a Connection `google_cloud_default`.

## Capabilities

### New Capabilities
- `sinan-ingestion`: detecção de novas versões dos microdados do SINAN no OpenDataSUS, preservação dos arquivos brutos no landing, materialização da tabela bronze por ano, validação e acionamento da modelagem.

### Modified Capabilities
- Nenhuma em `openspec/specs/` (ainda vazio). O efeito sobre a modelagem é o mesmo contrato de colunas do `bronze_dengue_brasil`, coberto nos requisitos de `sinan-ingestion`.

## Impact

- **Código:**
  - `airflow/dags/process_sinan_ingest_atlas.py`: DAG nova;
  - `airflow/dags/atlas_ingest/sinan.py`: funções de sensor, landing, carga e validação, testáveis sem rede;
  - `airflow/tests/`.
- **dbt:**
  - `models/sources.yaml`: nova source;
  - `models/bronze/bronze_dengue_brasil.sql`: mapeamento DATASUS e variável `sinan_source`;
  - seed `seed_uf_ibge.csv`: código do IBGE → sigla;
  - testes de equivalência com a fonte antiga.
- **GCP:**
  - **landing:** cerca de 1,4 GB de zips mais os CSVs no `ppgcc-bucket`, em `landing/`, na carga inicial;
  - **BigQuery:** nova tabela `bronze.sinan_dengue_opendatasus` (≈ 35 milhões de linhas) e a de controle;
  - **service account:** a `training-sa`, que já escreve no bucket e no BigQuery.
- **Agendamento:** é a primeira DAG do projeto com agendamento (`@daily`), porque o sensor precisa de execuções periódicas. As demais continuam manuais.
- **Dados:** a série do Brasil passa a ir até a semana mais recente publicada. Os descartados (`CLASSI_FIN=5`) também não vêm no OpenDataSUS nos anos recentes, então a definição de casos prováveis da gold continua correta.
