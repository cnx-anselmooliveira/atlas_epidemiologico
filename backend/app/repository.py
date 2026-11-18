"""Leitura das tabelas gold no BigQuery.

- Identificadores (tabela, colunas, ordenação) vêm só do registro em tables.py.
- Valores de filtro, limit e offset vão como ScalarQueryParameter, nunca no texto do SQL.
- Cada consulta tem teto de bytes faturados (max_bytes_billed).
- A "geração" de uma tabela é o last_modified do metadado (tables.get, sem custo de consulta).
"""

from __future__ import annotations

import json
from typing import Any

from google.cloud import bigquery

from app.tables import GoldTable


class FiltroNaoPermitido(ValueError):
    pass


def criar_cliente(project: str, location: str | None, credentials_json: str | None) -> bigquery.Client:
    credentials = None
    if credentials_json:
        from google.oauth2 import service_account

        credentials = service_account.Credentials.from_service_account_info(json.loads(credentials_json))
    return bigquery.Client(project=project, location=location, credentials=credentials)


class GoldRepository:
    def __init__(
        self,
        client: bigquery.Client,
        project: str,
        dataset: str,
        max_bytes_billed: int,
        forecast_dataset: str = "forecast",
    ):
        self.client = client
        self.project = project
        self.dataset = dataset
        self.forecast_dataset = forecast_dataset
        self.max_bytes_billed = max_bytes_billed

    def _ref(self, t: GoldTable) -> str:
        dataset = self.forecast_dataset if t.origem == "forecast" else self.dataset
        return f"{self.project}.{dataset}.{t.table}"

    def montar_consulta(
        self, t: GoldTable, filtros: dict[str, Any], limit: int, offset: int
    ) -> tuple[str, list[bigquery.ScalarQueryParameter]]:
        sql = [f"SELECT {', '.join(t.columns)}", f"FROM `{self._ref(t)}`", "WHERE TRUE"]
        params: list[bigquery.ScalarQueryParameter] = []
        for coluna, valor in filtros.items():
            if valor is None:
                continue
            if coluna not in t.filters:
                raise FiltroNaoPermitido(f"{coluna} não é filtrável em {t.table}")
            sql.append(f"AND {coluna} = @{coluna}")
            params.append(bigquery.ScalarQueryParameter(coluna, t.filters[coluna], valor))
        if t.order_by:
            sql.append("ORDER BY " + ", ".join(t.order_by))
        sql.append("LIMIT @limit OFFSET @offset")
        params += [
            bigquery.ScalarQueryParameter("limit", "INT64", limit),
            bigquery.ScalarQueryParameter("offset", "INT64", offset),
        ]
        return "\n".join(sql), params

    def consultar(self, t: GoldTable, filtros: dict[str, Any], limit: int, offset: int) -> list[dict]:
        sql, params = self.montar_consulta(t, filtros, limit, offset)
        config = bigquery.QueryJobConfig(query_parameters=params, maximum_bytes_billed=self.max_bytes_billed)
        return [dict(row.items()) for row in self.client.query(sql, job_config=config).result()]

    def geracao(self, t: GoldTable) -> str:
        """Muda a cada (re)construção da tabela pelo dbt."""
        return self.client.get_table(self._ref(t)).modified.isoformat()

    def verificar(self) -> None:
        """Health check: lê o metadado do dataset (sem custo de consulta)."""
        self.client.get_dataset(f"{self.project}.{self.dataset}")
