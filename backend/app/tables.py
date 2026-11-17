"""Tabelas gold servidas pela API: colunas devolvidas, filtros permitidos e ordenação.

É a whitelist da API: só o que está aqui chega ao SQL como identificador. Valores de filtro
sempre vão como parâmetro de consulta (ver repository.py).
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class GoldTable:
    table: str
    columns: tuple[str, ...]
    # coluna filtrável → tipo do parâmetro no BigQuery
    filters: dict[str, str] = field(default_factory=dict)
    order_by: tuple[str, ...] = ()


_COLUNAS_SEMANA = (
    "week_start",
    "epi_year",
    "epi_week",
    "notified_cases",
    "probable_cases",
    "confirmed_cases",
    "alarm_cases",
    "severe_cases",
    "deaths",
    "population",
    "incidence",
    "gold_generated_at",
)

CASOS_PROVAVEIS_BRASIL_SEMANAL = GoldTable(
    table="gold_dengue_casos_provaveis_brasil_semanal",
    columns=_COLUNAS_SEMANA,
    filters={"epi_year": "INT64"},
    order_by=("week_start",),
)

CASOS_PROVAVEIS_UF_SEMANAL = GoldTable(
    table="gold_dengue_casos_provaveis_uf_semanal",
    columns=("uf", *_COLUNAS_SEMANA),
    filters={"uf": "STRING", "epi_year": "INT64"},
    order_by=("week_start", "uf"),
)

TABELAS = (CASOS_PROVAVEIS_BRASIL_SEMANAL, CASOS_PROVAVEIS_UF_SEMANAL)
