"""CatBoost e SVR no painel sintético (exigem o grupo `models`)."""

import mlflow
import numpy as np
import pandas as pd
import pytest

from atlas_ml.config import load_settings
from atlas_ml.forecast.base import OOF_PREDICTIONS, PREDICTIONS, run_model
from atlas_ml.models import get_factory

from .helpers import SMALL, dataset_run

pytestmark = pytest.mark.models

FAST = {
    "catboost": {"iterations": 200, "od_wait": 30},
    "svr": {"n_iter": 3, "max_train_rows": 1500},
}


def _artifact(run_id, name):
    return pd.read_parquet(mlflow.artifacts.download_artifacts(f"runs:/{run_id}/{name}"))


@pytest.mark.parametrize("name", ["catboost", "svr"])
def test_modelo_registra_metricas_oof_e_e_reprodutivel(name, tracking_uri):
    pytest.importorskip("catboost" if name == "catboost" else "sklearn")
    ds = dataset_run()
    factory = get_factory(name, **FAST[name])
    a = run_model(factory, SMALL, ds, load_settings())
    run = mlflow.get_run(a.run_id)
    for key in ("test_nrmse_mean", "val_nrmse_mean", "oof_nrmse_mean"):
        assert key in run.data.metrics, key
    assert run.data.tags["atlas.model_family"] in ("gbm", "kernel")
    # entrada multivariada: janela × (incidência + 10 canais) + sazonalidade (2) + UF (1)
    assert run.data.params["model.n_input_columns"] == str(SMALL.window * (1 + len(SMALL.features)) + 2 + 1)
    assert "deaths" in run.data.params["model.channels"]
    oof = _artifact(a.run_id, OOF_PREDICTIONS)
    # nenhum alvo OOF previsto por um ajuste que já o tinha visto
    assert (pd.to_datetime(oof.target_date) >= pd.to_datetime(oof.fit_until)).all()

    # mesma semente → mesmas previsões
    b = run_model(factory, SMALL, ds, load_settings(), register=False)
    pa, pb = _artifact(a.run_id, PREDICTIONS), _artifact(b.run_id, PREDICTIONS)
    assert np.allclose(pa.y_pred, pb.y_pred, rtol=1e-6)

    # figuras: as duas comuns e a da família (importância no CatBoost, erro por semana no SVR)
    figs = {a.path.split("/")[-1] for a in mlflow.MlflowClient().list_artifacts(a.run_id, "figures")}
    family = "feature_importance.png" if name == "catboost" else "error_by_week.png"
    assert {"forecast_vs_observed.png", "error_by_uf.png", family} <= figs
    assert "atlas.figures_failed" not in run.data.tags
    # previsão do futuro das 3 UFs sintéticas
    assert (
        len(_artifact(a.run_id, "future_predictions.parquet"))
        == pd.read_parquet(
            mlflow.artifacts.download_artifacts(f"runs:/{a.run_id}/predictions.parquet")
        ).uf.nunique()
    )

    # o modelo registrado carrega e prevê
    model = mlflow.pyfunc.load_model(f"models:/atlas-br-{name}-h1_dev@dev")
    assert model is not None
