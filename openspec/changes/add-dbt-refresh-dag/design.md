# Design

## Context

- **Projeto dbt:** movido para `airflow/dags/utfpr_dengue/` (67 arquivos, nenhum `.py`).
  - Os diretórios gerados (`target/`, `logs/`, `dbt_packages/`) estão na pasta, ignorados pelo `.gitignore` do projeto.
  - Não há `.airflowignore`.
  - O `airflow/Dockerfile.dockerignore` envia `airflow/dags/**` inteiro para a imagem.
- **Profile:** só existe o pessoal, em `~/.dbt/profiles.yml`: `utfpr_dengue`, `method: service-account`, keyfile local, `location: US`, `dataset: ppgcc-dengue-dataset`, schemas via a macro `generate_schema_name`.
- **Imagem do Airflow:** `apache/airflow:3.3.2-python3.12`, com o `atlas_ml` num venv separado (`/opt/atlas-ml`) chamado por `BashOperator`. O dbt não está instalado.
- **Compose de dev:** monta `airflow/dags` e `platform/secrets` (`/secrets`) e define `GOOGLE_APPLICATION_CREDENTIALS=/secrets/training-sa.json`.
- **hml e prod:** `GitDagBundle` lendo `airflow/dags` das branches `hml` e `main`. O caminho do bundle é diferente de `/opt/airflow/dags`, e a cópia é tratada como somente leitura.
- **Escolha do usuário:** comandos dbt em poucas tarefas, e não uma tarefa por model.

## Goals / Non-Goals

**Goals:**
- Um disparo na UI do Airflow reconstrói a modelagem inteira ou uma seleção, com o mesmo resultado de rodar `dbt build` no notebook.
- Nenhuma escrita na pasta de DAGs, para funcionar com o bundle Git.

**Non-Goals:**
- Agendamento e encadeamento com ingestão e modelos: o `schedule` fica para quando a ingestão existir.
- Execução incremental por mudança: o `state:modified` exigiria artefatos de produção persistidos.

## Atualização: execução pelo Cosmos

A `process_etl_atlas` descrita nas decisões 3 e 5 (tarefas Bash por camada, relatório, sentinela, parâmetros e volume `dbt-artifacts`) foi substituída pela mudança `add-cosmos-dbt-dags`:
- um `DbtTaskGroup` do Cosmos por camada, com uma tarefa por model;
- sem parâmetros, relatório nem sentinela.

Continuam valendo:
- o projeto dentro das DAGs e o `.airflowignore`;
- o venv do dbt na imagem;
- o profile por variáveis;
- a credencial por Connection (seção 5 das tarefas).

## Decisions

### 1. dbt num venv próprio da imagem
`airflow/dags/utfpr_dengue/pyproject.toml` (`dbt-core` e `dbt-bigquery`, versões travadas no `uv.lock` do projeto). No `airflow/Dockerfile`:
```dockerfile
COPY airflow/dags/utfpr_dengue/pyproject.toml airflow/dags/utfpr_dengue/uv.lock /opt/dbt-src/
RUN cd /opt/dbt-src && UV_PROJECT_ENVIRONMENT=/opt/dbt uv sync --frozen --no-install-project --python /usr/python/bin/python3.12 \
 && ln -s /opt/dbt/bin/dbt /usr/local/bin/dbt
```
Mesmo padrão do `atlas_ml`: as restrições de versão do Airflow não colidem com as do dbt. O mesmo `pyproject` serve para rodar o dbt fora do container: `uv run --project airflow/dags/utfpr_dengue dbt …`.

Alternativa rejeitada: instalar `dbt-bigquery` no ambiente do Airflow, por causa dos conflitos de `protobuf` e `google-*` com os providers do Airflow.

### 2. Profile versionado no projeto
`airflow/dags/utfpr_dengue/profiles.yml`:
```yaml
utfpr_dengue:
  target: "{{ env_var('DBT_TARGET', 'dev') }}"
  outputs:
    dev:
      type: bigquery
      method: service-account
      project: "{{ env_var('DBT_GCP_PROJECT', 'ppgcc-dengue-project') }}"
      dataset: "{{ env_var('DBT_BQ_DATASET', 'ppgcc-dengue-dataset') }}"
      location: "{{ env_var('DBT_BQ_LOCATION', 'US') }}"
      keyfile: "{{ env_var('DBT_BQ_KEYFILE') }}"
      threads: "{{ env_var('DBT_THREADS', '4') | int }}"
      job_retries: 1
      job_execution_timeout_seconds: 900
```
- **Compose de dev:** recebe `DBT_BQ_KEYFILE=/secrets/training-sa.json`.
- **Stacks da VPS:** recebem a mesma variável apontando para o segredo montado (tarefa registrada na `add-ml-platform` módulo 7).

Este profile substitui o que a `add-gold-casos-provaveis-uf` (tarefa 1.2) ia criar em `utfpr_dengue/`, e o alinhamento faz parte das tarefas.

