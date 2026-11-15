"""Experimento de exemplo: valida a plataforma de ponta a ponta com dados sintéticos.

Simula casos semanais de dengue por região a partir de variáveis ambientais
(temperatura e chuva defasadas, umidade, altitude e sazonalidade). Não usa o
BigQuery nem representa o modelo de nicho ecológico real.
"""

from __future__ import annotations

from dataclasses import dataclass

import mlflow
import numpy as np
import pandas as pd
from mlflow.models import infer_signature
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error

from atlas_ml.config import Settings
from atlas_ml.registry import register_model
from atlas_ml.tracking import atlas_run

EXPERIMENT = "example"
MODEL_NAME = "atlas-example"
FEATURES = ["temp_lag2", "precip_lag3", "humidity", "elevation_m", "week_sin", "week_cos"]
TARGET = "cases"
VALIDATION_WEEKS = 52
# Único tipo do HistGradientBoosting fora da lista padrão do skops (interno do scikit-learn)
SKOPS_TRUSTED_TYPES = ["sklearn.ensemble._hist_gradient_boosting.predictor.TreePredictor"]


@dataclass(frozen=True)
class ExampleResult:
    run_id: str
    metrics: dict[str, float]
    model_version: str | None


def make_synthetic_data(seed: int, n_regions: int = 8, n_weeks: int = 260) -> pd.DataFrame:
    """Gera um painel região × semana determinístico para a semente dada."""
    rng = np.random.default_rng(seed)
    frames = []
    for region in range(n_regions):
        phase = rng.uniform(0, 2 * np.pi)
        elevation = float(rng.uniform(0, 2000))
        base = rng.normal(0, 0.3)
        week = np.arange(n_weeks)
        season = 2 * np.pi * week / 52
        temp = 24 + 4 * np.sin(season + phase) - elevation / 400 + rng.normal(0, 0.8, n_weeks)
        precip = np.clip(120 + 80 * np.sin(season + phase - 0.5) + rng.normal(0, 20, n_weeks), 0, None)
        humidity = np.clip(70 + 10 * np.sin(season + phase - 0.3) + rng.normal(0, 3, n_weeks), 30, 100)
        temp_lag2 = np.roll(temp, 2)
        precip_lag3 = np.roll(precip, 3)
        log_rate = 1.5 + base + 0.15 * (temp_lag2 - 24) + 0.004 * (precip_lag3 - 100) - 0.0006 * elevation
        cases = rng.poisson(np.exp(log_rate) * 10)
        frames.append(
            pd.DataFrame(
                {
                    "region": f"R{region:02d}",
                    "week": week,
                    "temp_lag2": temp_lag2,
                    "precip_lag3": precip_lag3,
                    "humidity": humidity,
                    "elevation_m": elevation,
                    "week_sin": np.sin(season),
                    "week_cos": np.cos(season),
                    TARGET: cases,
                }
            ).iloc[3:]  # descarta semanas cujas defasagens vieram do fim da série
        )
    return pd.concat(frames, ignore_index=True)


def temporal_split(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Validação = últimas semanas (nunca embaralha o tempo)."""
    cut = df["week"].max() - VALIDATION_WEEKS
    return df[df["week"] <= cut], df[df["week"] > cut]


def run_example(settings: Settings, *, seed: int = 42, register: bool = False) -> ExampleResult:
    df = make_synthetic_data(seed)
    train, valid = temporal_split(df)
    params = {
        "seed": seed,
        "n_regions": int(df["region"].nunique()),
        "n_weeks": int(df["week"].nunique()),
        "validation_weeks": VALIDATION_WEEKS,
        "loss": "poisson",
        "max_iter": 200,
        "learning_rate": 0.05,
        "max_depth": 4,
    }
    data_version = f"synthetic-seed{seed}"

    with atlas_run(settings, EXPERIMENT, data_version=data_version, run_name=f"example-seed{seed}") as run:
        mlflow.log_params(params)
        model = HistGradientBoostingRegressor(
            loss="poisson",
            max_iter=params["max_iter"],
            learning_rate=params["learning_rate"],
            max_depth=params["max_depth"],
            random_state=seed,
        )
        model.fit(train[FEATURES], train[TARGET])
        pred = model.predict(valid[FEATURES])
        metrics = {
            "val_mae": float(mean_absolute_error(valid[TARGET], pred)),
            "val_rmse": float(np.sqrt(mean_squared_error(valid[TARGET], pred))),
        }
        mlflow.log_metrics(metrics)
        mlflow.log_dict(
            {
                "data_version": data_version,
                "rows": {"train": len(train), "validation": len(valid)},
                "features": FEATURES,
                "target": TARGET,
                "period": {"weeks": [int(df["week"].min()), int(df["week"].max())]},
                "regions": sorted(df["region"].unique().tolist()),
            },
            "data_summary.json",
        )
        info = mlflow.sklearn.log_model(
            model,
            name="model",
            # skops (formato seguro, padrão do MLflow 3) exige declarar os tipos internos confiáveis
            skops_trusted_types=SKOPS_TRUSTED_TYPES,
            signature=infer_signature(valid[FEATURES], pred),
            input_example=valid[FEATURES].head(3),
        )
        version = register_model(settings, info.model_uri, MODEL_NAME) if register else None

    return ExampleResult(run_id=run.info.run_id, metrics=metrics, model_version=version)
