# Design

## Context

O que foi conferido em 16/11/2026:
- **Origem:** `https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/SINAN/Dengue/csv/DENGBR<aa>.csv.zip`, de 2000 (`00`) a 2026 (`26`).
  - **Acesso:** público; responde `HEAD` com `ETag`, `Last-Modified` e `Content-Length`.
  - **Frequência de atualização:** os anos de 2021 em diante foram republicados em 14/11/2026; os anteriores, em 01/10/2026.
  - **Tamanhos:** de 2,6 MB (2000) a 187 MB (2024, zipado).
  - **Formatos:** os formatos `parquet` e `dbc` respondem 403. O `json` existe, mas o CSV é o mais simples de carregar.
  - **Portal CKAN:** a API do OpenDataSUS não respondeu da rede corporativa. O S3 respondeu.
- **Conteúdo (`DENGBR26.csv`):**
  - CSV UTF-8, separador vírgula, 121 colunas com os nomes originais do DATASUS;
  - 489.197 linhas, com `DT_NOTIFIC` até 2026-11-02;
  - `CLASSI_FIN` sem o código 5 (descartados), como já acontecia na fonte da Base dos Dados.
- **Situação atual:**
  - `microdados.raw_uftpr_microdados_brasil` é uma cópia de `basedosdados.br_ms_sinan.microdados_dengue` (33.462.203 linhas, colunas renomeadas em português; UF já como sigla e município com 7 dígitos);
  - `bronze_dengue_brasil` (view) lê essa tabela e renomeia para inglês;
  - silver e gold dependem das colunas do bronze.
- **Plataforma:**
  - Airflow 3.3.2 com providers Google e Cosmos;
  - Connection `google_cloud_default` (`training-sa`, que escreve no `ppgcc-bucket` e no BigQuery);
  - `process_etl_atlas` (Cosmos) já faz a modelagem.

## Goals / Non-Goals

**Goals:**
- Camadas explícitas e auditáveis: **landing** (arquivo original no GCS), **tabela bronze** (materializada, sem transformação) e **modelagem** (dbt sobre a bronze como source).
- Ingestão incremental por ano, idempotente e atômica, acionada por mudança na origem.
- Manter o contrato de colunas do `bronze_dengue_brasil` e a fonte antiga como fallback.

**Non-Goals:**
- Outras doenças do SINAN (chikungunya, zika) ou outros países. O desenho permite estender depois.
- Formato JSON, DBC ou o portal CKAN.
- Limpeza do landing (retenção). As versões ficam; uma política de ciclo de vida do bucket fica para depois.
- Mudar silver e gold.

## Decisions

### 1. DAG `process_sinan_ingest_atlas`, uma tarefa por etapa

```
detectar_versoes ──► landing[ano] ──► carregar_bronze[ano] ──► validar[ano] ──► registrar_controle ──► disparar_modelagem
   (sensor)          (mapeada)         (mapeada)               (mapeada)
```
- **Execução:** `schedule="@daily"`, `catchup=False`, `max_active_runs=1` e `retries=2` (rede). As três etapas por ano usam *dynamic task mapping* sobre a lista de anos alterados, então cada ano aparece como instância própria na UI.
- **Sensor (`detectar_versoes`):** `@task.sensor(mode="reschedule", poke_interval=30 min, timeout=20 h, soft_fail=True)`.
  - Faz `HEAD` nos arquivos de 2000 até o ano corrente; o 404 do ano seguinte é ignorado.
  - Lê `bronze.sinan_dengue_opendatasus_controle`.
  - Devolve `PokeReturnValue(is_done=True, xcom_value=[{ano, url, etag, last_modified, tamanho}])` só quando algum ano tem ETag diferente do registrado.
  - `soft_fail`: sem mudança no dia, a execução fica pulada e nada a jusante roda.
  - O modo reschedule libera o slot do worker entre as checagens.
