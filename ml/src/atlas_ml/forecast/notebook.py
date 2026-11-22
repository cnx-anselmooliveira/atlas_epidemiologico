"""Execução do notebook do pipeline de previsão (tarefas do Airflow e uso à mão).

O pipeline é o notebook `ml/notebooks/forecast_pipeline.ipynb`; este módulo só o executa com
papermill e cuida do que fica em volta: o arquivo de resultado de cada passo, o diretório de uma
execução, a versão do notebook e o anexo do notebook executado à run do MLflow.

    result = run_notebook(nb, {"step": "train", "model": "catboost", ...}, out_dir, name="train-catboost-h1")
    attach_executed_notebook(result)

Os arquivos de uma execução ficam em `<ATLAS_PIPELINE_DIR>/<run_id>/` (padrão /tmp/atlas).
"""

from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path
from typing import Any

DEFAULT_BASE = "/tmp/atlas"
NOTEBOOK_FILE = "forecast_pipeline.ipynb"
# modelos com notebook próprio em <ATLAS_NOTEBOOKS_DIR>/<modelo>/<modelo>.ipynb
MODEL_NOTEBOOKS = ("baseline_bayes", "catboost", "svr", "lstm", "chronos", "ensemble")
GOLD_PROJECT = "ppgcc-dengue-project"
GOLD_TABLE = "gold_dengue_casos_provaveis_uf_semanal"
DEFAULT_NOTEBOOKS_DIR = "/opt/atlas/notebooks"  # cópia da imagem; no stack vem do clone do git-sync
RESULT_SUFFIX = ".result.json"
LOCAL = "local"  # versão do notebook quando não vem de um clone do git-sync


def require_api(minimum: int) -> None:
    """Falha se o pacote instalado for mais antigo que o contrato que o notebook exige."""
    from atlas_ml.forecast import NOTEBOOK_API

    if minimum > NOTEBOOK_API:
        raise RuntimeError(
            f"O notebook exige NOTEBOOK_API >= {minimum}, mas o atlas_ml instalado tem {NOTEBOOK_API}: "
            "atualize a imagem (o notebook mudou antes do pacote)."
        )


def notebook_sha(link: str | os.PathLike[str] | None = None) -> str:
    """Versão do notebook: o SHA da árvore para a qual o link do git-sync aponta, ou `local`.

    O git-sync mantém `<raiz>/.worktrees/<sha>` e um link (`current`) para ela; o SHA está no nome
    da árvore, então não é preciso `git` na imagem. `link` padrão: variável ATLAS_DAGS_LINK.
    A variável ATLAS_NOTEBOOK_SHA, se definida, vale por cima (a DAG a usa para repassar a versão).
    """
    if os.environ.get("ATLAS_NOTEBOOK_SHA"):
        return os.environ["ATLAS_NOTEBOOK_SHA"]
    link = link or os.environ.get("ATLAS_DAGS_LINK")
    if not link or not os.path.islink(link):
        return LOCAL
    return os.path.basename(os.readlink(link).rstrip("/\\")) or LOCAL


def run_dir(run_id: str, base: str | os.PathLike[str] | None = None) -> Path:
    """Diretório próprio de uma execução da DAG (nome do run_id sem caracteres problemáticos)."""
    base = base or os.environ.get("ATLAS_PIPELINE_DIR") or DEFAULT_BASE
    return Path(base) / re.sub(r"[^A-Za-z0-9_.-]", "-", run_id)


def clean_dir(path: str | os.PathLike[str]) -> None:
    """Remove o diretório de uma execução (sem erro se já não existe)."""
    shutil.rmtree(path, ignore_errors=True)


def result_path(out_dir: str | os.PathLike[str], name: str) -> Path:
    return Path(out_dir) / f"{name}{RESULT_SUFFIX}"


def run_notebook(
    notebook: str | os.PathLike[str],
    params: dict[str, Any],
    out_dir: str | os.PathLike[str],
    name: str,
    kernel_name: str = "python3",
) -> dict[str, Any]:
    """Executa o notebook com os parâmetros e devolve o conteúdo do arquivo de resultado.

    O notebook recebe também `result_path` (onde deve gravar o JSON do passo) e `out_dir`. Sem
    esse arquivo ao fim, a execução é tratada como falha. O notebook executado (com as saídas)
    fica em `<out_dir>/<name>.ipynb` e o caminho dele volta em `_notebook`.
    """
    import papermill as pm

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    res = result_path(out, name)
    res.unlink(missing_ok=True)  # um resultado velho nunca vale como o desta execução
    executed = out / f"{name}.ipynb"
    pm.execute_notebook(
        str(notebook),
        str(executed),
        parameters={**params, "result_path": str(res), "out_dir": str(out)},
        kernel_name=kernel_name,
        log_output=False,
        progress_bar=False,
        # o kernel começa por padrão na pasta do notebook de saída; fixar a de quem chama faz um
        # caminho relativo (painel_parquet, por exemplo) valer como em qualquer script
        cwd=os.getcwd(),
    )
    if not res.is_file():
        raise RuntimeError(f"O notebook terminou sem gravar o arquivo de resultado esperado: {res}")
    result = json.loads(res.read_text(encoding="utf-8"))
    result["_notebook"] = str(executed)
    return result


