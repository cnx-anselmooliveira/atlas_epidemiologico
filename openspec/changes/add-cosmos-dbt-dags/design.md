# Design

## Context

O que já existe e foi conferido:
- **Projeto dbt:** `airflow/dags/utfpr_dengue/`, com o profile por variáveis (`DBT_BQ_KEYFILE` etc.). O dbt fica num venv próprio da imagem, `/opt/dbt/bin/dbt` (dbt-core 1.12.7, dbt-bigquery 1.12.3). O `.airflowignore` já tira o projeto do processador de DAGs.
- **`process_etl_atlas` atual:** `dbt_debug → dbt_deps → dbt_seed → dbt_bronze → dbt_silver → dbt_gold → dbt_report`, mais a sentinela `dbt_status`, com artefatos no volume `dbt-artifacts`. A execução completa em dev levou 128 s de dbt e processou 9,19 GiB.
- **Imagem do Airflow (3.3.2):** já traz o `apache-airflow-providers-google` e o `google-cloud-storage`. O Cosmos ainda não está instalado.
- **Cosmos 1.16.0, conferido no código do pacote:**
  - `cosmos.operators.DbtDocsGCSOperator` (`DbtDocsGCSLocalOperator`) roda `dbt docs generate` e envia os arquivos de `target/` com o `GCSHook(connection_id)`, ajustando o tipo de conteúdo de cada arquivo;
  - o plugin do Airflow 3 lê `[cosmos] dbt_docs_projects`, um JSON `{slug: {dir, conn_id, index, name}}`, que é exatamente o formato do exemplo do usuário.
- **Bucket:** `ppgcc-bucket`.
  - A service account `mlflow-sa` tem `storage.objectAdmin` nele.
  - A `training-sa` lê e escreve no BigQuery; a escrita dela no bucket ainda não foi conferida (tarefa 1.2).

## Goals / Non-Goals

**Goals:**
- O Cosmos da forma mais simples:
  - execução local, com o dbt da imagem;
  - o profile do próprio projeto;
  - grafo por `dbt ls`;
  - padrões do Cosmos sempre que possível.
- Uma DAG de docs com uma única tarefa, que publica no bucket por ambiente; o Airflow exibe essa documentação.
- Nenhuma chave nova em imagem ou repositório.

**Non-Goals:**
- Os modos de execução virtualenv, Kubernetes ou Docker do Cosmos.
- Usar o `manifest.json` publicado para montar o grafo da ETL (`LoadMode.DBT_MANIFEST`). Fica como otimização futura, porque acoplaria a ETL à DAG de docs.
- Rodar a geração de docs automaticamente depois da ETL. Os dois disparos continuam manuais.
- Seleção de models por parâmetro no disparo.

## Decisions

### 1. Cosmos no ambiente do Airflow, dbt no venv separado
O Cosmos é provider/plugin, então precisa do Python do Airflow:
```dockerfile
USER airflow
RUN pip install --no-cache-dir "apache-airflow==${AIRFLOW_VERSION}" "astronomer-cosmos==1.16.0"
```
O `apache-airflow==` fixo impede que o pip mexa no Airflow. O dbt continua em `/opt/dbt`, como o Cosmos recomenda para evitar conflitos (`ExecutionConfig(dbt_executable_path="/opt/dbt/bin/dbt")`).

### 2. `process_etl_atlas` com um `DbtTaskGroup` por camada
```python
DBT_DIR = Path(__file__).resolve().parent / "utfpr_dengue"
project = ProjectConfig(DBT_DIR, install_dbt_deps=True)
profile = ProfileConfig(profile_name="utfpr_dengue", target_name="dev",
                        profiles_yml_filepath=DBT_DIR / "profiles.yml")
execution = ExecutionConfig(dbt_executable_path="/opt/dbt/bin/dbt")
LAYERS = {"seed": ["resource_type:seed"], "bronze": ["path:models/bronze"],
          "silver": ["path:models/silver"],
          "gold": ["path:models/gold", "path:models/metricflow_time_spine.sql"]}

with DAG("process_etl_atlas", schedule=None, max_active_runs=1, catchup=False,
         default_args={"retries": 0}, tags=["atlas", "dbt", "etl"]):
    groups = [DbtTaskGroup(group_id=name, project_config=project, profile_config=profile,
                           execution_config=execution,
                           render_config=RenderConfig(select=sel))
              for name, sel in LAYERS.items()]
    chain(*groups)
```
- **Seletores:** os mesmos da versão anterior. Juntos, cobrem os 28 models e os 5 seeds. Um teste de cobertura na DagBag garante isso.
- **Grafo:** `LoadMode` automático. Sem manifest, o Cosmos usa `dbt ls` e guarda o resultado em cache (Variable do Airflow), invalidado quando o projeto muda.
- **Testes:** `TestBehavior.AFTER_EACH`, o padrão: a tarefa de cada model roda `dbt run` e depois os testes dele.
- **Dependências entre camadas:** encadear os grupos garante a ordem pedida (seed, bronze, silver, gold). Dentro de cada grupo, o Cosmos segue o grafo do dbt.
- **Deps:** `install_dbt_deps=True` roda `dbt deps` na cópia temporária, no lugar da tarefa `dbt_deps`. Hoje o projeto não tem pacotes, então é só um aviso.
- **Saem:**
  - `dbt_debug`: uma credencial errada aparece já na primeira tarefa de seed;
  - `dbt_report` e `dbt_status`: com uma tarefa por model, a falha fica visível na própria tarefa, e as folhas seguintes ficam `upstream_failed`, o que deixa a execução vermelha;
  - os parâmetros e o volume `dbt-artifacts`.
