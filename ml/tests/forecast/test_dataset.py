from datetime import UTC, datetime

import mlflow
import pandas as pd
import pytest

from atlas_ml.config import load_settings
from atlas_ml.forecast.dataset import (
    CASES_TABLE,
    CHANNEL_COLUMNS,
    STATIC_COVARIATES,
    build_panel,
    cases_table,
    load_snapshot,
    prepare,
)


def raw_rows():
    """Duas UFs; a UF 'B' não tem linha na semana 2018-01-14 (deve ser preenchida)."""
    rows = []
    for uf, pop in (("A", 1_000_000), ("B", 200_000)):
        for d, c in (("2018-01-07", 10), ("2018-01-14", 20), ("2018-01-21", 30)):
            if uf == "B" and d == "2018-01-14":
                continue
            rows.append(
                {
                    "uf": uf,
                    "week_start": d,
                    "year": 2018,
                    "epi_week": 1,
                    "cases": c,
                    "population": pop,
                    **{canal: c + i for i, canal in enumerate(CHANNEL_COLUMNS)},
                    "mean_elevation_m": 100.0 if uf == "A" else 800.0,
                    "mean_slope_deg": 2.0,
                }
            )
    return pd.DataFrame(rows)


def test_painel_preenche_semanas_e_calcula_incidencia():
    p = build_panel(raw_rows())
    assert len(p) == 6
    assert not p.duplicated(["uf", "week_start"]).any()
    hole = p[(p.uf == "B") & (p.week_start == "2018-01-14")].iloc[0]
    assert hole.cases == 0 and bool(hole.filled)
    a = p[(p.uf == "A") & (p.week_start == "2018-01-21")].iloc[0]
    assert a.incidence == pytest.approx(30 / 1_000_000 * 1e5)
    assert p.uf_code.tolist() == [0, 0, 0, 1, 1, 1]
    # covariáveis estáticas preenchidas também na semana completada
    assert hole.mean_elevation_m == 800.0
    assert set(STATIC_COVARIATES) <= set(p.columns)


def test_painel_traz_os_canais_e_zera_a_semana_preenchida():
    p = build_panel(raw_rows())
    assert set(CHANNEL_COLUMNS) <= set(p.columns)
    hole = p[(p.uf == "B") & (p.week_start == "2018-01-14")].iloc[0]
    assert all(hole[c] == 0 for c in CHANNEL_COLUMNS)
    a = p[(p.uf == "A") & (p.week_start == "2018-01-21")].iloc[0]
    assert a.deaths == 30 + CHANNEL_COLUMNS.index("deaths")
    # nada de qualidade ou proveniência no painel
    for c in ("other_cases", "date_fallback_cases", "place_fallback_cases", "gold_generated_at"):
        assert c not in p.columns


def test_gold_sem_canal_falha_listando_o_canal():
    raw = raw_rows().drop(columns=["deaths", "severe_cases"])
    with pytest.raises(ValueError, match="severe_cases, deaths"):
        build_panel(raw)


def test_consulta_pede_os_canais():
    from atlas_ml.forecast.dataset import query_for

    sql = query_for(CASES_TABLE)
    assert all(c in sql for c in CHANNEL_COLUMNS)
    assert "other_cases" not in sql and "fallback" not in sql


def test_uf_sem_populacao_falha_listando_a_uf():
    raw = raw_rows()
    raw.loc[raw.uf == "B", "population"] = None
    with pytest.raises(ValueError, match="UFs sem população na gold: B"):
        build_panel(raw)


class FakeClient:
    def __init__(self, df):
        self.df, self.queries = df, []

    def get_table(self, table_id):
        return type("T", (), {"modified": datetime(2026, 11, 12, 22, 27, tzinfo=UTC)})()

    def query(self, sql):
        self.queries.append(sql)
        return type("J", (), {"to_dataframe": lambda _self: self.df})()


def test_prepare_registra_snapshot_e_versao(tracking_uri, monkeypatch):
    monkeypatch.setenv("ATLAS_PIPELINE_RUN", "manual__teste")
    client = FakeClient(raw_rows())
    run_id = prepare(load_settings(), client)
    run = mlflow.get_run(run_id)
    assert run.data.tags["atlas.pipeline_run"] == "manual__teste"
    assert run.data.tags["atlas.model_family"] == "dataset"
    version = run.data.tags["atlas.data_version"]
    assert CASES_TABLE in version
    panel, v = load_snapshot(run_id)
    assert v == version and len(panel) == 6
    assert "probable_cases AS cases" in client.queries[0]


def test_gold_por_ambiente():
    assert (
        cases_table("dev")
        == CASES_TABLE
        == "ppgcc-dengue-project.gold.gold_dengue_casos_provaveis_uf_semanal"
    )
    assert cases_table("hml") == "ppgcc-dengue-project.gold_hml.gold_dengue_casos_provaveis_uf_semanal"
    assert cases_table("prod") == "ppgcc-dengue-project.gold_prod.gold_dengue_casos_provaveis_uf_semanal"
    with pytest.raises(ValueError):
        cases_table("teste")


def test_prepare_em_hml_le_a_gold_de_hml(tracking_uri, monkeypatch):
    monkeypatch.setenv("ATLAS_ENV", "hml")
    client = FakeClient(raw_rows())
    run_id = prepare(load_settings(), client)
    assert "`ppgcc-dengue-project.gold_hml.gold_dengue_casos_provaveis_uf_semanal`" in client.queries[0]
    assert (
        "gold_hml.gold_dengue_casos_provaveis_uf_semanal"
        in mlflow.get_run(run_id).data.tags["atlas.data_version"]
    )
