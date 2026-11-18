"""Tabelas gold servidas pela API: colunas devolvidas, filtros permitidos e ordenação.

É a whitelist da API: só o que está aqui chega ao SQL como identificador. Valores de filtro
sempre vão como parâmetro de consulta (ver repository.py).
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class GoldTable:
    table: str
    columns: tuple[str, ...]
    # dataset de origem: "gold" (padrão) ou "forecast" (previsões exportadas do MLflow)
    origem: str = "gold"
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

# --- previsões (dataset forecast, mantido pela DAG process_forecast_export_atlas) ---
# Só as visões forecast_current_*: a run vigente de cada modelo e horizonte.
FORECAST_MODELS = GoldTable(
    table="forecast_current_models",
    origem="forecast",
    columns=(
        "model",
        "horizon",
        "family",
        "model_version",
        "data_version",
        "trained_at",
        "env",
        "nrmse",
        "mae",
        "rmse",
        "r2",
        "interval_coverage",
        "fit_seconds",
        "nrmse_br",
    ),
    filters={"model": "STRING", "horizon": "INT64"},
    order_by=("model", "horizon"),
)

FORECAST_METRICS_UF = GoldTable(
    table="forecast_current_metrics_uf",
    origem="forecast",
    columns=("model", "horizon", "split", "uf", "n", "nrmse", "mae", "rmse", "r2"),
    filters={"model": "STRING", "horizon": "INT64", "split": "STRING", "uf": "STRING"},
    order_by=("model", "horizon", "split", "uf"),
)

FORECAST_PREDICTIONS = GoldTable(
    table="forecast_current_predictions",
    origem="forecast",
    columns=(
        "model",
        "horizon",
        "split",
        "uf",
        "origin_date",
        "target_date",
        "y_true",
        "y_pred",
        "lower",
        "upper",
        "population",
    ),
    filters={"model": "STRING", "horizon": "INT64", "split": "STRING", "uf": "STRING"},
    order_by=("target_date", "split", "uf"),
)

# Figuras: a coluna gcs_path só é lida pelo servidor (nunca devolvida em JSON)
FORECAST_FIGURES = GoldTable(
    table="forecast_current_figures",
    origem="forecast",
    columns=("model", "horizon", "name", "caption", "gcs_path"),
    filters={"model": "STRING", "horizon": "INT64", "name": "STRING"},
    order_by=("horizon", "name"),
)

TABELAS = (
    CASOS_PROVAVEIS_BRASIL_SEMANAL,
    CASOS_PROVAVEIS_UF_SEMANAL,
    FORECAST_MODELS,
    FORECAST_METRICS_UF,
    FORECAST_PREDICTIONS,
    FORECAST_FIGURES,
)
