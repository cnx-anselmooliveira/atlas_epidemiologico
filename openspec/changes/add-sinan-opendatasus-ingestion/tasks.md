# Tasks

## 1. Plano do sync (sem rede)

- [x] 1.1 Criar `airflow/dags/atlas_ingest/__init__.py` e `sinan.py`:
  - `url_arquivo`;
  - `listar_origem`, com `HEAD` de 2000 até o ano corrente, 404 como ausente e falha geral como erro;
  - `listar_landing`, com os objetos `.csv.zip` e a metadata `origem_etag`, `origem_last_modified`, `registros` e `bronze_etag`;
  - `planejar_sync`, que devolve `baixar`, `apagar`, `carregar` e `remover_da_bronze`;
  - `contar_registros_csv`.

  Acrescentar `atlas_ingest/` ao `airflow/dags/.airflowignore`. Verificar com `ruff`.
- [x] 1.2 Testes unitários do plano em `airflow/tests/test_sinan_ingest.py`:
  - bucket vazio (tudo a baixar);
  - ETag igual (nada);
  - ETag diferente;
  - só a data diferente;
  - arquivo removido da origem com os demais respondendo (apagar e remover da bronze);
  - origem toda indisponível (erro, nada a apagar);
  - bronze atrás do landing (carregar sem baixar);
  - CSV com campo entre aspas contendo quebra de linha.

  Verificar rodando dentro da imagem.
- [x] 1.3 Commit em `dev` (`feat(ingest): plano de sync do SINAN OpenDataSUS`); verificar `git log -1 --stat`

## 2. Landing como espelho

- [x] 2.1 Implementar `baixar`: download em streaming, contagem de registros, upload do `.csv` e depois do `.csv.zip` com a metadata da origem, pulando o envio se o `origem_etag` já é o mesmo. Verificar baixando 2026 em dev e lendo a metadata do objeto.
- [x] 2.2 Rodar `baixar` de novo para 2026 e conferir que nada é reenviado; baixar 2024, o maior ano, e registrar tempo e tamanho no design
- [x] 2.3 Conferir encoding, separador, número de colunas e formato de data de 2000, 2013 e 2024 no landing; ajustar a carga se algum ano divergir (encoding por ano) e registrar no design (resultado: dois layouts, 2000–2006 SINAN Windows e 2007+ SINAN Net, registrados na seção 8 do design)
- [ ] 2.4 Implementar `apagar` (`.csv.zip` e `.csv`); verificar com um objeto de teste fora da lista da origem (ex.: `DENGBR99.csv.zip`) que o plano o marca para apagar e a tarefa o remove
- [ ] 2.5 Commit em `dev` (`feat(ingest): landing do SINAN como espelho da origem`); verificar `git log -1 --stat`

## 3. Tabela bronze materializada

- [ ] 3.1 Criar `bronze.sinan_dengue_opendatasus` (particionada por `ano_arquivo`, clusterizada por `SG_UF_NOT`) de forma idempotente na própria DAG; verificar com `bq show` o particionamento
- [ ] 3.2 Implementar `carregar_bronze`:
  1. load job do `.csv` do landing para a staging, com todas as colunas `STRING`;
  2. query job para a partição do ano, com `WRITE_TRUNCATE`, `ALLOW_FIELD_ADDITION` e colunas de linhagem;
  3. remoção da staging.

  Verificar carregando 2026 e depois 2000 (schema menor), conferindo que a carga de 2000 não mexe em 2026.
- [ ] 3.3 Implementar `validar` (contagem da partição = `registros` = `output_rows`; colunas obrigatórias com os nomes alternativos do layout antigo, com teste unitário para 2000 e 2026) e `marcar_carregado` (`bronze_etag` na metadata do zip); verificar com uma validação forçada a falhar que o `bronze_etag` não é gravado e que o plano seguinte inclui o ano em `carregar` sem `baixar`
- [ ] 3.4 Implementar `remover_da_bronze` (`DELETE` da partição do ano removido); verificar com o ano fictício do teste 2.4 carregado antes numa partição de teste
- [ ] 3.5 Commit em `dev` (`feat(ingest): tabela bronze do SINAN`); verificar `git log -1 --stat`

## 4. Modelagem sobre a bronze

