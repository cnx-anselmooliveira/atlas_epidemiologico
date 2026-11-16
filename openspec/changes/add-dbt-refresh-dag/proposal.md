# Proposal

## Why

O projeto dbt (`utfpr_dengue`) foi movido para `airflow/dags/utfpr_dengue/`. Assim ele viaja junto com as DAGs: em dev, pela pasta montada; em hml e prod, pelo `GitDagBundle`, que lê `airflow/dags/` das branches `hml` e `main`.

Hoje a modelagem é atualizada à mão, rodando `dbt` no notebook com um profile pessoal. Precisamos de uma DAG que atualize bronze, silver e gold sob demanda, com o mesmo código e a mesma credencial em todos os ambientes, e que seja o primeiro passo do encadeamento ingestão → dbt → modelos.

## What Changes

- **DAG `atlas_dbt_refresh` sem agendamento** (`schedule=None`), disparada manualmente, com uma execução por vez e parâmetros no disparo:
  - `select` (padrão: o projeto inteiro);
  - `exclude`;
  - `full_refresh`.
- **Tarefas:**
  1. `dbt_debug`: confere a conexão e o profile;
  2. `dbt_build`: seeds, models e testes na ordem do grafo do dbt;
  3. `dbt_report`: lê o `run_results.json` e resume quantos nós passaram, falharam ou foram pulados, mais os mais lentos.
  - Falha de teste ou de model falha a tarefa.
- **dbt instalado na imagem do Airflow** num ambiente separado (`/opt/dbt`), como já acontece com o `atlas_ml`. As versões ficam fixadas num `pyproject.toml` + `uv.lock` do próprio projeto dbt.
- **`profiles.yml` versionado no projeto dbt**, com projeto GCP, dataset, localização e caminho da chave vindos de variáveis de ambiente. Em dev, a chave é a `platform/secrets/training-sa.json`, já montada nos containers.
- **Artefatos do dbt fora da pasta de DAGs:** `target/` e logs de cada execução vão para um diretório gravável, separado por execução. Em hml e prod a pasta do bundle Git é só leitura.
- **Higiene da pasta de DAGs:**
  - `.airflowignore` para o Airflow não varrer o projeto dbt;
  - `target/`, `logs/` e `dbt_packages/` fora da imagem do Airflow.
- **Alinhamento das mudanças em aberto:** a `add-gold-casos-provaveis-uf` passa a usar o novo caminho do projeto (`airflow/dags/utfpr_dengue/`) e este profile e execução, em vez de criar os seus.

## Capabilities

### New Capabilities
- `dbt-orchestration`: execução da modelagem dbt pelo Airflow: disparo manual com seleção, ordem das etapas, credenciais por ambiente, isolamento dos artefatos por execução, relatório e regras de falha.

### Modified Capabilities
<!-- Nenhuma em openspec/specs/. A spec dbt-project-runtime da add-gold-casos-provaveis-uf (não arquivada) é alinhada nos artefatos daquela mudança: o profile e a execução passam a ser os desta. -->

## Impact

- **Código:**
  - `airflow/dags/atlas_dbt_refresh.py`;
  - `airflow/dags/.airflowignore`;
  - `airflow/dags/utfpr_dengue/{pyproject.toml,uv.lock,profiles.yml}`;
  - `airflow/Dockerfile` (venv `/opt/dbt`, CLI `dbt`);
  - `airflow/Dockerfile.dockerignore`;
  - `platform/compose.dev.yml` (variáveis do dbt e volume de artefatos);
  - `airflow/tests/test_dags.py`.
- **Imagem do Airflow:** mais cerca de 150 MB (dbt-core + dbt-bigquery).
- **BigQuery:** a DAG reconstrói as tabelas do projeto. A service account precisa de escrita nos datasets do dbt e de leitura nas fontes. O custo vem da leitura das silvers grandes (33 milhões de linhas do Brasil) a cada build completo, e o parâmetro `select` permite builds parciais.
- **CI:** o teste de integridade cobre a nova DAG. O `dbt parse` sem credenciais (planejado na `add-gold-casos-provaveis-uf`) passa a apontar para `airflow/dags/utfpr_dengue/`.
- **Fora de escopo:**
  - agendamento;
  - encadeamento automático com ingestão e treino;
  - uma tarefa por model (Cosmos);
  - publicar a documentação do dbt.
