"""Previsão de dengue por UF (Brasil): treina os modelos em 4 horizontes e registra tudo no MLflow.

Sem agendamento: disparada manualmente (de preferência depois da process_etl_atlas). Ao fim,
dispara a exportação para o BigQuery (process_forecast_export_atlas), de onde o site lê.

    prepare ─► por horizonte (1..4, em paralelo limitado):
                 train_baseline_bayes ──────────────────────────┐
                 train_chronos ─────────────────────────────────┤
                 train_catboost ─┐                              ├─► compare (all_done)
                 train_svr ──────┼─► train_ensemble ────────────┘
                 train_lstm ─────┘
              ─► exportar (dispara process_forecast_export_atlas)

- prepare: lê a gold_dengue_casos_provaveis_uf_semanal e grava o snapshot (run `dataset`);
  todos os modelos e horizontes usam esse mesmo snapshot (mesma atlas.data_version).
- As tarefas são Python (TaskFlow) e rodam no venv do atlas_ml (@task.external_python): chamam
  as funções de atlas_ml.forecast.pipeline, as mesmas do CLI `atlas-ml forecast ...`.
- ATLAS_PIPELINE_RUN = run_id da DAG: vira a tag atlas.pipeline_run de todas as runs; a comparação
  de cada horizonte junta as runs por ela e pelo horizonte, listando os modelos que faltarem.
- Um horizonte que falha não impede os outros; os modelos de um horizonte treinam em paralelo
  limitado por max_active_tasks.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from airflow.providers.standard.operators.trigger_dagrun import TriggerDagRunOperator
from airflow.sdk import DAG, Param, get_current_context, task, task_group

ATLAS_ML_PYTHON = "/opt/atlas-ml/bin/python"
BASES = ["baseline_bayes", "chronos", "catboost", "svr", "lstm"]
STACKED = ["catboost", "svr", "lstm"]
HORIZONTES = [1, 2, 3, 4]


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


@task.external_python(python="/opt/atlas-ml/bin/python", expect_airflow=False)
def prepare(fonte="") -> str:
    from atlas_ml.forecast.pipeline import prepare_snapshot

    return prepare_snapshot(fonte)


@task.external_python(python="/opt/atlas-ml/bin/python", expect_airflow=False)
def treinar(model, horizon, dataset_run, pipeline_run, window, seed, base_runs=None):
    from atlas_ml.forecast.pipeline import train

    return train(model, horizon, dataset_run, pipeline_run, window, seed, base_runs)


@task.external_python(
    python="/opt/atlas-ml/bin/python", expect_airflow=False, retries=0, trigger_rule="all_done"
)
def comparar(horizon, pipeline_run, _depende_de=None):
    """Registra a comparação mesmo com modelos faltando (aparecem em atlas.missing_models)."""
    from atlas_ml.forecast.pipeline import compare_horizon

    return compare_horizon(pipeline_run, horizon)


@task_group(group_id="horizonte")
def por_horizonte(horizon: int, dataset_run: str, pipeline_run: str, window: int, seed: int):
    """Seis modelos de um horizonte: bases em paralelo, ensemble sobre as três empilhadas."""
    runs = {
        nome: treinar.override(task_id=f"train_{nome}")(
            nome, horizon, dataset_run, pipeline_run, window, seed
        )
        for nome in BASES
    }
    ensemble = treinar.override(task_id="train_ensemble")(
        "ensemble",
        horizon,
        dataset_run,
        pipeline_run,
        window,
        seed,
        {nome: runs[nome] for nome in STACKED},
    )
    comparar(horizon, pipeline_run, [runs["baseline_bayes"], runs["chronos"], ensemble])


with DAG(
    dag_id="atlas_dengue_forecast_br",
    description="Treina baseline bayesiano, Chronos, CatBoost, SVR, LSTM e ensemble em 4 horizontes.",
    schedule=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    # MCMC, LSTM e Chronos em paralelo saturam a CPU
    max_active_tasks=3,
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
            type="string",
            description="Opcional. Tabela projeto.dataset.tabela no lugar da gold (ex.: amostra avulsa).",
        ),
    },
    default_args={"owner": "atlas", "retries": 1, "retry_delay": timedelta(minutes=2)},
) as dag:
    pipeline_run = "{{ run_id }}"
    config = configuracao()
    snapshot = prepare(config["fonte"])
    horizontes = lista_de_horizontes()
    grupos = por_horizonte.partial(
        dataset_run=snapshot,
        pipeline_run=pipeline_run,
        window=config["window"],
        seed=config["seed"],
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
