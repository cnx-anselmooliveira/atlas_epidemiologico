"""Leitura de features do BigQuery com resumo e versão dos dados (spec ml-training-pipeline).

A versão usa a última modificação da tabela (metadado `tables.get`, sem custo de
consulta), que muda a cada reconstrução do dbt — equivalente à geração da gold.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import pandas as pd

if TYPE_CHECKING:
    from google.cloud import bigquery

    from atlas_ml.config import Settings

# projeto.dataset.tabela (ou dataset.tabela) — impede SQL arbitrário no modo "table"
_TABLE_ID = re.compile(r"^(?:[A-Za-z0-9_-]+\.)?[A-Za-z0-9_]+\.[A-Za-z0-9_]+$")


@dataclass(frozen=True)
class DataSummary:
    rows: int
    columns: list[str]
    data_version: str
    period: tuple[str, str] | None = None
    sources: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "rows": self.rows,
            "columns": self.columns,
            "data_version": self.data_version,
            "period": list(self.period) if self.period else None,
            "sources": self.sources,
        }


def bigquery_client(settings: Settings) -> bigquery.Client:
    from google.cloud import bigquery

    return bigquery.Client(project=settings.gcp_project)


def table_version(client: Any, table: str) -> str:
    """`<tabela>@<última modificação ISO>`."""
    t = client.get_table(table)
    return f"{table}@{t.modified.isoformat()}"


def read_features(
    client: Any,
    *,
    table: str | None = None,
    query: str | None = None,
    source_tables: list[str] | None = None,
    date_column: str | None = None,
) -> tuple[pd.DataFrame, DataSummary]:
    """Lê uma tabela inteira (`table`) ou o resultado de uma consulta (`query`).

    Em `query`, informe em `source_tables` as tabelas lidas, para que a versão dos
    dados registre a geração de cada uma.
    """
    if (table is None) == (query is None):
        raise ValueError("Informe exatamente um entre 'table' e 'query'.")

    if table is not None:
        if not _TABLE_ID.match(table):
            raise ValueError(f"Identificador de tabela inválido: {table!r}")
        sources = {table: table_version(client, table)}
        sql = f"SELECT * FROM `{table}`"
        data_version = sources[table]
    else:
        sources = {t: table_version(client, t) for t in (source_tables or [])}
        digest = hashlib.sha1(query.encode()).hexdigest()[:12]
        data_version = "+".join([f"query:{digest}", *sources.values()])
        sql = query

    df = client.query(sql).to_dataframe()
    period = None
    if date_column and date_column in df.columns and len(df):
        period = (str(df[date_column].min()), str(df[date_column].max()))
    summary = DataSummary(
        rows=len(df), columns=list(df.columns), data_version=data_version, period=period, sources=sources
    )
    return df, summary
