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
    dag = _dagbag().dags["dbt_brasil"]
    assert dag.max_active_runs == 1
    # cada tarefa é um processo dbt dentro do scheduler: limitado para não derrubá-lo na VPS
    assert dag.max_active_tasks == 2
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
    dag = _dagbag().dags["dbt_brasil"]
    dbt = _dbt_task_ids(dag)
    for node, expected in _project_nodes().items():
        layers = {
            _layer_of(t) for t in dbt if t.split(".")[1] == node or t.split(".")[1].startswith(node + "_")
        }
        assert layers == {expected}, f"{node}: esperado em {expected}, encontrado em {layers}"
    assert any(t.startswith("gold.gold_dengue_casos_provaveis_uf_semanal") for t in dbt)


SINAN = [
    "detectar_diferencas",
    "lista_baixar",
    "baixar",
    "apagar",
    "carga_ano.carregar_bronze",
    "carga_ano.validar",
    "carga_ano.marcar_carregado",
    "remover_da_bronze",
    "resumo",
]


def _sem_agenda(dag) -> bool:
    return dag.schedule is None or str(dag.timetable.summary) in ("None", "Never")


def test_ingestao_sinan_brasil():
    from airflow.sdk.definitions.mappedoperator import MappedOperator

    dag = _dagbag().dags["ingestao_sinan_brasil"]
    assert _sem_agenda(dag), "a ingestão só roda disparada (etl_brasil ou à mão)"
    assert dag.catchup is False and dag.max_active_runs == 1
    assert dag.params["janela_horas"] == 0  # à mão: verifica uma vez
    assert set(SINAN) <= set(dag.task_ids)
    sensor = dag.get_task("detectar_diferencas")
    assert sensor.mode == "reschedule"
    for t in ("baixar", "apagar", "remover_da_bronze"):
        assert isinstance(dag.get_task(t), MappedOperator), t
    for t in ("carga_ano.carregar_bronze", "carga_ano.validar", "carga_ano.marcar_carregado"):
        assert dag.get_task(t).get_closest_mapped_task_group() is not None, t
    # landing antes da bronze; tudo antes do resumo
    carregar = dag.get_task("carga_ano.carregar_bronze")
    assert {"baixar", "apagar"} <= carregar.upstream_task_ids
    assert dag.get_task("carga_ano.validar").upstream_task_ids == {carregar.task_id}
    assert "apagar" in dag.get_task("remover_da_bronze").upstream_task_ids
    resumo = dag.get_task("resumo")
    assert {"carga_ano.marcar_carregado", "remover_da_bronze"} <= resumo.upstream_task_ids
    assert resumo.trigger_rule == "none_failed"
    for t in ("carga_ano.carregar_bronze", "remover_da_bronze"):
        assert dag.get_task(t).trigger_rule == "none_failed", t
    assert not _dbt_task_ids(dag), "o dbt fica na dbt_brasil"


def test_dbt_brasil_decide_antes_do_dbt():
    dag = _dagbag().dags["dbt_brasil"]
    assert _sem_agenda(dag), "o dbt só roda disparado (etl_brasil ou à mão)"
    assert dag.params["forcar_dbt"] is False
    decidir = dag.get_task("decidir_dbt")
    assert decidir.ignore_downstream_trigger_rules is True
    assert decidir.upstream_task_ids == set()
    roots_seed = [t for t in decidir.downstream_task_ids if _layer_of(t) == "seed"]
    assert roots_seed, "decidir_dbt precisa vir antes do grupo seed"
    # docs do dbt no fim: depois do gold, sem esperar, e pulada junto quando decidir_dbt pula
    docs = dag.get_task("gerar_docs")
    assert docs.trigger_dag_id == "process_dbt_docs_atlas" and docs.wait_for_completion is False
    assert docs.upstream_task_ids and all(_layer_of(u) == "gold" for u in docs.upstream_task_ids)
    assert docs.trigger_rule == "all_success"
    assert "process_dbt_docs_atlas" in _dagbag().dags


