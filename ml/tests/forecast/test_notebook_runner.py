"""Executor do notebook do pipeline (exige o grupo `models`, que traz papermill)."""

import os

import mlflow
import pytest

from atlas_ml.forecast import NOTEBOOK_API
from atlas_ml.forecast.notebook import (
    LOCAL,
    attach_executed_notebook,
    clean_dir,
    notebook_sha,
    require_api,
    result_path,
    run_dir,
    run_notebook,
)

nbformat = pytest.importorskip("nbformat")  # vem com o grupo `models` (papermill)

pytestmark = pytest.mark.models


def _notebook(path, body: str, parameters: str = "step = 'x'\nresult_path = ''\nout_dir = ''"):
    nb = nbformat.v4.new_notebook()
    params = nbformat.v4.new_code_cell(parameters)
    params.metadata["tags"] = ["parameters"]
    nb.cells = [params, nbformat.v4.new_code_cell(body)]
    nb.metadata["kernelspec"] = {"name": "python3", "language": "python", "display_name": "Python 3"}
    nbformat.write(nb, path)
    return path


def test_api_do_pacote_barra_notebook_mais_novo():
    require_api(NOTEBOOK_API)  # igual: passa
    with pytest.raises(RuntimeError, match="atualize a imagem"):
        require_api(NOTEBOOK_API + 1)


def test_notebook_sha_vem_do_nome_da_arvore_do_link(tmp_path):
    assert notebook_sha(tmp_path / "nao-existe") == LOCAL
    assert notebook_sha(None) == LOCAL
    arvore = tmp_path / ".worktrees" / "9f2c1ab"
    arvore.mkdir(parents=True)
    link = tmp_path / "current"
    try:
        os.symlink(arvore, link, target_is_directory=True)
    except OSError:
        pytest.skip("sem permissão para criar link simbólico neste sistema")
    assert notebook_sha(link) == "9f2c1ab"


def test_notebook_sha_sem_depender_de_link_real(monkeypatch):
    # o git-sync aponta `current` para `.worktrees/<sha>` (caminho relativo ou absoluto)
    monkeypatch.setattr(os.path, "islink", lambda p: True)
    monkeypatch.setattr(os, "readlink", lambda p: ".worktrees/abc123def/")
    assert notebook_sha("/opt/airflow/git/current") == "abc123def"
    monkeypatch.setenv("ATLAS_DAGS_LINK", "/opt/airflow/git/current")
    assert notebook_sha() == "abc123def"
    monkeypatch.setenv("ATLAS_NOTEBOOK_SHA", "fixado1")  # a variável explícita vale por cima
    assert notebook_sha() == "fixado1"


def test_diretorio_por_execucao_e_limpeza(tmp_path):
    a = run_dir("manual__2026-11-22T10:00:00+00:00", tmp_path)
    b = run_dir("manual__2026-11-22T11:00:00+00:00", tmp_path)
    assert a != b and a.parent == tmp_path
    assert ":" not in a.name and "+" not in a.name
    a.mkdir(parents=True)
    (a / "x.json").write_text("{}")
    clean_dir(a)
    assert not a.exists()
    clean_dir(a)  # sem erro se já foi removido


def test_executa_com_parametros_e_le_o_resultado(tmp_path):
    nb = _notebook(
        tmp_path / "ok.ipynb",
        "import json\nopen(result_path, 'w').write(json.dumps({'step': step, 'run_id': 'abc'}))",
    )
    out = tmp_path / "execucao"
    result = run_notebook(nb, {"step": "train"}, out, name="train-catboost-h2")
    assert result["step"] == "train" and result["run_id"] == "abc"
    assert result_path(out, "train-catboost-h2").is_file()
    assert (out / "train-catboost-h2.ipynb").is_file()
    assert result["_notebook"].endswith("train-catboost-h2.ipynb")


def test_caminho_relativo_vale_a_partir_da_pasta_de_quem_chama(tmp_path, monkeypatch):
    chamador = tmp_path / "chamador"
    chamador.mkdir()
    (chamador / "entrada.txt").write_text("ola")
    monkeypatch.chdir(chamador)
    nb = _notebook(
        tmp_path / "le.ipynb",
        "import json\nopen(result_path, 'w').write(json.dumps({'lido': open('entrada.txt').read()}))",
    )
    # a saída vai para outra pasta, e mesmo assim "entrada.txt" é achado a partir da pasta do chamador
    result = run_notebook(nb, {"step": "x"}, tmp_path / "execucao", name="le")
    assert result["lido"] == "ola"


def test_sem_arquivo_de_resultado_falha_indicando_o_arquivo(tmp_path):
    nb = _notebook(tmp_path / "mudo.ipynb", "x = 1")
    with pytest.raises(RuntimeError, match=r"arquivo de resultado esperado: .*prepare\.result\.json"):
        run_notebook(nb, {"step": "prepare"}, tmp_path / "execucao", name="prepare")


