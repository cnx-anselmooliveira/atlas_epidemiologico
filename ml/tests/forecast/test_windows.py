import dataclasses

import numpy as np
import pytest

from atlas_ml.forecast.splits import TEST, TRAIN, VAL
from atlas_ml.forecast.synthetic import synthetic_panel
from atlas_ml.forecast.windows import (
    assign_splits,
    augment,
    build_windows,
    drop_immature,
    prepare_batches,
)

from .helpers import SMALL


def _raw(panel, cfg=SMALL):
    raw = build_windows(drop_immature(panel, cfg), cfg)
    assign_splits(raw, cfg)
    return raw


def test_janelas_tem_alvo_h_semanas_depois_da_origem():
    panel = synthetic_panel(n_weeks=320)
    raw = _raw(panel)
    gap = (raw.meta["target_date"] - raw.meta["origin_date"]).dt.days
    assert (gap == 7 * SMALL.horizon).all()
    assert raw.hist.shape[1] == SMALL.window
    first = raw.meta.iloc[0]
    origin = panel[(panel.uf == first.uf) & (panel.week_start == first.origin_date)].incidence.iloc[0]
    assert raw.hist[0, -1] == pytest.approx(np.log1p(origin))


def test_semanas_imaturas_sao_descartadas():
    panel = synthetic_panel(n_weeks=320)
    kept = drop_immature(panel, SMALL)
    assert kept.week_start.nunique() == panel.week_start.nunique() - SMALL.drop_recent_weeks


def test_scaler_nao_muda_quando_validacao_e_teste_mudam():
    panel = synthetic_panel(n_weeks=320)
    raw = _raw(panel)
    a = prepare_batches(raw, SMALL).scaler
    cut = raw.meta.loc[raw.meta.split != TRAIN, "target_date"].min()
    changed = panel.copy()
    late = changed.week_start >= cut
    changed.loc[late, "incidence"] = changed.loc[late, "incidence"] * 50
    b = prepare_batches(_raw(changed), SMALL).scaler
    assert a.mean == pytest.approx(b.mean) and a.std == pytest.approx(b.std)


def test_alvos_de_treino_nunca_entram_no_periodo_de_validacao_ou_teste():
    m = _raw(synthetic_panel(n_weeks=320)).meta
    assert m.loc[m.split == TRAIN, "target_date"].max() < m.loc[m.split == VAL, "target_date"].min()
    assert m.loc[m.split == VAL, "target_date"].max() < m.loc[m.split == TEST, "target_date"].min()
    assert m.loc[m.split == TEST, "target_date"].nunique() == SMALL.test_weeks


def test_covariavel_nova_entra_nas_janelas_sem_mudar_codigo():
    panel = synthetic_panel(n_weeks=320)
    panel["temp_c"] = 25 + np.sin(np.arange(len(panel)) / 8)
    cfg = dataclasses.replace(SMALL, features=("temp_c", "mean_elevation_m"))
    prep = prepare_batches(_raw(panel, cfg), cfg)
    assert prep.train.features.shape[1] == 2 * cfg.window
    assert "temp_c_t-0" in prep.train.tabular_names()
    assert prep.train.tabular().shape[1] == cfg.window + 2 + 2 * cfg.window + 1


def test_covariavel_ausente_falha():
    cfg = dataclasses.replace(SMALL, features=("chuva_mm",))
    with pytest.raises(ValueError, match="chuva_mm"):
        build_windows(synthetic_panel(n_weeks=320), cfg)


def test_aumento_so_replica_o_batch_dado():
    prep = prepare_batches(_raw(synthetic_panel(n_weeks=320)), SMALL)
    aug = augment(prep.train, SMALL, np.random.default_rng(0))
    n = len(prep.train)
    assert len(aug) == n * (SMALL.augment + 1)
    assert np.allclose(aug.y[:n], prep.train.y)
    assert not np.allclose(aug.hist[n:], prep.train.hist)


def test_inversa_volta_para_incidencia_sem_negativos():
    prep = prepare_batches(_raw(synthetic_panel(n_weeks=320)), SMALL)
    inc = prep.test.to_incidence(prep.test.y)
    assert np.allclose(inc, prep.test.meta["y_true"], rtol=1e-6, atol=1e-9)
    assert (prep.scaler.inverse(np.array([-50.0])) == 0).all()
