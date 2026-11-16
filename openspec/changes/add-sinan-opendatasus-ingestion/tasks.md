# Tasks

## 1. Funções de ingestão (sem rede)

- [ ] 1.1 Criar `airflow/dags/atlas_ingest/__init__.py` e `sinan.py`:
  - URL por ano;
  - `listar_versoes`, com `HEAD` de 2000 até o ano corrente, ignorando o 404 do futuro;
  - `anos_alterados`, que compara com o controle;
  - `caminhos_landing` (`ano=<AAAA>/<etag>/…`);
  - `contar_registros_csv`, que respeita aspas e quebras de linha;
  - `sql_carga`, com partição, colunas de linhagem e `WRITE_TRUNCATE`;
  - `validar_contagens`, com a lista de colunas obrigatórias.

  Acrescentar `atlas_ingest/` ao `airflow/dags/.airflowignore`. Verificar com `ruff`.
- [ ] 1.2 Testes unitários em `airflow/tests/test_sinan_ingest.py`:
  - ano novo, ETag igual e ETag diferente;
  - caminho por ETag;
  - CSV com campo entre aspas contendo quebra de linha;
  - SQL com a partição e as colunas de linhagem;
  - validação falhando por contagem ou por coluna ausente.

  Verificar rodando dentro da imagem.
- [ ] 1.3 Commit em `dev` (`feat(ingest): funções de ingestão do SINAN OpenDataSUS`); verificar `git log -1 --stat`

## 2. Landing no bucket

- [ ] 2.1 Implementar a tarefa `landing` (download em streaming, upload do zip original e do CSV descompactado com `GCSHook`, pulando o envio se o objeto com o mesmo ETag já existe, contagem de registros); verificar rodando para 2026 em dev e listando `gs://ppgcc-bucket/landing/sinan/dengue/ano=2026/<etag>/`
- [ ] 2.2 Rodar o landing de novo para o mesmo ano e conferir que nada é reenviado; registrar o tempo e o tamanho de 2024, o maior ano, no design
- [ ] 2.3 Conferir encoding, separador, número de colunas e formato de data dos arquivos de 2000, 2013 e 2024 no landing; ajustar a carga se algum ano divergir (encoding por ano) e registrar no design

## 3. Tabela bronze materializada

- [ ] 3.1 Criar a tabela `bronze.sinan_dengue_opendatasus` (particionada por `ano_arquivo`, clusterizada por `SG_UF_NOT`) e a de controle `bronze.sinan_dengue_opendatasus_controle`, de forma idempotente na própria DAG (`CREATE TABLE IF NOT EXISTS`); verificar com `bq show` o particionamento
- [ ] 3.2 Implementar `carregar_bronze`:
  1. load job do CSV do landing para a staging, com todas as colunas `STRING`;
  2. query job para a partição do ano, com `WRITE_TRUNCATE` e `ALLOW_FIELD_ADDITION`;
  3. remoção da staging.

  Verificar carregando 2026 e depois 2000 (schema menor), conferindo que a carga de 2000 não mexe em 2026.
- [ ] 3.3 Implementar `validar` (contagem da partição = landing = `output_rows`; colunas obrigatórias) e `registrar_controle` (`MERGE`); verificar com uma falha forçada (contagem esperada alterada no teste) que o controle não é gravado
- [ ] 3.4 Commit em `dev` (`feat(ingest): landing e tabela bronze do SINAN`); verificar `git log -1 --stat`

## 4. Modelagem sobre a bronze

- [ ] 4.1 Declarar a source `sinan_opendatasus` em `models/sources.yaml` (descrição, `loaded_at_field: carregado_em`, freshness com aviso em 10 dias e erro em 30); verificar `dbt source freshness --select source:sinan_opendatasus`
- [ ] 4.2 Reescrever `bronze_dengue_brasil` com `var('sinan_source', 'basedosdados')` durante a comparação:
  - ramo OpenDataSUS:
    - UF pelo código do IBGE → sigla;
    - município de 6 → 7 dígitos pela dimensão;
    - datas pela `parse_date_any`;
    - idade decodificada;
    - mesmas colunas e o mesmo `case_id`;
  - ramo antigo sem mudança.

  Conferir coluna a coluna contra a Base dos Dados num ano completo (2023), por amostragem e por distribuição de valores.
- [ ] 4.3 Teste dbt de equivalência (singular, `severity: warn`): por ano completo e UF, total de notificações OpenDataSUS × Base dos Dados com diferença de até 1%; verificar rodando com as duas fontes carregadas
- [ ] 4.4 Commit em `dev` (`feat(dbt): bronze do Brasil a partir do OpenDataSUS`); verificar `git log -1 --stat`

## 5. DAG e corte

- [ ] 5.1 Escrever `airflow/dags/process_sinan_ingest_atlas.py`:
  - `@daily`, `catchup=False`, `max_active_runs=1`, `retries=2`;
  - sensor em reschedule (30 min, timeout de 20 h, `soft_fail`);
  - `landing`, `carregar_bronze` e `validar` mapeados por ano;
  - `registrar_controle`;
  - `TriggerDagRunOperator` da `process_etl_atlas`.

  Testes de DagBag para ordem, mapeamento, modo do sensor, `soft_fail` e trigger.
- [ ] 5.2 Carga inicial em dev pela DAG (controle vazio = todos os anos), com a modelagem ainda em `basedosdados`; registrar tempo total, linhas por ano e bytes no landing
- [ ] 5.3 Segunda execução sem mudança na origem: o sensor termina pulado e nada roda a jusante; verificar nos estados das tarefas
- [ ] 5.4 Comparar as fontes (teste 4.3 e consultas por ano/UF/classificação) e registrar em `docs/referencias/sinan-opendatasus.md`; com diferença ≤ 1%, mudar o padrão de `sinan_source` para `opendatasus` e rodar a `process_etl_atlas` completa, com todos os testes verdes e a gold de casos prováveis chegando à semana mais recente
- [ ] 5.5 Commits em `dev` (`feat(airflow): DAG process_sinan_ingest_atlas`; `docs: SINAN pelo OpenDataSUS e comparação de fontes`); verificar `git log --oneline -2`

## 6. Documentação

- [ ] 6.1 Atualizar:
  - `airflow/README.md`: DAG, sensor, landing, tabela bronze, controle e como forçar recarga de um ano apagando a linha do controle;
  - `airflow/dags/utfpr_dengue/README.md`: nova source e variável `sinan_source`;
  - `airflow/dags/utfpr_dengue/docs/architecture.md`: Brasil vindo do OpenDataSUS.

  Verificar links com lychee.
- [ ] 6.2 Commit em `dev` (`docs: ingestão do SINAN`); verificar `git push`

## Workflow follow-up

- Promover para `hml` por PR com o CI verde; na VPS, conferir a Connection `google_cloud_default` e despausar a DAG.
- Política de ciclo de vida do `landing/` no bucket, para reter só as últimas N versões por ano.
