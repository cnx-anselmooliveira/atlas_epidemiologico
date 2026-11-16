"""Baseline bayesiano: binomial negativa hierárquica em PyMC (README.md desta pasta).

    casos_t ~ NegBin(μ_t, α)
    log μ_t = log(pop/1e5) + a + u_uf + v_ano + Σ_k [b_k sin(2πk·s/52) + c_k cos(2πk·s/52)]
              + β · log1p(incidência_{t−H})

u_uf e v_ano são normais hierárquicos. Anos não vistos no treino (o do teste) recebem
v_ano da priori. Previsões e intervalos de 95% vêm da preditiva posterior, na escala de
incidência.
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

import mlflow
import numpy as np
import pandas as pd

from atlas_ml.forecast.config import ForecastConfig
from atlas_ml.forecast.windows import Batch

HARMONICS = 2


def _design(batch: Batch) -> dict[str, np.ndarray]:
    meta = batch.meta
    week = pd.DatetimeIndex(meta["target_date"]).isocalendar().week.to_numpy(dtype="float64")
    k = np.arange(1, HARMONICS + 1)
    ang = 2 * np.pi * week[:, None] * k[None, :] / 52.0
    lag = np.log1p(batch.to_incidence(batch.hist[:, -1]))  # incidência da origem (t − H)
    return {
        "uf": meta["uf_code"].to_numpy(dtype="int64"),
        "year": pd.DatetimeIndex(meta["target_date"]).year.to_numpy(),
        "fourier": np.concatenate([np.sin(ang), np.cos(ang)], axis=1),
        "lag": lag,
        "offset": np.log(meta["population"].to_numpy(dtype="float64") / 1e5),
        "pop": meta["population"].to_numpy(dtype="float64"),
        "cases": np.rint(meta["y_true"].to_numpy(dtype="float64") * meta["population"].to_numpy() / 1e5),
    }


class _PosteriorPyfunc(mlflow.pyfunc.PythonModel):
    """Previsão pela média posterior dos coeficientes (pontual), para servir sem PyMC."""

    def load_context(self, context):
        import json

        self.coef = json.loads(Path(context.artifacts["coef"]).read_text(encoding="utf-8"))

    def predict(self, context, model_input: pd.DataFrame, params=None):
        c = self.coef
        uf = model_input["uf_code"].astype(int).to_numpy()
        year = model_input["year"].astype(int).astype(str).to_numpy()
        week = model_input["epi_week"].to_numpy(dtype="float64")
        k = np.arange(1, HARMONICS + 1)
        ang = 2 * np.pi * week[:, None] * k[None, :] / 52.0
        four = np.concatenate([np.sin(ang), np.cos(ang)], axis=1)
        eta = (
            c["a"]
            + np.array(c["u_uf"])[uf]
            + np.array([c["v_year"].get(y, 0.0) for y in year])
            + four @ np.array(c["fourier"])
            + c["beta"] * np.log1p(model_input["lag_incidence"].to_numpy(dtype="float64"))
        )
        return np.exp(eta)  # incidência por 100 mil


class BayesBaseline:
    name = "baseline_bayes"
    family = "bayes"
    supports_oof = False  # comparador, fora do stacking

    def __init__(
        self,
        cfg: ForecastConfig,
        chains: int = 2,
        tune: int = 500,
        draws: int = 500,
        target_accept: float = 0.9,
        sampler: str = "nutpie",
    ):
        self.cfg = cfg
        self.hp = {
            "chains": chains,
            "tune": tune,
            "draws": draws,
            "target_accept": target_accept,
            "sampler": sampler,
            "harmonics": HARMONICS,
        }
        self.idata = None
        self.years: list[int] = []
        self.diag: dict[str, float] = {}
        self.n_ufs = 0

    def fit(self, train: Batch, val: Batch) -> None:
        import arviz as az
        import pymc as pm

        d = _design(train)
        self.n_ufs = int(max(train.meta["uf_code"].max(), val.meta["uf_code"].max() if len(val) else 0)) + 1
        self.years = sorted(set(d["year"].tolist()))
        year_idx = np.searchsorted(self.years, d["year"])
        with pm.Model():
            a = pm.Normal("a", 0.0, 2.0)
            su = pm.HalfNormal("sigma_uf", 1.0)
            u = pm.Normal("u_uf", 0.0, su, shape=self.n_ufs)
            sv = pm.HalfNormal("sigma_year", 1.0)
            v = pm.Normal("v_year", 0.0, sv, shape=len(self.years))
            f = pm.Normal("fourier", 0.0, 1.0, shape=2 * HARMONICS)
            beta = pm.Normal("beta", 0.0, 1.0)
            alpha = pm.HalfNormal("alpha", 10.0)
            log_mu = (
                d["offset"] + a + u[d["uf"]] + v[year_idx] + pm.math.dot(d["fourier"], f) + beta * d["lag"]
            )
            pm.NegativeBinomial("cases", mu=pm.math.exp(log_mu), alpha=alpha, observed=d["cases"])
            t0 = time.perf_counter()
            kwargs = {"nuts_sampler": self.hp["sampler"]} if self.hp["sampler"] != "pymc" else {}
            self.idata = pm.sample(
                draws=self.hp["draws"],
                tune=self.hp["tune"],
                chains=self.hp["chains"],
                target_accept=self.hp["target_accept"],
                random_seed=self.cfg.seed,
                progressbar=False,
                **kwargs,
            )
            self.diag["sampling_seconds"] = time.perf_counter() - t0
        summary = az.summary(self.idata, var_names=["a", "u_uf", "v_year", "fourier", "beta", "alpha"])
        self.diag["rhat_max"] = float(summary["r_hat"].max())
        self.diag["ess_bulk_min"] = float(summary["ess_bulk"].min())

    def _draws(self) -> dict[str, np.ndarray]:
        post = self.idata.posterior
        flat = {
            k: post[k].values.reshape(-1, *post[k].shape[2:])
            for k in ("a", "u_uf", "v_year", "sigma_year", "fourier", "beta", "alpha")
        }
        return flat

    def predict(self, batch: Batch) -> pd.DataFrame:
        d = _design(batch)
        p = self._draws()
        rng = np.random.default_rng(self.cfg.seed)
        n_draws = p["a"].shape[0]
        # efeito de ano: posterior para anos vistos, priori (N(0, σ_ano)) para anos novos
        v = np.empty((n_draws, len(d["year"])))
        for j, y in enumerate(d["year"]):
            if y in self.years:
                v[:, j] = p["v_year"][:, self.years.index(y)]
            else:
                v[:, j] = rng.normal(0.0, p["sigma_year"])
        eta = (
            p["a"][:, None]
            + p["u_uf"][:, d["uf"]]
            + v
            + p["fourier"] @ d["fourier"].T
            + p["beta"][:, None] * d["lag"][None, :]
        )
        rate = np.exp(eta)  # incidência por 100 mil (μ / pop × 1e5)
        mu = rate * d["pop"][None, :] / 1e5
        alpha = p["alpha"][:, None]
        # preditiva posterior da binomial negativa (gamma-poisson), em incidência
        lam = rng.gamma(alpha, mu / alpha)
        cases = rng.poisson(lam)
        inc = cases / d["pop"][None, :] * 1e5
        return pd.DataFrame(
            {
                "y_pred": np.median(inc, axis=0),
                "lower": np.percentile(inc, 2.5, axis=0),
                "upper": np.percentile(inc, 97.5, axis=0),
            }
        )

    def params(self) -> dict[str, object]:
        return {**self.hp, "interval": "95% preditiva posterior"}

    def log_model(self, example: Batch) -> str:
        import json

        p = self._draws()
        coef = {
            "a": float(p["a"].mean()),
            "u_uf": p["u_uf"].mean(axis=0).tolist(),
            "v_year": {str(y): float(p["v_year"][:, i].mean()) for i, y in enumerate(self.years)},
            "fourier": p["fourier"].mean(axis=0).tolist(),
            "beta": float(p["beta"].mean()),
            "alpha": float(p["alpha"].mean()),
        }
        mlflow.log_metrics({k: v for k, v in self.diag.items()})
        converged = self.diag.get("rhat_max", 9) <= 1.05 and self.diag.get("ess_bulk_min", 0) >= 100
        mlflow.set_tag("atlas.converged", str(converged).lower())
        with tempfile.TemporaryDirectory() as tmp:
            nc = Path(tmp) / "idata.nc"
            self.idata.to_netcdf(str(nc))
            mlflow.log_artifact(str(nc))
            coef_path = Path(tmp) / "coef.json"
            coef_path.write_text(json.dumps(coef), encoding="utf-8")
            example_df = pd.DataFrame(
                {
                    "uf_code": example.meta["uf_code"].head(3).to_numpy(dtype="int64"),
                    "year": pd.DatetimeIndex(example.meta["target_date"].head(3)).year.to_numpy(
                        dtype="int64"
                    ),
                    "epi_week": pd.DatetimeIndex(example.meta["target_date"].head(3))
                    .isocalendar()
                    .week.to_numpy(dtype="int64"),
                    "lag_incidence": example.to_incidence(example.hist[:3, -1]),
                }
            )
            info = mlflow.pyfunc.log_model(
                name="model",
                python_model=_PosteriorPyfunc(),
                artifacts={"coef": str(coef_path)},
                input_example=example_df,
            )
        return info.model_uri


def build(cfg: ForecastConfig, **kwargs) -> BayesBaseline:
    return BayesBaseline(cfg, **kwargs)
