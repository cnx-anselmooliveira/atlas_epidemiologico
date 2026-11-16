"""Painel UF × semana de incidência de dengue a partir da gold do SINAN (spec forecast-dataset)."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

import mlflow
import pandas as pd

from atlas_ml.config import Settings
from atlas_ml.data.bigquery import DataSummary, read_features
from atlas_ml.forecast import EXPERIMENT
from atlas_ml.tracking import atlas_run

GOLD = "ppgcc-dengue-project.gold"
EPI_TABLE = f"{GOLD}.gold_dengue_epi_curve_weekly"
POP_TABLE = f"{GOLD}.gold_dim_populacao_admin1"
PANEL_ARTIFACT = "panel.parquet"
PANEL_COLUMNS = [
    "uf",
    "uf_code",
    "week_start",
    "year",
    "epi_week",
    "cases",
    "population",
    "incidence",
    "filled",
]

# Casos por UF e semana + população do ano mais próximo (uma linha por UF/semana)
QUERY = f"""
WITH epi AS (
  SELECT admin1_name AS uf, epi_week_start_date AS week_start, year, epi_week,
         SUM(total_cases) AS cases
  FROM `{EPI_TABLE}`
  WHERE country_iso3 = 'BRA' AND admin1_name IS NOT NULL
  GROUP BY 1, 2, 3, 4
),
pop AS (
  SELECT admin1_name AS uf, population, population_year
  FROM `{POP_TABLE}`
  WHERE country_iso3 = 'BRA'
)
SELECT e.uf, e.week_start, e.year, e.epi_week, e.cases, p.population
FROM epi e
LEFT JOIN pop p
  ON p.uf = e.uf
QUALIFY ROW_NUMBER() OVER (
  PARTITION BY e.uf, e.week_start ORDER BY ABS(e.year - p.population_year), p.population_year DESC
) = 1
"""


def build_panel(raw: pd.DataFrame) -> pd.DataFrame:
    """Normaliza o resultado da consulta num painel regular (semanas faltantes → 0, filled=True)."""
    df = raw.copy()
    df["week_start"] = pd.to_datetime(df["week_start"])
    missing = sorted(df.loc[df["population"].isna(), "uf"].unique())
    if missing:
        raise ValueError(f"UFs sem população na gold: {', '.join(missing)}")
    if df.duplicated(["uf", "week_start"]).any():
        raise ValueError("A consulta retornou mais de uma linha por UF e semana.")

    frames = []
    for uf, g in df.groupby("uf", sort=True):
        g = g.set_index("week_start").sort_index()
        full = pd.date_range(g.index.min(), g.index.max(), freq="7D")
        g = g.reindex(full)
        g.index.name = "week_start"
        g["filled"] = g["cases"].isna()
        g["uf"] = uf
        g["cases"] = g["cases"].fillna(0).astype("int64")
        g["population"] = g["population"].ffill().bfill()
        iso = g.index.isocalendar()
        g["year"] = g["year"].fillna(pd.Series(iso.year.values, index=g.index)).astype("int64")
        g["epi_week"] = g["epi_week"].fillna(pd.Series(iso.week.values, index=g.index)).astype("int64")
        frames.append(g.reset_index())

    panel = pd.concat(frames, ignore_index=True)
    codes = {uf: i for i, uf in enumerate(sorted(panel["uf"].unique()))}
    panel["uf_code"] = panel["uf"].map(codes).astype("int64")
    panel["population"] = panel["population"].astype("float64")
    panel["incidence"] = panel["cases"] / panel["population"] * 1e5
    return panel[PANEL_COLUMNS].sort_values(["uf", "week_start"]).reset_index(drop=True)


def summarize(panel: pd.DataFrame, summary: DataSummary) -> dict[str, Any]:
    return {
        "data_version": summary.data_version,
        "sources": summary.sources,
        "rows": len(panel),
        "ufs": sorted(panel["uf"].unique().tolist()),
        "period": [str(panel["week_start"].min().date()), str(panel["week_start"].max().date())],
        "filled_weeks": int(panel["filled"].sum()),
        "total_cases": int(panel["cases"].sum()),
    }


def pipeline_tags() -> dict[str, str]:
    return {"atlas.pipeline_run": os.environ.get("ATLAS_PIPELINE_RUN", "manual")}


def prepare(settings: Settings, client: Any) -> str:
    """Lê a gold, monta o painel e registra o snapshot numa run `dataset`. Devolve o run_id."""
    raw, summary = read_features(client, query=QUERY, source_tables=[EPI_TABLE, POP_TABLE])
    panel = build_panel(raw)
    with (
        atlas_run(
            settings,
            EXPERIMENT,
            data_version=summary.data_version,
            run_name="dataset",
            extra_tags={**pipeline_tags(), "atlas.model_family": "dataset"},
        ) as run,
        tempfile.TemporaryDirectory() as tmp,
    ):
        path = Path(tmp) / PANEL_ARTIFACT
        panel.to_parquet(path, index=False)
        mlflow.log_artifact(str(path))
        info = summarize(panel, summary)
        mlflow.log_dict(info, "data_summary.json")
        mlflow.log_params(
            {"rows": info["rows"], "ufs": len(info["ufs"]), "filled_weeks": info["filled_weeks"]}
        )
    return run.info.run_id


def load_snapshot(dataset_run_id: str) -> tuple[pd.DataFrame, str]:
    """Baixa o painel de uma run `dataset` (nunca relê o BigQuery). Devolve (painel, data_version)."""
    run = mlflow.get_run(dataset_run_id)
    data_version = run.data.tags.get("atlas.data_version")
    if not data_version:
        raise ValueError(f"A run {dataset_run_id} não é um snapshot de dataset (sem atlas.data_version).")
    with tempfile.TemporaryDirectory() as tmp:
        local = mlflow.artifacts.download_artifacts(f"runs:/{dataset_run_id}/{PANEL_ARTIFACT}", dst_path=tmp)
        panel = pd.read_parquet(local)
    panel["week_start"] = pd.to_datetime(panel["week_start"])
    return panel, data_version


def dump_summary(info: dict[str, Any]) -> str:
    return json.dumps(info, ensure_ascii=False, indent=2)
