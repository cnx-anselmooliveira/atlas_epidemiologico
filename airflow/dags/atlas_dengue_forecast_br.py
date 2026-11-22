"""Previsão de dengue por UF (Brasil): treina os modelos em 4 horizontes e registra tudo no MLflow.

Sem agendamento: disparada pela etl_brasil (só quando a gold muda) ou à mão. Ao fim,
dispara a exportação para o BigQuery (process_forecast_export_atlas), de onde o site lê.

    iniciar_execucao ─► prepare ─► por horizonte (1..4, em paralelo limitado):
                 train_baseline_bayes ──────────────────────────┐
                 train_chronos ─────────────────────────────────┤
                 train_catboost ─┐                              ├─► compare (all_done)
                 train_svr ──────┼─► train_ensemble ────────────┘
                 train_lstm ─────┘
              ─► exportar (dispara process_forecast_export_atlas)
              ─► limpar (all_done: remove o diretório da execução)

- prepare: lê a gold_dengue_casos_provaveis_uf_semanal e grava o snapshot (run `dataset`);
  todos os modelos e horizontes usam esse mesmo snapshot (mesma atlas.data_version).
- Cada tarefa de ML executa o notebook do pipeline (ml/notebooks/forecast_pipeline.ipynb, papermill)
  no venv do atlas_ml (@task.external_python), com o passo e os parâmetros da tarefa. O notebook
  vem de ATLAS_NOTEBOOKS_DIR (no stack, o clone do git-sync) e grava o resultado do passo num
  arquivo do diretório da execução (ATLAS_PIPELINE_DIR/<run_id>/), que a tarefa lê; o notebook
  executado vira artefato da run. `iniciar_execucao` cria o diretório e registra a versão do
  notebook; se ela mudar no meio da execução (um merge), as tarefas seguintes falham com mensagem.
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
def iniciar_execucao(pipeline_run) -> dict:
    """Diretório próprio desta execução (arquivos entre tarefas) e a versão do notebook de partida."""
    from atlas_ml.forecast.notebook import notebook_sha, run_dir

    pasta = run_dir(pipeline_run)
    pasta.mkdir(parents=True, exist_ok=True)
    return {"out_dir": str(pasta), "notebook_sha": notebook_sha()}


@task.external_python(python="/opt/atlas-ml/bin/python", expect_airflow=False)
def prepare(fonte, pipeline_run, out_dir, notebook_sha) -> str:
    """Passo `prepare` do notebook: snapshot da gold numa run `dataset`. Devolve o dataset_run_id."""
    from atlas_ml.forecast.notebook import run_step

    params = {"fonte": fonte or "", "pipeline_run": pipeline_run}
    return run_step("prepare", params, out_dir, "prepare", notebook_sha)["dataset_run_id"]


@task.external_python(python="/opt/atlas-ml/bin/python", expect_airflow=False)
def treinar(model, horizon, dataset_run, pipeline_run, window, seed, out_dir, notebook_sha, base_runs=None):
    """Passo `train` do notebook: um modelo num horizonte. Devolve o run_id."""
    from atlas_ml.forecast.notebook import run_step

    params = {
        "model": model,
        "horizon": int(horizon),
        "dataset_run": dataset_run,
        "pipeline_run": pipeline_run,
        "window": int(window),
        "seed": int(seed),
    }
    if base_runs:
        params["base_runs"] = dict(base_runs)
    return run_step("train", params, out_dir, f"train-{model}-h{horizon}", notebook_sha)["run_id"]


@task.external_python(
    python="/opt/atlas-ml/bin/python", expect_airflow=False, retries=0, trigger_rule="all_done"
)
def comparar(horizon, pipeline_run, out_dir, notebook_sha, _depende_de=None):
    """Passo `compare` do notebook: registra a comparação mesmo com modelos faltando (aparecem em
    atlas.missing_models)."""
    from atlas_ml.forecast.notebook import run_step

    params = {"horizon": int(horizon), "pipeline_run": pipeline_run}
    return run_step("compare", params, out_dir, f"compare-h{horizon}", notebook_sha)["run_id"]


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
    dataset_run: str,
    pipeline_run: str,
    window: int,
    seed: int,
    out_dir: str,
    notebook_sha: str,
):
    """Seis modelos de um horizonte: bases em paralelo, ensemble sobre as três empilhadas."""
    runs = {
        nome: treinar.override(task_id=f"train_{nome}", **_recursos(nome))(
            nome, horizon, dataset_run, pipeline_run, window, seed, out_dir, notebook_sha
        )
        for nome in BASES
    }
    ensemble = treinar.override(task_id="train_ensemble", **_recursos("ensemble"))(
        "ensemble",
        horizon,
        dataset_run,
        pipeline_run,
        window,
        seed,
        out_dir,
        notebook_sha,
        {nome: runs[nome] for nome in STACKED},
    )
    comparar(
        horizon, pipeline_run, out_dir, notebook_sha, [runs["baseline_bayes"], runs["chronos"], ensemble]
    )


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
    inicio = iniciar_execucao(pipeline_run)
    snapshot = prepare(config["fonte"], pipeline_run, inicio["out_dir"], inicio["notebook_sha"])
    horizontes = lista_de_horizontes()
    grupos = por_horizonte.partial(
        dataset_run=snapshot,
        pipeline_run=pipeline_run,
        window=config["window"],
        seed=config["seed"],
        out_dir=inicio["out_dir"],
        notebook_sha=inicio["notebook_sha"],
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
