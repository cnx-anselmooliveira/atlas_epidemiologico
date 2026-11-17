"""CatBoost sobre as janelas (README.md desta pasta)."""

from __future__ import annotations

import mlflow
import pandas as pd

from atlas_ml.forecast.config import ForecastConfig
from atlas_ml.forecast.windows import Batch


def _frame(batch: Batch) -> pd.DataFrame:
    X = pd.DataFrame(batch.tabular(), columns=batch.tabular_names())
    X["uf_code"] = X["uf_code"].astype("int64")  # categórica
    return X


class CatBoostForecast:
    name = "catboost"
    family = "gbm"
    supports_oof = True

    def __init__(
        self,
        cfg: ForecastConfig,
        iterations: int = 5000,
        learning_rate: float = 0.03,
        depth: int = 6,
        od_wait: int = 300,
    ):
        self.cfg = cfg
        self.hp = {
            "iterations": iterations,
            "learning_rate": learning_rate,
            "depth": depth,
            "od_wait": od_wait,
        }
        self.model = None

    def fit(self, train: Batch, val: Batch) -> None:
        from catboost import CatBoostRegressor, Pool

        self.model = CatBoostRegressor(
            iterations=self.hp["iterations"],
            learning_rate=self.hp["learning_rate"],
            depth=self.hp["depth"],
            loss_function="RMSE",
            random_seed=self.cfg.seed,
            od_type="Iter",
            od_wait=self.hp["od_wait"],
            verbose=False,
            allow_writing_files=False,
            thread_count=-1,
        )
        train_pool = Pool(_frame(train), train.y, cat_features=["uf_code"])
        # early stopping só na validação; o teste nunca entra no ajuste
        eval_pool = Pool(_frame(val), val.y, cat_features=["uf_code"]) if len(val) else None
        self.model.fit(train_pool, eval_set=eval_pool, use_best_model=eval_pool is not None)

    def predict(self, batch: Batch) -> pd.DataFrame:
        return pd.DataFrame({"y_pred": batch.to_incidence(self.model.predict(_frame(batch)))})

    def params(self) -> dict[str, object]:
        best = self.model.get_best_iteration() if self.model is not None else None
        return {**self.hp, "loss": "RMSE", "best_iteration": best}

    def log_model(self, example: Batch) -> str:
        X = _frame(example)
        info = mlflow.catboost.log_model(self.model, name="model", input_example=X.head(5))
        return info.model_uri


def build(cfg: ForecastConfig, **kwargs) -> CatBoostForecast:
    return CatBoostForecast(cfg, **kwargs)
