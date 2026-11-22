"""Abertura de runs no MLflow com os metadados obrigatórios de reprodutibilidade
(spec ml-model-lifecycle: atlas.env, atlas.git_sha, atlas.image_tag, atlas.data_version)."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

import mlflow

from atlas_ml.config import ConfigError, Settings

TAG_ENV = "atlas.env"
TAG_GIT_SHA = "atlas.git_sha"
TAG_IMAGE_TAG = "atlas.image_tag"
TAG_DATA_VERSION = "atlas.data_version"
TAG_NOTEBOOK_SHA = "atlas.notebook_sha"  # opcional: versão do notebook que orquestrou a run
REQUIRED_TAGS = (TAG_ENV, TAG_GIT_SHA, TAG_IMAGE_TAG, TAG_DATA_VERSION)


def required_tags(settings: Settings, data_version: str) -> dict[str, str]:
    """Monta as tags obrigatórias; qualquer valor vazio interrompe antes de abrir a run."""
    tags = {
        TAG_ENV: settings.atlas_env,
        TAG_GIT_SHA: settings.git_sha,
        TAG_IMAGE_TAG: settings.atlas_image_tag,
        TAG_DATA_VERSION: data_version,
    }
    missing = [k for k, v in tags.items() if not v or not str(v).strip()]
    if missing:
        raise ConfigError("Tags obrigatórias sem valor: " + ", ".join(missing))
    return tags


@contextmanager
def atlas_run(
    settings: Settings,
    experiment: str,
    *,
    data_version: str,
    run_name: str | None = None,
    extra_tags: dict[str, str] | None = None,
) -> Iterator[mlflow.ActiveRun]:
    """Abre uma run com as tags `atlas.*` no experimento `atlas/<experiment>`."""
    tags = required_tags(settings, data_version)  # valida antes de tocar no servidor
    if os.environ.get("ATLAS_NOTEBOOK_SHA"):  # definida pelo notebook do pipeline de previsão
        tags[TAG_NOTEBOOK_SHA] = os.environ["ATLAS_NOTEBOOK_SHA"]
    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    mlflow.set_experiment(f"atlas/{experiment}")
    with mlflow.start_run(run_name=run_name, tags={**tags, **(extra_tags or {})}) as run:
        yield run
