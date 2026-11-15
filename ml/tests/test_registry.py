from datetime import UTC, datetime

import pytest
from mlflow import MlflowClient
from typer.testing import CliRunner

from atlas_ml.cli import app
from atlas_ml.config import load_settings
from atlas_ml.experiments.example import MODEL_NAME, run_example
from atlas_ml.registry import PromotionError, promote

NOW = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)


def _version(monkeypatch, env: str, seed: int) -> str:
    monkeypatch.setenv("ATLAS_ENV", env)
    return run_example(load_settings(), seed=seed, register=True).model_version


def test_promocao_direta_para_prod_e_recusada(tracking_uri, monkeypatch):
    v = _version(monkeypatch, "hml", 1)
    with pytest.raises(PromotionError, match="nunca passou por @hml"):
        promote(MODEL_NAME, v, "prod", actor="teste")
    assert "prod" not in MlflowClient().get_registered_model(MODEL_NAME).aliases


def test_modelo_treinado_em_dev_nao_vai_para_hml(tracking_uri, monkeypatch):
    v = _version(monkeypatch, "dev", 1)
    with pytest.raises(PromotionError, match="treinado em 'dev'"):
        promote(MODEL_NAME, v, "hml", actor="teste")


def test_promocao_valida_hml_depois_prod(tracking_uri, monkeypatch):
    v = _version(monkeypatch, "hml", 2)
    promote(MODEL_NAME, v, "hml", actor="ana", now=NOW)
    promote(MODEL_NAME, v, "prod", actor="bia", now=NOW)
    client = MlflowClient()
    assert str(client.get_model_version_by_alias(MODEL_NAME, "prod").version) == v
    tags = client.get_model_version(MODEL_NAME, v).tags
    assert tags["atlas.hml_by"] == "ana" and tags["atlas.prod_by"] == "bia"
    assert tags["atlas.prod_at"] == "2026-11-15T12:00:00+00:00"


def test_rollback_para_versao_que_ja_teve_prod(tracking_uri, monkeypatch):
    v1 = _version(monkeypatch, "hml", 3)
    v2 = _version(monkeypatch, "hml", 4)
    for v in (v1, v2):
        promote(MODEL_NAME, v, "hml", actor="t")
        promote(MODEL_NAME, v, "prod", actor="t")
    promote(MODEL_NAME, v1, "prod", actor="t")  # volta para a anterior
    assert str(MlflowClient().get_model_version_by_alias(MODEL_NAME, "prod").version) == v1


def test_cli_promote_recusa_ordem_invalida(tracking_uri, monkeypatch):
    v = _version(monkeypatch, "hml", 5)
    out = CliRunner().invoke(app, ["promote", MODEL_NAME, "--version", v, "--to", "prod"])
    assert out.exit_code == 1
    assert "dev → hml → prod" in out.output
    ok = CliRunner().invoke(app, ["promote", MODEL_NAME, "--version", v, "--to", "hml", "--by", "cli"])
    assert ok.exit_code == 0, ok.output
