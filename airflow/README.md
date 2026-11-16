# Airflow do Atlas (`atlas-epidemiologia-airflow`)

Airflow 3.3.2 (Python 3.12) com LocalExecutor. Ele dispara os treinos do pacote `atlas_ml`, e depois também a ingestão e o dbt. O pacote fica num venv separado (`/opt/atlas-ml`) e é chamado pelo CLI `atlas-ml`, o mesmo comando usado na sua máquina e na imagem de treino.

## Regra principal: DAG só muda pelo repositório

- As DAGs vivem em `airflow/dags/`. **Nunca edite uma DAG direto no servidor.**
- **Dev:** a pasta é montada no container, e o Airflow local relê os arquivos em cerca de 30 s, sem rebuild.
- **hml e prod:** as DAGs vão **dentro da imagem**. Uma DAG nova só chega a hml quando o commit é promovido para a branch `hml` e a imagem `:hml` é publicada e implantada. Para prod, o caminho é `main` + tag `vX.Y`.

## Como adicionar uma DAG

1. Crie `airflow/dags/<nome>.py`. Use `from airflow.sdk import DAG` e os operadores de `airflow.providers.standard`.
   - Tarefas de ML chamam o CLI (`BashOperator` com `atlas-ml …`). Não importe `atlas_ml` dentro da DAG: ele vive em outro venv.
   - Prefira `schedule=None` até a DAG estar validada. As DAGs nascem pausadas.
2. Valide a integridade, sem banco e sem subir o Airflow:
   ```sh
   docker build -f airflow/Dockerfile -t atlas-epidemiologia-airflow:local --build-arg ATLAS_GIT_SHA=$(git rev-parse HEAD) .
   docker run --rm -v "$PWD/airflow/dags:/opt/airflow/dags" --entrypoint python \
     atlas-epidemiologia-airflow:local /opt/atlas/tests/test_dags.py
   ```
   No Git Bash do Windows, prefixe o comando com `MSYS_NO_PATHCONV=1`.
3. Se a DAG tiver regras importantes (agendamento, retentativas, comando), acrescente uma função `test_*` em `airflow/tests/test_dags.py`.
4. Teste no Airflow local (`platform/compose.dev.yml`): despause e dispare pela UI em <http://127.0.0.1:8080>.
5. Faça um commit em `dev` ao concluir o módulo. A promoção segue `dev → hml → main`.

## Configuração

| Onde | O quê |
|---|---|
| `Dockerfile` (comum) | `LocalExecutor`, `parallelism=4`, sem DAGs de exemplo, DAGs pausadas ao criar |
| `config/dev.env` | `ATLAS_ENV=dev`, Simple Auth Manager (usuário `admin`), releitura rápida das DAGs |
| `config/vps.env` | FAB Auth Manager (login e senha), sem expor a configuração na API |
| Variáveis da stack (Portainer) | `ATLAS_ENV` (`hml`/`prod`), conexão do banco, chaves do Airflow, `MLFLOW_TRACKING_URI` e credenciais do MLflow |
| `config/init.sh` | Serviço `airflow-init`: `airflow db migrate` + admin (FAB) ou arquivo de senha (Simple). É idempotente |

As tarefas herdam o ambiente do container (`MLFLOW_TRACKING_URI`, `ATLAS_ENV`, `ATLAS_IMAGE_TAG`, `MLFLOW_TRACKING_USERNAME`/`PASSWORD`). Por isso as runs aparecem no MLflow com `atlas.env` e `atlas.image_tag` do ambiente certo.

## DAGs atuais

| DAG | Agendamento | O que faz |
|---|---|---|
| `atlas_ml_example_training` | manual | `atlas-ml train example --register`. Falha se a run não for registrada no MLflow; 2 retentativas |
| `process_etl_atlas` | manual | Atualiza a modelagem dbt (`dags/utfpr_dengue/`) no BigQuery: `dbt_debug → dbt_deps → dbt_seed → dbt_bronze → dbt_silver → dbt_gold → dbt_report`. Parâmetros opcionais `select`, `exclude` e `full_refresh`; sem configuração, roda o projeto inteiro. Uma etapa falhando interrompe as seguintes e deixa a execução vermelha (`dbt_status`). Sem retentativas |

### process_etl_atlas

- **Disparo:** Trigger na UI. Para reconstruir só uma tabela e seus antecessores, use `{"select": "+gold_dengue_casos_provaveis_uf_semanal"}`.
- **Artefatos:** `/opt/airflow/dbt-artifacts/<run_id>/<etapa>/` (`target/`, logs, `run_results.json`), no volume `dbt-artifacts` em dev. O relatório (`dbt_report`) resume contagens, falhas, nós mais lentos e GiB processados no log e no XCom.
- **Credencial:** `DBT_BQ_KEYFILE`; em dev, `/secrets/training-sa.json`.
- **Custo:** o build completo processa cerca de 9 GiB no BigQuery ([detalhes](dags/utfpr_dengue/README.md#custo-e-tempo-do-build-completo)).
- **Pasta de DAGs:** o projeto dbt fica dentro dela e é ignorado pelo processador de DAGs (`dags/.airflowignore`).
