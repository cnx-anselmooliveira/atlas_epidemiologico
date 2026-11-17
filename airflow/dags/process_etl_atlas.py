"""ETL do Atlas: sync do SINAN (OpenDataSUS → landing → bronze) e modelagem dbt pelo Cosmos.

Diária. Sem dados novos na origem, o dbt é pulado; `forcar_dbt=true` num disparo manual roda o
dbt mesmo assim (ex.: mudança só na modelagem).

    [sinan]  detectar_diferencas (sensor)
               ├─► baixar[arquivo] ─┐
               └─► apagar[arquivo] ─┴─► carga_ano[ano]: carregar_bronze ─► validar ─► marcar_carregado ─┐
                                    └─► remover_da_bronze[ano] ─────────────────────────────────────────┤
    decidir_dbt (pula o dbt sem dados novos, a menos que forcar_dbt) ◄──────────────────────────────────┘
       │
    [seed] ──► [bronze] ──► [silver] ──► [gold]   (Cosmos: uma tarefa por model, testes logo depois)

Sync do SINAN (atlas_ingest/sinan.py):
- detectar_diferencas: HEAD dos arquivos anuais DENGBR<aa>.csv.zip no OpenDataSUS × metadata dos
  objetos no landing (gs://<bucket>/landing/sinan/dengue/). No agendamento diário, espera em modo
  reschedule até haver diferença (pulado se não houver em 20 h); em disparo manual, verifica uma vez.
- O landing é espelho exato da origem: arquivo alterado é substituído, arquivo que sumiu é apagado
  (e sai da bronze). A bronze (bronze.sinan_dengue_opendatasus) tem uma partição por ano, substituída
  inteira; só depois da validação o ano é marcado (bronze_etag) e sai do plano dos próximos dias.

dbt (Cosmos): um grupo por camada, encadeados; projeto `utfpr_dengue/` ao lado deste arquivo, profile
do próprio projeto, dbt do venv /opt/dbt. Para refazer só parte da modelagem: clear da tarefa/grupo.
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from airflow.sdk import DAG, Param, PokeReturnValue, TaskGroup, chain, get_current_context, task, task_group
from cosmos import DbtTaskGroup, ExecutionConfig, ProfileConfig, ProjectConfig, RenderConfig
from cosmos.constants import InvocationMode, TestIndirectSelection

DBT_DIR = Path(__file__).resolve().parent / "utfpr_dengue"
DBT_EXECUTABLE = "/opt/dbt/bin/dbt"
GCP_CONN_ID = "google_cloud_default"
PROJETO = os.environ.get("GCP_PROJECT") or "ppgcc-dengue-project"
BUCKET = os.environ.get("ATLAS_LANDING_BUCKET", "ppgcc-bucket")

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
# Teste que referencia vários models (ex.: totais silver × agregada × gold) só roda quando os
# outros models já foram construídos. Com a seleção padrão (eager), ele rodava junto do primeiro
# model e comparava dado novo com tabelas ainda velhas, quebrando a execução sempre que a
# origem mudava.
execution_config = ExecutionConfig(
    dbt_executable_path=DBT_EXECUTABLE,
    invocation_mode=InvocationMode.SUBPROCESS,
    test_indirect_selection=TestIndirectSelection.BUILDABLE,
)


def _bucket():
    from airflow.providers.google.cloud.hooks.gcs import GCSHook

    return GCSHook(gcp_conn_id=GCP_CONN_ID).get_conn().bucket(BUCKET)


def _bigquery():
    from airflow.providers.google.cloud.hooks.bigquery import BigQueryHook

    return BigQueryHook(gcp_conn_id=GCP_CONN_ID, use_legacy_sql=False).get_client(project_id=PROJETO)


def _http():
    import requests

    sessao = requests.Session()
    sessao.headers["User-Agent"] = "atlas-etl"
    return sessao


# --- tarefas do SINAN (o import do módulo fica dentro das tarefas: leitura da DAG continua leve) ---


@task.sensor(
    task_id="detectar_diferencas",
    mode="reschedule",
    poke_interval=timedelta(minutes=30),
    timeout=timedelta(hours=20),
    soft_fail=True,
    retries=2,
    retry_delay=timedelta(minutes=5),
)
def detectar_diferencas() -> PokeReturnValue:
    from atlas_ingest.sinan import listar_landing, listar_origem, planejar_sync

    plano = planejar_sync(listar_origem(_http()), listar_landing(_bucket()))
    manual = get_current_context()["dag_run"].run_type == "manual"
    return PokeReturnValue(is_done=manual or not plano.vazio(), xcom_value=plano.as_dict())


@task
def lista_do_plano(plano: dict, chave: str) -> list:
    """Uma lista do plano (baixar, apagar, carregar, remover_da_bronze), para mapear as tarefas."""
    return plano.get(chave, [])


@task(
    retries=2, retry_delay=timedelta(minutes=5), map_index_template="{{ task.op_kwargs['versao']['nome'] }}"
)
def baixar(versao: dict) -> dict:
    from atlas_ingest.sinan import baixar_para_landing

    with tempfile.TemporaryDirectory() as tmp:
        return baixar_para_landing(_http(), _bucket(), versao, tmp)


@task(retries=2, retry_delay=timedelta(minutes=5))
def apagar(nome: str) -> list[str]:
    from atlas_ingest.sinan import apagar_do_landing

    return apagar_do_landing(_bucket(), nome)


@task(trigger_rule="none_failed", retries=1)
def carregar_bronze(ano: int) -> dict:
    from atlas_ingest.sinan import carregar_ano_na_bronze

    return carregar_ano_na_bronze(_bigquery(), _bucket(), ano, PROJETO)


@task
def validar(resultado: dict) -> dict:
    from atlas_ingest.sinan import validar_contagens

    validar_contagens(
        resultado["ano"],
        resultado["registros"],
        resultado["output_rows"],
        resultado["linhas_particao"],
        resultado["colunas"],
    )
    return {"ano": resultado["ano"], "etag": resultado["etag"]}


@task
def marcar_carregado(validado: dict) -> int:
    from atlas_ingest.sinan import marcar_carregado as marcar

    marcar(_bucket(), validado["ano"], validado["etag"])
    return validado["ano"]


@task_group(group_id="carga_ano")
def carga_ano(ano: int):
    """Uma cadeia por ano (grupo mapeado): a falha de um ano não impede os outros de serem
    validados e marcados; o ano que falhou volta no plano do dia seguinte."""
    marcar_carregado(validar(carregar_bronze(ano)))  # sem retorno: dependências valem para o grupo


@task(trigger_rule="none_failed", retries=1)
def remover_da_bronze(ano: int) -> int:
    from atlas_ingest.sinan import remover_ano_da_bronze

    return remover_ano_da_bronze(_bigquery(), ano, PROJETO)


@task.short_circuit(trigger_rule="none_failed", ignore_downstream_trigger_rules=True)
def decidir_dbt() -> bool:
    """Roda o dbt se algum ano foi carregado ou removido, ou se o disparo pediu forcar_dbt."""
    ctx = get_current_context()
    ti = ctx["ti"]
    marcados = [
        a for a in (ti.xcom_pull(task_ids="sinan.carga_ano.marcar_carregado", default=None) or []) if a
    ]
    removidos = [
        a for a in (ti.xcom_pull(task_ids="sinan.remover_da_bronze", default=None) or []) if a is not None
    ]
    forcar = bool(ctx["params"].get("forcar_dbt"))
    print(f"anos carregados={marcados} removidos={removidos} forcar_dbt={forcar}")
    return forcar or bool(marcados) or bool(removidos)


with DAG(
    dag_id="process_etl_atlas",
    description="ETL do Atlas: sync do SINAN (OpenDataSUS → landing → bronze) e modelagem dbt pelo Cosmos.",
    schedule="@daily",
    start_date=datetime(2026, 11, 1),
    catchup=False,
    max_active_runs=1,
    tags=["atlas", "dbt", "etl", "cosmos", "sinan"],
    params={
        "forcar_dbt": Param(
            False, type="boolean", description="Opcional. Roda o dbt mesmo sem dados novos na origem."
        ),
    },
    # Teste falhando não deve repetir sozinho: quem decide é a pessoa (tarefas de rede têm retries próprios)
    default_args={"owner": "atlas", "retries": 0},
) as dag:
    with TaskGroup(group_id="sinan") as sinan:
        plano = detectar_diferencas()

        def lista(chave):
            return lista_do_plano.override(task_id=f"lista_{chave}")(plano, chave)

        baixados = baixar.expand(versao=lista("baixar"))
        apagados = apagar.expand(nome=lista("apagar"))
        cargas = carga_ano.expand(ano=lista("carregar"))
        removidos = remover_da_bronze.expand(ano=lista("remover_da_bronze"))
        # landing primeiro; bronze depois (cargas e remoções esperam baixar/apagar terminarem)
        [baixados, apagados] >> cargas
        apagados >> removidos

    decidir = decidir_dbt()
    [cargas, removidos] >> decidir

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
    decidir >> groups[0]
    chain(*groups)
