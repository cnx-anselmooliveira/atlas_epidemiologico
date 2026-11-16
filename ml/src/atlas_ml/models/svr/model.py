"""SVR com one-hot da UF e busca aleatória com validação temporal (README.md desta pasta)."""

from __future__ import annotations

import mlflow
import numpy as np
import pandas as pd
from scipy.stats import loguniform
from sklearn.compose import ColumnTransformer
from sklearn.model_selection import RandomizedSearchCV, TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.svm import SVR

from atlas_ml.forecast.config import ForecastConfig
from atlas_ml.forecast.windows import Batch, augment

# Espaço do artigo de referência (kernel, C, gamma, epsilon)
SEARCH_SPACE = {
    "svr__kernel": ["rbf", "poly", "sigmoid"],
    "svr__C": loguniform(0.01, 10),
    "svr__gamma": ["scale", "auto"],
    "svr__epsilon": [0.01, 0.05, 0.1, 0.2],
}
# Tipos do pipeline fora da lista padrão do skops
SKOPS_TRUSTED_TYPES = ["scipy.stats._distn_infrastructure.rv_continuous_frozen"]


def _frame(batch: Batch) -> pd.DataFrame:
    return pd.DataFrame(batch.tabular(), columns=batch.tabular_names())


class SVRForecast:
    name = "svr"
    family = "kernel"
    supports_oof = True

    def __init__(
        self, cfg: ForecastConfig, n_iter: int = 10, max_train_rows: int = 8000, max_iter: int = 50_000
    ):
        self.cfg = cfg
        self.hp = {"n_iter": n_iter, "max_train_rows": max_train_rows, "max_iter": max_iter, "cv": 3}
        self.model: Pipeline | None = None
        self.best: dict[str, object] = {}

    def _pipeline(self, numeric: list[str]) -> Pipeline:
        prep = ColumnTransformer(
            [
                ("uf", OneHotEncoder(handle_unknown="ignore"), ["uf_code"]),
                ("num", StandardScaler(), numeric),
            ]
        )
        return Pipeline([("prep", prep), ("svr", SVR(cache_size=500, max_iter=self.hp["max_iter"]))])

    def fit(self, train: Batch, val: Batch) -> None:
        rng = np.random.default_rng(self.cfg.seed)
        # SVR é O(n²): usa as janelas de treino mais recentes (registrado em max_train_rows)
        order = np.argsort(train.meta["target_date"].to_numpy(), kind="stable")
        keep = order[-self.hp["max_train_rows"] :]
        sub = Batch(
            meta=train.meta.iloc[keep].reset_index(drop=True),
            hist=train.hist[keep],
            season=train.season[keep],
            features=train.features[keep],
            y=train.y[keep],
            scaler=train.scaler,
            feature_names=train.feature_names,
        )
        aug = augment(sub, self.cfg, rng)  # aumento só no treino
        X, y = _frame(aug), aug.y
        # TimeSeriesSplit precisa das linhas em ordem temporal (cópias aumentadas ficam juntas)
        t = np.argsort(aug.meta["target_date"].to_numpy(), kind="stable")
        X, y = X.iloc[t].reset_index(drop=True), y[t]
        numeric = [c for c in X.columns if c != "uf_code"]
        search = RandomizedSearchCV(
            self._pipeline(numeric),
            SEARCH_SPACE,
            n_iter=self.hp["n_iter"],
            cv=TimeSeriesSplit(n_splits=self.hp["cv"]),
            scoring="neg_root_mean_squared_error",
            random_state=self.cfg.seed,
            n_jobs=-1,
            refit=True,
        )
        search.fit(X, y)
        self.model = search.best_estimator_
        self.best = {k.replace("svr__", "best_"): v for k, v in search.best_params_.items()}
        self.best["cv_rmse"] = float(-search.best_score_)

    def predict(self, batch: Batch) -> pd.DataFrame:
        return pd.DataFrame({"y_pred": batch.to_incidence(self.model.predict(_frame(batch)))})

    def params(self) -> dict[str, object]:
        return {**self.hp, **self.best}

    def log_model(self, example: Batch) -> str:
        X = _frame(example)
        info = mlflow.sklearn.log_model(
            self.model, name="model", skops_trusted_types=SKOPS_TRUSTED_TYPES, input_example=X.head(5)
        )
        return info.model_uri


def build(cfg: ForecastConfig, **kwargs) -> SVRForecast:
    return SVRForecast(cfg, **kwargs)
