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

### 3. Sync como grupo da `process_etl_atlas` (antes do dbt)

```
process_etl_atlas  (@daily, catchup=False, max_active_runs=1, params: forcar_dbt=False)

[sinan]
  detectar_diferencas ─┬─► baixar[arquivo] ──┐
       (sensor)        │                     ├─► carregar_bronze[ano] ─► validar[ano] ─► marcar_carregado[ano] ─┐
                       ├─► apagar[arquivo] ──┴─► remover_da_bronze[ano] ────────────────────────────────────────┤
                       │                                                                                          ▼
                       └────────────────────────────────────────────────────────────────────────────────► decidir_dbt
                                                                                                                  │
[seed] ─► [bronze] ─► [silver] ─► [gold]   (DbtTaskGroup do Cosmos, sem mudança) ◄───────────────────────────────┘
```
- **Tudo em Python:** as tarefas usam `@task`, `@task.sensor` e `@task.short_circuit` (chamando `atlas_ingest.sinan`), e o dbt usa o Cosmos. Não há `BashOperator`.
- **`detectar_diferencas`:** `@task.sensor(mode="reschedule", poke_interval=30 min, timeout=20 h, soft_fail=True)`.
  - Faz o `HEAD` da origem e a listagem do landing, e devolve `PokeReturnValue(is_done, xcom_value=plano)`.
  - **No agendamento diário:** espera até haver diferença (`is_done=bool(plano)`).
  - **Em disparo manual** (`dag_run.run_type == "manual"`): verifica uma vez e termina (`is_done=True`), mesmo com o plano vazio, para não segurar quem pediu `forcar_dbt`.
  - Sem diferença até o timeout, fica pulada (`soft_fail`).
- **Tarefas mapeadas:** `baixar`, `apagar`, `carregar_bronze`, `validar`, `marcar_carregado` e `remover_da_bronze` usam *dynamic task mapping* sobre as listas do plano. Uma lista vazia vira tarefa pulada. Cada arquivo ou ano aparece como instância própria.
- **`decidir_dbt`:** `@task.short_circuit(trigger_rule="none_failed")`.
  - Devolve verdadeiro se `params.forcar_dbt` ou se algum ano foi marcado ou removido; do contrário, pula os grupos do dbt.
  - Com `none_failed`, roda mesmo quando o sensor ficou pulado.
  - Se uma etapa do sync falhar, não roda, e a execução fica vermelha.
  - Usa `ignore_downstream_trigger_rules=True`: tudo a jusante (os grupos do Cosmos) é pulado.
- **Retentativas:** `retries=2` nas tarefas de rede (sensor, baixar, apagar). Os grupos do dbt continuam com `retries=0`.
- **Sem DAG separada:** a `process_sinan_ingest_atlas` do plano anterior e o `TriggerDagRunOperator` saem.
- **Alinhamento:** o requisito "Disparo sem configuração" da `add-cosmos-dbt-dags` (sem agendamento e sem parâmetros) é atualizado lá (tarefa 5.2).

As etapas por ano, do jeito que já estão implementadas e medidas (seção 8):
- **`baixar`:**
  1. download em streaming e extração do CSV;
  2. contagem de registros e colunas, com detecção de encoding: UTF-8, com latin-1 como reserva;
  3. upload do `.csv` e depois do `.csv.zip`, com a metadata.

  Se o zip já tem o mesmo `origem_etag` e `origem_last_modified`, não envia de novo.
- **`apagar`:** remove o `.csv.zip` e o `.csv` do landing.
- **`carregar_bronze`:** duas etapas no BigQuery, ambas atômicas.
  1. **Staging:** load job do `.csv` para `bronze._stg_sinan_dengue_<ano>`, com o schema do próprio cabeçalho (todas as colunas `STRING`), `encoding` da metadata, `skip_leading_rows=1`, `allow_quoted_newlines=True` e `WRITE_TRUNCATE`.
  2. **Destino:** query job para a partição `$<ano>` com `WRITE_TRUNCATE` e `ALLOW_FIELD_ADDITION`, mais as colunas de linhagem. As colunas que a tabela tem e o ano não tem entram como `NULL` (seção 8).

  A staging é apagada no fim.
- **`validar`:**
  - `COUNT(*)` da partição = `registros` da metadata = `output_rows` do load;
  - colunas obrigatórias presentes.
