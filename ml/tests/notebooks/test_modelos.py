"""Notebooks de modelo executados de ponta a ponta (exigem o grupo `models`).

Painel sintético, MLflow em arquivo e sem BigQuery. Para cada modelo, o notebook é executado uma
vez e se confere: o contrato da run (tags `atlas.*`, métricas e os artefatos que a exportação lê), as
previsões out-of-fold dos modelos-base e, enquanto o pacote `atlas_ml` ainda tiver o código dos
modelos, a equivalência com ele (mesma configuração e semente).
"""

import importlib.util
import json
from pathlib import Path

import mlflow
import pandas as pd
import pytest

pytest.importorskip("papermill")

from atlas_ml.config import load_settings  # noqa: E402
from atlas_ml.forecast.base import run_model  # noqa: E402
from atlas_ml.forecast.config import ForecastConfig  # noqa: E402
from atlas_ml.forecast.dataset import prepare_from_parquet  # noqa: E402
from atlas_ml.forecast.notebook import run_model_notebook  # noqa: E402
from atlas_ml.forecast.synthetic import synthetic_panel  # noqa: E402
from atlas_ml.models import get_factory  # noqa: E402

pytestmark = pytest.mark.models

NOTEBOOKS = Path(__file__).resolve().parents[2] / "notebooks"
FAKE_CHRONOS = Path(__file__).resolve().parent / "fake_chronos"
EXPERIMENTO = "atlas/dengue-forecast-br"


