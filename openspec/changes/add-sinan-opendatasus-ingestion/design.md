# Design

## Context

O que foi conferido em 16/11/2026:
- **Origem:** `https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/SINAN/Dengue/csv/DENGBR<aa>.csv.zip`, de 2000 (`00`) a 2026 (`26`).
  - **Acesso:** público; responde `HEAD` com `ETag`, `Last-Modified` e `Content-Length`.
  - **Frequência de atualização:** os anos de 2021 em diante foram republicados em 14/11/2026; os anteriores, em 01/10/2026.
  - **Tamanhos:** de 2,6 MB (2000) a 187 MB (2024, zipado).
  - **ETag:** é de upload multipart do S3 (ex.: `"77c3b661…-5"`), ou seja, **não é o MD5 do conteúdo**. Não dá para comparar com o hash do objeto no GCS.
  - **Formatos:** `parquet` e `dbc` respondem 403. O `json` existe, mas o CSV é o mais simples.
  - **Portal CKAN:** a API não respondeu da rede corporativa. O S3 respondeu.
- **Conteúdo (`DENGBR26.csv`):**
  - CSV UTF-8, separador vírgula, 121 colunas com os nomes originais do DATASUS;
  - 489.197 linhas, com `DT_NOTIFIC` até 2026-11-02;
  - `CLASSI_FIN` sem o código 5 (descartados).
- **Situação atual:**
  - `microdados.raw_uftpr_microdados_brasil` é uma cópia de `basedosdados.br_ms_sinan.microdados_dengue` (33.462.203 linhas, colunas renomeadas em português; UF já como sigla e município com 7 dígitos);
  - `bronze_dengue_brasil` (view) lê essa tabela;
  - silver e gold dependem das colunas do bronze.
- **Plataforma:**
  - Airflow 3.3.2 com providers Google e Cosmos;
  - Connection `google_cloud_default` (`training-sa`, que escreve no `ppgcc-bucket` e no BigQuery);
  - `process_etl_atlas` (Cosmos) já faz a modelagem.

## Goals / Non-Goals

**Goals:**
- Camadas explícitas:
  - **landing:** espelho exato da origem no GCS;
  - **tabela bronze:** materializada, sem transformação;
  - **modelagem:** dbt sobre a bronze como source.
- Sync diário, incremental por arquivo, idempotente e retomável: uma falha num dia é recuperada no seguinte, sem baixar de novo o que já está no landing.
- Estado do sync no próprio bucket, sem tabela de controle e sem consulta ao BigQuery na verificação.
- Manter o contrato do `bronze_dengue_brasil` e a fonte antiga como fallback.

**Non-Goals:**
- Histórico de versões no landing (escolha do usuário: espelho exato).
- Outras doenças do SINAN ou outros países. O desenho permite estender depois.
- Formatos JSON, DBC ou o portal CKAN.
- Mudar silver e gold.

## Decisions

### 1. Estado do sync na metadata dos objetos do landing

Layout (espelho, uma versão por arquivo):
```
gs://ppgcc-bucket/landing/sinan/dengue/DENGBR26.csv.zip   ← zip original da origem
gs://ppgcc-bucket/landing/sinan/dengue/DENGBR26.csv       ← descompactado (entrada da carga)
```

Metadata customizada gravada no `.csv.zip`:

| Chave | Valor | Quando é gravada |
|---|---|---|
| `origem_etag` | ETag da origem | upload do zip |
| `origem_last_modified` | `Last-Modified` da origem | upload do zip |
| `origem_tamanho` | `Content-Length` | upload do zip |
| `registros` | número de registros do CSV | upload do zip |
| `bronze_etag` | ETag da versão carregada e validada na bronze | depois da validação |

O zip é o único objeto com o estado; o `.csv` é derivado dele.

### 2. Plano do sync (função pura, testável sem rede)

`planejar_sync(origem: dict[nome → (etag, last_modified, tamanho)], landing: dict[nome → metadata])` devolve:
- **`baixar`:** nomes na origem que não estão no landing, ou com `origem_etag` ou `origem_last_modified` diferente. O usuário pediu hash **ou** data: qualquer uma das duas diferente basta.
- **`apagar`:** nomes no landing que não estão na origem.
- **`carregar`:** anos em `baixar`, mais os anos já no landing com `bronze_etag` diferente de `origem_etag` (carga anterior que falhou).
- **`remover_da_bronze`:** anos em `apagar`.

