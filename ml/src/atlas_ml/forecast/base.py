"""Contrato dos modelos de previsão e o fluxo comum de treino/registro no MLflow.

Cada modelo (atlas_ml/models/<nome>/model.py) só implementa o que é específico dele:

    class Modelo:
        name = "catboost"; family = "gbm"; supports_oof = True
        def fit(self, train: Batch, val: Batch) -> None
        def predict(self, batch: Batch) -> pd.DataFrame   # y_pred (+ lower/upper) em incidência
        def params(self) -> dict
        def log_model(self, example: Batch) -> str        # devolve o model_uri
        def use_panel(self, panel) -> None                # opcional: histórico completo por UF

`run_model` cuida do resto: snapshot do dataset, janelas, divisão, ajuste, previsões de
validação e teste, OOF por blocos (rolling origin), métricas, artefatos e registro
como `atlas-br-<nome>-h<horizonte>` (alias @dev em dev), e a previsão das próximas semanas por UF.
"""

from __future__ import annotations

import os
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import mlflow
import numpy as np
import pandas as pd

from atlas_ml.config import Settings
from atlas_ml.forecast import EXPERIMENT
from atlas_ml.forecast.config import ForecastConfig
from atlas_ml.forecast.dataset import load_snapshot
from atlas_ml.forecast.evaluate import interval_coverage, metrics_by_uf, summarize_metrics
from atlas_ml.forecast.figures import make_figures
from atlas_ml.forecast.splits import TRAIN, VAL, oof_blocks
from atlas_ml.forecast.windows import (
    FUTURE,
    Batch,
    RawWindows,
    TrainOnlyScaler,
    assign_splits,
    build_future_windows,
    build_windows,
    drop_immature,
    make_batch,
    prepare_batches,
)
from atlas_ml.registry import register_model
from atlas_ml.tracking import atlas_run

PREDICTIONS = "predictions.parquet"
OOF_PREDICTIONS = "oof_predictions.parquet"
FUTURE_PREDICTIONS = "future_predictions.parquet"
METRICS_BY_UF = "metrics_by_uf.csv"
REGISTERED_PREFIX = "atlas-br-"
FUTURE_COLUMNS = ["uf", "origin_date", "target_date", "horizon", "y_pred", "lower", "upper"]
OOF_INNER_VAL_WEEKS = 26  # validação interna (early stopping) dentro de cada bloco OOF


class ForecastModel(Protocol):
    name: str
    family: str
    supports_oof: bool

    def fit(self, train: Batch, val: Batch) -> None: ...

    def predict(self, batch: Batch) -> pd.DataFrame: ...

    def params(self) -> dict[str, object]: ...

    def log_model(self, example: Batch) -> str: ...


ModelFactory = Callable[[ForecastConfig], ForecastModel]


@dataclass(frozen=True)
class ModelResult:
    run_id: str
    metrics: dict[str, float]
    model_version: str | None


def registered_name(model_name: str, horizon: int) -> str:
    """Um modelo registrado por horizonte: `atlas-br-<modelo>-h<H>` (cada um com seu alias de ambiente)."""
    return f"{REGISTERED_PREFIX}{model_name}-h{horizon}"


def pipeline_tags(name: str, family: str, dataset_run_id: str, horizon: int = 1) -> dict[str, str]:
    return {
        "atlas.horizon": str(horizon),
        "atlas.pipeline_run": os.environ.get("ATLAS_PIPELINE_RUN", "manual"),
        "atlas.model_family": family,
        "atlas.dataset_run": dataset_run_id,
        "atlas.forecast_model": name,
    }


def predict_frame(model: ForecastModel, batch: Batch, split: str) -> pd.DataFrame:
    """Previsões de um batch com a meta da janela; garante y_pred >= 0 e intervalos ordenados."""
    if not len(batch):
        return pd.DataFrame()
    out = model.predict(batch).reset_index(drop=True)
    df = batch.meta[["uf", "uf_code", "origin_date", "target_date", "population", "y_true"]].copy()
    df["split"] = split
    df["y_pred"] = np.clip(out["y_pred"].to_numpy(float), 0.0, None)
    for col in ("lower", "upper"):
        df[col] = np.clip(out[col].to_numpy(float), 0.0, None) if col in out else np.nan
    return df


def predict_future(
    model: ForecastModel, panel: pd.DataFrame, cfg: ForecastConfig, scaler: TrainOnlyScaler
) -> pd.DataFrame:
    """Previsão da semana origem + horizonte para cada UF, na escala de incidência.

    O painel é o mesmo do treino (já sem as semanas imaturas); a escala é a do treino.
    """
    batch = make_batch(build_future_windows(panel, cfg), scaler)
    df = predict_frame(model, batch, FUTURE)
    df["horizon"] = cfg.horizon
    return df[FUTURE_COLUMNS].reset_index(drop=True)


