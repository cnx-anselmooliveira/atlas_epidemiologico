"""Baseline bayesiano no painel sintético com poucos draws (exige o grupo `models`)."""

import mlflow
import pandas as pd
import pytest

from atlas_ml.config import load_settings
from atlas_ml.forecast.base import PREDICTIONS, run_model
from atlas_ml.models import get_factory

from .helpers import SMALL, dataset_run

pytestmark = pytest.mark.models


def test_bayes_intervalos_e_diagnosticos(tracking_uri):
    pytest.importorskip("pymc")
    ds = dataset_run()
    factory = get_factory("baseline_bayes", chains=2, tune=150, draws=150)
    res = run_model(factory, SMALL, ds, load_settings())
    run = mlflow.get_run(res.run_id)
    for key in ("rhat_max", "ess_bulk_min", "sampling_seconds", "test_nrmse_mean", "test_interval_coverage"):
        assert key in run.data.metrics, key
    assert run.data.tags["atlas.converged"] in ("true", "false")
    assert run.data.tags["atlas.model_family"] == "bayes"
    pred = pd.read_parquet(mlflow.artifacts.download_artifacts(f"runs:/{res.run_id}/{PREDICTIONS}"))
    assert (pred.lower <= pred.y_pred).all() and (pred.y_pred <= pred.upper).all()
    names = {a.path for a in mlflow.MlflowClient().list_artifacts(res.run_id)}
    assert "idata.nc" in names

    figs = {x.path.split("/")[-1] for x in mlflow.MlflowClient().list_artifacts(res.run_id, "figures")}
    assert "posterior.png" in figs and "atlas.figures_failed" not in run.data.tags
    future = pd.read_parquet(
        mlflow.artifacts.download_artifacts(f"runs:/{res.run_id}/future_predictions.parquet")
    )
    assert (future.lower <= future.upper).all() and (future.y_pred >= 0).all()

    # o pyfunc registrado prevê a partir de colunas simples
    model = mlflow.pyfunc.load_model("models:/atlas-br-baseline_bayes-h1_dev@dev")
    out = model.predict(
        pd.DataFrame(
            {"uf_code": [0, 1], "year": [2030, 2019], "epi_week": [10, 40], "lag_incidence": [5.0, 0.0]}
        )
    )
    assert len(out) == 2 and (out >= 0).all()
