"""ETL do Atlas: atualiza a modelagem dbt (seeds, bronze, silver e gold no BigQuery) sob demanda.

Sem agendamento: disparada manualmente, com parâmetros opcionais repassados ao dbt.

    dbt_debug ► dbt_deps ► dbt_seed ► dbt_bronze ► dbt_silver ► dbt_gold ► dbt_report
        └──────────┴──────────┴───────────┴────────────┴───────────┴──────► dbt_status

- Cada camada é um `dbt build` (models + testes) restrito à sua pasta; se uma camada
  falha, as seguintes não rodam. O relatório roda sempre; `dbt_status` só roda se algo
  falhou e deixa a execução vermelha.
- `select`/`exclude` valem para todas as camadas: com `select=+gold_x`, cada camada
  reconstrói só os antecessores de gold_x que estão nela (interseção `camada,seletor`).
- Projeto: `utfpr_dengue/`, ao lado deste arquivo (pasta de DAGs ou bundle Git da branch).
- Profile: `utfpr_dengue/profiles.yml`, todo por variáveis de ambiente (DBT_BQ_KEYFILE etc.).
- Artefatos (target/, logs, run_results.json e pacotes do deps):
  /opt/airflow/dbt-artifacts/<run_id>/<etapa>/, nunca na pasta de DAGs (pode ser somente leitura).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from airflow.providers.standard.operators.bash import BashOperator
from airflow.providers.standard.operators.python import PythonOperator
from airflow.sdk import DAG, Param, chain
from airflow.sdk.exceptions import AirflowFailException

log = logging.getLogger(__name__)

DBT_DIR = Path(__file__).resolve().parent / "utfpr_dengue"
ARTIFACTS_ROOT = "/opt/airflow/dbt-artifacts"
# run_id tem ':' e '+' (ex.: manual__2026-11-16T12:00:00+00:00); viram '_' no nome da pasta
ARTIFACTS = ARTIFACTS_ROOT + "/{{ run_id | replace(':', '_') | replace('+', '_') }}"

# Etapas de build, na ordem: (etapa, seletores que definem a camada)
LAYERS = [
    ("seed", ["resource_type:seed"]),
    ("bronze", ["path:models/bronze"]),
    ("silver", ["path:models/silver"]),
    # metricflow_time_spine fica na raiz de models/, mas é materializado no schema gold
    ("gold", ["path:models/gold", "path:models/metricflow_time_spine.sql"]),
]
STAGES = ["debug", "deps"] + [name for name, _ in LAYERS]


def stage_env(stage: str, layer: list[str] | None = None) -> dict[str, str]:
    """Ambiente de uma etapa. `env` é templated no BashOperator; com append_env=True o
    restante do ambiente do worker (DBT_BQ_KEYFILE, DBT_PARTIAL_PARSE...) é herdado.
    Parâmetros entram como variáveis, nunca interpolados no texto do comando."""
    env = {
        "DBT_PROJECT_DIR": str(DBT_DIR),
        "DBT_PROFILES_DIR": str(DBT_DIR),
        # um target por etapa: cada uma guarda o próprio run_results.json
        "DBT_TARGET_PATH": f"{ARTIFACTS}/{stage}/target",
        "DBT_LOG_PATH": f"{ARTIFACTS}/{stage}/logs",
        # lido pelo packages-install-path do dbt_project.yml; compartilhado entre as etapas
        "DBT_PACKAGES_INSTALL_PATH": f"{ARTIFACTS}/dbt_packages",
        "DBT_USE_COLORS": "false",
    }
    if layer is not None:
        env |= {
            "DBT_LAYER": " ".join(layer),
            "DBT_SELECT_ARG": "{{ params.select or '' }}",
            "DBT_EXCLUDE_ARG": "{{ params.exclude or '' }}",
            "DBT_FULL_REFRESH_ARG": "{{ 'true' if params.full_refresh else '' }}",
        }
    return env


COMMON = '--project-dir "$DBT_PROJECT_DIR" --profiles-dir "$DBT_PROFILES_DIR"'
DEBUG_CMD = f"set -euo pipefail\ndbt debug {COMMON}\n"
DEPS_CMD = f"set -euo pipefail\ndbt deps {COMMON}\n"

# set -f: seletores separados por espaço, sem expansão de glob (`tag:*` chega literal).
# Com `select`, cada seletor do usuário é cruzado com cada seletor da camada (`camada,sel`).
LAYER_CMD = r"""
set -euo pipefail
set -f
sel=()
for layer in $DBT_LAYER; do
  if [ -n "$DBT_SELECT_ARG" ]; then
    for s in $DBT_SELECT_ARG; do sel+=("$layer,$s"); done
  else
    sel+=("$layer")
  fi
