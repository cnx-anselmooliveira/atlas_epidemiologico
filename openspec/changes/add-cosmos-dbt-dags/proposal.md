# Proposal

## Why

Hoje a `process_etl_atlas` roda o dbt em tarefas Bash grandes, uma por camada. Quando algo falha, é preciso abrir o log para saber qual model ou teste quebrou, e não existe documentação navegável dos models. O Cosmos resolve as duas coisas com pouco código:
- uma tarefa por model, com o teste logo depois;
- um plugin que mostra o `dbt docs` dentro do próprio Airflow.

## What Changes

- **`process_etl_atlas` passa a usar o Cosmos**, da forma mais simples:
  - um `DbtTaskGroup` por camada, encadeados `seed → bronze → silver → gold`, com uma tarefa por model e o teste logo depois (`TestBehavior.AFTER_EACH`, o padrão);
  - execução local com o dbt da imagem (`/opt/dbt/bin/dbt`) e o `profiles.yml` do projeto;
  - `install_deps=True` no lugar da etapa de deps;
  - grafo montado por `dbt ls`, com o cache do Cosmos.
- **Remoção dos extras da versão anterior (BREAKING para quem dispara a DAG com parâmetros):**
  - `dbt_debug`;
  - `dbt_report` e `dbt_status`: com uma tarefa por model, a falha aparece na própria tarefa, e as camadas seguintes ficam `upstream_failed`;
  - os parâmetros `select`, `exclude` e `full_refresh`: o Cosmos monta o grafo na leitura da DAG, não no disparo. Para refazer parte da modelagem, limpe (clear) as tarefas ou o grupo na UI;
  - o volume `dbt-artifacts`: o Cosmos executa cada tarefa numa cópia temporária do projeto.
- **Nova DAG `process_dbt_docs_atlas`, sem agendamento:** uma tarefa `DbtDocsGCSOperator` roda `dbt docs generate` e envia `index.html`, `manifest.json` e `catalog.json` para `gs://ppgcc-bucket/dbt_docs/<ambiente>/`.
- **Docs no Airflow:** o plugin do Cosmos lê o bucket pela configuração `AIRFLOW__COSMOS__DBT_DOCS_PROJECTS`, no formato `{"atlas": {"dir": "gs://ppgcc-bucket/dbt_docs/<ambiente>", "conn_id": "google_cloud_default", "index": "index.html", "name": "dbt Docs (Atlas)"}}`.
- **Imagem do Airflow:** ganha `astronomer-cosmos==1.16.0` no ambiente do Airflow. O provider Google já vem na imagem base.
- **Compose de dev:**
  - a Connection `google_cloud_default` aponta para a chave já montada em `/secrets`;
  - o JSON do `DBT_DOCS_PROJECTS` aponta para `dbt_docs/dev`;
  - o volume `dbt-artifacts` sai.

## Capabilities

### New Capabilities
- `dbt-docs-publishing`: geração do `dbt docs` sob demanda, publicação no bucket por ambiente e exibição no Airflow.

### Modified Capabilities
<!-- Nenhuma spec principal existe ainda (openspec/specs vazio). A capability dbt-orchestration
     está em delta na mudança add-dbt-refresh-dag, ainda não arquivada; esta mudança traz os
     requisitos de execução pelo Cosmos em delta próprio e alinha aquela (tarefa 5.1). -->
- Nenhuma em `openspec/specs/`. Os requisitos novos da `dbt-orchestration` (execução pelo Cosmos) entram como delta desta mudança, e os requisitos substituídos ficam alinhados na `add-dbt-refresh-dag`.

## Impact

- **Código:**
  - `airflow/dags/process_etl_atlas.py`: reescrita;
  - `airflow/dags/process_dbt_docs_atlas.py`: nova;
  - `airflow/tests/test_dags.py`: testes trocados.
- **Imagem:** `airflow/Dockerfile` ganha o Cosmos no ambiente do Airflow; sai o diretório `dbt-artifacts`.
- **Compose:** `platform/compose.dev.yml` ganha a Connection GCP, o JSON do plugin e o timeout de importação de DAG; perde o volume `dbt-artifacts`.
- **GCP:** escrita no `ppgcc-bucket` pela service account da Connection.
  - O `dbt docs generate` consulta o `INFORMATION_SCHEMA` do BigQuery para o catálogo, com custo pequeno.
- **Stacks da VPS:** precisam da Connection `google_cloud_default` cadastrada pela UI e do JSON do plugin com o caminho do ambiente (hml/prod). Isso é registrado na seção de credenciais da `add-dbt-refresh-dag`.
- **Leitura das DAGs:** o processador de DAGs passa a rodar `dbt ls` na primeira leitura da DAG; depois o resultado fica em cache.
