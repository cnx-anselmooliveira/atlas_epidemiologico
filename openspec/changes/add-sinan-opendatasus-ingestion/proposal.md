# Proposal

## Why

Hoje os casos de dengue do Brasil chegam ao BigQuery por uma cópia manual da tabela pública da Base dos Dados (`microdados.raw_uftpr_microdados_brasil`, copiada em 20/09/2026, com notificações só até 29/06/2026), feita por um script que não está no repositório. O OpenDataSUS publica os mesmos microdados do SINAN direto do Ministério da Saúde e está bem mais atualizado: em 16/11/2026, o arquivo de 2026 já tinha 489 mil notificações, até 02/11/2026. Os arquivos ficam num endereço público com `ETag` e `Last-Modified`, o que permite saber se mudaram sem baixá-los.

## What Changes

- **A `process_etl_atlas` passa a ser a DAG completa da ETL:** primeiro o sync do SINAN, depois o dbt, na mesma execução.
  ```
  [sinan] detectar_diferencas ─► baixar/apagar ─► carregar_bronze/remover ─► validar ─► marcar_carregado
                                                                                            │
                                                              decidir_dbt (short-circuit) ◄─┘
                                                                     │
                                          [seed] ─► [bronze] ─► [silver] ─► [gold]   (Cosmos, como hoje)
  ```
  - **Agendamento diário (`@daily`)**, sem catchup, com no máximo uma execução ativa. Continua podendo ser disparada à mão.
  - **Sem novidade na origem:** o sync não faz nada e o dbt é **pulado**, sem custo de BigQuery.
  - **Com algum ano carregado ou removido:** o dbt roda na mesma execução.
  - **Parâmetro opcional `forcar_dbt` (padrão falso):** num disparo manual, roda o dbt mesmo sem dados novos (ex.: mudança só na modelagem).
  - **Disparo manual:** a verificação da origem é feita uma vez, sem ficar esperando. No agendamento diário, o sensor espera em modo reschedule.
- **Grupo `sinan` da DAG**, todas as tarefas em Python (`@task`), sem scripts Bash:
  1. **`detectar_diferencas` (sensor):** compara a origem com o landing.
     - **Origem:** `HEAD` de `DENGBR00` a `DENGBR<ano corrente>`.
     - **Landing:** o `ETag`/`Last-Modified` da origem, guardados na metadata dos objetos.
     - **Resultado:** o plano de baixar, apagar, carregar e remover.
  2. **Landing como espelho exato:** `gs://ppgcc-bucket/landing/sinan/dengue/DENGBR<aa>.csv.zip` (o zip original) e `DENGBR<aa>.csv`.
     - Arquivo alterado é substituído; arquivo que sumiu da origem é apagado, e o ano sai da bronze.
  3. **Tabela bronze materializada:** `bronze.sinan_dengue_opendatasus`, carregada do landing.
     - Sem transformação: todas as colunas como texto, mais as de linhagem.
     - Particionada por ano; cada ano é substituído por inteiro.
  4. **Validação e marcação:** confere linhas e colunas obrigatórias. Só então a metadata do objeto registra a versão como carregada na bronze.
- **Estado do sync no bucket:** a metadata dos objetos (`origem_etag`, `origem_last_modified`, `registros`, `colunas`, `encoding`, `bronze_etag`) guarda o estado. Não há tabela de controle, e a verificação não consulta o BigQuery.
- **dbt:**
  - a tabela bronze vira `source` (`sinan_opendatasus`);
  - o `bronze_dengue_brasil` mapeia os códigos do DATASUS para as colunas que o projeto já usa;
  - silver e gold não mudam de contrato.
- **Fallback:** a fonte antiga (Base dos Dados) continua selecionável pela variável dbt `sinan_source`.
- **Alinhamento com a `add-cosmos-dbt-dags`:** o requisito "Disparo sem configuração" daquela mudança (sem agendamento, sem parâmetros) passa a valer como descrito aqui: diário, com sync antes e o parâmetro opcional `forcar_dbt`.

## Capabilities

### New Capabilities
- `sinan-ingestion`: sync diário dos microdados do SINAN entre o OpenDataSUS e o landing do bucket (espelho exato), materialização da tabela bronze por ano, validação e a decisão de rodar a modelagem na mesma execução.

### Modified Capabilities
- Nenhuma em `openspec/specs/` (ainda vazio). O requisito de disparo da `dbt-orchestration` está em delta na `add-cosmos-dbt-dags`, ainda não arquivada; aquela mudança é alinhada por tarefa desta.

## Impact

- **Código:**
  - `airflow/dags/atlas_ingest/sinan.py`: funções do sync, landing, carga e validação, testáveis sem rede;
  - `airflow/dags/process_etl_atlas.py`: grupo `sinan`, `decidir_dbt`, `@daily` e `forcar_dbt`;
  - `airflow/tests/`.
  - Não haverá DAG separada de ingestão.
- **dbt:**
  - `models/sources.yaml`: nova source;
  - `models/bronze/bronze_dengue_brasil.sql`: mapeamento DATASUS e variável `sinan_source`;
  - teste de equivalência entre as fontes.
- **GCP:**
  - **landing:** cerca de 1,4 GB de zips mais cerca de 12 GB de CSVs descompactados no `ppgcc-bucket`, sem acumular versões. Medido: 2024 tem 187 MB zipado e 1,84 GB descompactado;
  - **BigQuery:** tabela `bronze.sinan_dengue_opendatasus` (≈ 35 milhões de linhas);
  - **service account:** a `training-sa`.
- **Comportamento da ETL:** passa de manual para diária, mas o dbt só roda quando há dados novos ou quando é forçado. O custo diário sem novidade é só o do `HEAD` e da listagem do bucket.
- **Dados:** a série do Brasil passa a ir até a semana mais recente publicada. O OpenDataSUS também não traz descartados (`CLASSI_FIN=5`) nos anos recentes, então a definição de casos prováveis da gold continua correta.
