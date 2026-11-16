"""Divisão temporal por data do alvo (spec forecast-dataset) e blocos out-of-fold."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from atlas_ml.forecast.config import ForecastConfig

TRAIN, VAL, TEST = "train", "val", "test"


@dataclass(frozen=True)
class SplitDates:
    """Datas de corte: alvo >= test_start → teste; val_start <= alvo < test_start → validação."""

    val_start: pd.Timestamp
    test_start: pd.Timestamp

    def assign(self, target_dates: pd.Series | pd.DatetimeIndex) -> np.ndarray:
        d = pd.to_datetime(pd.Series(target_dates)).to_numpy()
        out = np.full(len(d), TRAIN, dtype=object)
        out[d >= self.val_start.to_datetime64()] = VAL
        out[d >= self.test_start.to_datetime64()] = TEST
        return out


def split_dates(all_dates: pd.Series | pd.DatetimeIndex, cfg: ForecastConfig) -> SplitDates:
    """Calcula os cortes a partir das semanas distintas do painel (já sem semanas imaturas)."""
    weeks = pd.DatetimeIndex(pd.to_datetime(pd.Series(all_dates)).unique()).sort_values()
    needed = cfg.test_weeks + cfg.val_weeks + cfg.window + cfg.horizon
    if len(weeks) < needed:
        raise ValueError(f"Período curto demais: {len(weeks)} semanas, mínimo {needed}.")
    test_start = weeks[-cfg.test_weeks]
    val_start = weeks[-(cfg.test_weeks + cfg.val_weeks)]
    return SplitDates(val_start=val_start, test_start=test_start)


def oof_blocks(train_target_dates: pd.Series, cfg: ForecastConfig) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """Blocos finais do treino, em ordem cronológica: [(início, fim_exclusivo), ...].

    Para cada bloco, o modelo é treinado só com alvos anteriores ao início do bloco
    (rolling origin) e prevê o bloco — nenhum alvo previsto foi visto no ajuste.
    """
    weeks = pd.DatetimeIndex(pd.to_datetime(pd.Series(train_target_dates)).unique()).sort_values()
    total = cfg.oof_folds * cfg.oof_block_weeks
    if len(weeks) <= total:
        raise ValueError(
            f"Treino curto demais para {cfg.oof_folds} blocos OOF de {cfg.oof_block_weeks} semanas."
        )
    blocks = []
    for k in range(cfg.oof_folds, 0, -1):
        start = weeks[len(weeks) - k * cfg.oof_block_weeks]
        end_idx = len(weeks) - (k - 1) * cfg.oof_block_weeks
        end = weeks[end_idx] if end_idx < len(weeks) else weeks[-1] + pd.Timedelta(days=1)
        blocks.append((start, end))
    return blocks
