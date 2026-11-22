"""Previsão de dengue por UF (Brasil): treina os modelos em 4 horizontes e registra tudo no MLflow.

Sem agendamento: disparada pela etl_brasil (só quando a gold muda) ou à mão. Ao fim,
dispara a exportação para o BigQuery (process_forecast_export_atlas), de onde o site lê.

    iniciar_execucao ─► por horizonte (1..4, em paralelo limitado):
                 train_baseline_bayes ──────────────────────────┐
                 train_chronos ─────────────────────────────────┤
                 train_catboost ─┐                              ├─► compare (all_done)
                 train_svr ──────┼─► train_ensemble ────────────┘
                 train_lstm ─────┘
              ─► exportar (dispara process_forecast_export_atlas)
              ─► limpar (all_done: remove o diretório da execução)

- iniciar_execucao: cria o diretório da execução e registra a versão do notebook e a da gold. Cada
  notebook lê a gold direto (sem snapshot) e falha, antes de criar a run, se a gold mudou desde o início.
- Cada tarefa de modelo executa o notebook do modelo (ml/notebooks/<modelo>/<modelo>.ipynb, papermill)
  no venv do atlas_ml (@task.external_python), com os parâmetros da tarefa. Os notebooks vêm de
  ATLAS_NOTEBOOKS_DIR (no stack, o clone do git-sync) e gravam o resultado num arquivo do diretório
  da execução (ATLAS_PIPELINE_DIR/<run_id>/), que a tarefa lê; o notebook executado vira artefato da
  run. A comparação é código da própria DAG, não notebook.
- ATLAS_PIPELINE_RUN = run_id da DAG: vira a tag atlas.pipeline_run de todas as runs; a comparação
  de cada horizonte junta as runs por ela e pelo horizonte, listando os modelos que faltarem.
- Um horizonte que falha não impede os outros; os modelos de um horizonte treinam em paralelo
  limitado por max_active_tasks.
- Recursos (VPS de hml: 4 CPUs, 8 GB): os treinos usam o pool `atlas_treino` (2 vagas, criado pelo
  init.sh); LSTM, Bayesiano e Chronos ocupam as 2 vagas (um pesado por vez), os demais 1. Cada
  treino tem até 3 h e a execução inteira até 12 h; ATLAS_THREADS limita as threads de cada um.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from airflow.providers.standard.operators.trigger_dagrun import TriggerDagRunOperator
from airflow.sdk import DAG, Param, get_current_context, task, task_group

ATLAS_ML_PYTHON = "/opt/atlas-ml/bin/python"
BASES = ["baseline_bayes", "chronos", "catboost", "svr", "lstm"]
STACKED = ["catboost", "svr", "lstm"]
HORIZONTES = [1, 2, 3, 4]
# Pool dos treinos: os pesados (memória e CPU) ocupam o pool inteiro, um por vez
POOL_TREINO = "atlas_treino"
PESADOS = {"lstm", "baseline_bayes", "chronos"}
TEMPO_MAX_TREINO = timedelta(hours=3)


def _recursos(nome: str) -> dict:
    return {
        "pool": POOL_TREINO,
        "pool_slots": 2 if nome in PESADOS else 1,
        "execution_timeout": TEMPO_MAX_TREINO,
    }


# Tarefas de ML no venv do atlas_ml (o ambiente do Airflow não tem MLflow, CatBoost nem PyTorch).
# O decorador fica literal em cada função: o Airflow remove esse texto ao copiar a função para o venv.


@task(multiple_outputs=True)
def configuracao() -> dict:
    """Janela e semente desta execução (parâmetros do disparo), como números e não como texto."""
    params = get_current_context()["params"]
    return {"window": int(params["window"]), "seed": int(params["seed"]), "fonte": str(params["fonte"] or "")}


@task
def lista_de_horizontes() -> list[int]:
    """Horizontes desta execução (parâmetro `horizons`), de 1 a 4 semanas, sem repetição."""
    pedidos = get_current_context()["params"]["horizons"]
    horizontes = sorted({int(h) for h in pedidos})
    if not horizontes or horizontes[0] < 1 or horizontes[-1] > 4:
        raise ValueError(f"horizons deve ter valores de 1 a 4; recebido {pedidos}")
    return horizontes


@task.external_python(python="/opt/atlas-ml/bin/python", expect_airflow=False, multiple_outputs=True)
def iniciar_execucao(pipeline_run, fonte="") -> dict:
    """Pasta própria da execução e as versões de partida: do notebook e da gold.

    Sem snapshot, a versão da gold fixa os dados da execução: cada notebook a recebe como
    `data_version_esperada` e falha, antes de criar a run, se a gold foi reconstruída no meio.
    """
    import os

    from atlas_ml.forecast.notebook import gold_version, notebook_sha, run_dir

    pasta = run_dir(pipeline_run)
    pasta.mkdir(parents=True, exist_ok=True)
    return {
        "out_dir": str(pasta),
        "notebook_sha": notebook_sha(),
        "data_version": gold_version(os.environ.get("ATLAS_ENV", "dev"), fonte or ""),
    }


@task.external_python(python="/opt/atlas-ml/bin/python", expect_airflow=False)
def treinar(
    model, horizon, pipeline_run, window, seed, out_dir, notebook_sha, data_version, fonte="", base_runs=None
):
    """Executa o notebook do modelo (ml/notebooks/<modelo>/<modelo>.ipynb). Devolve o run_id."""
    from atlas_ml.forecast.notebook import run_model_notebook

    params = {
        "horizon": int(horizon),
        "window": int(window),
        "seed": int(seed),
        "pipeline_run": pipeline_run,
        "data_version_esperada": data_version,
        "fonte": fonte or "",
    }
    if base_runs:
        params["base_runs"] = dict(base_runs)
    return run_model_notebook(model, params, out_dir, f"train-{model}-h{horizon}", notebook_sha)["run_id"]


@task.external_python(
    python="/opt/atlas-ml/bin/python", expect_airflow=False, retries=0, trigger_rule="all_done"
)
def comparar(horizon, pipeline_run, _depende_de=None):
    """Compara as runs de um horizonte nesta execução e registra a run `compare`.

    Roda mesmo com modelos faltando (aparecem em `atlas.missing_models`). É código da DAG, não
    notebook, e o corpo é autocontido porque roda no venv do atlas_ml como `external_python`.
    """
    import os
    import tempfile
    from pathlib import Path

    import mlflow
    import pandas as pd

    from atlas_ml.config import load_settings
    from atlas_ml.tracking import atlas_run

    modelos = ("baseline_bayes", "catboost", "svr", "lstm", "chronos", "ensemble")
    colunas = ["test_nrmse_mean", "test_mae_mean", "test_rmse_mean", "test_r2_mean", "test_interval_coverage"]
    experimento = os.environ.get("ATLAS_FORECAST_EXPERIMENT", "dengue-forecast-br")
    settings = load_settings()
    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    exp = mlflow.get_experiment_by_name(f"atlas/{experimento}")
    if exp is None:
        raise ValueError(f"Experimento atlas/{experimento} não existe.")
    filtro = f"tags.`atlas.pipeline_run` = '{pipeline_run}' and tags.`atlas.horizon` = '{int(horizon)}'"
    runs = mlflow.search_runs([exp.experiment_id], filter_string=filtro, output_format="list")
    data_version, linhas = None, []
    for run in runs:
        tags = run.data.tags
        data_version = data_version or tags.get("atlas.data_version")
        nome = tags.get("atlas.forecast_model")
        if not nome or run.info.status != "FINISHED":
            continue
        metricas = {c: run.data.metrics.get(c) for c in colunas}
        linhas.append({"model": nome, "run_id": run.info.run_id, **metricas})
    if data_version is None:
        raise ValueError(f"Nenhuma run com atlas.pipeline_run={pipeline_run} e horizonte {horizon}.")
    tabela = pd.DataFrame(linhas, columns=["model", "run_id", *colunas])
    # se um modelo rodou mais de uma vez na mesma execução (retentativa), fica a última
    tabela = tabela.drop_duplicates("model", keep="first")
    for m in [m for m in modelos if m not in set(tabela["model"])]:
        tabela.loc[len(tabela)] = {"model": m, "run_id": None}
    tabela = tabela.sort_values("test_nrmse_mean", na_position="last").reset_index(drop=True)
    ordenados = tabela.dropna(subset=["test_nrmse_mean"])
    ausentes = tabela.loc[tabela["test_nrmse_mean"].isna(), "model"].tolist()
    tags = {
        "atlas.pipeline_run": pipeline_run,
        "atlas.model_family": "compare",
        "atlas.horizon": str(int(horizon)),
        "atlas.missing_models": ",".join(ausentes) or "-",
    }
    if len(ordenados):
        tags["atlas.best_model"] = ordenados.iloc[0]["model"]
    with (
        atlas_run(
            settings, experimento, data_version=data_version, run_name="compare", extra_tags=tags
        ) as run,
        tempfile.TemporaryDirectory() as tmp,
    ):
        caminho = Path(tmp) / "comparison.csv"
        tabela.to_csv(caminho, index=False)
        mlflow.log_artifact(str(caminho))
        mlflow.log_metrics(
            {f"{r.model}.test_nrmse_mean": float(r.test_nrmse_mean) for r in ordenados.itertuples()}
        )
        mlflow.log_params({"models_ok": len(ordenados), "models_missing": len(ausentes)})
    return run.info.run_id


@task.external_python(
    python="/opt/atlas-ml/bin/python", expect_airflow=False, retries=0, trigger_rule="all_done"
)
def limpar(out_dir, _depende_de=None):
    """Remove o diretório desta execução, com sucesso ou falha."""
    from atlas_ml.forecast.notebook import clean_dir

    clean_dir(out_dir)


@task_group(group_id="horizonte")
def por_horizonte(
    horizon: int,
    pipeline_run: str,
    window: int,
    seed: int,
    out_dir: str,
    notebook_sha: str,
    data_version: str,
    fonte: str,
):
    """Seis modelos de um horizonte: bases em paralelo, ensemble sobre as três empilhadas."""
    comuns = (pipeline_run, window, seed, out_dir, notebook_sha, data_version, fonte)
    runs = {
        nome: treinar.override(task_id=f"train_{nome}", **_recursos(nome))(nome, horizon, *comuns)
        for nome in BASES
    }
    ensemble = treinar.override(task_id="train_ensemble", **_recursos("ensemble"))(
        "ensemble", horizon, *comuns, {nome: runs[nome] for nome in STACKED}
    )
    comparar(horizon, pipeline_run, [runs["baseline_bayes"], runs["chronos"], ensemble])


with DAG(
    dag_id="atlas_dengue_forecast_br",
    description="Treina baseline bayesiano, Chronos, CatBoost, SVR, LSTM e ensemble em 4 horizontes.",
    schedule=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    # MCMC, LSTM e Chronos em paralelo saturam a CPU (o pool atlas_treino limita os pesados)
    max_active_tasks=2,
    dagrun_timeout=timedelta(hours=12),
    tags=["atlas", "ml", "forecast"],
    # Todos opcionais: disparar sem configuração usa janela 12, horizontes 1 a 4 e semente 42
    params={
        "window": Param(12, type="integer", minimum=1, description="Opcional. Semanas de histórico."),
        "horizons": Param(
            HORIZONTES,
            type="array",
            items={"type": "integer", "minimum": 1, "maximum": 4},
            description="Opcional. Horizontes em semanas (1 a 4).",
        ),
        "seed": Param(42, type="integer", description="Opcional. Semente."),
        "fonte": Param(
            "",
            # vazio vira None no disparo pela etl_brasil (e no formulário da UI): None = gold inteira
            type=["null", "string"],
            description="Opcional. Tabela projeto.dataset.tabela no lugar da gold (ex.: amostra avulsa).",
        ),
    },
    default_args={"owner": "atlas", "retries": 1, "retry_delay": timedelta(minutes=2)},
) as dag:
    pipeline_run = "{{ run_id }}"
    config = configuracao()
    inicio = iniciar_execucao(pipeline_run, config["fonte"])
    horizontes = lista_de_horizontes()
    grupos = por_horizonte.partial(
        pipeline_run=pipeline_run,
        window=config["window"],
        seed=config["seed"],
        out_dir=inicio["out_dir"],
        notebook_sha=inicio["notebook_sha"],
        data_version=inicio["data_version"],
        fonte=config["fonte"],
    ).expand(horizon=horizontes)

    # a exportação só precisa de algum horizonte com modelo registrado
    exportar = TriggerDagRunOperator(
        task_id="exportar",
        trigger_dag_id="process_forecast_export_atlas",
        trigger_rule="none_failed_min_one_success",
        wait_for_completion=False,
        retries=0,
    )
    grupos >> exportar
    # o diretório desta execução some no fim, com sucesso ou falha (trigger_rule all_done)
    grupos >> limpar(inicio["out_dir"])
