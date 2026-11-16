"""Integridade das DAGs. Roda dentro da imagem do Airflow, sem banco nem pytest:

    docker run --rm atlas-epidemiologia-airflow:local python /opt/atlas/tests/test_dags.py

Também é compatível com pytest (funções test_*).
"""

import os
import sys

DAGS_FOLDER = os.environ.get("ATLAS_DAGS_FOLDER", "/opt/airflow/dags")


def _dagbag():
    try:
        from airflow.dag_processing.dagbag import DagBag
    except ImportError:  # versões anteriores do Airflow 3
        from airflow.models.dagbag import DagBag
    # exemplos já desligados por AIRFLOW__CORE__LOAD_EXAMPLES=False na imagem
    return DagBag(dag_folder=DAGS_FOLDER)


def test_sem_erros_de_import():
    bag = _dagbag()
    assert not bag.import_errors, bag.import_errors
    assert bag.dags, "nenhuma DAG carregada"


def test_dag_de_exemplo():
    dag = _dagbag().dags["atlas_ml_example_training"]
    assert dag.schedule is None or str(dag.timetable.summary) in ("None", "Never"), "não pode ter agendamento"
    assert dag.max_active_runs == 1
    task = dag.get_task("train_example")
    assert task.retries == 2
    assert "atlas-ml train example --register" in task.bash_command
    assert "run_id=" in task.bash_command


if __name__ == "__main__":
    failures = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"ok   {name}")
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print(f"FAIL {name}: {exc}")
    sys.exit(1 if failures else 0)