done
args=(--select "${sel[@]}")
if [ -n "$DBT_EXCLUDE_ARG" ]; then args+=(--exclude $DBT_EXCLUDE_ARG); fi
if [ -n "$DBT_FULL_REFRESH_ARG" ]; then args+=(--full-refresh); fi
echo "dbt build ${args[*]}"
dbt build --project-dir "$DBT_PROJECT_DIR" --profiles-dir "$DBT_PROFILES_DIR" "${args[@]}"
"""

STATUSES = ("success", "pass", "error", "fail", "skipped", "warn")


def summarize_run_results(artifacts_dir: str, top: int = 5) -> dict:
    """Resume os run_results.json das etapas: contagens por status (total e por etapa),
    falhas, nós mais lentos e bytes processados no BigQuery.

    Etapas sem run_results.json (não rodaram) entram como "não executada"; nada disso
    gera erro: quem falha a execução é a sentinela dbt_status.
    """
    counts = dict.fromkeys(STATUSES, 0)
    stages, failed, timings = {}, [], []
    bytes_processed, elapsed = 0, 0.0
    for stage in STAGES:
        path = Path(artifacts_dir) / stage / "target" / "run_results.json"
        if not path.exists():
            stages[stage] = None
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        stage_counts = dict.fromkeys(STATUSES, 0)
        for r in data.get("results", []):
            status = r.get("status")
            stage_counts[status] = stage_counts.get(status, 0) + 1
            node = r.get("unique_id", "?")
            if status in ("error", "fail"):
                message = (r.get("message") or "")[:500]
                failed.append({"stage": stage, "node": node, "status": status, "message": message})
            timings.append((node, round(float(r.get("execution_time") or 0.0), 1)))
            bytes_processed += int((r.get("adapter_response") or {}).get("bytes_processed") or 0)
        for status, n in stage_counts.items():
            counts[status] = counts.get(status, 0) + n
        stages[stage] = {k: v for k, v in stage_counts.items() if v}
        elapsed += float(data.get("elapsed_time") or 0.0)

    timings.sort(key=lambda t: t[1], reverse=True)
    summary = {
        "artifacts_dir": artifacts_dir,
        "stages": stages,
        "elapsed_s": round(elapsed, 1),
        "nodes": len(timings),
        **counts,
        "failed_nodes": failed,
        "slowest": timings[:top],
        "bytes_processed": bytes_processed,
        "gib_processed": round(bytes_processed / 2**30, 3),
    }

    for stage, stage_counts in stages.items():
        log.info("etapa %-7s %s", stage, "não executada" if stage_counts is None else stage_counts)
    log.info(
        "dbt: %s nós em %ss | ok=%s pass=%s warn=%s skipped=%s error=%s fail=%s | %s GiB",
        summary["nodes"],
        summary["elapsed_s"],
        *(counts[s] for s in ("success", "pass", "warn", "skipped", "error", "fail")),
        summary["gib_processed"],
    )
    for item in failed:
        log.error("FALHOU [%s] %s (%s): %s", item["stage"], item["node"], item["status"], item["message"])
    for node, seconds in summary["slowest"]:
        log.info("lento  %6.1fs  %s", seconds, node)
    return summary


def fail_run() -> None:
    raise AirflowFailException("Uma etapa do dbt falhou; veja o log dela e o dbt_report.")


with DAG(
    dag_id="process_etl_atlas",
    description="ETL do Atlas no dbt (utfpr_dengue): deps, seed, bronze, silver, gold e relatório.",
    schedule=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["atlas", "dbt", "etl"],
    # Todos opcionais: disparar sem configuração roda o projeto inteiro
    params={
        "select": Param(
            None,
            type=["null", "string"],
            description="Opcional. Seletores do dbt (vazio = projeto inteiro). Ex.: +gold_x",
        ),
        "exclude": Param(None, type=["null", "string"], description="Opcional. Seletores a excluir."),
        "full_refresh": Param(
            False, type="boolean", description="Opcional. Recria tabelas incrementais do zero."
        ),
    },
    # Teste falhando não deve repetir sozinho: quem decide é a pessoa
    default_args={"owner": "atlas", "retries": 0},
) as dag:
    steps = [
        BashOperator(task_id="dbt_debug", bash_command=DEBUG_CMD, env=stage_env("debug"), append_env=True),
        BashOperator(task_id="dbt_deps", bash_command=DEPS_CMD, env=stage_env("deps"), append_env=True),
    ]
    for name, layer in LAYERS:
        steps.append(
            BashOperator(
                task_id=f"dbt_{name}",
                bash_command=LAYER_CMD,
                env=stage_env(name, layer),
                append_env=True,
            )
        )

    dbt_report = PythonOperator(
        task_id="dbt_report",
        python_callable=summarize_run_results,
        op_kwargs={"artifacts_dir": ARTIFACTS},
        trigger_rule="all_done",
    )
    # O estado da execução vem das tarefas folha; sem esta sentinela, uma etapa falha
    # terminaria com a execução verde porque o relatório (all_done) passa.
    dbt_status = PythonOperator(
        task_id="dbt_status",
        python_callable=fail_run,
        trigger_rule="one_failed",
    )

    chain(*steps, dbt_report)
    steps >> dbt_status