- **`marcar_carregado`:** grava `bronze_etag = origem_etag` na metadata do zip.
- **`remover_da_bronze`:** `DELETE` da partição do ano removido.

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
- **Source:** `sinan_opendatasus` (schema `bronze`, tabela `sinan_dengue_opendatasus`), com descrição e as colunas de linhagem. Sem bloco de freshness, a pedido do usuário: a coluna `carregado_em` continua disponível para consulta.
- **`bronze_dengue_brasil`:** escolhe a fonte por `var('sinan_source')`. No ramo OpenDataSUS:
  - **layout por linha:** `CLASSI_FIN IS NOT NULL OR ano_arquivo >= 2007` identifica o SINAN Net; antes disso, as colunas `CON_*` (seção 8);
  - **UF:** quando o valor é numérico (SINAN Net), o código do IBGE vira sigla pela dimensão de municípios; quando já é sigla (SINAN Windows), fica como está. Vale para notificação, residência e infecção (`COUFINF` / `CON_INF_UF`);
  - **município:** 6 dígitos (SINAN Net) viram o código de 7 dígitos pelo join com `bronze_dim_municipio_brasil` em `DIV(municipality_id, 10)`; 7 dígitos (SINAN Windows) ficam como estão;
  - **classificação, evolução e critério:** `COALESCE(CLASSI_FIN, CON_CLASSI)`, `COALESCE(EVOLUCAO, CON_EVOLUC)` e `COALESCE(CRITERIO, CON_CRITER)`;
  - **datas:** `parse_date_any`;
  - **idade:** decodificada para anos nos dois formatos: `NU_IDADE_N` (`4xxx`) e `NU_IDADE` (`Axxx`);
  - **demais colunas:** renomeadas para os mesmos nomes de hoje, com a mesma decodificação que a Base dos Dados aplicava, conferida coluna a coluna;
  - **`case_id`:** o mesmo md5 das colunas naturais.
- **Rollback:** `--vars '{sinan_source: basedosdados}'`.

### 7. Corte para a nova fonte
1. Sync inicial com o bucket vazio, ou seja, todos os anos. A variável fica em `basedosdados` durante a comparação.
2. Comparação entre as fontes, registrada em `docs/referencias/sinan-opendatasus.md`, com critério por tipo de ano:
   - **anos fechados (até 2020):** total por UF idêntico, 0%. Em 2000, 2003 e 2013, os totais anuais já batem exatamente;
   - **anos republicados (2021+):** o OpenDataSUS continua atualizando esses anos depois do retrato da Base dos Dados. Em 2023 houve +9,1%, todo em notificações novas (classes 10, 11 e 0), com inconclusivos e sem classificação idênticos e duplicidade de 0,1%. Por isso o critério é: por UF e classificação, OpenDataSUS ≥ 99% da Base dos Dados. A fonte nova pode ganhar registros, mas não perder.
   - **ano corrente:** fica fora do teste e só é documentado, por decisão do usuário. Em 2026, entre o retrato de junho e a publicação de novembro, os registros sem classificação e os inconclusivos caíram muito (ex.: TO, de 5.968 para 690 sem classificação), porque viraram confirmados ou descartados. O total subiu de 398.786 para 489.197.
3. Padrão trocado para `opendatasus` e `process_etl_atlas` completa.

### 8. Ajustes depois da primeira execução agendada

- **Carga por ano isolada:** `carregar_bronze → validar → marcar_carregado` virou um grupo mapeado por ano (`sinan.carga_ano`).
  - **Problema:** com três tarefas mapeadas encadeadas, uma falha num ano (2008) deixou `upstream_failed` o `validar` e o `marcar_carregado` de **todos** os anos. O Airflow só expande a tarefa seguinte quando todas as instâncias da anterior terminam bem.
  - **Agora:** cada ano tem sua cadeia; um ano ruim não impede os outros de serem marcados. O dbt continua sem rodar naquele dia (`decidir_dbt` com `none_failed`), e a execução fica vermelha.
- **Caracteres de controle:** o arquivo de 2008 tem um byte nulo (`\x00`) em `DT_OBITO` (linha 617.303). O load job agora usa `preserve_ascii_control_characters=True`, e a bronze guarda o dado como veio, em vez de rejeitar o arquivo.

### 9. Medições do landing (16/11/2026)

| Arquivo | Tempo | Zip | CSV | Registros | Colunas | Encoding |
|---|---:|---:|---:|---:|---:|---|
| DENGBR26 | 16 s | 15,9 MB | 137 MB | 489.197 | 121 | UTF-8 |
| DENGBR24 | 285 s | 187,3 MB | 1.840 MB | 6.564.924 | 121 | UTF-8 |
| DENGBR13 | 63 s | 41,0 MB | 394 MB | 2.035.119 | 66 | UTF-8 |
| DENGBR00 | 10 s | 2,6 MB | 39 MB | 172.855 | 107 | UTF-8 |

