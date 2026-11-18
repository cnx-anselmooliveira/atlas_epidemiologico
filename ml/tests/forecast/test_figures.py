"""Figuras PNG das runs: comuns, legendas, tamanho e falha isolada (sem o grupo `models`)."""

import mlflow
import pytest
from mlflow import MlflowClient

from atlas_ml.config import load_settings
from atlas_ml.forecast import figures
from atlas_ml.forecast.base import run_model

from .helpers import SMALL, Persistence, dataset_run


def _figures(run_id):
    client = MlflowClient()
    return {a.path.split("/")[-1]: a.file_size for a in client.list_artifacts(run_id, "figures")}


def test_run_grava_figuras_comuns_com_legenda_e_tamanho(tracking_uri):
    res = run_model(Persistence, SMALL, dataset_run(), load_settings(), register=False)
    files = _figures(res.run_id)
    assert {"forecast_vs_observed.png", "error_by_uf.png", "captions.json"} <= set(files)
    for name, size in files.items():
        if name.endswith(".png"):
            assert 0 < size <= figures.MAX_BYTES, name
    captions = mlflow.artifacts.load_dict(f"runs:/{res.run_id}/figures/captions.json")
    assert set(captions) == {"forecast_vs_observed.png", "error_by_uf.png"}
    assert all(text and text[0].isupper() for text in captions.values())  # legenda em português
    assert "atlas.figures_failed" not in mlflow.get_run(res.run_id).data.tags


def test_figura_que_falha_nao_derruba_a_run(tracking_uri, monkeypatch):
    def quebra(*args, **kwargs):
        raise RuntimeError("falha forçada")

    monkeypatch.setitem(figures.FUNCTIONS, "error_by_uf.png", quebra)
    res = run_model(Persistence, SMALL, dataset_run(), load_settings(), register=False)
    run = mlflow.get_run(res.run_id)
    assert run.info.status == "FINISHED"
    assert run.data.tags["atlas.figures_failed"] == "error_by_uf.png"
    files = _figures(res.run_id)
    assert "error_by_uf.png" not in files and "forecast_vs_observed.png" in files
    captions = mlflow.artifacts.load_dict(f"runs:/{res.run_id}/figures/captions.json")
    assert "error_by_uf.png" not in captions


def test_figura_acima_do_limite_e_recusada(tmp_path, monkeypatch):
    monkeypatch.setattr(figures, "MAX_BYTES", 10)  # nenhum PNG cabe
    plt = figures._plt()
    fig, _ = plt.subplots()
    with pytest.raises(ValueError, match="KB"):
        figures._save(fig, tmp_path / "x.png")
    plt.close(fig)


def test_figuras_previstas_por_familia():
    class M:
        name = "m"

    for family, expected in (
        ("gbm", "feature_importance.png"),
        ("stacking", "feature_importance.png"),
        ("rnn", "learning_curve.png"),
        ("kernel", "error_by_week.png"),
        ("bayes", "posterior.png"),
        ("foundation", "interval_coverage.png"),
    ):
        m = M()
        m.family = family
        assert expected in figures.planned(m)
        assert len(figures.planned(m)) == 3
    m = M()
    m.family = "naive"
    assert len(figures.planned(m)) == 2
