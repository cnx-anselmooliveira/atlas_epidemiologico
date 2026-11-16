"""Integridade das DAGs. Roda dentro da imagem do Airflow, sem banco nem pytest:

    docker run --rm atlas-epidemiologia-airflow:local python /opt/atlas/tests/test_dags.py

As DAGs do Cosmos rodam `dbt ls` na leitura: o profile exige DBT_BQ_KEYFILE definida (o
`dbt ls` não conecta ao BigQuery, então um caminho fictício basta) e, sem banco, o cache
do Cosmos fica desligado (AIRFLOW__COSMOS__ENABLE_CACHE_DBT_LS=False).

Também é compatível com pytest (funções test_*).
"""

import functools
import os
import sys

DAGS_FOLDER = os.environ.get("ATLAS_DAGS_FOLDER", "/opt/airflow/dags")


@functools.lru_cache(maxsize=1)
def _dagbag():
    # uma leitura só: as DAGs do Cosmos rodam `dbt ls` ao serem lidas
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


ETL_LAYERS = ["seed", "bronze", "silver", "gold"]


def _project_nodes() -> dict[str, str]:
    """Seeds e models do projeto dbt → camada esperada (pela pasta), lidos do próprio projeto."""
    from pathlib import Path

    root = Path(DAGS_FOLDER) / "utfpr_dengue"
    nodes = {p.stem: "seed" for p in (root / "seeds").glob("*.csv")}
    for p in (root / "models").rglob("*.sql"):
        rel = p.relative_to(root / "models").parts
        nodes[p.stem] = rel[0] if len(rel) > 1 else "gold"  # raiz de models/ (time spine) → gold
    return nodes


def _layer_of(task_id: str) -> str:
    return task_id.split(".", 1)[0]


def _dbt_task_ids(dag):
    return [t for t in dag.task_ids if _layer_of(t) in ETL_LAYERS]


def test_etl_cosmos_grupos_em_cadeia():
    dag = _dagbag().dags["process_etl_atlas"]
    assert dag.max_active_runs == 1
    dbt = _dbt_task_ids(dag)
    assert {_layer_of(t) for t in dbt} == set(ETL_LAYERS)
    for task_id in dbt:
        assert dag.get_task(task_id).retries == 0, f"{task_id} não pode ter retentativa"
    # cada camada só depende da anterior (ou dela mesma)
    order = {layer: i for i, layer in enumerate(ETL_LAYERS)}
    crossings = set()
    for task_id in dbt:
        for up in dag.get_task(task_id).upstream_task_ids:
            if _layer_of(up) not in order:
                continue
            a, b = order[_layer_of(up)], order[_layer_of(task_id)]
            assert a <= b, f"{up} -> {task_id} volta de camada"
            if a < b:
                crossings.add((a, b))
    assert crossings == {(0, 1), (1, 2), (2, 3)}, crossings


def test_etl_cosmos_cobre_cada_model_uma_vez():
    dag = _dagbag().dags["process_etl_atlas"]
    dbt = _dbt_task_ids(dag)
    for node, expected in _project_nodes().items():
        layers = {
            _layer_of(t) for t in dbt if t.split(".")[1] == node or t.split(".")[1].startswith(node + "_")
        }
        assert layers == {expected}, f"{node}: esperado em {expected}, encontrado em {layers}"
    assert any(t.startswith("gold.gold_dengue_casos_provaveis_uf_semanal") for t in dbt)


SINAN = [
    "sinan.detectar_diferencas",
    "sinan.lista_baixar",
    "sinan.baixar",
    "sinan.apagar",
    "sinan.carregar_bronze",
    "sinan.validar",
    "sinan.marcar_carregado",
    "sinan.remover_da_bronze",
]