def test_resultado_velho_nao_vale_para_a_execucao_nova(tmp_path):
    out = tmp_path / "execucao"
    out.mkdir()
    result_path(out, "prepare").write_text('{"dataset_run_id": "velho"}')
    nb = _notebook(tmp_path / "mudo.ipynb", "x = 1")
    with pytest.raises(RuntimeError, match="arquivo de resultado esperado"):
        run_notebook(nb, {"step": "prepare"}, out, name="prepare")


def test_erro_numa_celula_falha_a_execucao(tmp_path):
    nb = _notebook(tmp_path / "quebra.ipynb", "raise ValueError('modelo desconhecido')")
    with pytest.raises(Exception, match="modelo desconhecido"):
        run_notebook(nb, {"step": "train"}, tmp_path / "execucao", name="train")


def test_notebook_executado_vira_artefato_da_run(tmp_path, tracking_uri):
    nb = _notebook(tmp_path / "ok.ipynb", "x = 1")
    mlflow.set_experiment("atlas/teste-notebook")  # sem isto vale o experimento ativo de outro teste
    with mlflow.start_run() as run:
        pass
    executed = tmp_path / "execucao.ipynb"
    executed.write_text(nbformat.writes(nbformat.read(nb, as_version=4)))
    assert (
        attach_executed_notebook({"run_id": run.info.run_id, "_notebook": str(executed)}) == run.info.run_id
    )
    nomes = {a.path for a in mlflow.MlflowClient().list_artifacts(run.info.run_id, "notebook")}
    assert "notebook/execucao.ipynb" in nomes
    # sem run no resultado, nada a anexar
    assert attach_executed_notebook({"_notebook": str(executed)}) is None


def _pipeline_nb(
    pasta, corpo="import json\nopen(result_path, 'w').write(json.dumps({'step': step, 'run_id': 'abc'}))"
):
    pasta.mkdir(parents=True, exist_ok=True)
    return _notebook(pasta / "forecast_pipeline.ipynb", corpo)


def test_run_step_confere_a_versao_e_executa_o_notebook_da_pasta(tmp_path, monkeypatch):
    from atlas_ml.forecast.notebook import check_notebook_version, run_step

    # resultado sem run_id: o passo não cria run, então não há o que anexar (o anexo é testado à parte)
    _pipeline_nb(tmp_path / "nbs", "import json\nopen(result_path, 'w').write(json.dumps({'step': step}))")
    monkeypatch.setenv("ATLAS_NOTEBOOKS_DIR", str(tmp_path / "nbs"))
    monkeypatch.setenv("ATLAS_NOTEBOOK_SHA", "v1")
    assert check_notebook_version("v1") == "v1"
    assert check_notebook_version(None) == "v1"  # sem versão de partida, não confere
    result = run_step("train", {"model": "svr"}, tmp_path / "out", "train-svr-h1", expected_sha="v1")
    assert result["step"] == "train" and "run_id" not in result


def test_run_step_falha_se_o_notebook_mudou_no_meio_da_execucao(tmp_path, monkeypatch):
    from atlas_ml.forecast.notebook import run_step

    _pipeline_nb(tmp_path / "nbs")
    monkeypatch.setenv("ATLAS_NOTEBOOKS_DIR", str(tmp_path / "nbs"))
    monkeypatch.setenv("ATLAS_NOTEBOOK_SHA", "v2")  # um merge trocou a versão
    with pytest.raises(RuntimeError, match=r"mudou durante a execução \(início: v1, agora: v2\)"):
        run_step("train", {}, tmp_path / "out", "train", expected_sha="v1")
    assert not (tmp_path / "out").exists()  # nada foi executado


def test_run_step_sem_notebook_aponta_o_caminho(tmp_path, monkeypatch):
    from atlas_ml.forecast.notebook import run_step

    monkeypatch.setenv("ATLAS_NOTEBOOKS_DIR", str(tmp_path / "vazio"))
    with pytest.raises(FileNotFoundError, match="forecast_pipeline.ipynb"):
        run_step("prepare", {}, tmp_path / "out", "prepare")


