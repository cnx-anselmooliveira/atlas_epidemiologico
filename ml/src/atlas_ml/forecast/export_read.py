"""Leitura do MLflow para a exportação das previsões (DAG `process_forecast_export_atlas`).

Para cada modelo e horizonte, acha a versão registrada no alias do ambiente (`@dev`, `@hml`,
`@prod`), baixa os artefatos da run de origem para uma pasta e devolve um manifesto simples
(JSON) que a DAG usa para carregar o BigQuery e publicar as figuras. Roda no venv do
`atlas_ml` porque o ambiente do Airflow não tem MLflow. Não escreve em nenhum lugar além da
pasta de saída e nunca imprime credenciais.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import mlflow
from mlflow import MlflowClient
from mlflow.exceptions import MlflowException

from atlas_ml.forecast.base import FUTURE_PREDICTIONS, METRICS_BY_UF, PREDICTIONS, registered_name
from atlas_ml.forecast.figures import CAPTIONS

MAX_FIGURE_BYTES = 500 * 1024
FIGURE_DIR = "figures"


def _download(client: MlflowClient, run_id: str, path: str, dest: Path) -> Path | None:
    try:
        return Path(client.download_artifacts(run_id, path, str(dest)))
    except (MlflowException, OSError):
        return None


def _figures(client: MlflowClient, run_id: str, dest: Path, warnings: list[str]) -> list[dict[str, str]]:
    """Baixa só PNGs de até 500 KB de `figures/`; o que sai do padrão vira aviso."""
    captions: dict[str, str] = {}
    caption_file = _download(client, run_id, f"{FIGURE_DIR}/{CAPTIONS}", dest)
    if caption_file:
        captions = json.loads(caption_file.read_text(encoding="utf-8"))
    out = []
    try:
        items = client.list_artifacts(run_id, FIGURE_DIR)
    except MlflowException:
        return out
    for item in items:
        name = item.path.split("/")[-1]
        if item.is_dir or name == CAPTIONS:
            continue
        if not name.lower().endswith(".png"):
            warnings.append(f"{run_id}: {name} não é PNG; ignorada")
            continue
        if item.file_size is not None and item.file_size > MAX_FIGURE_BYTES:
            warnings.append(f"{run_id}: {name} passa de {MAX_FIGURE_BYTES // 1024} KB; ignorada")
            continue
        local = _download(client, run_id, item.path, dest)
        if local is None or local.stat().st_size > MAX_FIGURE_BYTES:
            warnings.append(f"{run_id}: {name} não pôde ser baixada dentro do limite; ignorada")
            continue
        out.append({"name": name, "path": str(local), "caption": captions.get(name, "")})
    return out


def _iso(ms: int | None) -> str | None:
    return None if ms is None else datetime.fromtimestamp(ms / 1000, tz=UTC).isoformat()


def read_versions(
    env: str,
    models: list[str],
    horizons: list[int],
    out_dir: str | Path,
    client: MlflowClient | None = None,
) -> dict[str, Any]:
    """Manifesto das versões no alias `env`: `entries` (uma por modelo e horizonte) e `missing`."""
    client = client or MlflowClient()
    out_dir = Path(out_dir)
    entries: list[dict[str, Any]] = []
    missing: list[str] = []
    warnings: list[str] = []
    for model in models:
        for horizon in horizons:
            name = registered_name(model, horizon, env)
            try:
                version = client.get_model_version_by_alias(name, env)
            except MlflowException:
                missing.append(f"{model}-h{horizon}")
                continue
            run = client.get_run(version.run_id)
            dest = out_dir / f"{model}-h{horizon}"
            dest.mkdir(parents=True, exist_ok=True)
            files = {
                key: _download(client, run.info.run_id, artifact, dest)
                for key, artifact in (
                    ("predictions", PREDICTIONS),
                    ("future", FUTURE_PREDICTIONS),
                    ("metrics_uf", METRICS_BY_UF),
                )
            }
            absent = [k for k, v in files.items() if v is None]
            if absent:
                missing.append(f"{model}-h{horizon} (sem {', '.join(absent)})")
                continue
            tags = run.data.tags
            entries.append(
                {
                    "model": model,
                    "horizon": horizon,
                    "family": tags.get("atlas.model_family", ""),
                    "model_version": str(version.version),
                    "mlflow_run_id": run.info.run_id,
                    "data_version": tags.get("atlas.data_version", ""),
                    "trained_at": _iso(run.info.start_time),
                    "env": env,
                    "params": dict(run.data.params),
                    "metrics": {k: float(v) for k, v in run.data.metrics.items()},
                    "figures_failed": [f for f in tags.get("atlas.figures_failed", "").split(",") if f],
                    "files": {k: str(v) for k, v in files.items()},
                    "figures": _figures(client, run.info.run_id, dest, warnings),
                }
            )
    return {"env": env, "entries": entries, "missing": missing, "warnings": warnings}


def read_versions_from_environment(
    env: str, models: list[str], horizons: list[int], out_dir: str, tracking_uri: str
) -> dict[str, Any]:
    """Ponto de entrada da DAG: define o servidor do MLflow e lê. As credenciais, se houver,
    já estão em MLFLOW_TRACKING_USERNAME/PASSWORD no ambiente da tarefa."""
    mlflow.set_tracking_uri(tracking_uri)
    return read_versions(env, models, horizons, out_dir)
