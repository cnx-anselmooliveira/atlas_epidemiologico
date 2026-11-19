"""Fluxo diário do Brasil: SINAN → bronze → dbt → treino dos modelos de previsão.

Todo dia às 03h00 de Brasília em hml e prod (em dev, só à mão). Cada etapa é uma DAG própria,
disparada em sequência; a seguinte só começa quando a anterior termina com sucesso.

    ingestao_sinan ──► modelagem_dbt ──► decidir_treino ──► treino_previsao
    (ingestao_sinan_brasil,   (dbt_brasil: só se    (só se a gold    (atlas_dengue_forecast_br com a
     espera até 3 h por        a bronze mudou)       mudou desde o    base inteira; no fim dispara a
     dados novos)                                    treino vigente)  exportação para o BigQuery)

- A espera pelas filhas fica no triggerer (deferrable): não ocupa vaga do LocalExecutor.
- Falha numa etapa: as seguintes não rodam e a etl_brasil fica com falha; o site continua com a
  gold e as previsões anteriores. Cada DAG pode ser reexecutada sozinha.
- `forcar_dbt` e `forcar_treino` refazem as etapas mesmo sem dados novos.
"""

from __future__ import annotations

import os
from datetime import timedelta

import pendulum
from airflow.providers.standard.operators.trigger_dagrun import TriggerDagRunOperator
from airflow.sdk import DAG, Param, get_current_context, task
from airflow.timetables.trigger import CronTriggerTimetable

FUSO = "America/Sao_Paulo"
AMBIENTE = os.environ.get("ATLAS_ENV", "dev")
# só hml e prod treinam todo dia; em dev a DAG roda à mão (não treina a base inteira na máquina local)
AGENDA = CronTriggerTimetable("0 3 * * *", timezone=FUSO) if AMBIENTE in ("hml", "prod") else None
JANELA_SINAN_HORAS = 3


@task.short_circuit(ignore_downstream_trigger_rules=True)
def decidir_treino() -> bool:
    """Treina se a gold atual não é a dos modelos vigentes no MLflow do ambiente (ou com forcar_treino)."""
    from atlas_ingest import gcp
    from atlas_ingest.etl_brasil import (
        GOLD_CASOS,
        data_versions_vigentes,
        nomes_registrados,
        treino_precisa_rodar,
        versao_tabela,
    )

    forcar = bool(get_current_context()["params"].get("forcar_treino"))
    modificada = gcp.modificada_em(gcp.bigquery(), GOLD_CASOS)
    if modificada is None:
        raise RuntimeError(f"A gold {GOLD_CASOS} não existe: não há o que treinar.")
    versao = versao_tabela(f"{gcp.PROJETO}.{GOLD_CASOS}", modificada)
    sessao, url = gcp.mlflow_sessao()
    vigentes = data_versions_vigentes(sessao, url, AMBIENTE, nomes_registrados())
    decisao = treino_precisa_rodar(versao, vigentes, forcar)
    print(("treina: " if decisao.rodar else "pula o treino: ") + decisao.motivo)
    return decisao.rodar


def disparar(task_id: str, dag_id: str, conf: dict) -> TriggerDagRunOperator:
    return TriggerDagRunOperator(
        task_id=task_id,
        trigger_dag_id=dag_id,
        conf=conf,
        wait_for_completion=True,
        deferrable=True,
        poke_interval=60,
        allowed_states=["success"],
        failed_states=["failed"],
    )


with DAG(
    dag_id="etl_brasil",
    description="Fluxo diário do Brasil: SINAN, dbt e treino, só com dados novos (03h00 de Brasília).",
    schedule=AGENDA,
    start_date=pendulum.datetime(2026, 11, 1, tz=FUSO),
    catchup=False,
    max_active_runs=1,
    # treino da base inteira leva horas na VPS; o teto evita uma execução presa para sempre
    dagrun_timeout=timedelta(hours=20),
    render_template_as_native_obj=True,
    tags=["atlas", "etl", "brasil", "orquestracao"],
    params={
        "forcar_dbt": Param(False, type="boolean", description="Opcional. Roda o dbt mesmo sem dados novos."),
        "forcar_treino": Param(
            False, type="boolean", description="Opcional. Treina mesmo que a gold não tenha mudado."
        ),
    },
    default_args={"owner": "atlas", "retries": 0},
) as dag:
    ingestao = disparar("ingestao_sinan", "ingestao_sinan_brasil", {"janela_horas": JANELA_SINAN_HORAS})
    modelagem = disparar("modelagem_dbt", "dbt_brasil", {"forcar_dbt": "{{ params.forcar_dbt }}"})
    # fonte vazia = gold completa (todas as UFs e todo o período), nunca a amostra avulsa
    treino = disparar("treino_previsao", "atlas_dengue_forecast_br", {"fonte": ""})
    ingestao >> modelagem >> decidir_treino() >> treino
