"""Janelas N → H por UF e transformações ajustadas só no treino (spec forecast-dataset).

Fluxo:
    panel ─ drop_immature ─► build_windows (log1p, sem escala) ─► split por data do alvo
          ─► TrainOnlyScaler.fit(treino) ─► Batch (X padronizado, y padronizado, meta)

Cada linha é uma janela: histórico das últimas `window` semanas até a origem t e alvo na
semana t + horizon. A escala é ajustada só nas linhas de treino; validação e teste só
recebem `transform`. Assim, mudar dados de validação/teste nunca muda o ajuste.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from atlas_ml.forecast.config import ForecastConfig
from atlas_ml.forecast.splits import TEST, TRAIN, VAL, SplitDates, split_dates

META_COLUMNS = ["uf", "uf_code", "origin_date", "target_date", "population", "y_true"]


def drop_immature(panel: pd.DataFrame, cfg: ForecastConfig) -> pd.DataFrame:
    """Descarta as últimas `drop_recent_weeks` semanas (atraso de notificação)."""
    if cfg.drop_recent_weeks <= 0:
        return panel
    weeks = np.sort(panel["week_start"].unique())
    cut = weeks[-cfg.drop_recent_weeks]
    return panel[panel["week_start"] < cut].reset_index(drop=True)


@dataclass
class RawWindows:
    """Janelas sem escala: histórico e alvo em log1p(incidência)."""

    meta: pd.DataFrame  # META_COLUMNS + split
    hist: np.ndarray  # (n, window) log1p(incidência)
    target: np.ndarray  # (n,) log1p(incidência) no alvo
    season: np.ndarray  # (n, 2) sin/cos da semana do ano do alvo
    features: np.ndarray  # (n, window * len(cfg.features)) covariáveis, sem escala
    feature_names: list[str]

    def subset(self, mask: np.ndarray) -> RawWindows:
        return RawWindows(
            meta=self.meta[mask].reset_index(drop=True),
            hist=self.hist[mask],
            target=self.target[mask],
            season=self.season[mask],
            features=self.features[mask],
            feature_names=self.feature_names,
        )

    def __len__(self) -> int:
        return len(self.meta)


def build_windows(panel: pd.DataFrame, cfg: ForecastConfig) -> RawWindows:
    """Monta todas as janelas possíveis por UF (painel já sem semanas imaturas)."""
    missing = [f for f in cfg.features if f not in panel.columns]
    if missing:
        raise ValueError(f"Covariáveis ausentes no painel: {', '.join(missing)}")
    metas, hists, targets, seasons, feats = [], [], [], [], []
    w, h = cfg.window, cfg.horizon
    for _, g in panel.sort_values(["uf", "week_start"]).groupby("uf", sort=True):
        z = np.log1p(g["incidence"].to_numpy(dtype="float64"))
        dates = g["week_start"].to_numpy()
        n = len(g) - w - h + 1
        if n <= 0:
            continue
        idx = np.arange(n)[:, None] + np.arange(w)[None, :]  # (n, w)
        origin = idx[:, -1]
        tgt = origin + h
        hists.append(z[idx])
        targets.append(z[tgt])
        target_dates = pd.DatetimeIndex(dates[tgt])
        angle = 2 * np.pi * (target_dates.isocalendar().week.to_numpy(dtype="float64") - 1) / 52.0
        seasons.append(np.column_stack([np.sin(angle), np.cos(angle)]))
        if cfg.features:
            cols = [g[f].to_numpy(dtype="float64")[idx] for f in cfg.features]
            feats.append(np.concatenate(cols, axis=1))
        else:
            feats.append(np.empty((n, 0)))
        metas.append(
            pd.DataFrame(
                {
                    "uf": g["uf"].iloc[0],
                    "uf_code": int(g["uf_code"].iloc[0]),
                    "origin_date": dates[origin],
                    "target_date": dates[tgt],
                    "population": g["population"].to_numpy()[tgt],
                    "y_true": g["incidence"].to_numpy(dtype="float64")[tgt],
                }
            )
        )
    if not metas:
        raise ValueError("Nenhuma janela: séries curtas demais para window + horizon.")
    names = [f"{f}_t-{w - 1 - k}" for f in cfg.features for k in range(w)]
    return RawWindows(
        meta=pd.concat(metas, ignore_index=True),
        hist=np.concatenate(hists),
        target=np.concatenate(targets),
        season=np.concatenate(seasons),
        features=np.concatenate(feats),
        feature_names=names,
    )


def assign_splits(raw: RawWindows, cfg: ForecastConfig) -> SplitDates:
    """Marca train/val/test pela data do alvo e devolve os cortes."""
    dates = split_dates(raw.meta["target_date"], cfg)
    raw.meta["split"] = dates.assign(raw.meta["target_date"])
    return dates


@dataclass(frozen=True)
class TrainOnlyScaler:
    """Padronização ajustada só no treino: uma média/desvio para log1p(incidência)
    (histórico e alvo compartilham a escala) e uma por covariável."""

    mean: float
    std: float
    feat_mean: np.ndarray
    feat_std: np.ndarray
    n_features: int

    @classmethod
    def fit(cls, train: RawWindows, n_features: int) -> TrainOnlyScaler:
        values = np.concatenate([train.hist.ravel(), train.target])
        std = float(values.std()) or 1.0
        if train.features.shape[1]:
            f = train.features.reshape(len(train), n_features, -1)
            fm = f.mean(axis=(0, 2))
            fs = f.std(axis=(0, 2))
            fs[fs == 0] = 1.0
        else:
            fm, fs = np.zeros(0), np.ones(0)
        return cls(float(values.mean()), std, fm, fs, n_features)

    def z(self, x: np.ndarray) -> np.ndarray:
        return (x - self.mean) / self.std

    def inverse(self, z: np.ndarray) -> np.ndarray:
        """Escala padronizada → incidência (expm1), nunca negativa."""
        return np.clip(np.expm1(np.asarray(z) * self.std + self.mean), 0.0, None)

    def features(self, f: np.ndarray) -> np.ndarray:
        if not self.n_features:
            return f
        n = len(f)
        r = f.reshape(n, self.n_features, -1)
        return ((r - self.feat_mean[None, :, None]) / self.feat_std[None, :, None]).reshape(n, -1)


@dataclass
class Batch:
    """Entrada dos modelos: tudo padronizado pelo scaler do treino."""

    meta: pd.DataFrame
    hist: np.ndarray  # (n, window)
    season: np.ndarray  # (n, 2)
    features: np.ndarray  # (n, window * k)
    y: np.ndarray  # (n,) alvo padronizado
    scaler: TrainOnlyScaler
    feature_names: list[str]

    def __len__(self) -> int:
        return len(self.meta)

    def tabular(self, with_uf: bool = True) -> np.ndarray:
        """[histórico, sin, cos, covariáveis, (uf_code)] — entrada de CatBoost/SVR."""
        parts = [self.hist, self.season, self.features]
        if with_uf:
            parts.append(self.meta["uf_code"].to_numpy(dtype="float64")[:, None])
        return np.concatenate(parts, axis=1)

    def tabular_names(self, with_uf: bool = True) -> list[str]:
        w = self.hist.shape[1]
        names = [f"inc_t-{w - 1 - k}" for k in range(w)] + ["season_sin", "season_cos"]
        names += self.feature_names
        return names + (["uf_code"] if with_uf else [])

    def to_incidence(self, z: np.ndarray) -> np.ndarray:
        return self.scaler.inverse(z)


def make_batch(raw: RawWindows, scaler: TrainOnlyScaler) -> Batch:
    return Batch(
        meta=raw.meta.reset_index(drop=True),
        hist=scaler.z(raw.hist),
        season=raw.season,
        features=scaler.features(raw.features),
        y=scaler.z(raw.target),
        scaler=scaler,
        feature_names=raw.feature_names,
    )


@dataclass
class Prepared:
    """Janelas divididas e padronizadas para um ajuste (completo ou de um bloco OOF)."""

    train: Batch
    val: Batch
    test: Batch
    scaler: TrainOnlyScaler


def prepare_batches(raw: RawWindows, cfg: ForecastConfig) -> Prepared:
    """Divide pelas colunas `split` já marcadas e ajusta o scaler só no treino."""
    split = raw.meta["split"].to_numpy()
    train = raw.subset(split == TRAIN)
    scaler = TrainOnlyScaler.fit(train, len(cfg.features))
    return Prepared(
        train=make_batch(train, scaler),
        val=make_batch(raw.subset(split == VAL), scaler),
        test=make_batch(raw.subset(split == TEST), scaler),
        scaler=scaler,
    )


def augment(batch: Batch, cfg: ForecastConfig, rng: np.random.Generator) -> Batch:
    """Cópias com ruído gaussiano no histórico padronizado (só para o treino)."""
    if cfg.augment <= 0:
        return batch
    copies = [batch.hist] + [
        batch.hist + rng.normal(0.0, cfg.augment_sigma, batch.hist.shape) for _ in range(cfg.augment)
    ]
    k = cfg.augment + 1
    return Batch(
        meta=pd.concat([batch.meta] * k, ignore_index=True),
        hist=np.concatenate(copies),
        season=np.tile(batch.season, (k, 1)),
        features=np.tile(batch.features, (k, 1)),
        y=np.tile(batch.y, k),
        scaler=batch.scaler,
        feature_names=batch.feature_names,
    )
