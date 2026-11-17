"""Ensemble por stacking sobre previsões out-of-fold (README.md desta pasta).

Meta-features por janela:
    - previsões dos modelos-base (CatBoost, SVR, LSTM): OOF no treino; modelo final em val/teste;
    - extrapolações polinomiais (graus 0, 1 e 2) da janela de incidência até t + horizon.
O meta-modelo (RandomForest) só vê linhas OOF — nunca previsões in-sample dos modelos-base.
Intervalo de 95%: percentis 2,5 e 97,5 entre as árvores.
"""

from __future__ import annotations

import mlflow
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor

from atlas_ml.forecast.base import OOF_PREDICTIONS, PREDICTIONS
from atlas_ml.forecast.config import ForecastConfig
from atlas_ml.forecast.windows import Batch

KEY = ["uf", "target_date"]
DEGREES = (0, 1, 2)


def _download(run_id: str, name: str) -> pd.DataFrame:
    try:
        path = mlflow.artifacts.download_artifacts(f"runs:/{run_id}/{name}")
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"A run {run_id} não tem {name}: {exc}") from exc
    df = pd.read_parquet(path)
    df["target_date"] = pd.to_datetime(df["target_date"])
    return df


def extrapolations(batch: Batch, horizon: int) -> np.ndarray:
    """Ajuste polinomial (graus 0-2) da janela em incidência, avaliado em t + horizon."""
    y = batch.to_incidence(batch.hist)  # (n, w)
    w = y.shape[1]
    x = np.arange(w, dtype="float64")
    target_x = w - 1 + horizon
    cols = []
    for deg in DEGREES:
        coef = np.polynomial.polynomial.polyfit(x, y.T, deg)  # (deg+1, n)
        cols.append(np.polynomial.polynomial.polyval(target_x, coef))
    return np.clip(np.column_stack(cols), 0.0, None)


class StackingEnsemble:
    name = "ensemble"
    family = "stacking"
    supports_oof = False

    def __init__(
        self,
        cfg: ForecastConfig,
        base_runs: dict[str, str] | None = None,
        bases: tuple[str, ...] = ("catboost", "svr", "lstm"),
        n_estimators: int = 300,
        max_depth: int = 8,
    ):
        self.cfg = cfg
        self.bases = bases
        self.base_runs = dict(base_runs or {})
        missing = [b for b in bases if b not in self.base_runs]
        if missing:
            raise ValueError(f"Ensemble sem as runs dos modelos-base: {', '.join(missing)}")
        self.hp = {
            "n_estimators": n_estimators,
            "max_depth": max_depth,
            "bases": ",".join(bases),
            "degrees": ",".join(map(str, DEGREES)),
            "interval": "95% (percentis entre árvores)",
        }
        # recusa treinar se faltar alguma OOF (falha já na construção)
        self.oof = {b: _download(self.base_runs[b], OOF_PREDICTIONS) for b in bases}
        self.pred = {b: _download(self.base_runs[b], PREDICTIONS) for b in bases}
        self.model: RandomForestRegressor | None = None
        self.train_rows: pd.DataFrame | None = None

    def _meta(self, batch: Batch, source: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, np.ndarray]:
        """Meta-features das linhas do batch que têm previsão de todos os modelos-base."""
        keys = batch.meta[KEY].copy()
        keys["target_date"] = pd.to_datetime(keys["target_date"])
        keys["_row"] = np.arange(len(keys))
        X = keys
        for b in self.bases:
            p = (
                source[b][[*KEY, "y_pred"]]
                .drop_duplicates(KEY, keep="last")
                .rename(columns={"y_pred": f"p_{b}"})
            )
            X = X.merge(p, on=KEY, how="inner")
        rows = X["_row"].to_numpy()
        ext = extrapolations(batch, self.cfg.horizon)[rows]
        for i, deg in enumerate(DEGREES):
            X[f"poly{deg}"] = ext[:, i]
        return X.drop(columns="_row"), rows

    def _features(self, X: pd.DataFrame) -> np.ndarray:
        cols = [f"p_{b}" for b in self.bases] + [f"poly{d}" for d in DEGREES]
        return X[cols].to_numpy(dtype="float64")

    def fit(self, train: Batch, val: Batch) -> None:
        X, rows = self._meta(train, self.oof)
        if X.empty:
            raise ValueError("Nenhuma janela de treino com previsão OOF de todos os modelos-base.")
        y = train.meta["y_true"].to_numpy(dtype="float64")[rows]
        self.model = RandomForestRegressor(
            n_estimators=self.hp["n_estimators"],
            max_depth=self.hp["max_depth"],
            random_state=self.cfg.seed,
            n_jobs=-1,
        )
        self.model.fit(self._features(X), y)
        self.train_rows = X[KEY]

    def predict(self, batch: Batch) -> pd.DataFrame:
        X, rows = self._meta(batch, self.pred)
        if len(rows) != len(batch):
            raise ValueError(f"{len(batch) - len(rows)} janelas sem previsão de algum modelo-base.")
        F = self._features(X)
        per_tree = np.stack([t.predict(F) for t in self.model.estimators_])  # (árvores, n)
        out = pd.DataFrame(
            {
                "y_pred": per_tree.mean(axis=0),
                "lower": np.percentile(per_tree, 2.5, axis=0),
                "upper": np.percentile(per_tree, 97.5, axis=0),
            },
            index=rows,
        )
        return out.sort_index().reset_index(drop=True)

    def params(self) -> dict[str, object]:
        return {
            **self.hp,
            **{f"base_run.{b}": r for b, r in self.base_runs.items()},
            "n_meta_train": 0 if self.train_rows is None else len(self.train_rows),
        }

    def log_model(self, example: Batch) -> str:
        cols = [f"p_{b}" for b in self.bases] + [f"poly{d}" for d in DEGREES]
        X, _ = self._meta(example, self.pred)
        info = mlflow.sklearn.log_model(
            self.model,
            name="model",
            # armazenamento de nós das árvores; o arquivo é gerado por esta própria run
            skops_trusted_types=["sklearn.tree._tree.Tree"],
            input_example=pd.DataFrame(self._features(X)[:5], columns=cols),
        )
        return info.model_uri


def build(cfg: ForecastConfig, **kwargs) -> StackingEnsemble:
    return StackingEnsemble(cfg, **kwargs)
