"""Configuração por ambiente, validada na inicialização (spec ml-training-pipeline)."""

from __future__ import annotations

import subprocess
from functools import cached_property
from typing import Literal

from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["dev", "hml", "prod"]
LOCAL_IMAGE_TAG = "local"


class ConfigError(RuntimeError):
    """Configuração ausente ou inválida; a execução deve parar antes de processar."""


class Settings(BaseSettings):
    """Lida das variáveis de ambiente (sem prefixo, mesmos nomes do compose e das stacks)."""

    model_config = SettingsConfigDict(env_file=None, extra="ignore", case_sensitive=False)

    atlas_env: Environment = "dev"
    mlflow_tracking_uri: str
    gcp_project: str | None = None
    atlas_git_sha: str | None = None
    atlas_image_tag: str = LOCAL_IMAGE_TAG

    @cached_property
    def git_sha(self) -> str:
        """Commit do código: variável da imagem ou, localmente, `git rev-parse HEAD`."""
        if self.atlas_git_sha:
            return self.atlas_git_sha
        sha = _git_head()
        if not sha:
            raise ConfigError(
                "Commit desconhecido: defina ATLAS_GIT_SHA ou rode dentro de um repositório git."
            )
        return sha


def _git_head() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True, timeout=10
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None


def load_settings() -> Settings:
    """Carrega e valida; converte erros do pydantic numa mensagem com as variáveis problemáticas."""
    try:
        return Settings()  # type: ignore[call-arg]
    except ValidationError as exc:
        problems = []
        for err in exc.errors():
            var = str(err["loc"][0]).upper() if err["loc"] else "?"
            if err["type"] == "missing":
                problems.append(f"{var} não definida")
            elif err["type"] == "literal_error":
                problems.append(f"{var} deve ser dev, hml ou prod")
            else:
                problems.append(f"{var}: {err['msg']}")
        raise ConfigError("Configuração inválida — " + "; ".join(problems)) from exc