def attach_executed_notebook(result: dict[str, Any]) -> str | None:
    """Anexa o notebook executado à run do resultado (artefato `notebook/`). Devolve o run_id.

    Só depois da execução o notebook está pronto, por isso o anexo é feito aqui e não dentro dele.
    Sem run no resultado (passo que não cria run), não faz nada.
    """
    import mlflow

    run_id = result.get("run_id") or result.get("dataset_run_id")
    executed = result.get("_notebook")
    if not run_id or not executed:
        return None
    mlflow.MlflowClient().log_artifact(run_id, executed, artifact_path="notebook")
    return str(run_id)


def notebooks_dir() -> Path:
    """Onde está o notebook: ATLAS_NOTEBOOKS_DIR (clone do git-sync ou pasta montada) ou a imagem."""
    return Path(os.environ.get("ATLAS_NOTEBOOKS_DIR") or DEFAULT_NOTEBOOKS_DIR)


def check_notebook_version(expected: str | None) -> str:
    """Falha se o notebook mudou desde o início da execução da DAG (um merge no meio dela).

    O Airflow não versiona o código das DAGs no modo pasta, então a DAG registra a versão do notebook
    no começo e cada tarefa confere: assim uma execução nunca mistura duas versões.
    """
    current = notebook_sha()
    if expected and current != expected:
        raise RuntimeError(
            f"O notebook mudou durante a execução (início: {expected}, agora: {current}): "
            "dispare a DAG de novo depois do merge."
        )
    return current


def run_step(
    step: str,
    params: dict[str, Any],
    out_dir: str | os.PathLike[str],
    name: str,
    expected_sha: str | None = None,
) -> dict[str, Any]:
    """Um passo do pipeline como as tarefas do Airflow o executam.

    Confere a versão do notebook, executa o notebook do pipeline com o passo e os parâmetros, e
    anexa o notebook executado à run criada. Devolve o resultado do passo.
    """
    check_notebook_version(expected_sha)
    notebook = notebooks_dir() / NOTEBOOK_FILE
    if not notebook.is_file():
        raise FileNotFoundError(f"Notebook do pipeline não encontrado: {notebook} (ATLAS_NOTEBOOKS_DIR)")
    result = run_notebook(notebook, {"step": step, **params}, out_dir, name)
    attach_executed_notebook(result)
    return result


def ingest_to_mlflow(run_id: str, path: str | os.PathLike[str], artifact_path: str | None = None) -> str:
    """Anexa à run um arquivo que o notebook deixou na pasta da execução (parquet ou JSON).

    O arquivo vai como artefato com o próprio nome. Repetir a ingestão sobrescreve esse artefato,
    sem duplicar nada (o `log_table` do MLflow acrescenta linhas a cada chamada, por isso não é
    usado). Sem o arquivo, falha antes de tocar no MLflow. Devolve o caminho do artefato.
    """
    import mlflow

    file = Path(path)
    if not file.is_file():
        raise FileNotFoundError(f"Arquivo de ingestão não encontrado: {file}")
    if file.suffix not in (".parquet", ".json"):
        raise ValueError(f"Formato não suportado (use .parquet ou .json): {file}")
    mlflow.MlflowClient().log_artifact(run_id, str(file), artifact_path=artifact_path)
    return f"{artifact_path}/{file.name}" if artifact_path else file.name


def run_model_notebook(
    model: str,
    params: dict[str, Any],
    out_dir: str | os.PathLike[str],
    name: str,
    expected_sha: str | None = None,
) -> dict[str, Any]:
    """Executa o notebook de um modelo como as tarefas do Airflow o executam.

    Lê `<ATLAS_NOTEBOOKS_DIR>/<modelo>/<modelo>.ipynb`, confere a versão do notebook (falha antes de
    executar se mudou desde o início da execução) e anexa o notebook executado à run criada.
    """
    if model not in MODEL_NOTEBOOKS:
        raise ValueError(f"Modelo sem notebook: {model!r} (use {', '.join(MODEL_NOTEBOOKS)})")
    check_notebook_version(expected_sha)
    notebook = notebooks_dir() / model / f"{model}.ipynb"
    if not notebook.is_file():
        raise FileNotFoundError(
            f"Notebook do modelo {model} não encontrado: {notebook} (ATLAS_NOTEBOOKS_DIR)"
        )
    result = run_notebook(notebook, params, out_dir, name)
    attach_executed_notebook(result)
    return result


def gold_version(env: str, source: str = "", client: Any = None) -> str:
    """`<tabela>@<última modificação>` da gold do ambiente (ou da tabela `source`), sem ler os dados.

    A DAG registra isto no início da execução e o passa a cada notebook como `data_version_esperada`:
    se a gold for reconstruída no meio, o notebook falha em vez de treinar com dados diferentes.
    """
    env = (env or "").strip().lower()
    if env not in ("dev", "hml", "prod"):
        raise ValueError(f"Ambiente inválido: {env!r} (use dev, hml ou prod)")
    table = source or f"{GOLD_PROJECT}.{'gold' if env == 'dev' else f'gold_{env}'}.{GOLD_TABLE}"
    if client is None:
        from google.cloud import bigquery

        client = bigquery.Client(project=os.environ.get("GCP_PROJECT") or GOLD_PROJECT)
    return f"{table}@{client.get_table(table).modified.isoformat()}"
