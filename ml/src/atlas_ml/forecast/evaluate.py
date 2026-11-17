"""Métricas de previsão por UF e médias (spec forecast-models).

NRMSE = RMSE / (máx − mín) do observado da UF no período avaliado (cai para a média
quando a série é constante), como no artigo de referência. Todas as métricas são
calculadas na escala de incidência (casos por 100 mil), depois de `expm1` e corte em 0.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

METRICS = ("nrmse", "mae", "rmse", "r2")


def _uf_metrics(y: np.ndarray, p: np.ndarray) -> dict[str, float]:
    err = p - y
    rmse = float(np.sqrt(np.mean(err**2)))
    span = float(y.max() - y.min())
    denom = span if span > 0 else (float(np.mean(np.abs(y))) or 1.0)
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = float(1 - np.sum(err**2) / ss_tot) if ss_tot > 0 else float("nan")
    return {"nrmse": rmse / denom, "mae": float(np.mean(np.abs(err))), "rmse": rmse, "r2": r2}


def metrics_by_uf(pred: pd.DataFrame) -> pd.DataFrame:
    """`pred` com colunas split, uf, y_true, y_pred → uma linha por (split, uf)."""
    rows = []
    for (split, uf), g in pred.groupby(["split", "uf"], sort=True):
        rows.append(
            {
                "split": split,
                "uf": uf,
                "n": len(g),
                **_uf_metrics(g["y_true"].to_numpy(float), g["y_pred"].to_numpy(float)),
            }
        )
    return pd.DataFrame(rows)


def summarize_metrics(by_uf: pd.DataFrame) -> dict[str, float]:
    """Médias entre UFs por split: `<split>_<métrica>_mean` (ex.: test_nrmse_mean)."""
    out: dict[str, float] = {}
    for split, g in by_uf.groupby("split"):
        for m in METRICS:
            values = g[m].dropna()
            if len(values):
                out[f"{split}_{m}_mean"] = float(values.mean())
    return out


def interval_coverage(pred: pd.DataFrame) -> dict[str, float]:
    """Fração de observados dentro de [lower, upper], por split, quando há intervalo."""
    if not {"lower", "upper"} <= set(pred.columns) or pred["lower"].isna().all():
        return {}
    out = {}
    for split, g in pred.groupby("split"):
        inside = (g["y_true"] >= g["lower"]) & (g["y_true"] <= g["upper"])
        out[f"{split}_interval_coverage"] = float(inside.mean())
    return out
