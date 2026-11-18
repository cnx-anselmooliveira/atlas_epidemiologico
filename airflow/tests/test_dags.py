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
        if rel[0] == "adhoc":  # modelos avulsos (desligados por padrão, fora da ETL)
            continue
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
    "sinan.carga_ano.carregar_bronze",
    "sinan.carga_ano.validar",
    "sinan.carga_ano.marcar_carregado",
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
    # tarefas por arquivo/ano são mapeadas; a cadeia de carga é um grupo mapeado por ano
    from airflow.sdk.definitions.mappedoperator import MappedOperator

    for t in ("sinan.baixar", "sinan.apagar", "sinan.remover_da_bronze"):
        assert isinstance(dag.get_task(t), MappedOperator), t
    for t in (
        "sinan.carga_ano.carregar_bronze",
        "sinan.carga_ano.validar",
        "sinan.carga_ano.marcar_carregado",
    ):
        assert dag.get_task(t).get_closest_mapped_task_group() is not None, t
    # landing antes da bronze; bronze antes da decisão; decisão antes do dbt
    carregar = dag.get_task("sinan.carga_ano.carregar_bronze")
    assert {"sinan.baixar", "sinan.apagar"} <= carregar.upstream_task_ids
    assert dag.get_task("sinan.carga_ano.validar").upstream_task_ids == {carregar.task_id}
    assert "sinan.apagar" in dag.get_task("sinan.remover_da_bronze").upstream_task_ids
    decidir = dag.get_task("decidir_dbt")
    assert {"sinan.carga_ano.marcar_carregado", "sinan.remover_da_bronze"} <= decidir.upstream_task_ids
    assert decidir.trigger_rule == "none_failed" and decidir.ignore_downstream_trigger_rules is True
    roots_seed = [t for t in decidir.downstream_task_ids if _layer_of(t) == "seed"]
    assert roots_seed, "decidir_dbt precisa vir antes do grupo seed"
    for t in ("sinan.carga_ano.carregar_bronze", "sinan.remover_da_bronze"):
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
FORECAST_STACKED = ["catboost", "svr", "lstm"]


def _forecast():
    return _dagbag().dags["atlas_dengue_forecast_br"]


def test_forecast_estrutura_e_regras():
    dag = _forecast()
    assert dag.schedule is None or str(dag.timetable.summary) in ("None", "Never"), "não pode ter agendamento"
    assert dag.max_active_runs == 1 and dag.max_active_tasks == 3
    por_horizonte = {f"horizonte.train_{b}" for b in FORECAST_BASES}
    esperado = {
        "prepare",
        "configuracao",
        "lista_de_horizontes",
        *por_horizonte,
        "horizonte.train_ensemble",
        "horizonte.comparar",
        "exportar",
    }
    assert set(dag.task_ids) == esperado
    # o ensemble depende só dos modelos empilhados
    ensemble = dag.get_task("horizonte.train_ensemble")
    do_grupo = lambda t: {u for u in t.upstream_task_ids if u.startswith("horizonte.")}  # noqa: E731
    assert do_grupo(ensemble) == {f"horizonte.train_{b}" for b in FORECAST_STACKED}
    assert {"prepare", "configuracao"} <= ensemble.upstream_task_ids  # snapshot, janela e semente
    comparar = dag.get_task("horizonte.comparar")
    assert do_grupo(comparar) == {
        "horizonte.train_baseline_bayes",
        "horizonte.train_chronos",
        "horizonte.train_ensemble",
    }
    assert comparar.trigger_rule == "all_done" and comparar.retries == 0
    for t in por_horizonte | {"prepare", "horizonte.train_ensemble"}:
        assert dag.get_task(t).retries == 1, t
    # um grupo por horizonte (mapeado) e a exportação depois dele
    from airflow.sdk.definitions.mappedoperator import MappedOperator

    for t in por_horizonte | {"horizonte.train_ensemble", "horizonte.comparar"}:
        assert dag.get_task(t).get_closest_mapped_task_group() is not None, t
    assert isinstance(dag.get_task("exportar"), MappedOperator) is False
    exportar = dag.get_task("exportar")
    assert exportar.trigger_dag_id == "process_forecast_export_atlas"
    assert exportar.trigger_rule == "none_failed_min_one_success" and exportar.retries == 0
    assert "horizonte.comparar" in exportar.upstream_task_ids


def test_forecast_parametros_e_ambiente():
    dag = _forecast()
    assert dag.params["window"] == 12 and dag.params["seed"] == 42
    assert dag.params["horizons"] == [1, 2, 3, 4]
    assert "horizon" not in dag.params  # substituído por horizons
    # tudo roda em Python no venv do atlas_ml, sem scripts de shell
    for t in dag.tasks:
        assert type(t).__name__ != "BashOperator", t.task_id
    for t in ["prepare", "horizonte.train_catboost", "horizonte.train_ensemble", "horizonte.comparar"]:
        assert dag.get_task(t).python == "/opt/atlas-ml/bin/python", t


def test_exportacao_das_previsoes():
    from airflow.sdk.definitions.mappedoperator import MappedOperator

    dag = _dagbag().dags["process_forecast_export_atlas"]
    assert dag.schedule is None or str(dag.timetable.summary) in ("None", "Never"), "não pode ter agendamento"
    assert dag.max_active_runs == 1
    assert set(dag.task_ids) == {
        "configuracao",
        "listar_versoes",
        "entradas",
        "montar",
        "consolidar",
        "publicar_figuras",
        "carregar_bigquery",
        "atualizar_visoes",
    }
    for t in dag.tasks:
        assert type(t).__name__ != "BashOperator", t.task_id  # DAG em Python, sem scripts de shell
    assert isinstance(dag.get_task("montar"), MappedOperator)  # um por modelo e horizonte
    assert (
        dag.get_task("listar_versoes").python == "/opt/atlas-ml/bin/python"
    )  # MLflow só no venv do atlas_ml
    # a visão vigente só muda na última tarefa, depois da carga e das figuras
    assert dag.get_task("carregar_bigquery").upstream_task_ids >= {"consolidar", "publicar_figuras"}
    assert "carregar_bigquery" in dag.get_task("atualizar_visoes").upstream_task_ids
    assert dag.get_task("atualizar_visoes").downstream_task_ids == set()
    treino = dag.dag_id == "process_forecast_export_atlas" and _forecast().get_task("exportar")
    assert treino.trigger_dag_id == dag.dag_id  # a DAG de treino dispara esta


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
