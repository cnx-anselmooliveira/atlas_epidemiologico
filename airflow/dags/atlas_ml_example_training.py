"""Treino do experimento de exemplo do Atlas, registrado no MLflow.

Sem agendamento: disparada manualmente. Executa o mesmo comando usado na
máquina local e no container de treino (`atlas-ml train example --register`)
e falha se a run não for registrada no MLflow (spec orchestration-runtime).
"""

from datetime import datetime, timedelta

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG

# `atlas-ml` imprime "run_id=<id> …" ao terminar; sem isso, a tarefa falha.
TRAIN_CMD = r"""
set -euo pipefail
out="$(atlas-ml train example --register)"
echo "$out"
echo "$out" | grep -q '^run_id=' || { echo "run não registrada no MLflow" >&2; exit 1; }
"""

with DAG(
    dag_id="atlas_ml_example_training",
    description="Treina o experimento de exemplo (dados sintéticos) e registra no MLflow.",
    schedule=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["atlas", "ml", "exemplo"],
    default_args={
        "owner": "atlas",
        "retries": 2,
        "retry_delay": timedelta(minutes=1),
    },
) as dag:
    BashOperator(
        task_id="train_example",
        bash_command=TRAIN_CMD,
        # herda o ambiente do worker: MLFLOW_TRACKING_URI, ATLAS_ENV, ATLAS_IMAGE_TAG, credenciais
        append_env=True,
    )