- **Reenvio:** uma segunda execução com o mesmo ETag não reenviou nada.
- **Colunas variam muito entre anos** (66 a 121). A tabela bronze acumula a união das colunas (`ALLOW_FIELD_ADDITION`).
- **Dois layouts do SINAN.** O separador é vírgula e as datas são ISO em todos os anos; o resto muda:

  | Item | 2000–2006 (SINAN Windows) | 2007 em diante (SINAN Net/Online) |
  |---|---|---|
  | Colunas | 107 | 63 (2007) a 121 (2024+) |
  | Classificação final | `CON_CLASSI` | `CLASSI_FIN` |
  | Evolução | `CON_EVOLUC` | `EVOLUCAO` |
  | Critério | `CON_CRITER` | `CRITERIO` |
  | Idade | `NU_IDADE`, ex.: `A021` (A = anos) | `NU_IDADE_N`, ex.: `4021` (4 = anos) |
  | UF (`SG_UF_NOT`, `SG_UF`) | sigla (`AC`) | código do IBGE (`12`) |
  | Município (`ID_MUNICIP`, `ID_MN_RESI`) | 7 dígitos | 6 dígitos |
  | Descartados (classificação 5) | presentes | ausentes nos anos recentes |

  A validação aceita os nomes alternativos de cada coluna obrigatória: classificação = `CLASSI_FIN` **ou** `CON_CLASSI`, evolução = `EVOLUCAO` **ou** `CON_EVOLUC`. O mapeamento do dbt trata os dois layouts (seção 6).
- **Partições de anos com menos colunas:** o SQL de carga projeta a lista completa da tabela, com `CAST(NULL AS STRING) AS <col>` para as ausentes. Isso não depende de o BigQuery aceitar uma partição com schema menor.

## Risks / Trade-offs

- **[Sem histórico no landing]** → é escolha do usuário. A versão carregada fica registrada em `arquivo_etag` na bronze. Se a origem publicar algo errado, a recuperação depende de uma nova publicação ou do fallback para a Base dos Dados.
- **[Arquivo some da origem por falha momentânea do S3]** → só conta como removido se a origem respondeu aos outros arquivos. A remoção apaga dados da bronze e dispara a modelagem, então essa regra evita apagar por instabilidade.
- **[ETag multipart não é hash do conteúdo]** → a comparação é sempre contra a metadata gravada no upload, nunca contra o MD5/CRC do GCS. Se a origem republicar o mesmo conteúdo com outro ETag, o arquivo é baixado e recarregado (custo pequeno, resultado igual).
- **[Schema varia entre anos (colunas, encoding, formato de data)]** → tudo como `STRING`, `ALLOW_FIELD_ADDITION` e datas pela `parse_date_any`. A tarefa 2.3 confere os anos 2000, 2013 e 2024.
- **[Partição com menos colunas que a tabela]** → conferido na carga de 2000 depois de 2026. Se o BigQuery recusar, o SQL completa as colunas ausentes com `NULL` a partir do schema da tabela.
- **[2024 com 187 MB zipado, mais de 1 GB descompactado]** → streaming para disco temporário e load job a partir do GCS. O tempo é registrado na tarefa 2.2.
- **[A ETL passa a ser agendada]** → o sensor em reschedule ocupa o worker só nos pokes. O `soft_fail` e o `decidir_dbt` evitam execuções vermelhas e custo de dbt em dias sem novidade. O dbt manual continua possível com `forcar_dbt`.
- **[Sensor segurando a execução por até 20 h]** → enquanto a execução diária espera, não começa outra (`max_active_runs=1`). Um disparo manual nesse período fica na fila. Por isso o disparo manual verifica a origem só uma vez: assim ele não fica preso esperando.
- **[Divergência com a Base dos Dados]** → critério por tipo de ano (seção 7): igualdade exata até 2020 e, de 2021 em diante, "não perder registros" (≥ 99% por UF e classificação). Fora disso, o corte não acontece.

## Migration Plan

Segue a seção 7 de Decisions. Para voltar atrás, use `sinan_source=basedosdados` e pause a DAG. O landing e a bronze podem ficar.

## Open Questions

- Nenhuma que bloqueie. A janela de 20 h do sensor pode ser revista depois de algumas semanas observando os `Last-Modified` da origem.
