"""Registro de modelos e promoção dev → hml → prod (spec ml-model-lifecycle).

O MLflow não guarda histórico de aliases, então a passagem por cada ambiente fica
gravada em tags da versão: atlas.hml_at / atlas.hml_by e atlas.prod_at / atlas.prod_by.
"""

from __future__ import annotations

import getpass
import os
from datetime import UTC, datetime
from typing import Literal

import mlflow
from mlflow import MlflowClient

from atlas_ml.config import Settings
from atlas_ml.tracking import TAG_ENV

Target = Literal["hml", "prod"]


class PromotionError(RuntimeError):
    """Promoção fora da ordem dev → hml → prod ou sem os requisitos do ambiente."""


def register_model(settings: Settings, model_uri: str, name: str) -> str:
    """Registra uma nova versão. No MLflow de dev local, aponta o alias @dev para ela."""
    mv = mlflow.register_model(model_uri, name)
    if settings.atlas_env == "dev":
        MlflowClient().set_registered_model_alias(name, "dev", mv.version)
    return str(mv.version)


def default_actor() -> str:
    return os.environ.get("MLFLOW_TRACKING_USERNAME") or getpass.getuser()


def promote(
    name: str,
    version: str | int,
    to: Target,
    *,
    actor: str | None = None,
    client: MlflowClient | None = None,
    now: datetime | None = None,
) -> None:
    """Move o alias @hml ou @prod para a versão, se as regras de ordem forem cumpridas."""
    if to not in ("hml", "prod"):
        raise PromotionError(f"Destino inválido '{to}': use hml ou prod (@dev é só do MLflow local).")
    client = client or MlflowClient()
    version = str(version)
    mv = client.get_model_version(name, version)
    run = client.get_run(mv.run_id)

    if to == "hml":
        trained_in = run.data.tags.get(TAG_ENV)
        if trained_in != "hml":
            raise PromotionError(
                f"{name} v{version} foi treinado em '{trained_in}'. Para homologar, treine com a "
                "imagem de tag hml contra o MLflow da VPS (ordem dev → hml → prod)."
            )
    else:
        if not mv.tags.get("atlas.hml_at"):
            raise PromotionError(
                f"{name} v{version} nunca passou por @hml. A ordem é dev → hml → prod; "
                f"promova primeiro com --to hml."
            )
        if not any(k.startswith("val_") for k in run.data.metrics):
            raise PromotionError(f"{name} v{version} não tem métricas de validação (val_*) registradas.")

    stamp = (now or datetime.now(UTC)).isoformat(timespec="seconds")
    client.set_registered_model_alias(name, to, version)
    client.set_model_version_tag(name, version, f"atlas.{to}_at", stamp)
    client.set_model_version_tag(name, version, f"atlas.{to}_by", actor or default_actor())
