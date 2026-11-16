"""Ensemble com modelos-base falsos e Chronos com pipeline falso (sem download)."""

import mlflow
import numpy as np
import pandas as pd
import pytest

from atlas_ml.config import load_settings
from atlas_ml.forecast.base import PREDICTIONS, run_model
from atlas_ml.models import get_factory

from .helpers import SMALL, Persistence, dataset_run


def _artifact(run_id, name):
    return pd.read_parquet(mlflow.artifacts.download_artifacts(f"runs:/{run_id}/{name}"))


def _base(name, scale):
    class Base(Persistence):
        def predict(self, batch):
            y = batch.to_incidence(batch.hist[:, -1]) * scale
            return pd.DataFrame({"y_pred": y})

    Base.name = name
    return Base


def test_ensemble_treina_so_em_oof_e_preve_val_teste(tracking_uri):
    ds = dataset_run()
    runs = {
        n: run_model(_base(n, s), SMALL, ds, load_settings(), register=False).run_id
        for n, s in (("catboost", 1.0), ("svr", 0.9), ("lstm", 1.1))
    }
    factory = get_factory("ensemble", base_runs=runs, n_estimators=20)
    res = run_model(factory, SMALL, ds, load_settings())
    run = mlflow.get_run(res.run_id)
    assert run.data.tags["atlas.model_family"] == "stacking"
    assert int(run.data.params["model.n_meta_train"]) > 0
    for b, r in runs.items():
        assert run.data.params[f"model.base_run.{b}"] == r

    # meta-modelo só com linhas OOF: todas anteriores à validação e cobertas pelas OOF das bases
    model = factory(SMALL)
    oof_keys = set(map(tuple, model.oof["catboost"][["uf", "target_date"]].astype(str).to_numpy()))
    model.fit(*_train_val(ds))
    seen = set(map(tuple, model.train_rows.astype(str).to_numpy()))
    assert seen and seen <= oof_keys
    assert pd.to_datetime(model.train_rows.target_date).max() < pd.Timestamp(run.data.params["val_start"])

    pred = _artifact(res.run_id, PREDICTIONS)
    assert set(pred.split) == {"val", "test"}
    assert (pred.lower <= pred.upper).all()


def _train_val(ds):
    from atlas_ml.forecast.dataset import load_snapshot
    from atlas_ml.forecast.windows import assign_splits, build_windows, drop_immature, prepare_batches

    panel, _ = load_snapshot(ds)
    raw = build_windows(drop_immature(panel, SMALL), SMALL)
    assign_splits(raw, SMALL)
    prep = prepare_batches(raw, SMALL)
    return prep.train, prep.val


def test_ensemble_recusa_sem_oof(tracking_uri):
    ds = dataset_run()

    class SemOOF(Persistence):
        name = "svr"
        supports_oof = False

    runs = {
        "catboost": run_model(_base("catboost", 1.0), SMALL, ds, load_settings(), register=False).run_id,
        "svr": run_model(SemOOF, SMALL, ds, load_settings(), register=False).run_id,
        "lstm": run_model(_base("lstm", 1.0), SMALL, ds, load_settings(), register=False).run_id,
    }
    with pytest.raises(ValueError, match="oof_predictions"):
        get_factory("ensemble", base_runs=runs)(SMALL)
    with pytest.raises(ValueError, match="lstm"):
        get_factory("ensemble", base_runs={"catboost": runs["catboost"], "svr": runs["svr"]})(SMALL)


class FakeChronos:
    """predict_quantiles devolve o último valor do contexto ± 20% (formato do chronos)."""

    def __init__(self):
        self.calls = 0

    def predict_quantiles(self, inputs, prediction_length, quantile_levels):
        import torch

        self.calls += 1
        last = torch.stack([c[-1] for c in inputs])
        q = torch.stack([last * 0.8, last, last * 1.2], dim=1)  # (n, 3)
        q = q[:, None, :].repeat(1, prediction_length, 1)
        return q, q[:, :, 1]


def test_chronos_usa_contexto_longo_e_quantis(tracking_uri):
    pytest.importorskip("torch")
    pytest.importorskip("chronos")
    ds = dataset_run()
    fake = FakeChronos()
    res = run_model(get_factory("chronos", pipeline=fake, batch_size=500), SMALL, ds, load_settings())
    run = mlflow.get_run(res.run_id)
    assert run.data.params["model.checkpoint"] == "amazon/chronos-bolt-small"
    assert run.data.params["model.interval"].startswith("80%")
    assert run.data.tags["atlas.checkpoint"].endswith("@teste")
    assert fake.calls >= 1
    pred = _artifact(res.run_id, PREDICTIONS)
    # pipeline falso = persistência: y_pred é a incidência da origem, intervalo ±20%
    assert np.allclose(pred.lower, pred.y_pred * 0.8, rtol=1e-5)
    assert np.allclose(pred.upper, pred.y_pred * 1.2, rtol=1e-5)
    assert "test_interval_coverage" in run.data.metrics