A lista da origem cobre de 2000 até o ano corrente. O ano corrente pode ainda não existir em janeiro: um 404 da origem é "ausente", não erro. Mas um 404 num ano que já existia no landing, **com os demais anos respondendo**, conta como remoção. Se a origem inteira falhar (rede), o sensor falha e tenta de novo, sem apagar nada.

### 3. DAG `process_sinan_ingest_atlas`

```
detectar_diferencas ─┬─► baixar[arquivo] ──┐
     (sensor)        │                     ├─► carregar_bronze[ano] ─► validar[ano] ─► marcar_carregado[ano] ─┐
                     ├─► apagar[arquivo] ──┴─► remover_da_bronze[ano] ────────────────────────────────────────┴─► disparar_modelagem
```
- **Execução:**
  - `schedule="@daily"`, `catchup=False`, `max_active_runs=1` e `retries=2` (rede);
  - `baixar`, `apagar`, `carregar_bronze`, `validar`, `marcar_carregado` e `remover_da_bronze` usam *dynamic task mapping*: cada arquivo ou ano aparece como instância própria na UI, e uma lista vazia vira tarefa pulada.
- **`detectar_diferencas`:** `@task.sensor(mode="reschedule", poke_interval=30 min, timeout=20 h, soft_fail=True)`.
  - Faz o `HEAD` da origem e a listagem do landing (`GCSHook.list` + metadata).
  - Devolve `PokeReturnValue(is_done=bool(plano), xcom_value=plano)`.
  - Sem diferença até o timeout, fica pulada, e nada a jusante roda.
- **`baixar`:**
  1. download em streaming para disco temporário;
  2. contagem dos registros do CSV com o leitor de CSV, que respeita quebras de linha entre aspas;
  3. upload do `.csv` e depois do `.csv.zip`, com a metadata (sem `bronze_etag`). Assim, o estado só muda quando os dois objetos já estão no lugar.

  Se o objeto no landing já tem o mesmo `origem_etag` (retentativa), não envia de novo.
- **`apagar`:** remove o `.csv.zip` e o `.csv` do landing.
- **`carregar_bronze`:** duas etapas no BigQuery, ambas atômicas.
  1. **Staging:** load job do `.csv` do landing para `bronze._stg_sinan_dengue_<ano>`, com o schema do cabeçalho (todas as colunas `STRING`), `skip_leading_rows=1`, `allow_quoted_newlines=True` e `WRITE_TRUNCATE`.
  2. **Destino:** query job `SELECT *, <ano> AS ano_arquivo, @etag AS arquivo_etag, @uri AS arquivo_uri, CURRENT_TIMESTAMP() AS carregado_em` para a partição `bronze.sinan_dengue_opendatasus$<ano>`, com `WRITE_TRUNCATE` e `ALLOW_FIELD_ADDITION`. Se falhar, a partição antiga fica intacta.

  A staging é apagada no fim.
- **`validar`:**
  - `COUNT(*)` da partição = `registros` da metadata = `output_rows` do load;
  - colunas obrigatórias presentes: `DT_NOTIFIC`, `SG_UF_NOT`, `ID_MUNICIP`, `SG_UF`, `ID_MN_RESI`, `DT_SIN_PRI`, `CLASSI_FIN` e `EVOLUCAO`.
- **`marcar_carregado`:** grava `bronze_etag = origem_etag` na metadata do zip. Só depois disso o ano sai do plano dos dias seguintes.
- **`remover_da_bronze`:** `DELETE` da partição do ano removido, ou expiração da partição.
- **`disparar_modelagem`:** `TriggerDagRunOperator(trigger_dag_id="process_etl_atlas")`.
  - `trigger_rule="none_failed_min_one_success"`: roda se algum ano foi marcado ou removido e nada falhou.
  - Não espera o término da modelagem.

### 4. Tabela bronze
- **Tabela:** `bronze.sinan_dengue_opendatasus`, particionada por intervalo inteiro em `ano_arquivo` (2000–2100, passo 1) e clusterizada por `SG_UF_NOT`.
- **Criação:** pela própria DAG (`CREATE TABLE IF NOT EXISTS`) na primeira carga.
- **Nomes de coluna:** os da origem, para auditoria contra o arquivo.
- **Dataset:** `bronze`, por pedido do usuário. É uma tabela carregada, não gerenciada pelo dbt; o nome sem o prefixo `bronze_` a distingue das views do dbt.

