# Proposal

## Why

Hoje os casos de dengue do Brasil chegam ao BigQuery por uma cópia manual da tabela pública da Base dos Dados (`microdados.raw_uftpr_microdados_brasil`, copiada em 20/09/2026, com notificações só até 29/06/2026), feita por um script que não está no repositório. O OpenDataSUS publica os mesmos microdados do SINAN direto do Ministério da Saúde e está bem mais atualizado: em 16/11/2026, o arquivo de 2026 já tinha 489 mil notificações, até 02/11/2026. Os arquivos ficam num endereço público com `ETag` e `Last-Modified`, o que permite saber se mudaram sem baixá-los.

## What Changes

- **Nova DAG diária `process_sinan_ingest_atlas`**, quebrada em etapas explícitas:
  1. **Sensor de sync (`detectar_diferencas`):** compara a origem com o landing do bucket.
     - **Origem:** `HEAD` dos arquivos anuais `DENGBR00` a `DENGBR<ano corrente>`.
     - **Bucket:** o `ETag` e o `Last-Modified` da origem, guardados na metadata de cada objeto do landing.
     - **Plano devolvido:**
       - arquivos a **baixar**: novos na origem ou com hash ou data diferente;
       - arquivos a **apagar**: estão no bucket e não estão mais na origem;
       - anos a **carregar na bronze**: o landing tem uma versão que a bronze ainda não recebeu.
     - Sem diferença, a execução termina pulada.
  2. **Landing como espelho exato:** `gs://ppgcc-bucket/landing/sinan/dengue/DENGBR<aa>.csv.zip` (o zip original) e `DENGBR<aa>.csv` (descompactado).
     - Arquivo alterado é **substituído**.
     - Arquivo que sumiu da origem é **apagado**, e a partição do ano sai da bronze.
     - O bucket guarda só a versão atual de cada arquivo da origem.
  3. **Tabela bronze materializada:** `bronze.sinan_dengue_opendatasus`, carregada do landing.
     - Sem transformação: todas as colunas de origem como texto, mais `ano_arquivo`, `arquivo_etag`, `arquivo_uri` e `carregado_em`.
     - Particionada por ano; cada ano é substituído por inteiro (idempotente e atômico).
  4. **Validação:** linhas da partição = registros do CSV, e as colunas obrigatórias existem. Só depois a metadata do objeto no landing é marcada como carregada.
  5. **Modelagem:** dispara a `process_etl_atlas` quando algum ano foi carregado ou removido.
- **Estado no próprio bucket:** a metadata dos objetos (`origem_etag`, `origem_last_modified`, `bronze_etag`) é a fonte da verdade do sync. Não há tabela de controle, e a verificação diária não consulta o BigQuery.
- **dbt:**
  - a tabela bronze vira `source` (`sinan_opendatasus`);
  - o `bronze_dengue_brasil` mapeia os códigos do DATASUS para as colunas que o projeto já usa:
    - UF por código do IBGE → sigla;
    - município de 6 → 7 dígitos;
    - datas;
    - idade;
  - silver e gold não mudam de contrato.
- **Fallback:** a fonte antiga (Base dos Dados) continua selecionável pela variável dbt `sinan_source` (`opendatasus`, o padrão depois do corte, ou `basedosdados`).
- **Imagem/compose:** nenhum pacote novo. A DAG usa a Connection `google_cloud_default`.

## Capabilities

### New Capabilities
- `sinan-ingestion`: sync diário dos microdados do SINAN entre o OpenDataSUS e o landing do bucket (espelho exato), materialização da tabela bronze por ano, validação e acionamento da modelagem.

### Modified Capabilities
- Nenhuma em `openspec/specs/` (ainda vazio). O contrato de colunas do `bronze_dengue_brasil` fica coberto pelos requisitos de `sinan-ingestion`.

## Impact

- **Código:**
  - `airflow/dags/process_sinan_ingest_atlas.py`: DAG nova;
  - `airflow/dags/atlas_ingest/sinan.py`: listagem da origem e do bucket, plano de sync, download e substituição, remoção, carga e validação; testável sem rede;
  - `airflow/tests/`.
- **dbt:**
  - `models/sources.yaml`: nova source;
  - `models/bronze/bronze_dengue_brasil.sql`: mapeamento DATASUS e variável `sinan_source`;
  - teste de equivalência entre as fontes.
- **GCP:**
  - **landing:** cerca de 1,4 GB de zips mais os CSVs descompactados no `ppgcc-bucket`, sem acumular versões;
  - **BigQuery:** tabela `bronze.sinan_dengue_opendatasus` (≈ 35 milhões de linhas);
  - **service account:** a `training-sa`, que já escreve no bucket e no BigQuery.
- **Agendamento:** é a primeira DAG do projeto com agendamento (`@daily`). As demais continuam manuais.
- **Histórico:** o landing não guarda versões anteriores. Quem precisar de uma versão antiga depende da origem. A coluna `arquivo_etag` da bronze registra qual versão está carregada.
- **Dados:** a série do Brasil passa a ir até a semana mais recente publicada. O OpenDataSUS também não traz descartados (`CLASSI_FIN=5`) nos anos recentes, então a definição de casos prováveis da gold continua correta.
