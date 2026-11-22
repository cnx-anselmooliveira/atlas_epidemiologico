"""Tarefas da DAG `atlas_dengue_forecast_br` que rodam no venv do atlas_ml: a comparação e o treino.

O Airflow copia o corpo de cada `@task.external_python` para o venv do atlas_ml, então o corpo é
autocontido. Aqui as funções são extraídas do arquivo da DAG (sem importar o Airflow) e executadas
com MLflow em arquivo, para testar o que de fato roda lá.
"""

import ast
from pathlib import Path

import mlflow
import pytest

from atlas_ml.config import load_settings
from atlas_ml.tracking import atlas_run

DAG = Path(__file__).resolve().parents[3] / "airflow" / "dags" / "atlas_dengue_forecast_br.py"
EXPERIMENTO = "dengue-forecast-br"


def tarefa(nome):
    """A função de uma tarefa da DAG sem o decorador (como o Airflow a copia para o venv)."""
    modulo = ast.parse(DAG.read_text(encoding="utf-8"))
    no = next(n for n in modulo.body if isinstance(n, ast.FunctionDef) and n.name == nome)
    no.decorator_list = []
    espaco = {}
    exec(compile(ast.Module(body=[no], type_ignores=[]), str(DAG), "exec"), espaco)  # noqa: S102
    return espaco[nome]


def run_de_modelo(modelo, horizonte, execucao, nrmse, versao="gold@2026-11-20", status="FINISHED"):
    with atlas_run(
        load_settings(),
        EXPERIMENTO,
        data_version=versao,
        run_name=modelo,
        extra_tags={
            "atlas.pipeline_run": execucao,
            "atlas.horizon": str(horizonte),
            "atlas.forecast_model": modelo,
            "atlas.model_family": "x",
        },
    ) as run:
        if nrmse is not None:
            mlflow.log_metrics({"test_nrmse_mean": nrmse, "test_mae_mean": nrmse * 10})
        if status == "FAILED":
            mlflow.end_run(status="FAILED")
    return run.info.run_id


def test_comparar_junta_as_runs_do_horizonte_e_lista_os_ausentes(tracking_uri):
    run_de_modelo("catboost", 2, "exec1", 0.10)
    run_de_modelo("svr", 2, "exec1", 0.20)
    run_de_modelo("lstm", 2, "exec1", 0.05, status="FAILED")  # falhou: conta como ausente
    run_de_modelo("catboost", 3, "exec1", 0.01)  # outro horizonte: fora
    run_de_modelo("catboost", 2, "exec2", 0.02)  # outra execução: fora

    run_id = tarefa("comparar")(2, "exec1")

    run = mlflow.get_run(run_id)
    tags = run.data.tags
    assert tags["atlas.model_family"] == "compare" and tags["atlas.horizon"] == "2"
    assert tags["atlas.pipeline_run"] == "exec1" and tags["atlas.best_model"] == "catboost"
    assert set(tags["atlas.missing_models"].split(",")) == {"baseline_bayes", "lstm", "chronos", "ensemble"}
    assert tags["atlas.data_version"] == "gold@2026-11-20"
    assert run.data.metrics == {"catboost.test_nrmse_mean": 0.10, "svr.test_nrmse_mean": 0.20}
    assert run.data.params == {"models_ok": "2", "models_missing": "4"}
    import pandas as pd

    tabela = pd.read_csv(mlflow.artifacts.download_artifacts(f"runs:/{run_id}/comparison.csv"))
    assert list(tabela["model"][:2]) == ["catboost", "svr"] and len(tabela) == 6


def test_comparar_sem_nenhuma_run_da_execucao_falha(tracking_uri):
    run_de_modelo("catboost", 1, "exec1", 0.1)
    with pytest.raises(ValueError, match="Nenhuma run com atlas.pipeline_run=outra e horizonte 1"):
        tarefa("comparar")(1, "outra")


def test_comparar_respeita_o_experimento_configurado(tracking_uri, monkeypatch):
    monkeypatch.setenv("ATLAS_FORECAST_EXPERIMENT", "sandbox")
    with pytest.raises(ValueError, match="Experimento atlas/sandbox não existe"):
        tarefa("comparar")(1, "exec1")


def test_treinar_executa_o_notebook_do_modelo_com_os_parametros_da_tarefa(monkeypatch):
    chamadas = []

    def falso(model, params, out_dir, name, expected_sha=None):
        chamadas.append((model, params, out_dir, name, expected_sha))
        return {"run_id": f"run-{model}"}

    monkeypatch.setattr("atlas_ml.forecast.notebook.run_model_notebook", falso)
    treinar = tarefa("treinar")
    assert treinar("catboost", 2, "exec1", 12, 42, "/tmp/atlas/exec1", "sha1", "gold@x", "") == "run-catboost"
    modelo, params, out_dir, nome, sha = chamadas[-1]
    assert (modelo, nome, out_dir, sha) == ("catboost", "train-catboost-h2", "/tmp/atlas/exec1", "sha1")
    assert params == {
        "horizon": 2,
        "window": 12,
        "seed": 42,
        "pipeline_run": "exec1",
        "data_version_esperada": "gold@x",
        "fonte": "",
    }
    # o ensemble recebe as runs das três bases
    treinar(
        "ensemble",
        1,
        "exec1",
        12,
        42,
        "/tmp/atlas/exec1",
        "sha1",
        "gold@x",
        "p.d.t",
        {"catboost": "a", "svr": "b"},
    )
    _, params, *_ = chamadas[-1]
    assert params["base_runs"] == {"catboost": "a", "svr": "b"} and params["fonte"] == "p.d.t"
