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


ETL_STEPS = ["dbt_debug", "dbt_deps", "dbt_seed", "dbt_bronze", "dbt_silver", "dbt_gold"]


def test_etl_estrutura():
    dag = _dagbag().dags["process_etl_atlas"]
    assert dag.schedule is None or str(dag.timetable.summary) in ("None", "Never"), "não pode ter agendamento"
    assert dag.max_active_runs == 1
    assert set(dag.task_ids) == {*ETL_STEPS, "dbt_report", "dbt_status"}
    # sequência deps → seed → bronze → silver → gold, cada etapa também ligada à sentinela
    for upstream, downstream in zip(ETL_STEPS, ETL_STEPS[1:] + ["dbt_report"], strict=True):
        assert dag.get_task(upstream).downstream_task_ids == {downstream, "dbt_status"}, upstream
    assert dag.get_task("dbt_status").upstream_task_ids == set(ETL_STEPS)
    assert dag.get_task("dbt_report").trigger_rule == "all_done"
    assert dag.get_task("dbt_status").trigger_rule == "one_failed"
    for task in dag.tasks:
        assert task.retries == 0, f"{task.task_id} não pode ter retentativa"


def test_etl_parametros_e_caminhos():
    dag = _dagbag().dags["process_etl_atlas"]
    params = dag.params
    # parâmetros opcionais: disparo sem configuração roda o projeto inteiro
    assert params["select"] is None and params["exclude"] is None and params["full_refresh"] is False
    layers = {
        "dbt_seed": "resource_type:seed",
        "dbt_bronze": "path:models/bronze",
        "dbt_silver": "path:models/silver",
        "dbt_gold": "path:models/gold",
    }
    for task_id, layer in layers.items():
        task = dag.get_task(task_id)
        assert "dbt build" in task.bash_command and "--full-refresh" in task.bash_command
        assert layer in task.env["DBT_LAYER"].split(), (task_id, task.env["DBT_LAYER"])
        # parâmetros só como variáveis de ambiente, nunca interpolados no comando
        assert "params." not in task.bash_command
        assert "params.select" in task.env["DBT_SELECT_ARG"]
    assert "dbt deps" in dag.get_task("dbt_deps").bash_command
    targets = set()
    for task_id in ETL_STEPS:
        env = dag.get_task(task_id).env
        assert env["DBT_PROJECT_DIR"].endswith("/utfpr_dengue")
        assert env["DBT_PROFILES_DIR"] == env["DBT_PROJECT_DIR"]
        for key in ("DBT_TARGET_PATH", "DBT_LOG_PATH", "DBT_PACKAGES_INSTALL_PATH"):
            assert env[key].startswith("/opt/airflow/dbt-artifacts/"), env[key]
            assert not env[key].startswith(DAGS_FOLDER), "artefatos não podem ir para a pasta de DAGs"
        targets.add(env["DBT_TARGET_PATH"])
    assert len(targets) == len(ETL_STEPS), "cada etapa precisa do próprio target (run_results.json)"


def test_etl_relatorio():
    import json
    import tempfile
    from pathlib import Path

    sys.path.insert(0, DAGS_FOLDER)
    from process_etl_atlas import summarize_run_results

    base = Path(tempfile.mkdtemp())
    empty = summarize_run_results(str(base))
    assert empty["nodes"] == 0 and all(v is None for v in empty["stages"].values())

    def write(stage, results):
        (base / stage / "target").mkdir(parents=True)
        payload = {"elapsed_time": 2.0, "results": results}
        (base / stage / "target" / "run_results.json").write_text(json.dumps(payload))

    write(
        "bronze",
        [
            {
                "unique_id": "model.a",
                "status": "success",
                "execution_time": 3.0,
                "adapter_response": {"bytes_processed": 2**30},
            }
        ],
    )
    write(
        "silver",
        [
            {"unique_id": "test.b", "status": "fail", "execution_time": 1.0, "message": "Got 3 results"},
            {"unique_id": "model.c", "status": "skipped", "execution_time": 0.0},
        ],
    )
    summary = summarize_run_results(str(base))
    assert (
        summary["nodes"] == 3 and summary["success"] == 1 and summary["fail"] == 1 and summary["skipped"] == 1
    )
    assert summary["failed_nodes"][0]["node"] == "test.b" and summary["failed_nodes"][0]["stage"] == "silver"
    assert summary["stages"]["gold"] is None and summary["stages"]["bronze"] == {"success": 1}
    assert summary["slowest"][0] == ("model.a", 3.0)
    assert summary["gib_processed"] == 1.0 and summary["elapsed_s"] == 4.0


def test_projeto_dbt_ignorado():
    bag = _dagbag()
    assert not any("utfpr_dengue" in path for path in bag.file_last_changed), "o DagBag varreu o projeto dbt"
    assert all("utfpr_dengue" not in (dag.fileloc or "") for dag in bag.dags.values())


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
