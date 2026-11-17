import pandas as pd
import pytest

from atlas_ml.forecast.config import ForecastConfig
from atlas_ml.forecast.splits import TEST, TRAIN, VAL, oof_blocks, split_dates

WEEKS = pd.date_range("2015-01-04", periods=520, freq="7D")
CFG = ForecastConfig()


def test_cortes_deixam_52_semanas_de_teste_e_52_de_validacao():
    s = split_dates(WEEKS, CFG)
    labels = s.assign(WEEKS)
    assert (labels == TEST).sum() == 52
    assert (labels == VAL).sum() == 52
    # nenhum alvo de treino nas 104 semanas finais
    assert pd.Series(WEEKS[labels == TRAIN]).max() < s.val_start


def test_periodo_curto_falha():
    with pytest.raises(ValueError, match="curto"):
        split_dates(WEEKS[:100], CFG)


def test_blocos_oof_sao_cronologicos_e_antes_da_validacao():
    s = split_dates(WEEKS, CFG)
    train_targets = pd.Series(WEEKS[s.assign(WEEKS) == TRAIN])
    blocks = oof_blocks(train_targets, CFG)
    assert len(blocks) == 3
    for (a0, a1), (b0, _b1) in zip(blocks, blocks[1:], strict=False):
        assert a0 < a1 <= b0
    assert blocks[-1][1] <= s.val_start + pd.Timedelta(days=1)
    for start, end in blocks:
        n = ((train_targets >= start) & (train_targets < end)).sum()
        assert n == 52


def test_config_invalida():
    with pytest.raises(ValueError):
        ForecastConfig(window=0)