- [ ] 4.1 Declarar a source `sinan_opendatasus` em `models/sources.yaml` (descrição, `loaded_at_field: carregado_em`, freshness com aviso em 10 dias e erro em 30); verificar `dbt source freshness --select source:sinan_opendatasus`
- [ ] 4.2 Reescrever `bronze_dengue_brasil` com `var('sinan_source', 'basedosdados')` durante a comparação:
  - ramo OpenDataSUS, com os dois layouts:
    - UF: código do IBGE → sigla (2007+), sigla mantida (2000–2006);
    - município: 6 → 7 dígitos pela dimensão (2007+), 7 dígitos mantidos (2000–2006);
    - `COALESCE` de classificação, evolução e critério (`CLASSI_FIN`/`CON_CLASSI` etc.);
    - datas pela `parse_date_any`;
    - idade decodificada (`4xxx` e `Axxx`);
    - mesmas colunas e o mesmo `case_id`;
  - ramo antigo sem mudança.

  Conferir coluna a coluna contra a Base dos Dados em 2003 (layout antigo) e 2023, por amostragem e por distribuição de valores.
- [ ] 4.3 Teste dbt de equivalência (singular, `severity: warn`): por ano completo e UF, total de notificações OpenDataSUS × Base dos Dados com diferença de até 1%; verificar com as duas fontes carregadas
- [ ] 4.4 Commit em `dev` (`feat(dbt): bronze do Brasil a partir do OpenDataSUS`); verificar `git log -1 --stat`

## 5. Sync dentro da `process_etl_atlas` e corte

- [ ] 5.1 Acrescentar à `airflow/dags/process_etl_atlas.py`:
  - o grupo `sinan`, todo em `@task` / `@task.sensor`, sem Bash:
    - `detectar_diferencas` em reschedule (30 min, timeout de 20 h, `soft_fail`), verificando uma vez só em disparo manual;
    - `baixar`, `apagar`, `carregar_bronze`, `validar`, `marcar_carregado` e `remover_da_bronze` mapeados;
  - `decidir_dbt` (`@task.short_circuit`, `trigger_rule="none_failed"`, `ignore_downstream_trigger_rules=True`) antes do grupo `seed` do Cosmos;
  - `schedule="@daily"` e o parâmetro opcional `forcar_dbt=False`;
  - `retries=2` só nas tarefas de rede.

  Testes de DagBag:
  - ordem `sinan` → `decidir_dbt` → `seed`;
  - mapeamentos;
  - modo do sensor e `soft_fail`;
  - trigger rule;
  - parâmetro e agendamento.
- [ ] 5.2 Alinhar a `add-cosmos-dbt-dags`: o requisito "Disparo sem configuração" passa a "diário, com sync do SINAN antes e `forcar_dbt` opcional", e o teste `assert not dag.params` muda para o parâmetro novo; verificar `openspec validate add-cosmos-dbt-dags --strict`
- [ ] 5.3 Primeira execução em dev com o bucket parcialmente carregado: os anos que faltam são baixados e todos vão para a bronze, com o dbt ainda em `basedosdados`; registrar tempo total, registros por ano e bytes no landing
- [ ] 5.4 Execução sem mudança na origem: o sync não faz nada e os grupos do dbt ficam pulados; depois, um disparo manual com `forcar_dbt=true` roda o dbt sem esperar o sensor. Verificar nos estados das tarefas e que o sensor não consultou o BigQuery.
- [ ] 5.5 Comparar as fontes (teste 4.3 e consultas por ano/UF/classificação) e registrar em `docs/referencias/sinan-opendatasus.md`; com diferença ≤ 1%, mudar o padrão de `sinan_source` para `opendatasus` e rodar a `process_etl_atlas` com `forcar_dbt`, com os testes verdes e a gold de casos prováveis chegando à semana mais recente
- [ ] 5.6 Commits em `dev` (`feat(airflow): sync do SINAN dentro da process_etl_atlas`; `docs: SINAN pelo OpenDataSUS e comparação de fontes`); verificar `git log --oneline -2`

## 6. Documentação

- [ ] 6.1 Atualizar:
  - `airflow/README.md`: `process_etl_atlas` diária com o sync antes do dbt, `forcar_dbt`, sync espelho, metadata dos objetos, como forçar a recarga de um ano apagando o `bronze_etag` ou o objeto;
  - `airflow/dags/utfpr_dengue/README.md`: nova source e variável `sinan_source`;
  - `airflow/dags/utfpr_dengue/docs/architecture.md`: Brasil vindo do OpenDataSUS.

  Verificar links com lychee.
- [ ] 6.2 Commit em `dev` (`docs: ingestão do SINAN`); verificar `git push`

## Workflow follow-up

- Promover para `hml` por PR com o CI verde; na VPS, conferir a Connection `google_cloud_default` e despausar a `process_etl_atlas`, que passa a ser diária.