- **Landing (`landing`):**
  - baixa em streaming para um diretório temporário;
  - grava o zip original em `gs://ppgcc-bucket/landing/sinan/dengue/ano=<AAAA>/<etag>/DENGBR<aa>.csv.zip` e o CSV descompactado em `…/DENGBR<aa>.csv`;
  - se os objetos já existem com o mesmo ETag (retentativa), não envia de novo;
  - conta os registros do CSV com o leitor de CSV, que respeita quebras de linha entre aspas, e devolve a contagem para a validação.
- **Carga (`carregar_bronze`):** duas etapas no BigQuery, ambas atômicas.
  1. **Staging:** load job do CSV do landing para `bronze._stg_sinan_dengue_<ano>`, com o schema do cabeçalho (todas as colunas `STRING`), `skip_leading_rows=1`, `allow_quoted_newlines=True` e `WRITE_TRUNCATE`.
  2. **Destino:** query job `SELECT *, <ano> AS ano_arquivo, @etag AS arquivo_etag, @uri AS arquivo_uri, CURRENT_TIMESTAMP() AS carregado_em FROM stg` para a partição `bronze.sinan_dengue_opendatasus$<ano>`, com `WRITE_TRUNCATE` e `schema_update_options=[ALLOW_FIELD_ADDITION]`. Substitui só aquele ano; se falhar, a partição antiga fica intacta.

  A staging é apagada no fim.
- **Tabela bronze:** `bronze.sinan_dengue_opendatasus`, particionada por intervalo inteiro em `ano_arquivo` (2000–2100, passo 1) e clusterizada por `SG_UF_NOT`.
  - **Nomes:** os de origem, para auditoria contra o arquivo.
  - **Dataset:** `bronze`, por pedido do usuário. É uma tabela carregada, não gerenciada pelo dbt: o nome sem prefixo `bronze_` a distingue das views do dbt no mesmo dataset.
- **Validação (`validar`):**
  - `COUNT(*)` da partição = registros contados no landing = `output_rows` do load;
  - presença de `DT_NOTIFIC`, `SG_UF_NOT`, `ID_MUNICIP`, `SG_UF`, `ID_MN_RESI`, `DT_SIN_PRI`, `CLASSI_FIN` e `EVOLUCAO`.

  Qualquer divergência levanta erro.
- **Controle (`registrar_controle`):** `MERGE` em `bronze.sinan_dengue_opendatasus_controle` (ano, etag, last_modified, tamanho, linhas, arquivo_uri, carregado_em). Roda só se todas as validações passarem; assim, uma falha faz o ano ser tentado de novo no dia seguinte.
- **Modelagem (`disparar_modelagem`):** `TriggerDagRunOperator(trigger_dag_id="process_etl_atlas")`, sem esperar o término.

### 2. Código testável fora do Airflow
- **Funções:** as funções puras e de I/O ficam em `airflow/dags/atlas_ingest/sinan.py` (`listar_versoes`, `anos_alterados`, `caminhos_landing`, `contar_registros_csv`, `sql_carga`, `validar_contagens`).
- **Hooks:** a DAG usa `GCSHook` e `BigQueryHook` com `google_cloud_default`, e `requests` para o `HEAD`/download. Em dev, o `REQUESTS_CA_BUNDLE` já aponta para o bundle corporativo.
- **`.airflowignore`:** ganha `atlas_ingest/`. O módulo continua importável, porque a pasta de DAGs está no `sys.path`, mas o processador não o varre.
- **Testes:**
  - sem rede: comparação de versões, caminhos, contagem de CSV com aspas e quebra de linha, SQL gerado;
  - DagBag: sensor em reschedule e `soft_fail`, mapeamento, ordem e trigger.

