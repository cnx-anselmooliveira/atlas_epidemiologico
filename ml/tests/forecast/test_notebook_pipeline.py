"""O notebook do pipeline de previsão executado de ponta a ponta (exige o grupo `models`).

Painel sintético e MLflow temporário, sem BigQuery: `prepare` (com `painel_parquet`), `train` de um
modelo e `compare`, como as tarefas do Airflow os chamam.
"""

from pathlib import Path

import mlflow
import nbformat
import pytest

from atlas_ml.forecast import EXPERIMENT
from atlas_ml.forecast.notebook import attach_executed_notebook, run_notebook
from atlas_ml.forecast.synthetic import synthetic_panel

pytestmark = pytest.mark.models

NOTEBOOK = Path(__file__).resolve().parents[2] / "notebooks" / "forecast_pipeline.ipynb"


def _runs() -> int:
    exp = mlflow.get_experiment_by_name(f"atlas/{EXPERIMENT}")
    return 0 if exp is None else len(mlflow.search_runs(experiment_ids=[exp.experiment_id]))


@pytest.fixture
def painel(tmp_path):
    path = tmp_path / "painel.parquet"
    synthetic_panel(n_weeks=320).to_parquet(path, index=False)
    return path


def test_notebook_executa_prepare_train_e_compare(tracking_uri, tmp_path, painel):
    out = tmp_path / "execucao"
    base = {"pipeline_run": "manual__teste", "seed": 7}

    prep = run_notebook(NOTEBOOK, {**base, "step": "prepare", "painel_parquet": str(painel)}, out, "prepare")
    ds = prep["dataset_run_id"]
    tags = mlflow.get_run(ds).data.tags
    assert tags["atlas.pipeline_run"] == "manual__teste"
    assert tags["atlas.notebook_sha"] == "local"  # sem clone do git-sync
    assert tags["atlas.model_family"] == "dataset"

    treino = run_notebook(
        NOTEBOOK,
        {**base, "step": "train", "model": "catboost", "horizon": 2, "dataset_run": ds},
        out,
        "train-catboost-h2",
    )
    run = mlflow.get_run(treino["run_id"])
    assert run.data.params["horizon"] == "2" and run.data.params["seed"] == "7"
    assert run.data.tags["atlas.notebook_sha"] == "local"
    assert run.data.tags["atlas.pipeline_run"] == "manual__teste"
    assert "test_nrmse_mean" in treino["metrics"]

    # o notebook executado vira artefato da run
    assert attach_executed_notebook(treino) == treino["run_id"]
    nomes = {a.path for a in mlflow.MlflowClient().list_artifacts(treino["run_id"], "notebook")}
    assert "notebook/train-catboost-h2.ipynb" in nomes

    comp = run_notebook(NOTEBOOK, {**base, "step": "compare", "horizon": 2}, out, "compare-h2")
    tags = mlflow.get_run(comp["run_id"]).data.tags
    assert tags["atlas.pipeline_run"] == "manual__teste" and tags["atlas.horizon"] == "2"
    assert tags["atlas.missing_models"] == "-" or "catboost" not in tags["atlas.missing_models"]


@pytest.mark.parametrize(
    ("params", "mensagem"),
    [
        ({"step": "treinar"}, "step inválido"),
        ({"step": "train", "model": "xgboost", "dataset_run": "x"}, "model inválido"),
        ({"step": "train", "model": "catboost"}, "dataset_run"),
        ({"step": "train", "model": "ensemble", "dataset_run": "x"}, "base_runs"),
    ],
)
def test_passo_ou_modelo_invalido_falha_sem_criar_run(tracking_uri, tmp_path, params, mensagem):
    antes = _runs()
    with pytest.raises(Exception, match=mensagem):
        run_notebook(NOTEBOOK, params, tmp_path / "execucao", "invalido")
    assert _runs() == antes == 0


def test_notebook_mais_novo_que_o_pacote_falha_antes_de_criar_run(tracking_uri, tmp_path):
    nb = nbformat.read(NOTEBOOK, as_version=4)
    for cell in nb.cells:
        cell.source = cell.source.replace("REQUIRES_API = 1", "REQUIRES_API = 999")
    novo = tmp_path / "futuro.ipynb"
    nbformat.write(nb, novo)
    with pytest.raises(Exception, match="atualize a imagem"):
        run_notebook(novo, {"step": "prepare"}, tmp_path / "execucao", "prepare")
    assert _runs() == 0