- **Artefatos:** cada tarefa do Cosmos copia o projeto para um diretório temporário. Nada é escrito na pasta de DAGs, o que cumpre o requisito de pasta somente leitura.

### 3. DAG `process_dbt_docs_atlas`
```python
DbtDocsGCSOperator(
    task_id="dbt_docs_gcs",
    project_dir=DBT_DIR, profile_config=profile, dbt_executable_path="/opt/dbt/bin/dbt",
    connection_id="google_cloud_default",
    bucket_name=os.environ.get("ATLAS_DBT_DOCS_BUCKET", "ppgcc-bucket"),
    folder_dir=f"dbt_docs/{os.environ.get('ATLAS_ENV', 'dev')}",
    install_deps=True,
)
```
- **Agendamento e retentativas:** `schedule=None`, `max_active_runs=1` e `retries=0`.
- **Pasta no bucket:** vem do `ATLAS_ENV` do container (dev, hml, prod).
- **Arquivos enviados:** `index.html`, `manifest.json` e `catalog.json`. O operador envia o que o `dbt docs generate` produz em `target/`, já com o tipo de conteúdo certo.

### 4. Exibição no Airflow
No compose de dev:
```yaml
AIRFLOW__COSMOS__DBT_DOCS_PROJECTS: '{"atlas":{"dir":"gs://ppgcc-bucket/dbt_docs/dev","conn_id":"google_cloud_default","index":"index.html","name":"dbt Docs (Atlas)"}}'
```
O plugin roda no `api-server` e lê o bucket com a mesma Connection. Nas stacks da VPS, o valor muda só no sufixo (`hml`/`prod`).

### 5. Connection `google_cloud_default`
- **Dev:** vem por variável de ambiente, só com o caminho da chave montada, sem o conteúdo:
  ```yaml
  AIRFLOW_CONN_GOOGLE_CLOUD_DEFAULT: '{"conn_type": "google_cloud_platform", "extra": {"key_path": "/secrets/<sa>.json"}}'
  ```
  A chave é a `training-sa`, se ela puder escrever no `ppgcc-bucket` (conferido na tarefa 1.2); senão, a `mlflow-sa`, que já tem `objectAdmin` só nesse bucket.
- **VPS:** cadastro pela UI, junto com a Connection de credenciais planejada na seção 5 da `add-dbt-refresh-dag`, que o usuário vai criar depois.
- **Chaves:** nenhuma chave entra em imagem, código ou log.

### 6. Leitura das DAGs com `dbt ls`
- **Tempo de leitura:** o primeiro `dbt ls` leva alguns segundos por grupo (4 grupos). O `AIRFLOW__CORE__DAGBAG_IMPORT_TIMEOUT` sobe para 120 s no compose e nas stacks. Depois, o cache do Cosmos evita repetir o `dbt ls`.
- **Credencial:** o `dbt ls` não conecta ao BigQuery, mas o profile exige `DBT_BQ_KEYFILE` definida, o que já acontece em todos os containers.
- **CI:** no job `dags`, o teste roda a DagBag dentro da imagem com `DBT_BQ_KEYFILE` apontando para um arquivo fictício.

### 7. Testes da DagBag
- **ETL:**
  - grupos `seed`, `bronze`, `silver` e `gold` em cadeia;
  - cobertura: cada model de `models/` aparece em exatamente um grupo (lista tirada do próprio projeto);
  - existência da tarefa de `gold_dengue_casos_provaveis_uf_semanal`;
  - `retries=0` e nenhum parâmetro obrigatório.
- **Docs:** uma única tarefa `DbtDocsGCSOperator`, com bucket e pasta `dbt_docs/<ATLAS_ENV>`.
- **Saem:** os testes antigos de `dbt_report` e `dbt_status`.

## Risks / Trade-offs

- **[Mais tarefas: cerca de 33 por execução, contra 7]** → é o que dá a visibilidade por model. Cada tarefa paga a partida do dbt, alguns segundos. O tempo total deve subir em relação aos 128 s atuais e será medido na tarefa 3.3. Com `parallelism=4`, models independentes rodam em paralelo.
- **[Leitura da DAG depende do `dbt ls`]** → cache do Cosmos e timeout de 120 s. Se o `dbt ls` falhar (projeto inválido), a DAG aparece com erro de importação, e o job `dbt parse` do CI pega o problema antes.
- **[Perda dos parâmetros `select`/`exclude`/`full_refresh`]** → o clear de tarefas e grupos cobre o uso parcial. O `full_refresh` não é usado hoje: não há models incrementais.
- **[Perda do relatório agregado (GiB processados)]** → o custo continua visível no log de cada tarefa e no console do BigQuery. O README do dbt mantém a medição feita.
- **[Service account com escrita no bucket]** → escolhida na tarefa 1.2, com a menor permissão que funcione.
- **[Cosmos instalado com o pip do Airflow]** → `pip check` e `airflow version` na imagem antes de seguir.

## Migration Plan

1. Imagem com o Cosmos e compose (Connection, plugin, timeout), em dev.
2. Nova `process_etl_atlas` com Cosmos; execução completa em dev, comparando com a anterior (todas as tabelas verdes, tempo total).
3. `process_dbt_docs_atlas` em dev; conferir o menu de docs no Airflow.
4. **Rollback:** reverter o commit da `process_etl_atlas`. A versão por camadas em Bash volta sem mudança no dbt.

## Open Questions

- Nenhuma que bloqueie. A service account do bucket é decidida na tarefa 1.2.
