from datetime import UTC, datetime

import mlflow
import pandas as pd
import pytest

from atlas_ml.config import load_settings
from atlas_ml.forecast.dataset import EPI_TABLE, POP_TABLE, build_panel, load_snapshot, prepare


def raw_rows():
    """Duas UFs; a UF 'B' não tem linha na semana 2018-01-14 (deve ser preenchida)."""
    rows = []
    for uf, pop in (("A", 1_000_000), ("B", 200_000)):
        for d, c in (("2018-01-07", 10), ("2018-01-14", 20), ("2018-01-21", 30)):
            if uf == "B" and d == "2018-01-14":
                continue
            rows.append(
                {"uf": uf, "week_start": d, "year": 2018, "epi_week": 1, "cases": c, "population": pop}
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
    assert EPI_TABLE in version and POP_TABLE in version
    panel, v = load_snapshot(run_id)
    assert v == version and len(panel) == 6
    assert "country_iso3 = 'BRA'" in client.queries[0]