def test_ingestao_no_mlflow_e_idempotente_e_falha_sem_arquivo(tmp_path, tracking_uri):
    import pandas as pd

    from atlas_ml.forecast.notebook import ingest_to_mlflow

    mlflow.set_experiment("atlas/teste-notebook")  # sem isto vale o experimento ativo de outro teste
    with mlflow.start_run() as run:
        pass
    rid = run.info.run_id
    tabela = tmp_path / "comparacao.parquet"
    pd.DataFrame({"model": ["catboost", "svr"], "nrmse": [0.09, 0.1]}).to_parquet(tabela, index=False)
    params = tmp_path / "parametros.json"
    params.write_text('{"window": 12, "seed": 42}')

    for _ in range(2):  # repetir a ingestão sobrescreve o mesmo artefato
        assert ingest_to_mlflow(rid, tabela) == "comparacao.parquet"
        assert ingest_to_mlflow(rid, params) == "parametros.json"
    nomes = sorted(a.path for a in mlflow.MlflowClient().list_artifacts(rid))
    assert nomes == ["comparacao.parquet", "parametros.json"]
    baixada = mlflow.artifacts.download_artifacts(f"runs:/{rid}/comparacao.parquet")
    assert list(pd.read_parquet(baixada)["model"]) == ["catboost", "svr"]  # sem linhas repetidas
    assert mlflow.artifacts.load_dict(f"runs:/{rid}/parametros.json") == {"window": 12, "seed": 42}

    with pytest.raises(FileNotFoundError, match="não encontrado"):
        ingest_to_mlflow(rid, tmp_path / "nao-existe.parquet")
    (tmp_path / "dados.csv").write_text("a,b\n1,2\n")
    with pytest.raises(ValueError, match="Formato não suportado"):
        ingest_to_mlflow(rid, tmp_path / "dados.csv")
    assert sorted(a.path for a in mlflow.MlflowClient().list_artifacts(rid)) == nomes


def test_run_model_notebook_executa_o_notebook_do_modelo(tmp_path, monkeypatch, tracking_uri):
    from atlas_ml.forecast.notebook import run_model_notebook

    (tmp_path / "nbs" / "svr").mkdir(parents=True)
    corpo = "import json\nopen(result_path, 'w').write(json.dumps({'modelo': 'svr', 'horizonte': horizon}))"
    params_nb = "horizon = 1\nresult_path = ''\nout_dir = ''"
    _notebook(tmp_path / "nbs" / "svr" / "svr.ipynb", corpo, parameters=params_nb)
    monkeypatch.setenv("ATLAS_NOTEBOOKS_DIR", str(tmp_path / "nbs"))
    monkeypatch.setenv("ATLAS_NOTEBOOK_SHA", "v1")
    resultado = run_model_notebook("svr", {"horizon": 3}, tmp_path / "out", "train-svr-h3", expected_sha="v1")
    assert resultado == {
        "modelo": "svr",
        "horizonte": 3,
        "_notebook": str(tmp_path / "out" / "train-svr-h3.ipynb"),
    }


def test_run_model_notebook_recusa_modelo_desconhecido_e_notebook_ausente(tmp_path, monkeypatch):
    from atlas_ml.forecast.notebook import run_model_notebook

    monkeypatch.setenv("ATLAS_NOTEBOOKS_DIR", str(tmp_path / "vazio"))
    with pytest.raises(ValueError, match="Modelo sem notebook: '../etc'"):
        run_model_notebook("../etc", {}, tmp_path / "out", "x")  # nada de caminho montado pelo nome
    with pytest.raises(FileNotFoundError, match=r"catboost.*catboost\.ipynb.*ATLAS_NOTEBOOKS_DIR"):
        run_model_notebook("catboost", {}, tmp_path / "out", "x")
    assert not (tmp_path / "out").exists()


def test_run_model_notebook_falha_antes_de_executar_se_o_notebook_mudou(tmp_path, monkeypatch):
    from atlas_ml.forecast.notebook import run_model_notebook

    (tmp_path / "nbs" / "lstm").mkdir(parents=True)
    _notebook(tmp_path / "nbs" / "lstm" / "lstm.ipynb", "x = 1")
    monkeypatch.setenv("ATLAS_NOTEBOOKS_DIR", str(tmp_path / "nbs"))
    monkeypatch.setenv("ATLAS_NOTEBOOK_SHA", "v2")
    with pytest.raises(RuntimeError, match=r"início: v1, agora: v2"):
        run_model_notebook("lstm", {}, tmp_path / "out", "x", expected_sha="v1")
    assert not (tmp_path / "out").exists()


def test_gold_version_traz_tabela_e_ultima_modificacao_sem_ler_dados():
    from datetime import UTC, datetime
    from types import SimpleNamespace

    from atlas_ml.forecast.notebook import gold_version

    consultadas = []

    class Cliente:
        def get_table(self, tabela):
            consultadas.append(tabela)
            return SimpleNamespace(modified=datetime(2026, 11, 20, 10, 0, tzinfo=UTC))

        def query(self, *_):
            raise AssertionError("não pode ler os dados")

    gold = "ppgcc-dengue-project.gold_hml.gold_dengue_casos_provaveis_uf_semanal"
    assert gold_version("hml", client=Cliente()) == f"{gold}@2026-11-20T10:00:00+00:00"
    assert consultadas == [gold]
    assert gold_version("dev", client=Cliente()).startswith("ppgcc-dengue-project.gold.gold_dengue")
    assert gold_version("prod", "p.d.amostra", client=Cliente()).startswith("p.d.amostra@")
    with pytest.raises(ValueError, match="Ambiente inválido"):
        gold_version("teste", client=Cliente())
