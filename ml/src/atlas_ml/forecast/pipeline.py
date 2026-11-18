"""Etapas do pipeline de previsão, chamadas pela DAG `atlas_dengue_forecast_br` e pelo CLI.

Cada função faz o que um comando `atlas-ml forecast ...` faz e devolve um valor simples (id de
run), para a DAG encadear as tarefas sem scripts de shell.
"""

from __future__ import annotations

import os

import mlflow

from atlas_ml.config import Settings, load_settings


def _settings() -> Settings:
    settings = load_settings()
    _ = settings.git_sha  # falha cedo se o commit em uso não estiver definido
    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    return settings


def prepare_snapshot(source_table: str = "") -> str:
    """Lê a gold do BigQuery (ou `source_table`, p.ex. uma amostra) e grava o painel numa run
    `dataset`. Devolve o run_id."""
    from atlas_ml.data.bigquery import bigquery_client
    from atlas_ml.forecast.dataset import CASES_TABLE, prepare

    settings = _settings()
    return prepare(settings, bigquery_client(settings), source_table or CASES_TABLE)


def train(
    model: str,
    horizon: int,
    dataset_run: str,
    pipeline_run: str,
    window: int = 12,
    seed: int = 42,
    base_runs: dict[str, str] | None = None,
) -> str:
    """Treina um modelo para um horizonte sobre o snapshot e registra no MLflow. Devolve o run_id."""
    from atlas_ml.forecast.base import run_model
    from atlas_ml.forecast.config import ForecastConfig
    from atlas_ml.models import get_factory

    # a tag atlas.pipeline_run de todas as runs da execução
    os.environ["ATLAS_PIPELINE_RUN"] = pipeline_run
    settings = _settings()
    cfg = ForecastConfig(window=window, horizon=horizon, seed=seed)
    kwargs = {"base_runs": dict(base_runs)} if model == "ensemble" and base_runs else {}
    return run_model(get_factory(model, **kwargs), cfg, dataset_run, settings).run_id


def compare_horizon(pipeline_run: str, horizon: int) -> str:
    """Registra a run `compare` do horizonte (modelos que faltarem ficam em atlas.missing_models)."""
    from atlas_ml.forecast.compare import compare

    run_id, _table = compare(_settings(), pipeline_run, horizon)
    return run_id
