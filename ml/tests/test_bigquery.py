from datetime import UTC, datetime

import pandas as pd
import pytest

from atlas_ml.data.bigquery import read_features

GOLD = "ppgcc-dengue-project.gold.gold_dengue_epi_curve_weekly"
DIM = "ppgcc-dengue-project.gold.gold_dim_populacao_admin1"


class FakeTable:
    def __init__(self, modified):
        self.modified = modified


class FakeJob:
    def __init__(self, df):
        self._df = df

    def to_dataframe(self):
        return self._df


class FakeClient:
    """Simula o cliente do BigQuery: metadado de tabela + execução de consulta."""

    def __init__(self, df, modified):
        self.df, self.modified, self.queries = df, modified, []

    def get_table(self, table_id):
        return FakeTable(self.modified[table_id])

    def query(self, sql):
        self.queries.append(sql)
        return FakeJob(self.df)


@pytest.fixture
def client():
    df = pd.DataFrame(
        {
            "epi_week_start_date": pd.to_datetime(["2024-01-07", "2024-03-03", "2024-02-04"]),
            "total_cases": [10, 30, 20],
        }
    )
    modified = {
        GOLD: datetime(2026, 11, 14, 6, 12, tzinfo=UTC),
        DIM: datetime(2026, 11, 10, 3, 0, tzinfo=UTC),
    }
    return FakeClient(df, modified)


def test_tabela_gold_traz_dados_e_versao_com_geracao(client):
    df, s = read_features(client, table=GOLD, date_column="epi_week_start_date")
    assert len(df) == 3 and s.rows == 3
    assert s.data_version == f"{GOLD}@2026-11-14T06:12:00+00:00"
    assert s.period == ("2024-01-07 00:00:00", "2024-03-03 00:00:00")
    assert client.queries == [f"SELECT * FROM `{GOLD}`"]


def test_consulta_registra_a_versao_de_cada_tabela_fonte(client):
    _, s = read_features(client, query="SELECT 1", source_tables=[GOLD, DIM])
    assert s.data_version.startswith("query:")
    assert f"{GOLD}@2026-11-14T06:12:00+00:00" in s.data_version
    assert f"{DIM}@2026-11-10T03:00:00+00:00" in s.data_version
    assert s.as_dict()["sources"] == s.sources


def test_identificador_de_tabela_invalido(client):
    with pytest.raises(ValueError, match="inválido"):
        read_features(client, table="gold.t; DROP TABLE x")


def test_exige_exatamente_uma_fonte(client):
    with pytest.raises(ValueError):
        read_features(client)
    with pytest.raises(ValueError):
        read_features(client, table=GOLD, query="SELECT 1")
