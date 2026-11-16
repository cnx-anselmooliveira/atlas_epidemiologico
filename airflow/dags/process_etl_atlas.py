"""ETL do Atlas: modelagem dbt (seeds, bronze, silver e gold no BigQuery) pelo Cosmos.

Sem agendamento e sem parâmetros: disparar roda o projeto inteiro.

    [seed] ──► [bronze] ──► [silver] ──► [gold]

- Um grupo por camada, encadeados. Dentro de cada grupo, o Cosmos cria uma tarefa por
  seed/model, com os testes do model logo depois (TestBehavior.AFTER_EACH, o padrão),
  na ordem do grafo do dbt. Model novo numa pasta aparece sozinho no grupo certo.
- Falha num model ou teste: a tarefa dele fica vermelha, as dependentes ficam
  `upstream_failed` e a execução termina com falha. Sem retentativas.
- Para refazer só parte da modelagem: limpe (clear) a tarefa ou o grupo na UI.
- Projeto: `utfpr_dengue/`, ao lado deste arquivo; profile do próprio projeto
  (DBT_BQ_KEYFILE etc.); dbt do venv da imagem. Cada tarefa roda numa cópia temporária
  do projeto, então nada é escrito na pasta de DAGs (pode ser somente leitura).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from airflow.sdk import DAG, chain
from cosmos import DbtTaskGroup, ExecutionConfig, ProfileConfig, ProjectConfig, RenderConfig
from cosmos.constants import InvocationMode

DBT_DIR = Path(__file__).resolve().parent / "utfpr_dengue"
DBT_EXECUTABLE = "/opt/dbt/bin/dbt"

# Seletores de cada camada (juntos cobrem todos os seeds e models do projeto)
LAYERS = {
    "seed": ["resource_type:seed"],
    "bronze": ["path:models/bronze"],
    "silver": ["path:models/silver"],
    # metricflow_time_spine fica na raiz de models/, mas é materializado no schema gold
    "gold": ["path:models/gold", "path:models/metricflow_time_spine.sql"],
}

project_config = ProjectConfig(dbt_project_path=DBT_DIR, install_dbt_deps=True)
profile_config = ProfileConfig(
    profile_name="utfpr_dengue",
    target_name="dev",
    profiles_yml_filepath=DBT_DIR / "profiles.yml",
)
# dbt só existe no venv /opt/dbt (não no Python do Airflow): chamar o executável, nunca o
# dbtRunner em processo (padrão do Cosmos 1.16 quando não se informa o modo)
execution_config = ExecutionConfig(
    dbt_executable_path=DBT_EXECUTABLE, invocation_mode=InvocationMode.SUBPROCESS
)

with DAG(
    dag_id="process_etl_atlas",
    description="ETL do Atlas no dbt (utfpr_dengue) pelo Cosmos: seed, bronze, silver e gold.",
    schedule=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["atlas", "dbt", "etl", "cosmos"],
    # Teste falhando não deve repetir sozinho: quem decide é a pessoa
    default_args={"owner": "atlas", "retries": 0},
) as dag:
    groups = [
        DbtTaskGroup(
            group_id=layer,
            project_config=project_config,
            profile_config=profile_config,
            execution_config=execution_config,
            render_config=RenderConfig(
                select=selectors,
                dbt_executable_path=DBT_EXECUTABLE,
                invocation_mode=InvocationMode.SUBPROCESS,
            ),
        )
        for layer, selectors in LAYERS.items()
    ]
    chain(*groups)
