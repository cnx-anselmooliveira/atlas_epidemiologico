"""Chronos-Bolt zero-shot (README.md desta pasta).

Sem treino: para cada janela (UF, origem t), o contexto é o histórico de incidência da UF
até t (no máximo `context_weeks`), e a previsão é o passo t + horizon. Quantis 0,1 e 0,9
viram `lower`/`upper` (intervalo de 80%).
"""

from __future__ import annotations

import mlflow
import numpy as np
import pandas as pd
from mlflow.models import ModelSignature
from mlflow.types import ColSpec, Schema

from atlas_ml.forecast.config import ForecastConfig
from atlas_ml.forecast.windows import Batch

CHECKPOINT = "amazon/chronos-bolt-small"
QUANTILES = [0.1, 0.5, 0.9]


def load_pipeline(checkpoint: str, revision: str | None = None):
    import torch
    from chronos import BaseChronosPipeline

    return BaseChronosPipeline.from_pretrained(
        checkpoint, revision=revision, device_map="cpu", torch_dtype=torch.float32
    )


def resolve_revision(checkpoint: str) -> str:
    """Commit do checkpoint no Hugging Face (registrado na run); 'desconhecida' sem rede."""
    try:
        from huggingface_hub import HfApi

        return HfApi().model_info(checkpoint).sha or "desconhecida"
    except Exception:  # noqa: BLE001
        return "desconhecida"


def _quantiles(pipeline, contexts: list[np.ndarray], horizon: int, batch_size: int) -> np.ndarray:
    """(n, len(QUANTILES)) no passo `horizon` para cada contexto."""
    import torch

    out = []
    for i in range(0, len(contexts), batch_size):
        chunk = [torch.tensor(c, dtype=torch.float32) for c in contexts[i : i + batch_size]]
        q, _mean = pipeline.predict_quantiles(chunk, prediction_length=horizon, quantile_levels=QUANTILES)
        out.append(np.asarray(q[:, horizon - 1, :], dtype="float64"))
    return np.concatenate(out) if out else np.empty((0, len(QUANTILES)))


class _ChronosPyfunc(mlflow.pyfunc.PythonModel):
    """Entrada longa: colunas series_id, value (em ordem temporal). Saída: mediana em t + horizon."""

    def __init__(self, checkpoint: str, revision: str, horizon: int, context_weeks: int):
        self.checkpoint, self.revision = checkpoint, revision
        self.horizon, self.context_weeks = horizon, context_weeks

    def load_context(self, context):
        rev = None if self.revision == "desconhecida" else self.revision
        self.pipeline = load_pipeline(self.checkpoint, rev)

    def predict(self, context, model_input: pd.DataFrame, params=None):
        groups = model_input.groupby("series_id", sort=False)["value"]
        ctx = [g.to_numpy(dtype="float64")[-self.context_weeks :] for _, g in groups]
        q = _quantiles(self.pipeline, ctx, self.horizon, 64)
        return pd.DataFrame({"series_id": list(groups.groups.keys()), "y_pred": q[:, 1]})


class ChronosForecast:
    name = "chronos"
    family = "foundation"
    supports_oof = False  # comparador, fora do stacking

    def __init__(
        self,
        cfg: ForecastConfig,
        checkpoint: str = CHECKPOINT,
        context_weeks: int = 512,
        batch_size: int = 64,
        pipeline=None,
    ):
        self.cfg = cfg
        self.checkpoint = checkpoint
        self.hp = {
            "checkpoint": checkpoint,
            "context_weeks": context_weeks,
            "batch_size": batch_size,
            "quantiles": "0.1,0.5,0.9",
            "interval": "80% (q0.1-q0.9)",
            "zero_shot": True,
        }
        self._pipeline = pipeline  # injetável nos testes (sem download)
        self.revision = "teste" if pipeline is not None else None
        self.series: dict[str, pd.Series] = {}

    def use_panel(self, panel: pd.DataFrame) -> None:
        for uf, g in panel.sort_values("week_start").groupby("uf"):
            self.series[uf] = g.set_index("week_start")["incidence"].astype("float64")

    @property
    def pipeline(self):
        if self._pipeline is None:
            self.revision = resolve_revision(self.checkpoint)
            rev = None if self.revision == "desconhecida" else self.revision
            self._pipeline = load_pipeline(self.checkpoint, rev)
        return self._pipeline

    def fit(self, train: Batch, val: Batch) -> None:
        if not self.series:
            raise ValueError("Chronos precisa do painel (use_panel) para montar os contextos.")
        # carrega o pipeline (e resolve a revisão do checkpoint) antes do registro dos parâmetros
        _ = self.pipeline

    def predict(self, batch: Batch) -> pd.DataFrame:
        contexts = []
        for uf, origin in zip(batch.meta["uf"], batch.meta["origin_date"], strict=True):
            s = self.series[uf]
            contexts.append(s.loc[:origin].to_numpy()[-self.hp["context_weeks"] :])
        q = np.clip(_quantiles(self.pipeline, contexts, self.cfg.horizon, self.hp["batch_size"]), 0.0, None)
        return pd.DataFrame({"y_pred": q[:, 1], "lower": q[:, 0], "upper": q[:, 2]})

    def params(self) -> dict[str, object]:
        return {**self.hp, "revision": self.revision or "pendente"}

    def log_model(self, example: Batch) -> str:
        _ = self.pipeline  # garante a revisão resolvida
        signature = ModelSignature(
            inputs=Schema([ColSpec("string", "series_id"), ColSpec("double", "value")]),
            outputs=Schema([ColSpec("string", "series_id"), ColSpec("double", "y_pred")]),
        )
        info = mlflow.pyfunc.log_model(
            name="model",
            python_model=_ChronosPyfunc(
                self.checkpoint, self.revision or "desconhecida", self.cfg.horizon, self.hp["context_weeks"]
            ),
            signature=signature,
            pip_requirements=["chronos-forecasting", "torch"],
        )
        mlflow.set_tag("atlas.checkpoint", f"{self.checkpoint}@{self.revision}")
        return info.model_uri


def build(cfg: ForecastConfig, **kwargs) -> ChronosForecast:
    return ChronosForecast(cfg, **kwargs)
