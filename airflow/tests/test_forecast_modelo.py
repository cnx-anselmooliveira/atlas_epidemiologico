"""Busca das runs de base do ensemble (DAG atlas_forecast_ensemble), com um MLflow simulado.

Roda na imagem do Airflow, sem rede nem pytest (também compatível com pytest):

    docker run --rm atlas-epidemiologia-airflow:local python /opt/atlas/tests/test_forecast_modelo.py

O corpo da tarefa `bases` roda no venv do atlas_ml em produção; aqui ele é chamado direto, com
`mlflow` e `atlas_ml.config` falsos em sys.modules.
"""

import os
import re
import sys
import types
from contextlib import contextmanager

DAGS_FOLDER = os.environ.get("ATLAS_DAGS_FOLDER", "/opt/airflow/dags")
if DAGS_FOLDER not in sys.path:
    sys.path.append(DAGS_FOLDER)


def _run(run_id, tags, params=None, start=0):
    return types.SimpleNamespace(
        info=types.SimpleNamespace(run_id=run_id, status="FINISHED", start_time=start),
        data=types.SimpleNamespace(tags=tags, params=params or {"window": "12", "seed": "42"}),
    )


class _MlflowFalso(types.ModuleType):
    """search_runs que entende o subconjunto de filtro usado pela tarefa (igualdades com and)."""

    def __init__(self, runs):
        super().__init__("mlflow")
        self.runs = runs
        self.filtros = []

    def set_tracking_uri(self, uri):
        pass

    def get_experiment_by_name(self, name):
        return types.SimpleNamespace(experiment_id="1")

    def search_runs(self, ids, filter_string, order_by=None, max_results=None, output_format=None):
        self.filtros.append(filter_string)
        condicoes = re.findall(r"(tags\.`([^`]+)`|attributes\.status) = '([^']*)'", filter_string)
        achadas = []
        for run in self.runs:
            ok = True
            for _, tag, valor in condicoes:
                atual = run.data.tags.get(tag) if tag else run.info.status
                ok = ok and atual == valor
            if ok:
                achadas.append(run)
        achadas.sort(key=lambda r: r.info.start_time, reverse=True)
        return achadas[:max_results] if max_results else achadas


@contextmanager
def _mlflow(runs):
    falso = _MlflowFalso(runs)
    config = types.ModuleType("atlas_ml.config")
    config.load_settings = lambda: types.SimpleNamespace(mlflow_tracking_uri="http://mlflow")
    pacote = types.ModuleType("atlas_ml")
    pacote.__path__ = []
    anteriores = {k: sys.modules.get(k) for k in ("mlflow", "atlas_ml", "atlas_ml.config")}
    sys.modules.update({"mlflow": falso, "atlas_ml": pacote, "atlas_ml.config": config})
    try:
        yield falso
    finally:
        for k, v in anteriores.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


def _bases():
    from atlas_ingest.forecast_modelo import bases

    return bases.function


def _tags(modelo, h, pipeline_run, dados="gold@1"):
    return {
        "atlas.forecast_model": modelo,
        "atlas.horizon": str(h),
        "atlas.pipeline_run": pipeline_run,
        "atlas.data_version": dados,
    }


def test_pelo_orquestrador_usa_o_mesmo_pipeline_run():
    runs = [_run(f"{m}-p1", _tags(m, 2, "p1"), start=1) for m in ("catboost", "svr", "lstm")]
    # mais recentes, mas de outra execução: não podem ser escolhidas
    runs += [_run(f"{m}-p2", _tags(m, 2, "p2"), start=9) for m in ("catboost", "svr", "lstm")]
    with _mlflow(runs) as mf:
        escolhidas = _bases()(2, "p1", True, "gold@1")
    assert escolhidas == {"catboost": "catboost-p1", "svr": "svr-p1", "lstm": "lstm-p1"}, escolhidas
    assert all("atlas.pipeline_run` = 'p1'" in f for f in mf.filtros)


def test_sozinho_usa_a_mais_recente_com_a_mesma_gold():
    runs = [_run(f"{m}-velha", _tags(m, 1, "a"), start=1) for m in ("catboost", "svr", "lstm")]
    runs += [_run(f"{m}-nova", _tags(m, 1, "b"), start=5) for m in ("catboost", "svr", "lstm")]
    # mais nova de todas, mas com outra versão da gold
    runs += [_run("lstm-outra-gold", _tags("lstm", 1, "c", dados="gold@2"), start=9)]
    with _mlflow(runs) as mf:
        escolhidas = _bases()(1, "run-proprio", False, "gold@1")
    assert escolhidas == {"catboost": "catboost-nova", "svr": "svr-nova", "lstm": "lstm-nova"}, escolhidas
    assert all("atlas.data_version` = 'gold@1'" in f for f in mf.filtros)
    assert not any("pipeline_run" in f for f in mf.filtros)


def test_base_ausente_falha_nomeando_o_modelo():
    runs = [_run(f"{m}-p1", _tags(m, 3, "p1")) for m in ("catboost", "svr")]  # sem LSTM
    runs.append(_run("lstm-h2", _tags("lstm", 2, "p1")))  # LSTM de outro horizonte não serve
    with _mlflow(runs):
        try:
            _bases()(3, "p1", True, "gold@1")
        except ValueError as exc:
            assert "lstm" in str(exc) and "h3" in str(exc) and "catboost" not in str(exc), exc
        else:
            raise AssertionError("o ensemble aceitou um horizonte sem o LSTM")


def test_so_runs_concluidas():
    runs = [_run(f"{m}-p1", _tags(m, 1, "p1")) for m in ("catboost", "svr", "lstm")]
    runs[2].info.status = "FAILED"
    with _mlflow(runs) as mf:
        try:
            _bases()(1, "p1", True, "gold@1")
        except ValueError as exc:
            assert "lstm" in str(exc), exc
        else:
            raise AssertionError("uma run com falha foi aceita como base")
    assert all("attributes.status = 'FINISHED'" in f for f in mf.filtros)


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