def oof_predictions(factory: ModelFactory, raw: RawWindows, cfg: ForecastConfig) -> pd.DataFrame:
    """Previsões out-of-fold nos blocos finais do treino (rolling origin).

    Para cada bloco, um modelo novo é ajustado só com alvos anteriores ao início do bloco
    (scaler também reajustado nesse recorte) e prevê o bloco. Nenhum alvo previsto foi
    visto no ajuste correspondente.
    """
    train_raw = raw.subset(raw.meta["split"].to_numpy() == TRAIN)
    target = train_raw.meta["target_date"]
    frames = []
    for fold, (start, end) in enumerate(oof_blocks(target, cfg)):
        fit_raw = train_raw.subset((target < start).to_numpy())
        weeks = np.sort(fit_raw.meta["target_date"].unique())
        inner = min(OOF_INNER_VAL_WEEKS, max(1, len(weeks) // 4))
        vcut = weeks[-inner]
        is_val = (fit_raw.meta["target_date"] >= vcut).to_numpy()
        scaler = TrainOnlyScaler.fit(fit_raw.subset(~is_val), len(cfg.features))
        model = factory(cfg)
        model.fit(make_batch(fit_raw.subset(~is_val), scaler), make_batch(fit_raw.subset(is_val), scaler))
        block = make_batch(train_raw.subset(((target >= start) & (target < end)).to_numpy()), scaler)
        df = predict_frame(model, block, "oof")
        df["fold"] = fold
        df["fit_until"] = start
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def _log_frame(df: pd.DataFrame, name: str, tmp: str) -> None:
    path = Path(tmp) / name
    if name.endswith(".csv"):
        df.to_csv(path, index=False)
    else:
        df.to_parquet(path, index=False)
    mlflow.log_artifact(str(path))


def run_model(
    factory: ModelFactory,
    cfg: ForecastConfig,
    dataset_run_id: str,
    settings: Settings,
    *,
    register: bool = True,
    extra: Callable[[ForecastModel, str], None] | None = None,
) -> ModelResult:
    """Treina, avalia e registra um modelo a partir do snapshot `dataset_run_id`."""
    panel, data_version = load_snapshot(dataset_run_id)
    panel = drop_immature(panel, cfg)
    raw = build_windows(panel, cfg)
    dates = assign_splits(raw, cfg)
    prep = prepare_batches(raw, cfg)
    model = factory(cfg)
    # modelos que precisam do histórico longo (ex.: Chronos) recebem o painel já sem semanas imaturas
    if hasattr(model, "use_panel"):
        model.use_panel(panel)

    with (
        atlas_run(
            settings,
            EXPERIMENT,
            data_version=data_version,
            run_name=model.name,
            extra_tags=pipeline_tags(model.name, model.family, dataset_run_id, cfg.horizon),
        ) as run,
        tempfile.TemporaryDirectory() as tmp,
    ):
        mlflow.log_params(
            {
                **cfg.as_params(),
                "val_start": str(dates.val_start.date()),
                "test_start": str(dates.test_start.date()),
                "n_train": len(prep.train),
                "n_val": len(prep.val),
                "n_test": len(prep.test),
            }
        )
        t0 = time.perf_counter()
        model.fit(prep.train, prep.val)
        fit_seconds = time.perf_counter() - t0
        # depois do ajuste: alguns valores só existem aqui (melhor iteração, épocas, busca)
        mlflow.log_params({f"model.{k}": v for k, v in model.params().items()})

        pred = pd.concat(
            [predict_frame(model, prep.val, VAL), predict_frame(model, prep.test, "test")],
            ignore_index=True,
        )
        pred["horizon"] = cfg.horizon
        by_uf = metrics_by_uf(pred)
        by_uf["horizon"] = cfg.horizon
        metrics = {**summarize_metrics(by_uf), **interval_coverage(pred), "fit_seconds": fit_seconds}

        if model.supports_oof:
            t0 = time.perf_counter()
            oof = oof_predictions(factory, raw, cfg)
            metrics["oof_seconds"] = time.perf_counter() - t0
            metrics.update(summarize_metrics(metrics_by_uf(oof)))  # oof_<métrica>_mean
            _log_frame(oof, OOF_PREDICTIONS, tmp)

        mlflow.log_metrics(metrics)
        _log_frame(pred, PREDICTIONS, tmp)
        _log_frame(by_uf, METRICS_BY_UF, tmp)
        # próximas semanas: janela terminando na última semana madura, sem alvo observado
        future = predict_future(model, panel, cfg, prep.scaler)
        _log_frame(future, FUTURE_PREDICTIONS, tmp)
        # figuras da run: uma que falhe nunca derruba o treino (vira a tag atlas.figures_failed)
        figures_dir = Path(tmp) / "figures"
        _, failed = make_figures(model, pred, by_uf, figures_dir)
        mlflow.log_artifacts(str(figures_dir), "figures")
        if failed:
            mlflow.set_tag("atlas.figures_failed", ",".join(failed))
        model_uri = model.log_model(prep.test if len(prep.test) else prep.val)
        if extra:
            extra(model, tmp)
        version = (
            register_model(settings, model_uri, registered_name(model.name, cfg.horizon))
            if register
            else None
        )

    return ModelResult(run_id=run.info.run_id, metrics=metrics, model_version=version)
