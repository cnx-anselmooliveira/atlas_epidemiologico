"""Utilidades dos testes de previsão: snapshot sintético no MLflow e um modelo trivial."""

from __future__ import annotations

import tempfile
from pathlib import Path

import mlflow
import pandas as pd

from atlas_ml.config import load_settings
from atlas_ml.forecast import EXPERIMENT
from atlas_ml.forecast.config import ForecastConfig
from atlas_ml.forecast.dataset import PANEL_ARTIFACT
from atlas_ml.forecast.synthetic import synthetic_panel
from atlas_ml.forecast.windows import Batch
from atlas_ml.tracking import atlas_run

# Configuração pequena para o painel sintético (3 UFs × ~6 anos)
SMALL = ForecastConfig(
    window=8,
    test_weeks=26,
    val_weeks=26,
    oof_folds=2,
    oof_block_weeks=26,
    drop_recent_weeks=4,
    augment=1,
)


def dataset_run(panel: pd.DataFrame | None = None) -> str:
    """Grava um painel (sintético por padrão) como run `dataset` e devolve o run_id."""
    panel = synthetic_panel(n_weeks=320) if panel is None else panel
    with (
        atlas_run(load_settings(), EXPERIMENT, data_version="synthetic@teste", run_name="dataset") as run,
        tempfile.TemporaryDirectory() as tmp,
    ):
        path = Path(tmp) / PANEL_ARTIFACT
        panel.to_parquet(path, index=False)
        mlflow.log_artifact(str(path))
    return run.info.run_id


class _PersistencePyfunc(mlflow.pyfunc.PythonModel):
    def predict(self, context, model_input, params=None):
        return model_input.iloc[:, -1].to_numpy()


class Persistence:
    """Prevê a última semana observada (na escala de incidência)."""

    name = "persistence"
    family = "naive"
    supports_oof = True

    def __init__(self, cfg: ForecastConfig):
        self.cfg = cfg

    def fit(self, train: Batch, val: Batch) -> None:
        pass

    def predict(self, batch: Batch) -> pd.DataFrame:
        y = batch.to_incidence(batch.hist[:, -1])
        return pd.DataFrame({"y_pred": y, "lower": y * 0.5, "upper": y * 1.5})

    def params(self) -> dict[str, object]:
        return {"kind": "last_value"}

    def log_model(self, example: Batch) -> str:
        X = pd.DataFrame(example.hist, columns=[f"h{i}" for i in range(example.hist.shape[1])])
        info = mlflow.pyfunc.log_model(
            name="model", python_model=_PersistencePyfunc(), input_example=X.head(2)
        )
        return info.model_uri
