"""Leitura do MLflow para a exportação: versão do alias, artefatos, figuras e ausentes."""

import dataclasses
from pathlib import Path

import pytest
from mlflow import MlflowClient

from atlas_ml.config import load_settings
from atlas_ml.forecast import export_read
from atlas_ml.forecast.base import run_model

from .helpers import SMALL, Persistence, dataset_run


def _train(horizons, ds):
    return {
        h: run_model(Persistence, dataclasses.replace(SMALL, horizon=h), ds, load_settings())
        for h in horizons
    }


def test_manifesto_traz_versao_do_alias_arquivos_e_figuras(tracking_uri, tmp_path):
    results = _train((1, 3), dataset_run())
    manifest = export_read.read_versions("dev", ["persistence"], [1, 2, 3], tmp_path)
    assert {e["horizon"] for e in manifest["entries"]} == {1, 3}
    assert manifest["missing"] == ["persistence-h2"]  # nunca treinado nesse horizonte
    for entry in manifest["entries"]:
        res = results[entry["horizon"]]
        assert entry["mlflow_run_id"] == res.run_id and entry["model_version"] == res.model_version
        assert entry["family"] == "naive" and entry["data_version"] == "synthetic@teste"
        assert entry["params"]["horizon"] == str(entry["horizon"])
        assert "test_nrmse_mean" in entry["metrics"]
        assert all(Path(p).exists() for p in entry["files"].values())
        names = {f["name"] for f in entry["figures"]}
        assert names == {"forecast_vs_observed.png", "error_by_uf.png"}
        assert all(f["caption"] for f in entry["figures"])  # legenda do captions.json
        assert entry["figures_failed"] == []


def test_alias_de_outro_ambiente_nao_aparece(tracking_uri, tmp_path):
    _train((1,), dataset_run())  # em dev o registro só aponta @dev
    manifest = export_read.read_versions("hml", ["persistence"], [1], tmp_path)
    assert manifest["entries"] == [] and manifest["missing"] == ["persistence-h1"]


def test_exportacao_de_hml_le_o_nome_com_sufixo_hml(tracking_uri, tmp_path, monkeypatch):
    # treino de hml registra atlas-br-<m>-h<H>_hml (sem alias); a promoção aponta @hml nesse nome
    monkeypatch.setenv("ATLAS_ENV", "hml")
    res = _train((1,), dataset_run())[1]
    MlflowClient().set_registered_model_alias("atlas-br-persistence-h1_hml", "hml", res.model_version)
    manifest = export_read.read_versions("hml", ["persistence"], [1], tmp_path)
    assert [e["mlflow_run_id"] for e in manifest["entries"]] == [res.run_id]
    # e o dev não enxerga o modelo de hml
    assert export_read.read_versions("dev", ["persistence"], [1], tmp_path)["entries"] == []


def test_figura_grande_ou_fora_do_padrao_e_ignorada_com_aviso(tracking_uri, tmp_path, monkeypatch):
    _train((1,), dataset_run())
    monkeypatch.setattr(export_read, "MAX_FIGURE_BYTES", 10)
    manifest = export_read.read_versions("dev", ["persistence"], [1], tmp_path)
    assert manifest["entries"][0]["figures"] == []
    assert len(manifest["warnings"]) == 2 and all("KB" in w for w in manifest["warnings"])


def test_run_sem_future_predictions_vira_ausente(tracking_uri, tmp_path, monkeypatch):
    _train((1,), dataset_run())
    # versão treinada antes desta mudança: o artefato de futuro não existe na run
    monkeypatch.setattr(export_read, "FUTURE_PREDICTIONS", "nao_existe.parquet")
    manifest = export_read.read_versions("dev", ["persistence"], [1], tmp_path)
    assert manifest["entries"] == []
    assert manifest["missing"] == ["persistence-h1 (sem future)"]


@pytest.mark.parametrize("env", ["dev"])
def test_ponto_de_entrada_define_o_servidor(tracking_uri, tmp_path, env):
    import mlflow

    _train((1,), dataset_run())
    out = export_read.read_versions_from_environment(
        env, ["persistence"], [1], str(tmp_path), mlflow.get_tracking_uri()
    )
    assert len(out["entries"]) == 1