def test_etl_diaria_com_sync_do_sinan_antes_do_dbt():
    dag = _dagbag().dags["process_etl_atlas"]
    assert "@daily" in str(dag.schedule) or "daily" in str(dag.timetable.summary).lower(), (
        dag.timetable.summary
    )
    assert dag.catchup is False
    assert dag.params["forcar_dbt"] is False
    assert set(SINAN) <= set(dag.task_ids)
    sensor = dag.get_task("sinan.detectar_diferencas")
    assert sensor.mode == "reschedule" and sensor.soft_fail is True
    # tarefas por arquivo/ano são mapeadas
    for t in (
        "sinan.baixar",
        "sinan.apagar",
        "sinan.carregar_bronze",
        "sinan.validar",
        "sinan.marcar_carregado",
        "sinan.remover_da_bronze",
    ):
        from airflow.sdk.definitions.mappedoperator import MappedOperator

        assert isinstance(dag.get_task(t), MappedOperator), t
    # landing antes da bronze; bronze antes da decisão; decisão antes do dbt
    assert {"sinan.baixar", "sinan.apagar"} <= dag.get_task("sinan.carregar_bronze").upstream_task_ids
    assert "sinan.apagar" in dag.get_task("sinan.remover_da_bronze").upstream_task_ids
    decidir = dag.get_task("decidir_dbt")
    assert {"sinan.marcar_carregado", "sinan.remover_da_bronze"} <= decidir.upstream_task_ids
    assert decidir.trigger_rule == "none_failed" and decidir.ignore_downstream_trigger_rules is True
    roots_seed = [t for t in decidir.downstream_task_ids if _layer_of(t) == "seed"]
    assert roots_seed, "decidir_dbt precisa vir antes do grupo seed"
    for t in ("sinan.carregar_bronze", "sinan.remover_da_bronze"):
        assert dag.get_task(t).trigger_rule == "none_failed", t


def test_docs_dag():
    dag = _dagbag().dags["process_dbt_docs_atlas"]
    assert dag.schedule is None or str(dag.timetable.summary) in ("None", "Never"), "não pode ter agendamento"
    assert dag.task_ids == ["dbt_docs_gcs"]
    task = dag.get_task("dbt_docs_gcs")
    assert type(task).__name__ == "DbtDocsGCSLocalOperator"
    assert task.connection_id == "google_cloud_default"
    assert task.bucket_name == os.environ.get("ATLAS_DBT_DOCS_BUCKET", "ppgcc-bucket")
    assert task.folder_dir == f"dbt_docs/{os.environ.get('ATLAS_ENV', 'dev')}"
    assert task.retries == 0


FORECAST_BASES = ["baseline_bayes", "chronos", "catboost", "svr", "lstm"]


def test_forecast_estrutura_e_regras():
    dag = _dagbag().dags["atlas_dengue_forecast_br"]
    assert dag.schedule is None or str(dag.timetable.summary) in ("None", "Never"), "não pode ter agendamento"
    assert dag.max_active_runs == 1 and dag.max_active_tasks == 3
    tasks = {f"train_{b}" for b in FORECAST_BASES}
    assert set(dag.task_ids) == {"prepare", *tasks, "train_ensemble", "compare"}
    assert dag.get_task("prepare").downstream_task_ids == tasks
    # o ensemble depende só dos modelos empilhados
    assert dag.get_task("train_ensemble").upstream_task_ids == {"train_catboost", "train_svr", "train_lstm"}
    compare = dag.get_task("compare")
    assert compare.upstream_task_ids == {"train_baseline_bayes", "train_chronos", "train_ensemble"}
    assert compare.trigger_rule == "all_done"
    for t in tasks | {"prepare", "train_ensemble"}:
        assert dag.get_task(t).retries == 1, t


def test_forecast_parametros_e_ambiente():
    dag = _dagbag().dags["atlas_dengue_forecast_br"]
    assert dag.params["window"] == 12 and dag.params["horizon"] == 1 and dag.params["seed"] == 42
    for task in dag.tasks:
        assert task.env["ATLAS_PIPELINE_RUN"] == "{{ run_id }}", task.task_id
        assert "params." not in task.bash_command, task.task_id
    cat = dag.get_task("train_catboost")
    assert "atlas-ml forecast train catboost" in cat.bash_command
    assert "xcom_pull(task_ids='prepare')" in cat.env["DATASET_RUN"]
    base_runs = dag.get_task("train_ensemble").env["BASE_RUNS"]
    for b in ("catboost", "svr", "lstm"):
        assert f"{b}=" in base_runs and f"train_{b}" in base_runs
    assert "forecast compare" in dag.get_task("compare").bash_command


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
