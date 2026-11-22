"""Painel UF × semana de incidência de casos prováveis de dengue (gold do SINAN, spec forecast-dataset)."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

import mlflow
import pandas as pd

from atlas_ml.config import Settings
from atlas_ml.data.bigquery import DataSummary, read_features
from atlas_ml.forecast import EXPERIMENT
from atlas_ml.forecast.config import CHANNELS
from atlas_ml.forecast.config import STATIC_COVARIATES as _STATIC
from atlas_ml.tracking import atlas_run

PROJECT = "ppgcc-dengue-project"
CASES_TABLE_NAME = "gold_dengue_casos_provaveis_uf_semanal"


def cases_table(env: str = "dev") -> str:
    """Gold de casos prováveis do ambiente: `gold` em dev, `gold_<ambiente>` em hml e prod.

    Mesma regra do Airflow (atlas_ingest/ambiente.py) e do dbt (macro generate_schema_name).
    """
    env = (env or "").strip().lower()
    if env not in ("dev", "hml", "prod"):
        raise ValueError(f"Ambiente inválido: {env!r} (use dev, hml ou prod)")
    dataset = "gold" if env == "dev" else f"gold_{env}"
    return f"{PROJECT}.{dataset}.{CASES_TABLE_NAME}"


# Tabela de dev (compatibilidade); o treino usa cases_table(settings.atlas_env)
CASES_TABLE = cases_table("dev")
PANEL_ARTIFACT = "panel.parquet"
STATIC_COVARIATES = list(_STATIC)
CHANNEL_COLUMNS = list(CHANNELS)
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
    *CHANNEL_COLUMNS,
    *STATIC_COVARIATES,
]


# Casos prováveis (notificações não descartadas) por UF de residência e semana do início
# dos sintomas, com população do ano epidemiológico e relevo da UF. A gold já garante a
# série regular (27 UFs × todas as semanas); build_panel só valida e completa por segurança.
def query_for(table: str) -> str:
    return f"""
SELECT uf, week_start, epi_year AS year, epi_week, probable_cases AS cases, population,
       {", ".join(CHANNEL_COLUMNS)},
       {", ".join(STATIC_COVARIATES)}
FROM `{table}`
"""


QUERY = query_for(CASES_TABLE)


def check_source(table: str) -> str:
    """Tabela de origem no formato projeto.dataset.tabela (o nome vai dentro de crases na consulta)."""
    if not re.fullmatch(r"[A-Za-z0-9_-]+\.[A-Za-z0-9_]+\.[A-Za-z0-9_]+", table):
        raise ValueError(f"Tabela de origem inválida: {table!r} (use projeto.dataset.tabela)")
    return table


def build_panel(raw: pd.DataFrame) -> pd.DataFrame:
    """Normaliza o resultado da consulta num painel regular (semanas faltantes → 0, filled=True)."""
    df = raw.copy()
    df["week_start"] = pd.to_datetime(df["week_start"])
    sem_canal = [c for c in CHANNEL_COLUMNS if c not in df]
    if sem_canal:
        raise ValueError(f"A gold não trouxe os canais: {', '.join(sem_canal)}")
    for col in STATIC_COVARIATES:
        if col not in df:
            df[col] = float("nan")
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
        for col in CHANNEL_COLUMNS:  # semana completada = sem notificação em nenhum canal
            g[col] = g[col].fillna(0).astype("int64")
        g["population"] = g["population"].ffill().bfill()
        for col in STATIC_COVARIATES:
            g[col] = g[col].ffill().bfill()
        iso = g.index.isocalendar()
        g["year"] = g["year"].fillna(pd.Series(iso.year.values, index=g.index)).astype("int64")
        g["epi_week"] = g["epi_week"].fillna(pd.Series(iso.week.values, index=g.index)).astype("int64")
        frames.append(g.reset_index())

    panel = pd.concat(frames, ignore_index=True)
    codes = {uf: i for i, uf in enumerate(sorted(panel["uf"].unique()))}
    panel["uf_code"] = panel["uf"].map(codes).astype("int64")
    panel["population"] = panel["population"].astype("float64")
    for col in STATIC_COVARIATES:
        panel[col] = panel[col].astype("float64")
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


def _register_snapshot(settings: Settings, panel: pd.DataFrame, summary: DataSummary) -> str:
    """Grava o painel numa run `dataset` (panel.parquet e data_summary.json). Devolve o run_id."""
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


def prepare(settings: Settings, client: Any, source_table: str | None = None) -> str:
    """Lê a gold do ambiente (ou outra tabela de mesmo formato), monta o painel e registra o
    snapshot numa run `dataset`. Devolve o run_id."""
    source_table = check_source(source_table or cases_table(settings.atlas_env))
    raw, summary = read_features(client, query=query_for(source_table), source_tables=[source_table])
    return _register_snapshot(settings, build_panel(raw), summary)


def prepare_from_parquet(settings: Settings, path: str | os.PathLike[str]) -> str:
    """Registra como snapshot um painel já montado (parquet com as colunas de PANEL_COLUMNS), sem
    ler o BigQuery: testes do pipeline e reprocessamento de um painel guardado."""
    file = Path(path)
    panel = pd.read_parquet(file)
    missing = [c for c in PANEL_COLUMNS if c not in panel.columns]
    if missing:
        raise ValueError(f"O painel {file.name} não tem as colunas: {', '.join(missing)}")
    panel["week_start"] = pd.to_datetime(panel["week_start"])
    version = "parquet:" + hashlib.sha1(file.read_bytes()).hexdigest()[:12]
    summary = DataSummary(
        rows=len(panel), columns=list(panel.columns), data_version=version, sources={file.name: version}
    )
    return _register_snapshot(settings, panel[PANEL_COLUMNS], summary)


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
