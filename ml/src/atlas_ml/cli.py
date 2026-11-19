"""Linha de comando `atlas-ml` (o mesmo comando local, no container e no Airflow)."""

from __future__ import annotations

import os
import sys

os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")

# Console do Windows (cp1252) não codifica os emojis que o MLflow imprime ao encerrar a run
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure") and (_stream.encoding or "").lower() not in ("utf-8", "utf8"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

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


forecast_app = typer.Typer(help="Previsão de dengue por UF (painel SINAN-BR).", no_args_is_help=True)
app.add_typer(forecast_app, name="forecast")


def _forecast_config(window: int, horizon: int, seed: int, features: str):
    from atlas_ml.forecast.config import ForecastConfig

    feats = tuple(f.strip() for f in features.split(",") if f.strip())
    return ForecastConfig(window=window, horizon=horizon, seed=seed, features=feats)


@forecast_app.command("prepare")
def forecast_prepare(
    source_table: str = typer.Option(
        "", "--source-table", help="Outra tabela projeto.dataset.tabela com as mesmas colunas (ex.: amostra)."
    ),
) -> None:
    """Lê a gold do BigQuery e grava o painel numa run `dataset` (imprime dataset_run_id=)."""
    import mlflow

    from atlas_ml.data.bigquery import bigquery_client
    from atlas_ml.forecast.dataset import prepare

    try:
        settings = load_settings()
        _ = settings.git_sha
        mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
        run_id = prepare(settings, bigquery_client(settings), source_table or None)
    except (ConfigError, ValueError) as exc:
        _fail(str(exc))
    typer.echo(f"dataset_run_id={run_id}")


@forecast_app.command("train")
def forecast_train(
    model: str = typer.Argument(..., help="baseline_bayes, catboost, svr, lstm, chronos ou ensemble."),
    dataset_run: str = typer.Option(..., "--dataset-run", help="Run `dataset` com o painel."),
    window: int = typer.Option(12, help="Semanas de histórico por janela."),
    horizon: int = typer.Option(1, help="Semanas à frente do alvo."),
    seed: int = typer.Option(42, help="Semente."),
    features: str = typer.Option("", help="Covariáveis do painel, separadas por vírgula."),
    base_runs: str = typer.Option(
        "", "--base-runs", help="Só ensemble: catboost=ID,svr=ID,lstm=ID (runs com OOF)."
    ),
    register: bool = typer.Option(
        True, "--register/--no-register", help="Registra atlas-br-<modelo>-h<horizonte>."
    ),
) -> None:
    """Treina um modelo sobre o snapshot, avalia e registra no MLflow (imprime run_id=)."""
    import mlflow

    from atlas_ml.forecast.base import run_model
    from atlas_ml.models import get_factory

    kwargs = {}
    if model == "ensemble":
        pairs = [p.split("=", 1) for p in base_runs.split(",") if "=" in p]
        kwargs["base_runs"] = {k.strip(): v.strip() for k, v in pairs}
    try:
        settings = load_settings()
        _ = settings.git_sha
        mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
        cfg = _forecast_config(window, horizon, seed, features)
        result = run_model(get_factory(model, **kwargs), cfg, dataset_run, settings, register=register)
    except (ConfigError, ValueError) as exc:
        _fail(str(exc))
    shown = {k: v for k, v in result.metrics.items() if k.startswith("test_")}
    typer.echo(" ".join(f"{k}={v:.4f}" for k, v in shown.items()))
    if result.model_version:
        typer.echo(f"model_version={result.model_version}")
    typer.echo(f"run_id={result.run_id}")


@forecast_app.command("compare")
def forecast_compare(
    pipeline_run: str = typer.Option(..., "--pipeline-run", help="Valor da tag atlas.pipeline_run."),
    horizon: int = typer.Option(0, help="Compara só as runs deste horizonte (0 = todas)."),
) -> None:
    """Compara as runs de uma execução e registra a run `compare` (imprime run_id=)."""
    import mlflow

    from atlas_ml.forecast.compare import compare

    try:
        settings = load_settings()
        _ = settings.git_sha
        mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
        run_id, table = compare(settings, pipeline_run, horizon or None)
    except (ConfigError, ValueError) as exc:
        _fail(str(exc))
    typer.echo(table)
    typer.echo(f"run_id={run_id}")


if __name__ == "__main__":
    app()