### 5. Código testável fora do Airflow
- **Funções:** `airflow/dags/atlas_ingest/sinan.py` traz `url_arquivo`, `listar_origem`, `listar_landing`, `planejar_sync`, `contar_registros_csv`, `sql_carga` e `validar_contagens`.
- **Hooks e rede:** `GCSHook` e `BigQueryHook` com `google_cloud_default`, e `requests` para `HEAD`/download. Em dev, `REQUESTS_CA_BUNDLE` já aponta para o bundle corporativo.
- **`.airflowignore`:** ganha `atlas_ingest/`. O módulo continua importável, mas o processador não o varre.
- **Testes sem rede:**
  - plano (arquivo novo, ETag diferente, só a data diferente, removido da origem, bronze atrás do landing, origem toda indisponível);
  - contagem de CSV com aspas e quebra de linha;
  - SQL gerado;
  - DagBag (sensor em reschedule com `soft_fail`, mapeamentos, trigger rule do disparo).

### 6. dbt: bronze como source e mapeamento DATASUS
- **Source:** `sinan_opendatasus` (schema `bronze`, tabela `sinan_dengue_opendatasus`), com `loaded_at_field: carregado_em` e freshness (aviso com 10 dias, erro com 30).
- **`bronze_dengue_brasil`:** escolhe a fonte por `var('sinan_source')`. No ramo OpenDataSUS:
  - **UF:** `SG_UF_NOT`, `SG_UF` e `COUFINF` (código do IBGE) viram sigla pela dimensão de municípios;
  - **município:** `ID_MUNICIP`, `ID_MN_RESI` e `COMUNINF` (6 dígitos) viram o código de 7 dígitos pelo join com `bronze_dim_municipio_brasil` em `DIV(municipality_id, 10)`;
  - **datas:** `parse_date_any`;
  - **idade:** `NU_IDADE_N` decodificada para anos;
  - **demais colunas:** renomeadas para os mesmos nomes de hoje, com a mesma decodificação que a Base dos Dados aplicava, conferida coluna a coluna;
  - **`case_id`:** o mesmo md5 das colunas naturais.
- **Rollback:** `--vars '{sinan_source: basedosdados}'`.

### 7. Corte para a nova fonte
1. Sync inicial com o bucket vazio, ou seja, todos os anos. A variável fica em `basedosdados` durante a comparação.
2. Comparação por ano e UF entre as fontes, registrada em `docs/referencias/sinan-opendatasus.md`.
3. Padrão trocado para `opendatasus` e `process_etl_atlas` completa.

## Risks / Trade-offs

- **[Sem histórico no landing]** → é escolha do usuário. A versão carregada fica registrada em `arquivo_etag` na bronze. Se a origem publicar algo errado, a recuperação depende de uma nova publicação ou do fallback para a Base dos Dados.
- **[Arquivo some da origem por falha momentânea do S3]** → só conta como removido se a origem respondeu aos outros arquivos. A remoção apaga dados da bronze e dispara a modelagem, então essa regra evita apagar por instabilidade.
- **[ETag multipart não é hash do conteúdo]** → a comparação é sempre contra a metadata gravada no upload, nunca contra o MD5/CRC do GCS. Se a origem republicar o mesmo conteúdo com outro ETag, o arquivo é baixado e recarregado (custo pequeno, resultado igual).
- **[Schema varia entre anos (colunas, encoding, formato de data)]** → tudo como `STRING`, `ALLOW_FIELD_ADDITION` e datas pela `parse_date_any`. A tarefa 2.3 confere os anos 2000, 2013 e 2024.
- **[Partição com menos colunas que a tabela]** → conferido na carga de 2000 depois de 2026. Se o BigQuery recusar, o SQL completa as colunas ausentes com `NULL` a partir do schema da tabela.
- **[2024 com 187 MB zipado, mais de 1 GB descompactado]** → streaming para disco temporário e load job a partir do GCS. O tempo é registrado na tarefa 2.2.
- **[Primeira DAG agendada]** → o sensor em reschedule ocupa o worker só nos pokes, e o `soft_fail` evita execuções vermelhas em dias sem novidade.
- **[Divergência com a Base dos Dados]** → limite de 1% por UF e ano completo, com as diferenças documentadas. Acima disso, o corte não acontece.

## Migration Plan

Segue a seção 7 de Decisions. Para voltar atrás, use `sinan_source=basedosdados` e pause a DAG. O landing e a bronze podem ficar.

## Open Questions

- Nenhuma que bloqueie. A janela de 20 h do sensor pode ser revista depois de algumas semanas observando os `Last-Modified` da origem.