def _pipeline_falso():
    spec = importlib.util.spec_from_file_location("chronos_falso", FAKE_CHRONOS / "chronos" / "__init__.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo.FakePipeline()


# hiperparâmetros pequenos, iguais no notebook e no pacote (a equivalência exige a mesma configuração)
MODELOS = {
    "catboost": {
        "familia": "gbm",
        "figura": "feature_importance.png",
        "oof": True,
        "tol": 1e-6,
        "rapido": {"iterations": 200, "od_wait": 30},
    },
    "svr": {
        "familia": "kernel",
        "figura": "error_by_week.png",
        "oof": True,
        "tol": 1e-6,
        "rapido": {"n_iter": 3, "max_train_rows": 1500},
    },
    "lstm": {
        "familia": "rnn",
        "figura": "learning_curve.png",
        "oof": True,
        "tol": 0.02,
        "rapido": {"max_epochs": 12, "patience": 4, "hidden1": 16, "hidden2": 8},
    },
    "baseline_bayes": {
        "familia": "bayes",
        "figura": "posterior.png",
        "oof": False,
        "tol": 0.02,
        "rapido": {"draws": 100, "tune": 100},
    },
    "chronos": {
        "familia": "foundation",
        "figura": "interval_coverage.png",
        "oof": False,
        "tol": 1e-6,
        "rapido": {},
    },
}

ARTEFATOS_DA_EXPORTACAO = {
    "predictions.parquet",
    "metrics_by_uf.csv",
    "future_predictions.parquet",
    "figures/captions.json",
    "figures/forecast_vs_observed.png",
    "figures/error_by_uf.png",
}


def notebook(modelo: str) -> Path:
    return NOTEBOOKS / modelo / f"{modelo}.ipynb"


@pytest.fixture
def painel(tmp_path) -> Path:
    caminho = tmp_path / "painel.parquet"
    synthetic_panel(n_weeks=320).to_parquet(caminho, index=False)
    return caminho


@pytest.fixture(autouse=True)
def chronos_simulado(monkeypatch):
    # o kernel do papermill herda o ambiente: o `chronos` falso vem antes do real e a rede fica desligada
    monkeypatch.setenv("PYTHONPATH", str(FAKE_CHRONOS))
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("ATLAS_NOTEBOOKS_DIR", str(NOTEBOOKS))  # como o Airflow acha os notebooks


def artefatos(run_id: str) -> set[str]:
    cliente = mlflow.MlflowClient()
    achados, pastas = set(), [""]
    while pastas:
        for a in cliente.list_artifacts(run_id, pastas.pop() or None):
            if a.is_dir:
                pastas.append(a.path)
            else:
                achados.add(a.path)
    return achados


def n_runs() -> int:
    exp = mlflow.get_experiment_by_name(EXPERIMENTO)
    return 0 if exp is None else len(mlflow.search_runs(experiment_ids=[exp.experiment_id]))


def executar(modelo: str, painel: Path, tmp_path: Path, **params):
    base = {
        "painel_parquet": str(painel),
        "pipeline_run": "manual__teste",
        "seed": 7,
        "horizon": 2,
        **MODELOS.get(modelo, {}).get("rapido", {}),
        **params,
    }
    return run_model_notebook(modelo, base, tmp_path / f"execucao-{modelo}", f"{modelo}-teste")


def textos_impressos(resultado) -> str:
    executado = json.loads(Path(resultado["_notebook"]).read_text(encoding="utf-8"))
    return "".join(
        s
        for c in executado["cells"]
        if c["cell_type"] == "code"
        for o in c.get("outputs", [])
        for s in o.get("text", [])
    )


def test_parametros_do_notebook_sao_todos_reconhecidos_pelo_papermill():
    import ast

    import nbformat
    from papermill.inspection import inspect_notebook

    pastas = [p for p in NOTEBOOKS.glob("*/") if (p / f"{p.name}.ipynb").exists() and p.name[0] != "_"]
    assert {p.name for p in pastas} >= set(MODELOS) | {"ensemble"}
    for pasta in pastas:
        modelo = pasta.name
        nb = nbformat.read(notebook(modelo), as_version=4)
        celula = next(c for c in nb.cells if "parameters" in c.metadata.get("tags", []))
        atribuidos = {
            alvo.id
            for no in ast.parse(celula.source).body
            if isinstance(no, ast.Assign)
            for alvo in no.targets
        }
        reconhecidos = set(inspect_notebook(str(notebook(modelo))))
        # um comentário com vírgula ou ponto e vírgula faz o papermill deixar o parâmetro de fora
        assert atribuidos == reconhecidos, f"{modelo}: papermill não reconhece {atribuidos - reconhecidos}"


@pytest.mark.parametrize("modelo", list(MODELOS))
def test_notebook_executa_registra_no_contrato_e_equivale_ao_pacote(modelo, tracking_uri, tmp_path, painel):
    cfg = MODELOS[modelo]
    resultado = executar(modelo, painel, tmp_path)

    # --- contrato da run no MLflow (o que a comparação, a exportação e o etl_brasil leem)
    run = mlflow.get_run(resultado["run_id"])
    tags = run.data.tags
    assert tags["atlas.forecast_model"] == modelo and tags["atlas.model_family"] == cfg["familia"]
    assert tags["atlas.horizon"] == "2" and tags["atlas.pipeline_run"] == "manual__teste"
    assert tags["atlas.notebook_sha"] == "local" and tags["atlas.env"] == "dev"
    assert tags["atlas.data_version"].startswith("parquet:")
    assert "atlas.dataset_run" not in tags and "atlas.figures_failed" not in tags
    assert run.data.params["horizon"] == "2" and run.data.params["seed"] == "7"
    assert run.data.params["features"].startswith("notified_cases,")
    for chave in ("test_nrmse_mean", "val_nrmse_mean", "fit_seconds"):
        assert chave in run.data.metrics, chave
    arquivos = artefatos(resultado["run_id"])
    assert ARTEFATOS_DA_EXPORTACAO | {f"figures/{cfg['figura']}"} <= arquivos
    assert resultado["model_version"] == "1"
    assert f"notebook/{modelo}-teste.ipynb" in arquivos  # o notebook executado é artefato da run
    basicas = {"test_nrmse_mean", "test_mae_mean", "test_rmse_mean", "test_r2_mean"}
    assert basicas <= set(resultado["metrics"]) <= basicas | {"test_interval_coverage"}
    if modelo in ("baseline_bayes", "chronos"):  # comparadores com intervalo
        assert "test_interval_coverage" in run.data.metrics
    if modelo == "baseline_bayes":
        assert {"rhat_max", "ess_bulk_min"} <= set(run.data.metrics) and "atlas.converged" in tags
        lower_upper = pd.read_parquet(
            mlflow.artifacts.download_artifacts(f"runs:/{resultado['run_id']}/predictions.parquet")
        )
        assert (lower_upper["lower"] <= lower_upper["y_pred"]).all() and (
            lower_upper["y_pred"] <= lower_upper["upper"]
        ).all()
    if modelo == "chronos":
        assert "atlas.checkpoint" in tags and run.data.params["model.revision"]
    if modelo == "lstm":
        assert "model_extra/input_contract.json" in arquivos
        assert run.data.params["model.n_inputs_per_step"] == "11"
    if modelo != "chronos":  # o pyfunc do Chronos baixaria o checkpoint
        assert mlflow.pyfunc.load_model(f"models:/atlas-br-{modelo}-h2_dev@dev") is not None

    # --- as saídas impressas de cada etapa aparecem no notebook executado
    texto = textos_impressos(resultado)
    for trecho in ("Pacotes deste notebook", "versão dos dados:", "janelas: treino=", "run_id="):
        assert trecho in texto, trecho

    # --- previsões out-of-fold só nos modelos-base do ensemble, sem alvo visto no ajuste
    assert ("oof_predictions.parquet" in arquivos) == cfg["oof"]
    if cfg["oof"]:
        oof = pd.read_parquet(
            mlflow.artifacts.download_artifacts(f"runs:/{resultado['run_id']}/oof_predictions.parquet")
        )
        assert (pd.to_datetime(oof.target_date) >= pd.to_datetime(oof.fit_until)).all()
        assert "oof_nrmse_mean" in run.data.metrics

    # --- equivalência com o pacote (mesmo painel, configuração e semente)
    kwargs = {"pipeline": _pipeline_falso()} if modelo == "chronos" else cfg["rapido"]
    ds = prepare_from_parquet(load_settings(), painel)
    pacote = run_model(
        get_factory(modelo, **kwargs), ForecastConfig(horizon=2, seed=7), ds, load_settings(), register=False
    )
    a, b = pacote.metrics["test_nrmse_mean"], run.data.metrics["test_nrmse_mean"]
    assert abs(a - b) <= cfg["tol"] * max(a, 1e-9), (modelo, a, b)


def test_lstm_reproduz_com_a_mesma_semente(tracking_uri, tmp_path, painel):
    a = executar("lstm", painel, tmp_path, register=False)
    b = executar("lstm", painel, tmp_path / "outra", register=False)
    ma = mlflow.get_run(a["run_id"]).data.metrics["test_nrmse_mean"]
    mb = mlflow.get_run(b["run_id"]).data.metrics["test_nrmse_mean"]
    assert abs(ma - mb) <= 0.02 * max(ma, 1e-9)  # variação de no máximo 2% com a mesma semente


@pytest.mark.parametrize("modelo", ["catboost", "svr", "lstm", "baseline_bayes", "chronos", "ensemble"])
def test_versao_esperada_diferente_falha_antes_de_criar_a_run(modelo, tracking_uri, tmp_path, painel):
    with pytest.raises(Exception, match="A gold mudou desde o início da execução"):
        executar(modelo, painel, tmp_path, data_version_esperada="parquet:outra-versao")
    assert n_runs() == 0


def test_ensemble_usa_so_oof_das_tres_bases_e_equivale_ao_pacote(tracking_uri, tmp_path, painel):
    bases_rapidas = {
        "catboost": {"iterations": 100, "od_wait": 20},
        "svr": {"n_iter": 2, "max_train_rows": 800},
        "lstm": {"max_epochs": 3, "patience": 2, "hidden1": 8, "hidden2": 4},
    }
    base_runs = {
        modelo: executar(modelo, painel, tmp_path, register=False, **params)["run_id"]
        for modelo, params in bases_rapidas.items()
    }
    antes = n_runs()
    assert antes == 3

    # sem uma das bases: falha antes de criar a run
    sem_lstm = {k: v for k, v in base_runs.items() if k != "lstm"}
    with pytest.raises(Exception, match="Ensemble sem as runs dos modelos-base: lstm"):
        executar("ensemble", painel, tmp_path, base_runs=sem_lstm)
    assert n_runs() == antes

    resultado = executar("ensemble", painel, tmp_path, base_runs=base_runs)
    run = mlflow.get_run(resultado["run_id"])
    assert (
        run.data.tags["atlas.model_family"] == "stacking"
        and run.data.tags["atlas.forecast_model"] == "ensemble"
    )
    assert run.data.params["model.bases"] == "catboost,svr,lstm"
    assert {f"model.base_run.{m}": r for m, r in base_runs.items()}.items() <= run.data.params.items()
    assert {"test_interval_coverage", "test_nrmse_mean"} <= set(run.data.metrics)
    assert ARTEFATOS_DA_EXPORTACAO | {"figures/feature_importance.png"} <= artefatos(resultado["run_id"])
    assert "oof_predictions.parquet" not in artefatos(resultado["run_id"])
    # nenhuma linha de treino do meta-modelo vem de previsão in-sample: só as linhas out-of-fold
    n_meta, n_train = int(run.data.params["model.n_meta_train"]), int(run.data.params["n_train"])
    assert 0 < n_meta <= 3 * 52 * 3 < n_train  # 3 blocos de 52 semanas × 3 UFs, contra o treino todo

    # equivalência com o pacote, sobre as mesmas runs-base
    ds = prepare_from_parquet(load_settings(), painel)
    pacote = run_model(
        get_factory("ensemble", base_runs=base_runs),
        ForecastConfig(horizon=2, seed=7),
        ds,
        load_settings(),
        register=False,
    )
    a, b = pacote.metrics["test_nrmse_mean"], run.data.metrics["test_nrmse_mean"]
    assert abs(a - b) <= 1e-6 * max(a, 1e-9), (a, b)
