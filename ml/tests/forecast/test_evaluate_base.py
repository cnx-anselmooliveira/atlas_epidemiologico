import math

import mlflow
import numpy as np
import pandas as pd
import pytest
from mlflow import MlflowClient

from atlas_ml.config import load_settings
from atlas_ml.forecast.base import METRICS_BY_UF, OOF_PREDICTIONS, PREDICTIONS, run_model
from atlas_ml.forecast.compare import compare
from atlas_ml.forecast.evaluate import interval_coverage, metrics_by_uf, summarize_metrics

from .helpers import SMALL, Persistence, dataset_run


def _artifact(run_id: str, name: str) -> pd.DataFrame:
    return pd.read_parquet(mlflow.artifacts.download_artifacts(f"runs:/{run_id}/{name}"))


def test_metricas_por_uf():
    pred = pd.DataFrame(
        {
            "split": "test",
            "uf": ["A"] * 4 + ["B"] * 4,
            "y_true": [0, 10, 20, 30, 5, 5, 5, 5],
            "y_pred": [0, 10, 20, 40, 5, 5, 5, 7],
        }
    )
    by = metrics_by_uf(pred).set_index("uf")
    assert by.loc["A", "rmse"] == pytest.approx(5.0)
    assert by.loc["A", "nrmse"] == pytest.approx(5.0 / 30)
    assert by.loc["A", "mae"] == pytest.approx(2.5)
    assert math.isnan(by.loc["B", "r2"])  # série constante
    assert by.loc["B", "nrmse"] == pytest.approx(1.0 / 5)  # cai para a média
    summary = summarize_metrics(by.reset_index())
    assert summary["test_nrmse_mean"] == pytest.approx((5 / 30 + 0.2) / 2)
    assert "test_r2_mean" in summary  # a média ignora o NaN


def test_cobertura_do_intervalo():
    pred = pd.DataFrame(
        {"split": "test", "y_true": [1, 2, 3, 4], "lower": [0, 0, 5, 0], "upper": [2, 3, 6, 5]}
    )
    assert interval_coverage(pred) == {"test_interval_coverage": 0.75}


def test_run_model_registra_metricas_artefatos_oof_e_modelo(tracking_uri, monkeypatch):
    monkeypatch.setenv("ATLAS_PIPELINE_RUN", "manual__teste")
    ds = dataset_run()
    result = run_model(Persistence, SMALL, ds, load_settings())
    run = mlflow.get_run(result.run_id)
    tags = run.data.tags
    assert tags["atlas.pipeline_run"] == "manual__teste"
    assert tags["atlas.model_family"] == "naive" and tags["atlas.dataset_run"] == ds
    assert tags["atlas.data_version"] == "synthetic@teste"
    for key in ("test_nrmse_mean", "val_nrmse_mean", "oof_nrmse_mean", "test_interval_coverage"):
        assert key in run.data.metrics, key
    assert run.data.params["window"] == str(SMALL.window)

    client = MlflowClient()
    names = {a.path for a in client.list_artifacts(result.run_id)}
    assert {PREDICTIONS, OOF_PREDICTIONS, METRICS_BY_UF} <= names
    pred = _artifact(result.run_id, PREDICTIONS)
    assert set(pred.split) == {"val", "test"} and (pred.y_pred >= 0).all()

    # OOF: cada bloco previsto só por um ajuste com alvos anteriores a ele, e tudo antes da validação
    oof = _artifact(result.run_id, OOF_PREDICTIONS)
    assert oof.fold.nunique() == SMALL.oof_folds
    assert (pd.to_datetime(oof.target_date) >= pd.to_datetime(oof.fit_until)).all()
    assert pd.to_datetime(oof.target_date).max() < pd.Timestamp(run.data.params["val_start"])

    mv = client.get_model_version_by_alias("atlas-br-persistence", "dev")
    assert str(mv.version) == result.model_version


def test_compare_lista_modelos_ausentes(tracking_uri, monkeypatch):
    monkeypatch.setenv("ATLAS_PIPELINE_RUN", "manual__cmp")
    ds = dataset_run()
    run_model(Persistence, SMALL, ds, load_settings(), register=False)
    run_id, table = compare(load_settings(), "manual__cmp")
    run = mlflow.get_run(run_id)
    assert run.data.tags["atlas.best_model"] == "persistence"
    missing = set(run.data.tags["atlas.missing_models"].split(","))
    assert {"catboost", "lstm", "ensemble"} <= missing
    assert "persistence" in table


def test_compare_sem_runs_falha(tracking_uri):
    dataset_run()
    with pytest.raises(ValueError, match="Nenhuma run"):
        compare(load_settings(), "nao-existe")


def test_previsoes_negativas_viram_zero(tracking_uri):
    class Negativo(Persistence):
        name = "negativo"
        supports_oof = False

        def predict(self, batch):
            return pd.DataFrame({"y_pred": -np.ones(len(batch))})

    result = run_model(Negativo, SMALL, dataset_run(), load_settings(), register=False)
    assert (_artifact(result.run_id, PREDICTIONS).y_pred == 0).all()
