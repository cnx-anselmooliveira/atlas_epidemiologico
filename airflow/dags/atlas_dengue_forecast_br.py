"""Previsão de dengue por UF (Brasil): treina os modelos e registra tudo no MLflow.

Sem agendamento: disparada manualmente (de preferência depois da process_etl_atlas).

    prepare ─┬─ train_baseline_bayes ────────────────────────┐
             ├─ train_chronos ───────────────────────────────┤
             ├─ train_catboost ─┐                            ├─► compare (all_done)
             ├─ train_svr ──────┼─► train_ensemble ──────────┘
             └─ train_lstm ─────┘

- prepare: lê a gold_dengue_casos_provaveis_uf_semanal e grava o snapshot (run `dataset`);
  todos os modelos usam esse mesmo snapshot (mesma atlas.data_version).
- Cada tarefa roda o mesmo CLI usado localmente (`atlas-ml forecast …`). O CLI imprime o ID
  da run na última linha, que o BashOperator envia por XCom (o log fica completo).
- ATLAS_PIPELINE_RUN = run_id da DAG: vira a tag atlas.pipeline_run de todas as runs, e a
  comparação final junta as runs por ela, listando os modelos que faltarem.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG, Param

BASES = ["baseline_bayes", "chronos", "catboost", "svr", "lstm"]
STACKED = ["catboost", "svr", "lstm"]

# Parâmetros entram como variáveis de ambiente, nunca interpolados no texto do comando
ENV = {
    "ATLAS_PIPELINE_RUN": "{{ run_id }}",
    "FC_WINDOW": "{{ params.window }}",
    "FC_HORIZON": "{{ params.horizon }}",
    "FC_SEED": "{{ params.seed }}",
}
OPTS = '--window "$FC_WINDOW" --horizon "$FC_HORIZON" --seed "$FC_SEED"'


def _id(task_id: str, prefix: str) -> str:
    """Template que extrai o ID da última linha (`prefix=<id>`) devolvida pela tarefa."""
    return "{{ ti.xcom_pull(task_ids='" + task_id + "') | replace('" + prefix + "=', '') }}"


DATASET = _id("prepare", "dataset_run_id")

with DAG(
    dag_id="atlas_dengue_forecast_br",
    description="Treina baseline bayesiano, Chronos, CatBoost, SVR, LSTM e ensemble e registra no MLflow.",
    schedule=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    # MCMC, LSTM e Chronos em paralelo saturam a CPU
    max_active_tasks=3,
    tags=["atlas", "ml", "forecast"],
    # Todos opcionais: disparar sem configuração usa janela 12, horizonte 1 e semente 42
    params={
        "window": Param(12, type="integer", minimum=1, description="Opcional. Semanas de histórico."),
        "horizon": Param(1, type="integer", minimum=1, description="Opcional. Semanas à frente."),
        "seed": Param(42, type="integer", description="Opcional. Semente."),
    },
    default_args={"owner": "atlas", "retries": 1, "retry_delay": timedelta(minutes=2)},
) as dag:
    prepare = BashOperator(
        task_id="prepare",
        bash_command="set -euo pipefail\natlas-ml forecast prepare\n",
        env=ENV,
        append_env=True,
    )

    trained = {}
    for name in BASES:
        trained[name] = BashOperator(
            task_id=f"train_{name}",
            bash_command=(
                f'set -euo pipefail\natlas-ml forecast train {name} --dataset-run "$DATASET_RUN" {OPTS}\n'
            ),
            env={**ENV, "DATASET_RUN": DATASET},
            append_env=True,
        )
        prepare >> trained[name]

    base_runs = ",".join(f"{n}={_id(f'train_{n}', 'run_id')}" for n in STACKED)
    ensemble = BashOperator(
        task_id="train_ensemble",
        bash_command=(
            "set -euo pipefail\n"
            f'atlas-ml forecast train ensemble --dataset-run "$DATASET_RUN" --base-runs "$BASE_RUNS" {OPTS}\n'
        ),
        env={**ENV, "DATASET_RUN": DATASET, "BASE_RUNS": base_runs},
        append_env=True,
    )
    [trained[n] for n in STACKED] >> ensemble

    compare = BashOperator(
        task_id="compare",
        bash_command='set -euo pipefail\natlas-ml forecast compare --pipeline-run "$ATLAS_PIPELINE_RUN"\n',
        env=ENV,
        append_env=True,
        # registra a comparação mesmo com modelos faltando (aparecem em atlas.missing_models)
        trigger_rule="all_done",
        retries=0,
    )
    [trained["baseline_bayes"], trained["chronos"], ensemble] >> compare
