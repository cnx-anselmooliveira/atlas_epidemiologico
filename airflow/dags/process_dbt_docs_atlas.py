"""dbt docs do Atlas: gera a documentação do projeto dbt e publica no bucket.

Sem agendamento: dispare depois de mudanças na modelagem (ex.: após a dbt_brasil).

- Uma tarefa: `dbt docs generate` (consulta o BigQuery para o catálogo) e envio de
  index.html, manifest.json e catalog.json para gs://<bucket>/dbt_docs/<ATLAS_ENV>/,
  com o tipo de conteúdo certo de cada arquivo.
- O plugin do Cosmos mostra essa pasta no menu de dbt docs do Airflow
  (AIRFLOW__COSMOS__DBT_DOCS_PROJECTS, mesmo bucket e pasta).
- Bucket pela Connection `google_cloud_default` (em dev, aponta para a chave montada;
  em hml/prod, cadastrada pela UI). Nenhuma chave no código.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from airflow.sdk import DAG
from cosmos import ProfileConfig
from cosmos.operators import DbtDocsGCSOperator

DBT_DIR = Path(__file__).resolve().parent / "utfpr_dengue"
BUCKET = os.environ.get("ATLAS_DBT_DOCS_BUCKET", "ppgcc-bucket")
FOLDER = f"dbt_docs/{os.environ.get('ATLAS_ENV', 'dev')}"

profile_config = ProfileConfig(
    profile_name="utfpr_dengue",
    target_name="dev",
    profiles_yml_filepath=DBT_DIR / "profiles.yml",
)

with DAG(
    dag_id="process_dbt_docs_atlas",
    description="Gera o dbt docs do projeto utfpr_dengue e publica no bucket para o Airflow exibir.",
    schedule=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["atlas", "dbt", "docs", "cosmos"],
    default_args={"owner": "atlas", "retries": 0},
) as dag:
    DbtDocsGCSOperator(
        task_id="dbt_docs_gcs",
        project_dir=str(DBT_DIR),
        profile_config=profile_config,
        dbt_executable_path="/opt/dbt/bin/dbt",
        install_deps=True,
        connection_id="google_cloud_default",
        bucket_name=BUCKET,
        folder_dir=FOLDER,
    )