def test_etl_brasil_encadeia_as_etapas():
    dag = _dagbag().dags["etl_brasil"]
    assert dag.catchup is False and dag.max_active_runs == 1
    assert dag.params["forcar_dbt"] is False and dag.params["forcar_treino"] is False
    ordem = ["ingestao_sinan", "modelagem_dbt", "decidir_treino", "treino_previsao"]
    assert set(dag.task_ids) == set(ordem)
    for antes, depois in zip(ordem, ordem[1:], strict=False):
        assert dag.get_task(depois).upstream_task_ids == {antes}, (antes, depois)
    alvos = {
        "ingestao_sinan": "ingestao_sinan_brasil",
        "modelagem_dbt": "dbt_brasil",
        "treino_previsao": "atlas_dengue_forecast_br",
    }
    for task_id, dag_id in alvos.items():
        t = dag.get_task(task_id)
        assert type(t).__name__ == "TriggerDagRunOperator", task_id
        assert t.trigger_dag_id == dag_id and dag_id in _dagbag().dags, task_id
        assert t.wait_for_completion is True and t.deferrable is True, task_id
        assert list(t.failed_states) == ["failed"] and list(t.allowed_states) == ["success"], task_id
    assert dag.get_task("ingestao_sinan").conf["janela_horas"] == 3
    assert dag.get_task("treino_previsao").conf == {"fonte": ""}  # base inteira, nunca a amostra
    assert "forcar_dbt" in str(dag.get_task("modelagem_dbt").conf["forcar_dbt"])
    assert dag.get_task("decidir_treino").ignore_downstream_trigger_rules is True


def _ler_dag(arquivo: str, ambiente: str):
    """Lê uma DAG isolada com ATLAS_ENV definido (o agendamento depende do ambiente)."""
    import importlib.util

    anterior = os.environ.get("ATLAS_ENV")
    os.environ["ATLAS_ENV"] = ambiente
    try:
        spec = importlib.util.spec_from_file_location(f"_dag_{ambiente}", os.path.join(DAGS_FOLDER, arquivo))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.dag
    finally:
        if anterior is None:
            os.environ.pop("ATLAS_ENV", None)
        else:
            os.environ["ATLAS_ENV"] = anterior


def test_etl_brasil_agenda_por_ambiente():
    for ambiente in ("hml", "prod"):
        dag = _ler_dag("etl_brasil.py", ambiente)
        tt = dag.timetable
        assert type(tt).__name__ == "CronTriggerTimetable", (ambiente, tt)
        assert tt._expression == "0 3 * * *", tt._expression
        assert str(tt._timezone.name) == "America/Sao_Paulo", tt._timezone
    assert _sem_agenda(_ler_dag("etl_brasil.py", "dev")), "em dev a etl_brasil roda só à mão"


