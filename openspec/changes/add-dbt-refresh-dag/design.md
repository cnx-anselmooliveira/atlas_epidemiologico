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

### 3. DAG `atlas_dbt_refresh`
```python
DBT_DIR = Path(__file__).parent / "utfpr_dengue"   # funciona no dags-folder e no bundle Git
ARTIFACTS = "/opt/airflow/dbt-artifacts/{{ run_id | replace(':', '_') }}"
params = {"select": Param("", type="string"), "exclude": Param("", type="string"),
          "full_refresh": Param(False, type="boolean")}
with DAG("atlas_dbt_refresh", schedule=None, max_active_runs=1, catchup=False,
         default_args={"retries": 0}, params=params, tags=["atlas", "dbt"]):
    debug  = BashOperator(task_id="dbt_debug",  bash_command=f"dbt debug  {COMMON}")
    build  = BashOperator(task_id="dbt_build",  bash_command=f"dbt build  {COMMON} {SELECTION}")
    report = PythonOperator(task_id="dbt_report", python_callable=summarize_run_results,
                            trigger_rule="all_done")
    debug >> build >> report
```
- **`COMMON`:** `--project-dir {DBT_DIR} --profiles-dir {DBT_DIR} --target-path {ARTIFACTS}/target --log-path {ARTIFACTS}/logs`.
- **`SELECTION`:** montada por template Jinja, só com os parâmetros não vazios (`--select`, `--exclude`, `--full-refresh`). Os valores entram com aspas na linha de comando, sem concatenação insegura.
- **Variáveis:** `DBT_PROFILES_DIR` não é usada; `--profiles-dir` deixa explícito.
- **Partial parse:** `DBT_PARTIAL_PARSE=false`, porque cada execução usa um target novo.
- **Retentativas:** `retries=0`. Um build com teste falhando não deve repetir, e quem decide é a pessoa.
- **`summarize_run_results`:** lê `{ARTIFACTS}/target/run_results.json` e devolve, no log e no XCom, `{"success": n, "error": n, "fail": n, "skipped": n, "warn": n, "failed_nodes": [...], "slowest": [(nó, s)×5]}`. Se o arquivo não existir (o debug falhou), registra isso e termina sem erro adicional.
- **Artefatos:** `/opt/airflow/dbt-artifacts/` fica num volume no compose de dev, com retenção manual. Na VPS segue a mesma ideia; a limpeza fica para depois.

### 4. Higiene da pasta de DAGs
- **`airflow/dags/.airflowignore`:** contém `utfpr_dengue/`, para o processador de DAGs não varrer o projeto dbt.
- **`airflow/Dockerfile.dockerignore`:** acrescenta `airflow/dags/utfpr_dengue/target`, `logs`, `dbt_packages` e `**/__pycache__`. As DAGs continuam entrando na imagem como alternativa ao bundle.
- **`airflow/tests/test_dags.py`:** novos testes para a DAG:
  - sem agendamento;
  - `max_active_runs=1`;
  - ordem `dbt_debug → dbt_build → dbt_report`;
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