### 3. DAG `process_etl_atlas`
Uma tarefa por etapa, na ordem pedida (deps, seed, bronze, silver, gold), com a checagem de conexão na frente:
```
dbt_debug ► dbt_deps ► dbt_seed ► dbt_bronze ► dbt_silver ► dbt_gold ► dbt_report
    └──────────┴──────────┴───────────┴────────────┴───────────┴──────► dbt_status
```
- **Camadas:** cada uma é um `dbt build` (models + testes) com `--select` da camada: `resource_type:seed`, `path:models/bronze`, `path:models/silver` e `path:models/gold` + `path:models/metricflow_time_spine.sql` (fica na raiz de `models/`, mas é materializado no schema gold). Juntas cobrem os 28 models.
- **Parâmetros:** `select`, `exclude` e `full_refresh` valem para todas as camadas. Com `select`, cada seletor do usuário é cruzado com o da camada (`path:models/silver,+gold_x`), então cada camada só reconstrói os antecessores que estão nela. Os parâmetros chegam ao bash como variáveis de ambiente (`DBT_SELECT_ARG` etc.) e viram um array de argumentos com `set -f`; nunca são interpolados no texto do comando.
- **Artefatos por etapa:** `DBT_TARGET_PATH=/opt/airflow/dbt-artifacts/<run_id>/<etapa>/target` e `DBT_LOG_PATH=…/<etapa>/logs`, por variável de ambiente, porque o `dbt debug` não aceita `--target-path`. Um target por etapa porque cada comando sobrescreve o `run_results.json`.
- **`deps`:** o `dbt_project.yml` usa `packages-install-path: "{{ env_var('DBT_PACKAGES_INSTALL_PATH', 'dbt_packages') }}"`, e a DAG aponta para `…/<run_id>/dbt_packages`, compartilhado pelas etapas. Hoje o projeto não tem pacotes e o `deps` só avisa; quando houver, o `package-lock.yml` deve ser versionado.
- **Partial parse:** `DBT_PARTIAL_PARSE=false`, porque cada execução usa um target novo.
- **Retentativas:** `retries=0`. Um teste falhando não deve repetir, e quem decide é a pessoa.
- **`dbt_report`:** `trigger_rule=all_done`. Lê os `run_results.json` de todas as etapas e devolve, no log e no XCom: contagens por status (total e por etapa), nós que falharam com a etapa, os 5 mais lentos e os bytes processados (`adapter_response.bytes_processed`). Etapas que não rodaram aparecem como "não executada", sem erro adicional.
- **`dbt_status`:** o Airflow decide o estado da execução pelas tarefas folha. Com o relatório (`all_done`) como folha, uma etapa falha deixaria a execução verde. Por isso `dbt_status` depende de todas as etapas do dbt com `trigger_rule=one_failed` e só levanta erro: fica pulada quando tudo passa e deixa a execução vermelha quando algo falha.
- **Nome:** `process_etl_atlas`, a pedido do usuário, no lugar do `atlas_dbt_refresh` do planejamento.

### 4. Higiene da pasta de DAGs
- **`airflow/dags/.airflowignore`:** contém `utfpr_dengue/`, para o processador de DAGs não varrer o projeto dbt.
- **`airflow/Dockerfile.dockerignore`:** acrescenta `airflow/dags/utfpr_dengue/target`, `logs`, `dbt_packages` e `**/__pycache__`. As DAGs continuam entrando na imagem como alternativa ao bundle.
- **`airflow/tests/test_dags.py`:** novos testes para a DAG:
  - sem agendamento;
  - `max_active_runs=1`;
  - ordem `dbt_debug → dbt_deps → dbt_seed → dbt_bronze → dbt_silver → dbt_gold → dbt_report`, todas ligadas à sentinela `dbt_status`;
  - `trigger_rule` do relatório;
  - comandos com `--project-dir` e `--target-path` fora da pasta de DAGs.
  - E também o `.airflowignore` ignorando o dbt: o `DagBag` só tem DAGs de verdade.

### 5. Verificação local
No compose de dev, disparar a DAG com `select=+gold_dengue_casos_provaveis_uf_semanal`, ou com um model pequeno se essa gold ainda não existir, para conferir:
- o debug passa;
- o build passa;
- o relatório tem números coerentes;
- os artefatos ficam em `dbt-artifacts/<run_id>/`;
- nenhuma escrita acontece em `airflow/dags/utfpr_dengue/`.

Depois, um build completo, medindo tempo e bytes processados, registrados no README do projeto dbt.

## Risks / Trade-offs

- **[Build completo caro (lê os 33 milhões de casos do Brasil)]** → o padrão é o projeto inteiro, mas o `select` permite builds parciais. O custo medido fica documentado.
- **[Permissão da service account para criar e substituir tabelas nos datasets]** → conferida no `dbt debug` e no primeiro build. Se faltar, ajustar o IAM (fora do código).
- **[Pasta de DAGs gravável em dev pode receber `target/` se alguém rodar dbt dentro dela à mão]** → os diretórios estão no `.gitignore` e no dockerignore. A DAG nunca escreve lá.
- **[`dbt debug` exige `git` para alguns checks]** → a imagem do Airflow já tem `git` (o provider de git exige).

## Migration Plan

1. Implementar em `dev`, rodar a DAG no compose local e fazer um commit por assunto.
2. Promover por PR `dev → hml`. O CI cobre a integridade da DAG.
3. Na VPS, a DAG aparece via bundle Git assim que as stacks existirem (`add-ml-platform` módulo 7).
