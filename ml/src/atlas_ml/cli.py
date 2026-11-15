"""Linha de comando `atlas-ml` (o mesmo comando local, no container e no Airflow)."""

from __future__ import annotations

import os

os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")

import typer  # noqa: E402

from atlas_ml import __version__  # noqa: E402
from atlas_ml.config import ConfigError, load_settings  # noqa: E402

app = typer.Typer(help="Atlas da Dengue — treino e promoção de modelos.", no_args_is_help=True)


def _fail(message: str) -> None:
    typer.secho(f"erro: {message}", fg=typer.colors.RED, err=True)
    raise typer.Exit(code=1)


@app.command()
def info() -> None:
    """Mostra versão, ambiente e destino do MLflow."""
    typer.echo(f"atlas-ml {__version__}")
    try:
        s = load_settings()
    except ConfigError as exc:
        typer.echo(f"configuração: {exc}")
        return
    typer.echo(f"ambiente: {s.atlas_env} · imagem: {s.atlas_image_tag} · mlflow: {s.mlflow_tracking_uri}")


@app.command()
def train(
    experiment: str = typer.Argument(..., help="Nome do experimento (ex.: example)."),
    register: bool = typer.Option(False, "--register", help="Registra o modelo no registro do MLflow."),
    seed: int = typer.Option(42, help="Semente do experimento de exemplo."),
) -> None:
    """Treina um experimento e registra a run no MLflow."""
    from atlas_ml.experiments import EXPERIMENTS

    if experiment not in EXPERIMENTS:
        _fail(f"experimento desconhecido '{experiment}'. Disponíveis: {', '.join(sorted(EXPERIMENTS))}")
    try:
        settings = load_settings()
        _ = settings.git_sha  # falha cedo se o commit for desconhecido
        result = EXPERIMENTS[experiment](settings, seed=seed, register=register)
    except ConfigError as exc:
        _fail(str(exc))
    metrics = " ".join(f"{k}={v:.4f}" for k, v in result.metrics.items())
    typer.echo(f"run_id={result.run_id} {metrics}")
    if result.model_version:
        typer.echo(f"model_version={result.model_version}")


@app.command()
def promote(
    name: str = typer.Argument(..., help="Nome do modelo registrado (ex.: atlas-example)."),
    version: str = typer.Option(..., "--version", help="Versão a promover."),
    to: str = typer.Option(..., "--to", help="Destino: hml ou prod."),
    by: str = typer.Option(None, "--by", help="Autor da promoção (padrão: usuário do MLflow/sistema)."),
) -> None:
    """Promove uma versão para @hml ou @prod, respeitando a ordem dev → hml → prod."""
    import mlflow

    from atlas_ml.registry import PromotionError
    from atlas_ml.registry import promote as do_promote

    try:
        settings = load_settings()
        mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
        do_promote(name, version, to, actor=by)  # type: ignore[arg-type]
    except (ConfigError, PromotionError) as exc:
        _fail(str(exc))
    typer.echo(f"{name} v{version} → @{to}")


if __name__ == "__main__":
    app()
