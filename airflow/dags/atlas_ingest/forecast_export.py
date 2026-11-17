"""Funções puras da exportação das previsões (MLflow → BigQuery), sem Airflow e sem rede.

A leitura do MLflow roda no venv do `atlas_ml` (atlas_ml.forecast.export_read) e entrega um
manifesto; aqui se monta o que vai para as tabelas do dataset `forecast`:
    forecast_model_runs · forecast_metrics · forecast_metrics_uf · forecast_predictions ·
    forecast_figures
A linha `BR` é calculada a partir das UFs (o modelo é por UF): incidência ponderada pela
população, sem intervalo, com as métricas recalculadas sobre a série agregada.
As fórmulas das métricas repetem as de atlas_ml.forecast.evaluate (NRMSE = RMSE / amplitude).
"""

from __future__ import annotations

import json
import math
from typing import Any

import numpy as np
import pandas as pd

BRASIL = "BR"
SPLITS = ("val", "test")
METRICS = ("nrmse", "mae", "rmse", "r2")
MAX_FIGURE_BYTES = 500 * 1024
PREDICTION_COLUMNS = [
    "model",
    "horizon",
    "mlflow_run_id",
    "split",
    "uf",
    "origin_date",
    "target_date",
    "y_true",
    "y_pred",
    "lower",
    "upper",
    "population",
]


def add_brazil(pred: pd.DataFrame) -> pd.DataFrame:
    """Acrescenta a UF `BR`: média das UFs ponderada pela população, em cada semana e split.

    A coluna `population` do BR é a soma. O intervalo fica nulo (intervalos por UF não se somam).
    Espera uma linha por UF, semana e split.
    """
    keys = ["split", "origin_date", "target_date"]
    g = pred.groupby(keys, sort=True)
    pop = g["population"].sum()

    def weighted(col: str) -> pd.Series:
        # semana futura não tem y_true (NaN): a soma ponderada fica NaN, não zero
        w = pred["population"].where(pred[col].notna(), 0.0)
        total = (pred[col].fillna(0.0) * w).groupby([pred[k] for k in keys]).sum()
        wsum = w.groupby([pred[k] for k in keys]).sum()
        return (total / wsum).where(wsum > 0)

    br = pd.DataFrame(
        {
            "y_true": weighted("y_true"),
            "y_pred": weighted("y_pred"),
            "lower": np.nan,
            "upper": np.nan,
            "population": pop,
        }
    ).reset_index()
    br["uf"] = BRASIL
    for col in pred.columns:
        if col not in br.columns:  # model, horizon, mlflow_run_id: iguais em toda a run
            br[col] = pred[col].iloc[0]
    return pd.concat([pred[br.columns.tolist()], br[br.columns.tolist()]], ignore_index=True)


def uf_metrics(y: np.ndarray, p: np.ndarray) -> dict[str, float]:
    """NRMSE, MAE, RMSE e R² de uma série (mesma definição de atlas_ml.forecast.evaluate)."""
    err = p - y
    rmse = float(np.sqrt(np.mean(err**2)))
    span = float(y.max() - y.min())
    denom = span if span > 0 else (float(np.mean(np.abs(y))) or 1.0)
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = float(1 - np.sum(err**2) / ss_tot) if ss_tot > 0 else float("nan")
    return {"nrmse": rmse / denom, "mae": float(np.mean(np.abs(err))), "rmse": rmse, "r2": r2}


def brazil_metrics(pred_with_br: pd.DataFrame) -> pd.DataFrame:
    """Métricas por split da série agregada `BR` (validação e teste)."""
    rows = []
    br = pred_with_br[pred_with_br["uf"] == BRASIL]
    for split in SPLITS:
        g = br[br["split"] == split].dropna(subset=["y_true", "y_pred"])
        if len(g):
            rows.append(
                {
                    "split": split,
                    "uf": BRASIL,
                    "n": len(g),
                    **uf_metrics(g["y_true"].to_numpy(float), g["y_pred"].to_numpy(float)),
                }
            )
    return pd.DataFrame(rows)


