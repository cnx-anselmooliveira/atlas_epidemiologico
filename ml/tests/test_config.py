import pytest

from atlas_ml import config
from atlas_ml.config import ConfigError, load_settings


def test_carrega_com_variaveis_minimas(monkeypatch):
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "http://mlflow:5000")
    monkeypatch.setenv("ATLAS_GIT_SHA", "abc1234")
    s = load_settings()
    assert s.atlas_env == "dev"
    assert s.atlas_image_tag == "local"
    assert s.git_sha == "abc1234"


def test_url_do_mlflow_ausente_lista_a_variavel():
    with pytest.raises(ConfigError, match="MLFLOW_TRACKING_URI não definida"):
        load_settings()


def test_ambiente_invalido(monkeypatch):
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "http://mlflow:5000")
    monkeypatch.setenv("ATLAS_ENV", "staging")
    with pytest.raises(ConfigError, match="ATLAS_ENV deve ser dev, hml ou prod"):
        load_settings()


def test_commit_vem_do_git_quando_nao_ha_variavel(monkeypatch):
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "http://mlflow:5000")
    monkeypatch.setattr(config, "_git_head", lambda: "deadbeef")
    assert load_settings().git_sha == "deadbeef"


def test_commit_desconhecido_falha(monkeypatch):
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "http://mlflow:5000")
    monkeypatch.setattr(config, "_git_head", lambda: None)
    with pytest.raises(ConfigError, match="Commit desconhecido"):
        _ = load_settings().git_sha
