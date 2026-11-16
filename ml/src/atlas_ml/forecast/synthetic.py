"""Painel sintético no mesmo formato do painel real — para testes e desenvolvimento offline."""

from __future__ import annotations

import numpy as np
import pandas as pd

from atlas_ml.forecast.dataset import PANEL_COLUMNS


def synthetic_panel(
    n_ufs: int = 3, n_weeks: int = 260, seed: int = 0, start: str = "2018-01-07"
) -> pd.DataFrame:
    """Casos semanais sazonais com epidemias esporádicas, população fixa por UF."""
    rng = np.random.default_rng(seed)
    weeks = pd.date_range(start, periods=n_weeks, freq="7D")
    frames = []
    for i in range(n_ufs):
        pop = float(rng.integers(500_000, 5_000_000))
        phase = rng.uniform(0, 2 * np.pi)
        t = np.arange(n_weeks)
        season = np.exp(1.2 * np.sin(2 * np.pi * t / 52 + phase))
        outbreak = 1 + 4 * (rng.random(n_weeks // 52 + 1)[t // 52] > 0.6)
        rate = 5 * season * outbreak  # casos por 100 mil
        cases = rng.poisson(rate * pop / 1e5)
        iso = weeks.isocalendar()
        frames.append(
            pd.DataFrame(
                {
                    "uf": f"UF{i:02d}",
                    "uf_code": i,
                    "week_start": weeks,
                    "year": iso.year.to_numpy().astype("int64"),
                    "epi_week": iso.week.to_numpy().astype("int64"),
                    "cases": cases.astype("int64"),
                    "population": pop,
                    "incidence": cases / pop * 1e5,
                    "filled": False,
                }
            )
        )
    return pd.concat(frames, ignore_index=True)[PANEL_COLUMNS]
