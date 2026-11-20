import dataclasses
import math

import mlflow
import numpy as np
import pandas as pd
import pytest
from mlflow import MlflowClient

from atlas_ml.config import load_settings
from atlas_ml.forecast.base import (
    FUTURE_PREDICTIONS,
    METRICS_BY_UF,
    OOF_PREDICTIONS,
    PREDICTIONS,
    registered_name,
    run_model,
)
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

    mv = client.get_model_version_by_alias("atlas-br-persistence-h1_dev", "dev")
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


def test_previsao_do_futuro_por_uf_e_nome_por_horizonte(tracking_uri):
    from atlas_ml.forecast.dataset import load_snapshot
    from atlas_ml.forecast.windows import drop_immature

    ds = dataset_run()
    cfg = dataclasses.replace(SMALL, horizon=3)
    result = run_model(Persistence, cfg, ds, load_settings())
    future = _artifact(result.run_id, FUTURE_PREDICTIONS)

    panel, _ = load_snapshot(ds)
    mature = drop_immature(panel, cfg)
    last_mature = pd.Timestamp(mature.week_start.max())
    assert sorted(future.uf) == sorted(panel.uf.unique())  # uma linha por UF
    assert (pd.to_datetime(future.origin_date) == last_mature).all()  # origem = última semana madura
    assert (pd.to_datetime(future.target_date) == last_mature + pd.Timedelta(weeks=3)).all()
    assert (future.horizon == 3).all() and (future.y_pred >= 0).all()
    # a Persistence repete a última semana madura: prova que nada posterior à origem entrou
    last = mature[mature.week_start == last_mature].set_index("uf").incidence
    for row in future.itertuples():
        assert row.y_pred == pytest.approx(last[row.uf])

    by_uf = pd.read_csv(mlflow.artifacts.download_artifacts(f"runs:/{result.run_id}/{METRICS_BY_UF}"))
    assert (by_uf.horizon == 3).all()
    assert str(
        MlflowClient().get_model_version_by_alias(registered_name("persistence", 3, "dev"), "dev").version
    ) == (result.model_version)
    # os três ambientes podem dividir um MLflow: dev e hml com sufixo, prod com o nome puro
    assert registered_name("catboost", 2, "dev") == "atlas-br-catboost-h2_dev"
    assert registered_name("catboost", 2, "hml") == "atlas-br-catboost-h2_hml"
    assert registered_name("catboost", 2, "prod") == "atlas-br-catboost-h2"
    with pytest.raises(ValueError):
        registered_name("catboost", 2, "teste")


def test_horizontes_independentes_nas_metricas(tracking_uri):
    ds = dataset_run()
    runs = {
        h: run_model(Persistence, dataclasses.replace(SMALL, horizon=h), ds, load_settings(), register=False)
        for h in (1, 4)
    }
    for h, r in runs.items():
        assert mlflow.get_run(r.run_id).data.params["horizon"] == str(h)
    # persistência piora com o horizonte: erro do horizonte 4 maior que o do 1
    assert runs[4].metrics["test_nrmse_mean"] > runs[1].metrics["test_nrmse_mean"]


def test_horizonte_fora_de_1_a_4_e_recusado():
    from atlas_ml.forecast.config import ForecastConfig

    for h in (0, 5):
        with pytest.raises(ValueError, match="horizon"):
            ForecastConfig(horizon=h)


def test_compare_filtra_por_horizonte(tracking_uri, monkeypatch):
    monkeypatch.setenv("ATLAS_PIPELINE_RUN", "manual__hor")
    ds = dataset_run()
    for h in (1, 3):
        run_model(Persistence, dataclasses.replace(SMALL, horizon=h), ds, load_settings(), register=False)
    run_id, _ = compare(load_settings(), "manual__hor", horizon=3)
    run = mlflow.get_run(run_id)
    assert run.data.tags["atlas.horizon"] == "3"
    comparison = pd.read_csv(mlflow.artifacts.download_artifacts(f"runs:/{run_id}/comparison.csv"))
    persistence = comparison[comparison.model == "persistence"]
    assert len(persistence) == 1  # só o horizonte 3, sem misturar com o 1
    only3 = mlflow.get_run(persistence.run_id.iloc[0])
    assert only3.data.params["horizon"] == "3"
