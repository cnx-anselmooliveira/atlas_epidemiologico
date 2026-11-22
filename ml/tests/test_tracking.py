import mlflow
import pytest

from atlas_ml.config import ConfigError, load_settings
from atlas_ml.tracking import REQUIRED_TAGS, atlas_run


def test_run_recebe_todas_as_tags_obrigatorias(tracking_uri):
    settings = load_settings()
    with atlas_run(settings, "teste", data_version="synthetic-seed1") as run:
        mlflow.log_metric("m", 1.0)
    tags = mlflow.get_run(run.info.run_id).data.tags
    for tag in REQUIRED_TAGS:
        assert tags.get(tag), tag
    assert tags["atlas.env"] == "dev"
    assert tags["atlas.git_sha"] == "abc1234"
    assert tags["atlas.image_tag"] == "local"
    assert mlflow.get_experiment(run.info.experiment_id).name == "atlas/teste"


def test_run_leva_a_versao_do_notebook_quando_ha(tracking_uri, monkeypatch):
    settings = load_settings()
    with atlas_run(settings, "teste", data_version="synthetic-seed1") as sem:
        pass
    assert "atlas.notebook_sha" not in mlflow.get_run(sem.info.run_id).data.tags
    monkeypatch.setenv("ATLAS_NOTEBOOK_SHA", "9f2c1ab")
    with atlas_run(settings, "teste", data_version="synthetic-seed1") as com:
        pass
    assert mlflow.get_run(com.info.run_id).data.tags["atlas.notebook_sha"] == "9f2c1ab"


def test_versao_de_dados_vazia_falha_antes_de_abrir_run(tracking_uri):
    settings = load_settings()
    with (
        pytest.raises(ConfigError, match="atlas.data_version"),
        atlas_run(settings, "teste", data_version=" "),
    ):
        pytest.fail("não deveria abrir a run")
    assert mlflow.search_experiments(filter_string="name = 'atlas/teste'") == []
