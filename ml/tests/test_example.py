import json

import mlflow
from mlflow import MlflowClient
from typer.testing import CliRunner

from atlas_ml.cli import app
from atlas_ml.config import load_settings
from atlas_ml.experiments.example import FEATURES, make_synthetic_data, run_example, temporal_split


def test_dados_sinteticos_sao_deterministicos():
    a, b = make_synthetic_data(7), make_synthetic_data(7)
    assert a.equals(b)
    assert set(FEATURES) <= set(a.columns)


def test_split_temporal_nao_mistura_semanas():
    train, valid = temporal_split(make_synthetic_data(1))
    assert train["week"].max() < valid["week"].min()


def test_mesma_semente_mesma_metrica(tracking_uri):
    s = load_settings()
    r1 = run_example(s, seed=3)
    r2 = run_example(s, seed=3)
    assert r1.metrics == r2.metrics
    assert r1.run_id != r2.run_id


def test_run_tem_parametros_metricas_modelo_e_resumo(tracking_uri):
    result = run_example(load_settings(), seed=5)
    run = mlflow.get_run(result.run_id)
    assert run.data.params["seed"] == "5"
    assert {"val_mae", "val_rmse"} <= set(run.data.metrics)
    assert run.data.tags["atlas.data_version"] == "synthetic-seed5"

    summary = json.loads(mlflow.artifacts.load_text(f"runs:/{result.run_id}/data_summary.json"))
    assert summary["features"] == FEATURES

    model_info = mlflow.models.get_model_info(f"runs:/{result.run_id}/model")
    assert model_info.signature is not None
    loaded = mlflow.pyfunc.load_model(f"runs:/{result.run_id}/model")
    assert len(loaded.predict(make_synthetic_data(5)[FEATURES].head(4))) == 4


def test_cli_train_register_aponta_alias_dev(tracking_uri):
    out = CliRunner().invoke(app, ["train", "example", "--register", "--seed", "2"])
    assert out.exit_code == 0, out.output
    assert "model_version=1" in out.output
    assert str(MlflowClient().get_model_version_by_alias("atlas-example", "dev").version) == "1"


def test_cli_experimento_desconhecido(tracking_uri):
    out = CliRunner().invoke(app, ["train", "nicho"])
    assert out.exit_code == 1
    assert "experimento desconhecido" in out.output


def test_cli_sem_url_do_mlflow_falha_antes_de_treinar():
    out = CliRunner().invoke(app, ["train", "example"])
    assert out.exit_code == 1
    assert "MLFLOW_TRACKING_URI" in out.output