### 3. dbt: bronze como source e mapeamento DATASUS
- **Source:** `sinan_opendatasus` (schema `bronze`, tabela `sinan_dengue_opendatasus`), com descrição e `loaded_at_field: carregado_em`, para `dbt source freshness` (aviso com 10 dias, erro com 30).
- **`bronze_dengue_brasil`:** escolhe a fonte por `var('sinan_source', 'opendatasus')`. No ramo OpenDataSUS:
  - **UF:**
    - `SG_UF_NOT` e `SG_UF` chegam como código do IBGE de 2 dígitos;
    - a sigla vem da dimensão de municípios (os 2 primeiros dígitos do código do IBGE + `state_code`), sem seed nova;
  - **município:** `ID_MUNICIP`, `ID_MN_RESI` e `COMUNINF` chegam com 6 dígitos (sem o dígito verificador); o código de 7 dígitos vem do join com `bronze_dim_municipio_brasil` em `DIV(municipality_id, 10)`;
  - **datas:** macro `parse_date_any`, já existente, porque o formato pode variar entre anos;
  - **idade:** `NU_IDADE_N` vem codificada (o primeiro dígito é a unidade; 4 = anos) e é decodificada para anos, como a Base dos Dados entrega;
  - **demais colunas:** sexo, raça, escolaridade, gestante, internação, classificação, critério, FHD, autóctone, sorotipo, país/UF de infecção, evolução, sistema e digitação são renomeadas para os mesmos nomes de hoje. Onde a Base dos Dados entregava o valor já decodificado, o model aplica a mesma decodificação; a tarefa 4.2 confere coluna a coluna;
  - **`case_id`:** o mesmo md5 das colunas naturais, já mapeadas.
- **Rollback:** `--vars '{sinan_source: basedosdados}'` usa a tabela antiga sem mudar código.

### 4. Corte para a nova fonte
1. Carga inicial de todos os anos pela DAG, com a modelagem ainda na fonte antiga: a variável fica em `basedosdados` durante a comparação.
2. Comparação por ano e UF entre as fontes, no BigQuery, registrada em `docs/referencias/sinan-opendatasus.md`.
3. Troca do padrão para `opendatasus` e `process_etl_atlas` completa.

## Risks / Trade-offs

- **[Schema varia entre anos (colunas, encoding, formato de data)]** → tudo como `STRING` na bronze, `ALLOW_FIELD_ADDITION` e datas pela `parse_date_any`. A tarefa 2.3 confere os anos 2000, 2013 e 2024 (encoding e colunas) antes da carga completa. Se algum ano vier em latin-1, a carga declara `encoding` por ano.
- **[Partição com menos colunas que a tabela]** → o `SELECT *` de um ano antigo pode não ter colunas que a tabela já tem. Isso será conferido na carga de 2000 depois de 2026. Se o BigQuery recusar, o SQL de carga completa as colunas ausentes com `NULL` a partir do schema da tabela.
- **[2024 com 187 MB zipado, mais de 1 GB descompactado]** → streaming para disco temporário, upload por arquivo e load job a partir do GCS (o BigQuery lê direto, sem passar pela memória do worker).
- **[Primeira DAG agendada]** → o sensor em reschedule ocupa o worker só nos pokes, e o `soft_fail` evita execuções vermelhas em dias sem novidade.
- **[OpenDataSUS fora do ar ou URL alterada]** → o sensor falha só depois das retentativas; sem nova versão, a modelagem segue com a última carga válida. O padrão da URL fica numa constante.
- **[Divergência com a Base dos Dados]** → limite de 1% por UF e ano completo, com as diferenças documentadas. Acima disso, o corte não acontece.
- **[Custo]** → o `HEAD` diário é grátis. A carga de um ano recente (≈ 500 mil linhas) é um load job, também grátis, mais um query job sobre a staging (dezenas de MB). A carga inicial completa lê cerca de 15 GB de staging uma vez.

## Migration Plan

Segue a seção 4 de Decisions. Para voltar atrás, use a variável `sinan_source=basedosdados` e pause a DAG. A tabela bronze e o landing podem ficar.

## Open Questions

- Nenhuma que bloqueie. A frequência `@daily` com janela de 20 h pode ser revista depois de algumas semanas de observação dos `Last-Modified`.
