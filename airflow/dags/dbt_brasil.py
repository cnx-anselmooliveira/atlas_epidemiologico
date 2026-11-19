"""Modelagem dbt do Atlas pelo Cosmos (seed → bronze → silver → gold), só com dados novos.

Sem agendamento: disparada pela etl_brasil depois da ingestão do SINAN, ou à mão.

    decidir_dbt ──► [seed] ──► [bronze] ──► [silver] ──► [gold] ──► gerar_docs
                  (uma tarefa por model, testes logo depois)      (dispara a process_dbt_docs_atlas)

decidir_dbt roda o dbt se a bronze do SINAN foi modificada depois da gold (decisão pelo estado das
tabelas: uma ingestão que não chegou ao dbt ontem é modelada hoje), ou com `forcar_dbt=true` (por
exemplo, mudança só na modelagem). Projeto `utfpr_dengue/` ao lado deste arquivo, profile do próprio
projeto, dbt do venv /opt/dbt. Para refazer só parte da modelagem: clear da tarefa ou do grupo.
Os datasets seguem o ambiente (ATLAS_ENV): bronze/silver/gold em dev, *_hml em hml, *_prod em prod.
Quando o dbt roda, a documentação (process_dbt_docs_atlas) é disparada no fim, sem esperar; quando
decidir_dbt pula, a documentação também é pulada.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from airflow.providers.standard.operators.trigger_dagrun import TriggerDagRunOperator
from airflow.sdk import DAG, Param, chain, get_current_context, task
from cosmos import DbtTaskGroup, ExecutionConfig, ProfileConfig, ProjectConfig, RenderConfig
from cosmos.constants import InvocationMode, TestIndirectSelection

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
# dbtRunner em processo. Teste que referencia vários models só roda quando os outros já foram
# construídos (BUILDABLE); com a seleção padrão ele comparava dado novo com tabela ainda velha.
execution_config = ExecutionConfig(
    dbt_executable_path=DBT_EXECUTABLE,
    invocation_mode=InvocationMode.SUBPROCESS,
    test_indirect_selection=TestIndirectSelection.BUILDABLE,
)


@task.short_circuit(ignore_downstream_trigger_rules=True)
def decidir_dbt() -> bool:
    """Roda o dbt se a bronze do SINAN é mais nova que a gold, ou se o disparo pediu forcar_dbt."""
    from atlas_ingest import ambiente, gcp
    from atlas_ingest.etl_brasil import dbt_precisa_rodar

    forcar = bool(get_current_context()["params"].get("forcar_dbt"))
    print(ambiente.descrever())
    cliente = gcp.bigquery()
    decisao = dbt_precisa_rodar(
        gcp.modificada_em(cliente, ambiente.bronze_sinan()),
        gcp.modificada_em(cliente, ambiente.gold_casos()),
        forcar,
    )
    print(("roda o dbt: " if decisao.rodar else "pula o dbt: ") + decisao.motivo)
    return decisao.rodar


with DAG(
    dag_id="dbt_brasil",
    description="Modelagem dbt (Cosmos) do Atlas, só quando a bronze do SINAN mudou.",
    schedule=None,
    start_date=datetime(2026, 11, 1),
    catchup=False,
    max_active_runs=1,
    # Cada tarefa do Cosmos é um processo dbt dentro do scheduler (LocalExecutor), e
    # 4 de uma vez (o padrão da imagem) já derrubavam o scheduler na VPS de hml (3 CPUs, 3,5 GB):
    # o scheduler parava de dar heartbeat, o Swarm o reiniciava e as tarefas morriam junto.
    max_active_tasks=2,
    tags=["atlas", "dbt", "etl", "cosmos", "brasil"],
    params={
        "forcar_dbt": Param(
            False, type="boolean", description="Opcional. Roda o dbt mesmo sem dados novos na bronze."
        ),
    },
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
    decidir_dbt() >> groups[0]
    chain(*groups)
    # documentação do dbt do ambiente (dbt_docs/<ambiente>/), só depois de uma modelagem completa
    groups[-1] >> TriggerDagRunOperator(
        task_id="gerar_docs",
        trigger_dag_id="process_dbt_docs_atlas",
        wait_for_completion=False,
    )
