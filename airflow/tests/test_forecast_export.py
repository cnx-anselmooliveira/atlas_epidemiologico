"""Funções puras da exportação das previsões (sem rede nem Airflow).

    docker run --rm --entrypoint python <imagem do Airflow> /opt/atlas/tests/test_forecast_export.py

Também compatível com pytest.
"""

import math
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.environ.get("ATLAS_DAGS_FOLDER", "/opt/airflow/dags"))

from atlas_ingest import forecast_export as fe  # noqa: E402

ENTRY = {
    "model": "catboost",
    "horizon": 2,
    "family": "gbm",
    "model_version": "7",
    "mlflow_run_id": "run123",
    "data_version": "query:abc",
    "trained_at": "2026-11-17T10:00:00+00:00",
    "env": "dev",
    "params": {"window": "12", "horizon": "2"},
    "metrics": {
        "test_nrmse_mean": 0.2,
        "test_mae_mean": 1.0,
        "test_rmse_mean": 2.0,
        "test_r2_mean": 0.5,
        "val_nrmse_mean": 0.3,
        "test_interval_coverage": 0.8,
        "fit_seconds": 12.5,
    },
    "figures_failed": [],
}


def _pred():
    rows = []
    for split, target, a, b in (("test", "2026-05-03", 10.0, 12.0), ("test", "2026-05-10", 20.0, 18.0)):
        for uf, pop, k in (("SP", 100.0, 1.0), ("MG", 300.0, 2.0)):
            rows.append(
                {
                    "split": split,
                    "uf": uf,
                    "origin_date": pd.Timestamp(target) - pd.Timedelta(weeks=2),
                    "target_date": pd.Timestamp(target),
                    "y_true": a * k,
                    "y_pred": b * k,
                    "lower": b * k - 1,
                    "upper": b * k + 1,
                    "population": pop,
                }
            )
    return pd.DataFrame(rows)


def _future():
    return pd.DataFrame(
        {
            "uf": ["SP", "MG"],
            "origin_date": pd.Timestamp("2026-05-10"),
            "target_date": pd.Timestamp("2026-05-24"),
            "horizon": 2,
            "y_pred": [5.0, 7.0],
            "lower": [4.0, np.nan],
            "upper": [6.0, np.nan],
        }
    )


def test_brasil_e_media_ponderada_pela_populacao_sem_intervalo():
    out = fe.predictions_frame(ENTRY, _pred(), _future())
    br = out[out.uf == "BR"].sort_values("target_date").reset_index(drop=True)
    sp, mg = 100.0, 300.0
    esperado = (12.0 * sp + 24.0 * mg) / (sp + mg)  # primeira semana de teste: y_pred
    assert br.loc[0, "y_pred"] == pytest_approx(esperado)
    assert br.loc[0, "y_true"] == pytest_approx((10.0 * sp + 20.0 * mg) / (sp + mg))
    assert br.loc[0, "population"] == 400.0
    assert br["lower"].isna().all() and br["upper"].isna().all()


def test_futuro_tem_split_proprio_sem_observado_e_com_brasil():
    out = fe.predictions_frame(ENTRY, _pred(), _future())
    fut = out[out.split == "future"]
    assert set(fut.uf) == {"SP", "MG", "BR"}
    assert fut["y_true"].isna().all()
    br = fut[fut.uf == "BR"].iloc[0]
    assert br["y_pred"] == pytest_approx(
        (5.0 * 100 + 7.0 * 300) / 400
    )  # população da última semana conhecida
    assert math.isnan(br["lower"])
    assert (out["model"] == "catboost").all() and (out["horizon"] == 2).all()
    assert list(out.columns) == fe.PREDICTION_COLUMNS
    assert set(out.split) == {"test", "future"}


def test_metricas_do_brasil_sobre_a_serie_agregada():
    out = fe.predictions_frame(ENTRY, _pred(), _future())
    br = fe.brazil_metrics(out)
    assert list(br.split) == ["test"] and br.loc[0, "uf"] == "BR" and br.loc[0, "n"] == 2
    serie = out[(out.uf == "BR") & (out.split == "test")].sort_values("target_date")
    esperado = fe.uf_metrics(serie.y_true.to_numpy(float), serie.y_pred.to_numpy(float))
    for k in fe.METRICS:
        assert br.loc[0, k] == pytest_approx(esperado[k])
    perfeito = fe.uf_metrics(np.array([1.0, 2.0, 4.0]), np.array([1.0, 2.0, 4.0]))
    assert perfeito["nrmse"] == 0 and perfeito["r2"] == 1


def test_metricas_por_run_e_por_uf():
    out = fe.predictions_frame(ENTRY, _pred(), _future())
    br = fe.brazil_metrics(out)
    m = fe.metrics_frame(ENTRY, br)
    test = m[m.split == "test"].iloc[0]
    assert test["nrmse"] == 0.2 and test["interval_coverage"] == 0.8 and test["fit_seconds"] == 12.5
    assert test["nrmse_br"] == pytest_approx(br.loc[0, "nrmse"])
    by_uf = pd.DataFrame(
        {
            "split": ["test", "test"],
            "uf": ["SP", "MG"],
            "n": [2, 2],
            "nrmse": [0.1, 0.2],
            "mae": [1, 2],
            "rmse": [1, 2],
            "r2": [0.5, 0.6],
        }
    )
    mu = fe.metrics_uf_frame(ENTRY, by_uf, br)
    assert set(mu.uf) == {"SP", "MG", "BR"} and (mu.horizon == 2).all() and (mu.model == "catboost").all()


def test_linha_de_run_com_parametros_em_json():
    row = fe.model_runs_row(ENTRY)
    assert row["model"] == "catboost" and row["horizon"] == 2 and row["model_version"] == "7"
    assert '"window": "12"' in row["params"] and row["figures_failed"] is None


def test_figura_so_png_pequeno_e_sem_caminho():
    assert fe.valid_figure("error_by_uf.png", 40_000)
    assert not fe.valid_figure("grande.png", fe.MAX_FIGURE_BYTES + 1)
    assert not fe.valid_figure("nota.txt", 10)
    assert not fe.valid_figure("../segredo.png", 10) and not fe.valid_figure("a/b.png", 10)
    assert not fe.valid_figure("vazio.png", 0) and not fe.valid_figure("x.png", None)
    assert (
        fe.figure_object("hml", "lstm", 3, "r1", "posterior.png") == "forecast/hml/lstm/h3/r1/posterior.png"
    )


def test_origem_divergente_entre_horizontes_e_descartada():
    def fut(origin):
        return pd.DataFrame({"origin_date": [pd.Timestamp(origin)] * 3})

    kept, warnings = fe.consistent_origins(
        {"a-h1": fut("2026-05-10"), "a-h2": fut("2026-05-10"), "a-h3": fut("2026-05-03")}
    )
    assert kept == {"a-h1", "a-h2"} and set(warnings) == {"a-h3"} and "diverge" in warnings["a-h3"]
    assert fe.consistent_origins({}) == (set(), {})


def pytest_approx(x, tol=1e-9):
    class _A:
        def __eq__(self, other):
            return abs(other - x) <= tol * max(1.0, abs(x))

    return _A()


if __name__ == "__main__":
    failures = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"ok   {name}")
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print(f"FAIL {name}: {exc!r}")
    sys.exit(1 if failures else 0)