def test_so_a_etl_brasil_tem_agenda():
    bag = _dagbag()
    assert "process_etl_atlas" not in bag.dags, "substituída por ingestao_sinan_brasil + dbt_brasil"
    for dag_id in (
        "ingestao_sinan_brasil",
        "dbt_brasil",
        "atlas_dengue_forecast_br",
        "process_forecast_export_atlas",
        "process_dbt_docs_atlas",
    ):
        assert _sem_agenda(bag.dags[dag_id]), f"{dag_id} não pode ter agendamento próprio"


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
    assert dag.max_active_runs == 1 and dag.max_active_tasks == 2
    assert dag.dagrun_timeout is not None and dag.dagrun_timeout.total_seconds() == 12 * 3600
    # pool dos treinos: pesados ocupam as 2 vagas (um por vez), leves 1; todos com tempo máximo
    for nome in FORECAST_BASES + ["ensemble"]:
        t = dag.get_task(f"horizonte.train_{nome}")
        assert t.pool == "atlas_treino", nome
        assert t.pool_slots == (2 if nome in ("lstm", "baseline_bayes", "chronos") else 1), nome
        assert t.execution_timeout.total_seconds() == 3 * 3600, nome
    por_horizonte = {f"horizonte.train_{b}" for b in FORECAST_BASES}
    esperado = {
        "configuracao",
        "iniciar_execucao",
        "lista_de_horizontes",
        *por_horizonte,
        "horizonte.train_ensemble",
        "horizonte.comparar",
        "exportar",
        "limpar",
    }
    assert set(dag.task_ids) == esperado
    # o ensemble depende só dos modelos empilhados
    ensemble = dag.get_task("horizonte.train_ensemble")
    do_grupo = lambda t: {u for u in t.upstream_task_ids if u.startswith("horizonte.")}  # noqa: E731
    assert do_grupo(ensemble) == {f"horizonte.train_{b}" for b in FORECAST_STACKED}
    # snapshot, janela e semente, e o diretório e a versão do notebook da execução
    assert {"configuracao", "iniciar_execucao"} <= ensemble.upstream_task_ids
    comparar = dag.get_task("horizonte.comparar")
    assert do_grupo(comparar) == {
        "horizonte.train_baseline_bayes",
        "horizonte.train_chronos",
        "horizonte.train_ensemble",
    }
    assert comparar.trigger_rule == "all_done" and comparar.retries == 0
    for t in por_horizonte | {"horizonte.train_ensemble"}:
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


def test_forecast_executa_o_notebook_e_limpa_a_execucao():
    dag = _forecast()
    inicio = dag.get_task("iniciar_execucao")
    assert inicio.python == "/opt/atlas-ml/bin/python"
    def ancestrais(task_id):
        vistos, pendentes = set(), [task_id]
        while pendentes:
            for pai in dag.get_task(pendentes.pop()).upstream_task_ids:
                if pai not in vistos:
                    vistos.add(pai)
                    pendentes.append(pai)
        return vistos

    # os treinos dependem direto do início; o comparar, pelos treinos (transitivo)
    for t in ["horizonte.train_catboost", "horizonte.train_ensemble"]:
        assert "iniciar_execucao" in dag.get_task(t).upstream_task_ids, t
    assert "iniciar_execucao" in ancestrais("horizonte.comparar")
    assert "horizonte.train_ensemble" in dag.get_task("horizonte.comparar").upstream_task_ids
    # o diretório da execução some no fim, com sucesso ou falha
    limpar = dag.get_task("limpar")
    assert limpar.trigger_rule == "all_done" and limpar.retries == 0
    assert "horizonte.comparar" in limpar.upstream_task_ids
    assert limpar.python == "/opt/atlas-ml/bin/python"
    # sem snapshot; as tarefas executam o notebook do modelo; o pipeline antigo e o CLI saíram
    with open(os.path.join(DAGS_FOLDER, "atlas_dengue_forecast_br.py"), encoding="utf-8") as f:
        fonte = f.read()
    assert "run_model_notebook" in fonte and "run_step" not in fonte
    assert "forecast.pipeline" not in fonte and "atlas-ml forecast" not in fonte
    assert "prepare" not in dag.task_ids


def test_forecast_parametros_e_ambiente():
    dag = _forecast()
    assert dag.params["window"] == 12 and dag.params["seed"] == 42
    assert dag.params["horizons"] == [1, 2, 3, 4]
    assert "horizon" not in dag.params  # substituído por horizons
    # o disparo da etl_brasil com fonte "" chega como None: precisa ser aceito (gold inteira)
    fonte = dag.params.get_param("fonte")
    assert fonte.resolve(None) is None and fonte.resolve("") == ""
    # tudo roda em Python no venv do atlas_ml, sem scripts de shell
    for t in dag.tasks:
        assert type(t).__name__ != "BashOperator", t.task_id
    for t in [
        "iniciar_execucao",
        "horizonte.train_catboost",
        "horizonte.train_ensemble",
        "horizonte.comparar",
        "limpar",
    ]:
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
