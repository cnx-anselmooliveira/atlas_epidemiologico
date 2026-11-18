"""Run de comparação de uma execução da DAG: métricas de teste lado a lado (spec forecast-models)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import mlflow
import pandas as pd

from atlas_ml.config import Settings
from atlas_ml.forecast import EXPERIMENT
from atlas_ml.tracking import atlas_run

COLUMNS = ["test_nrmse_mean", "test_mae_mean", "test_rmse_mean", "test_r2_mean", "test_interval_coverage"]


def collect(pipeline_run: str, horizon: int | None = None) -> tuple[pd.DataFrame, str | None]:
    """Runs de modelo da execução (e do horizonte, se informado) → (tabela, data_version)."""
    from atlas_ml.models import MODELS

    experiment = mlflow.get_experiment_by_name(f"atlas/{EXPERIMENT}")
    if experiment is None:
        raise ValueError(f"Experimento atlas/{EXPERIMENT} não existe.")
    filter_string = f"tags.`atlas.pipeline_run` = '{pipeline_run}'"
    if horizon is not None:
        filter_string += f" and tags.`atlas.horizon` = '{int(horizon)}'"
    runs = mlflow.search_runs(
        [experiment.experiment_id],
        filter_string=filter_string,
        output_format="list",
    )
    data_version = None
    rows = []
    for run in runs:
        tags = run.data.tags
        data_version = data_version or tags.get("atlas.data_version")
        name = tags.get("atlas.forecast_model")
        if not name or run.info.status != "FINISHED":
            continue
        rows.append(
            {"model": name, "run_id": run.info.run_id, **{c: run.data.metrics.get(c) for c in COLUMNS}}
        )
    table = pd.DataFrame(rows, columns=["model", "run_id", *COLUMNS])
    # se um modelo rodou mais de uma vez na mesma execução (retentativa), fica a última
    table = table.drop_duplicates("model", keep="first")
    present = set(table["model"])
    missing = [m for m in MODELS if m not in present]
    for m in missing:
        table.loc[len(table)] = {"model": m, "run_id": None}
    return table.sort_values("test_nrmse_mean", na_position="last").reset_index(drop=True), data_version


def compare(settings: Settings, pipeline_run: str, horizon: int | None = None) -> tuple[str, str]:
    """Registra a run `compare` (por horizonte, se informado) com comparison.csv e o melhor modelo."""
    table, data_version = collect(pipeline_run, horizon)
    if data_version is None:
        raise ValueError(f"Nenhuma run com atlas.pipeline_run={pipeline_run}.")
    ranked = table.dropna(subset=["test_nrmse_mean"])
    missing = table.loc[table["test_nrmse_mean"].isna(), "model"].tolist()
    tags = {
        "atlas.pipeline_run": pipeline_run,
        "atlas.model_family": "compare",
        **({"atlas.horizon": str(horizon)} if horizon is not None else {}),
        "atlas.missing_models": ",".join(missing) or "-",
    }
    if len(ranked):
        tags["atlas.best_model"] = ranked.iloc[0]["model"]
    with (
        atlas_run(
            settings, EXPERIMENT, data_version=data_version, run_name="compare", extra_tags=tags
        ) as run,
        tempfile.TemporaryDirectory() as tmp,
    ):
        path = Path(tmp) / "comparison.csv"
        table.to_csv(path, index=False)
        mlflow.log_artifact(str(path))
        mlflow.log_metrics(
            {f"{r.model}.test_nrmse_mean": float(r.test_nrmse_mean) for r in ranked.itertuples()}
        )
        mlflow.log_params({"models_ok": len(ranked), "models_missing": len(missing)})
    return run.info.run_id, table.to_string(index=False)