def predictions_frame(entry: dict[str, Any], pred: pd.DataFrame, future: pd.DataFrame) -> pd.DataFrame:
    """Previsões de validação, teste e futuro de uma run, com a linha `BR` e as colunas da tabela."""
    base = pred[pred["split"].isin(SPLITS)][
        ["split", "uf", "origin_date", "target_date", "y_true", "y_pred", "lower", "upper", "population"]
    ].copy()
    fut = future.copy()
    fut["split"] = "future"
    fut["y_true"] = np.nan
    fut = fut.merge(  # a população da semana prevista é a da última semana conhecida de cada UF
        base.sort_values("target_date").groupby("uf", as_index=False)["population"].last(),
        on="uf",
        how="left",
    )
    fut = fut[base.columns.tolist()]
    both = pd.concat([base, fut], ignore_index=True)
    for col in ("origin_date", "target_date"):
        both[col] = pd.to_datetime(both[col]).dt.date
    both["model"] = entry["model"]
    both["horizon"] = int(entry["horizon"])
    both["mlflow_run_id"] = entry["mlflow_run_id"]
    both = both[PREDICTION_COLUMNS]
    return add_brazil(both)[PREDICTION_COLUMNS]


def metrics_frame(entry: dict[str, Any], br: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por split (validação e teste) com as médias entre UFs registradas na run,
    mais o NRMSE do Brasil agregado em `nrmse_br` (o resumo do site usa o do Brasil)."""
    m = entry["metrics"]
    rows = []
    for split in SPLITS:
        row = {
            "model": entry["model"],
            "horizon": int(entry["horizon"]),
            "mlflow_run_id": entry["mlflow_run_id"],
            "split": split,
            "fit_seconds": m.get("fit_seconds"),
            "interval_coverage": m.get(f"{split}_interval_coverage"),
        }
        for k in METRICS:
            row[k] = m.get(f"{split}_{k}_mean")
        b = br[br["split"] == split]
        row["nrmse_br"] = float(b["nrmse"].iloc[0]) if len(b) else None
        rows.append(row)
    return pd.DataFrame(rows)


def metrics_uf_frame(entry: dict[str, Any], by_uf: pd.DataFrame, br: pd.DataFrame) -> pd.DataFrame:
    """Métricas por UF e split, com a linha `BR` recalculada sobre a série agregada."""
    cols = ["split", "uf", "n", *METRICS]
    frame = pd.concat([by_uf[cols], br[cols]], ignore_index=True)
    frame.insert(0, "model", entry["model"])
    frame.insert(1, "horizon", int(entry["horizon"]))
    frame.insert(2, "mlflow_run_id", entry["mlflow_run_id"])
    return frame


def model_runs_row(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "model": entry["model"],
        "horizon": int(entry["horizon"]),
        "family": entry["family"],
        "model_version": entry["model_version"],
        "mlflow_run_id": entry["mlflow_run_id"],
        "data_version": entry["data_version"],
        "trained_at": entry["trained_at"],
        "env": entry["env"],
        "params": json.dumps(entry["params"], ensure_ascii=False, sort_keys=True),
        "figures_failed": ",".join(entry.get("figures_failed", [])) or None,
    }


def figure_object(
    env: str, model: str, horizon: int, run_id: str, name: str, prefix: str = "forecast"
) -> str:
    """Caminho no bucket: forecast/<ambiente>/<modelo>/h<horizonte>/<run>/<arquivo>."""
    return f"{prefix}/{env}/{model}/h{horizon}/{run_id}/{name}"


def valid_figure(name: str, size: int | None) -> bool:
    """Só PNG de até 500 KB (nome sem caminho, para o nome nunca montar um caminho fora do prefixo)."""
    return (
        name.lower().endswith(".png")
        and "/" not in name
        and "\\" not in name
        and ".." not in name
        and size is not None
        and 0 < size <= MAX_FIGURE_BYTES
    )


def consistent_origins(futures: dict[str, pd.DataFrame]) -> tuple[set[str], dict[str, str]]:
    """Confere a origem das previsões futuras entre os horizontes (mesmo snapshot → mesma origem).

    `futures` mapeia "<modelo>-h<H>" ao DataFrame de futuro. Devolve (chaves mantidas, avisos).
    A origem de referência é a mais frequente; as divergentes são descartadas com aviso.
    """
    origin: dict[str, str] = {}
    for key, df in futures.items():
        values = {str(pd.Timestamp(v).date()) for v in df["origin_date"].unique()}
        origin[key] = ",".join(sorted(values))
    if not origin:
        return set(), {}
    counts = pd.Series(list(origin.values())).value_counts()
    reference = max(counts.index, key=lambda o: (counts[o], o))  # a mais frequente; empate: a mais recente
    kept = {k for k, v in origin.items() if v == reference}
    warnings = {
        k: f"origem {v} diverge da de referência {reference}; descartada"
        for k, v in origin.items()
        if k not in kept
    }
    return kept, warnings


def is_finite(value: Any) -> bool:
    return value is not None and not (isinstance(value, float) and math.isnan(value))
