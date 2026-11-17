"""LSTM no painel sintético (exige o grupo `models`)."""

import mlflow
import numpy as np
import pandas as pd
import pytest

from atlas_ml.config import load_settings
from atlas_ml.forecast.base import OOF_PREDICTIONS, PREDICTIONS, run_model
from atlas_ml.models import get_factory

from .helpers import SMALL, dataset_run

pytestmark = pytest.mark.models
FAST = {"max_epochs": 15, "patience": 4, "hidden1": 16, "hidden2": 8}


def _artifact(run_id, name):
    return pd.read_parquet(mlflow.artifacts.download_artifacts(f"runs:/{run_id}/{name}"))


def test_lstm_registra_oof_e_varia_pouco_entre_execucoes(tracking_uri):
    pytest.importorskip("torch")
    ds = dataset_run()
    factory = get_factory("lstm", **FAST)
    a = run_model(factory, SMALL, ds, load_settings())
    run = mlflow.get_run(a.run_id)
    assert "test_nrmse_mean" in run.data.metrics and "oof_nrmse_mean" in run.data.metrics
    assert run.data.params["model.lr"] == "0.001"  # lr de fato aplicado e registrado
    assert int(run.data.params["model.epochs_run"]) <= FAST["max_epochs"]
    oof = _artifact(a.run_id, OOF_PREDICTIONS)
    assert (pd.to_datetime(oof.target_date) >= pd.to_datetime(oof.fit_until)).all()

    b = run_model(factory, SMALL, ds, load_settings(), register=False)
    ma = run.data.metrics["test_nrmse_mean"]
    mb = mlflow.get_run(b.run_id).data.metrics["test_nrmse_mean"]
    assert abs(ma - mb) <= 0.02 * max(ma, 1e-9)  # variação <= 2% com a mesma semente
    pa, pb = _artifact(a.run_id, PREDICTIONS), _artifact(b.run_id, PREDICTIONS)
    assert np.allclose(pa.y_pred, pb.y_pred, rtol=0.02, atol=1e-6)

    figs = {x.path.split("/")[-1] for x in mlflow.MlflowClient().list_artifacts(a.run_id, "figures")}
    assert "learning_curve.png" in figs and "atlas.figures_failed" not in run.data.tags

    contract = mlflow.artifacts.load_dict(f"runs:/{a.run_id}/model_extra/input_contract.json")
    assert contract["window"] == SMALL.window and "mean" in contract
