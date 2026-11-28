"""Fábrica das DAGs de modelo de previsão (`atlas_forecast_<modelo>`, mudança add-forecast-model-dags).

Cada modelo tem a própria DAG do Airflow, num arquivo `airflow/dags/atlas_forecast_<modelo>.py` que só
chama `criar_dag_modelo(<modelo>)`. Ela treina o modelo nos horizontes pedidos executando o notebook
dele (ml/notebooks/<modelo>/<modelo>.ipynb, papermill) e registra a run e o modelo no MLflow:

    configuracao ─► lista_de_horizontes ─► iniciar ─► horizonte (1..4, mapeado):
                                                        [bases ─►] treinar
                                                    ─► concluir (all_success: falha se algum horizonte falhou)
                                                    ─► limpar (all_done: remove a pasta da execução)

- Disparada sozinha, treina e registra; não compara nem exporta. Disparada pelo orquestrador
  (atlas_dengue_forecast_br), recebe `pipeline_run` e as versões da gold e dos notebooks na `conf`.
- `bases` só existe no ensemble: busca no MLflow, por horizonte, as runs concluídas de CatBoost, SVR e
  LSTM (as do mesmo `pipeline_run` quando ele vem do orquestrador; senão, as mais recentes com a mesma
  versão da gold) e falha nomeando o modelo que faltar.
- Um horizonte que falha não para os outros (grupo mapeado); a run da DAG termina com falha.
- Recursos: pool `atlas_treino`; LSTM, bayesiano e Chronos ocupam as 2 vagas, os demais 1; até 3 h por
  treino. As DAGs nascem despausadas (só rodam por disparo), para o orquestrador não esperar à toa.

As tarefas external_python rodam o corpo da função no venv do atlas_ml (o Airflow não tem MLflow,
CatBoost nem PyTorch): o decorador fica literal em cada função e o corpo é autocontido (nada deste
módulo lá dentro); o log delas é por print(flush=True).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from airflow.sdk import DAG, Param, get_current_context, task, task_group

log = logging.getLogger(__name__)

MODELOS = ("baseline_bayes", "chronos", "catboost", "svr", "lstm", "ensemble")
BASES = ("baseline_bayes", "chronos", "catboost", "svr", "lstm")
STACKED = ("catboost", "svr", "lstm")  # alimentam o ensemble (stacking)
HORIZONTES = [1, 2, 3, 4]  # semanas à frente
POOL_TREINO = "atlas_treino"
PESADOS = {"lstm", "baseline_bayes", "chronos"}
TEMPO_MAX_TREINO = timedelta(hours=3)
TEMPO_MAX_EXECUCAO = timedelta(hours=8)


def dag_id_do_modelo(modelo: str) -> str:
    return f"atlas_forecast_{modelo}"


def recursos(modelo: str) -> dict:
    """Pool, vagas e tempo máximo de um treino (os pesados ocupam as 2 vagas do pool)."""
    return {
        "pool": POOL_TREINO,
        "pool_slots": 2 if modelo in PESADOS else 1,
        "execution_timeout": TEMPO_MAX_TREINO,
    }


def validar_horizontes(pedidos) -> list[int]:
    """Horizontes de 1 a 4 semanas, sem repetição e em ordem; erro claro fora disso."""
    horizontes = sorted({int(h) for h in (pedidos or [])})
    if not horizontes or horizontes[0] < 1 or horizontes[-1] > 4:
        raise ValueError(f"horizons deve ter valores de 1 a 4; recebido {pedidos}")
    return horizontes


def params_comuns() -> dict:
    """Parâmetros das DAGs de previsão (as de modelo e o orquestrador): todos opcionais."""
    return {
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
    }


# ---------------------------------------------------------------------------------------
# 1) Parâmetros e início
# ---------------------------------------------------------------------------------------
@task(multiple_outputs=True)
def configuracao() -> dict:
    """Parâmetros efetivos: janela, semente, fonte e a execução (do orquestrador ou desta DAG)."""
    ctx = get_current_context()
    params, run = ctx["params"], ctx["dag_run"]
    externo = str(params.get("pipeline_run") or "")
    cfg = {
        "window": int(params["window"]),
        "seed": int(params["seed"]),
        "fonte": str(params["fonte"] or ""),
        # sem pipeline_run na conf, a execução é esta DAG (disparo isolado)
        "pipeline_run": externo or run.run_id,
        "pelo_orquestrador": bool(externo),
        "data_version": str(params.get("data_version") or ""),
        "notebook_sha": str(params.get("notebook_sha") or ""),
    }
    log.info(
        "execução %s (tipo %s): janela=%d | semente=%d | dados=%s | %s",
        run.run_id,
        run.run_type,
        cfg["window"],
        cfg["seed"],
        cfg["fonte"] or "gold do ambiente (inteira)",
        f"disparada pelo orquestrador (pipeline_run={externo})"
        if externo
        else "disparo isolado: treina e registra, sem comparar nem exportar",
    )
    if run.conf:
        log.info("conf recebida no disparo: %s", dict(run.conf))
    return cfg


@task
def lista_de_horizontes() -> list[int]:
    """Horizontes desta execução (parâmetro `horizons`), de 1 a 4 semanas, sem repetição."""
    horizontes = validar_horizontes(get_current_context()["params"]["horizons"])
    log.info("horizontes: %s semana(s) à frente", horizontes)
    return horizontes


@task.external_python(python="/opt/atlas-ml/bin/python", expect_airflow=False, multiple_outputs=True)
def iniciar(model, pipeline_run, fonte="", data_version="", notebook_sha="") -> dict:
    """Pasta da execução deste modelo e as versões de partida (recebidas do orquestrador ou atuais)."""
    import os

    from atlas_ml.forecast.notebook import gold_version, notebooks_dir, run_dir
    from atlas_ml.forecast.notebook import notebook_sha as sha_atual

    env = os.environ.get("ATLAS_ENV", "dev")
    pasta = run_dir(pipeline_run) / model
    pasta.mkdir(parents=True, exist_ok=True)
    sha = notebook_sha or sha_atual()
    versao_gold = data_version or gold_version(env, fonte or "")
    origem = "do orquestrador" if data_version else "lidas agora"
    print(f"ambiente: {env} | modelo: {model} | execução (atlas.pipeline_run): {pipeline_run}", flush=True)
    print(f"pasta da execução: {pasta} (removida pela tarefa limpar no fim)", flush=True)
    print(f"versões ({origem}): notebook {sha} | dados {versao_gold}", flush=True)
    print(
        f"MLflow: {os.environ.get('MLFLOW_TRACKING_URI', '-')} | experimento "
        f"atlas/{os.environ.get('ATLAS_FORECAST_EXPERIMENT', 'dengue-forecast-br')} | "
        f"threads por treino (ATLAS_THREADS): {os.environ.get('ATLAS_THREADS', '-')}",
        flush=True,
    )
    nb = notebooks_dir() / model / f"{model}.ipynb"
    if not nb.is_file():
        raise FileNotFoundError(f"Notebook do modelo {model} não encontrado: {nb} (ATLAS_NOTEBOOKS_DIR)")
    print(f"notebook: {nb} ({nb.stat().st_size / 1024:.0f} KB)", flush=True)
    return {"out_dir": str(pasta), "notebook_sha": sha, "data_version": versao_gold}


# ---------------------------------------------------------------------------------------
# 2) Runs de base do ensemble e treino
# ---------------------------------------------------------------------------------------
@task.external_python(python="/opt/atlas-ml/bin/python", expect_airflow=False)
def bases(horizon, pipeline_run, pelo_orquestrador, data_version):
    """Runs de CatBoost, SVR e LSTM que o ensemble deste horizonte vai empilhar.

    Pelo orquestrador: as runs concluídas do mesmo `pipeline_run`. Sozinho: as concluídas mais
    recentes com a mesma versão da gold. Falha nomeando o modelo que faltar.
    """
    import os

    import mlflow

    from atlas_ml.config import load_settings

    empilhados = ("catboost", "svr", "lstm")
    experimento = os.environ.get("ATLAS_FORECAST_EXPERIMENT", "dengue-forecast-br")
    mlflow.set_tracking_uri(load_settings().mlflow_tracking_uri)
    exp = mlflow.get_experiment_by_name(f"atlas/{experimento}")
    if exp is None:
        raise ValueError(f"Experimento atlas/{experimento} não existe.")
    if pelo_orquestrador:
        criterio = f"tags.`atlas.pipeline_run` = '{pipeline_run}'"
    else:
        criterio = f"tags.`atlas.data_version` = '{data_version}'"
    escolhidas, faltam = {}, []
    for modelo in empilhados:
        filtro = (
            f"{criterio} and tags.`atlas.forecast_model` = '{modelo}' "
            f"and tags.`atlas.horizon` = '{int(horizon)}' and attributes.status = 'FINISHED'"
        )
        runs = mlflow.search_runs(
            [exp.experiment_id],
            filter_string=filtro,
            order_by=["attributes.start_time DESC"],
            max_results=1,
            output_format="list",
        )
        if not runs:
            faltam.append(modelo)
            continue
        run = runs[0]
        escolhidas[modelo] = run.info.run_id
        p = run.data.params
        print(
            f"  {modelo} h{horizon}: run {run.info.run_id} (pipeline_run "
            f"{run.data.tags.get('atlas.pipeline_run', '-')}, janela {p.get('window', '-')}, "
            f"semente {p.get('seed', '-')})",
            flush=True,
        )
    if faltam:
        onde = f"no pipeline_run {pipeline_run}" if pelo_orquestrador else f"com os dados {data_version}"
        raise ValueError(
            f"Ensemble h{horizon}: falta run concluída de {', '.join(faltam)} {onde}. "
            "Treine esses modelos antes (DAGs atlas_forecast_<modelo>) ou dispare o orquestrador."
        )
    return escolhidas


@task.external_python(python="/opt/atlas-ml/bin/python", expect_airflow=False)
def treinar(
    model, horizon, pipeline_run, window, seed, out_dir, notebook_sha, data_version, fonte="", base_runs=None
):
    """Executa o notebook do modelo (ml/notebooks/<modelo>/<modelo>.ipynb). Devolve o run_id."""
    import os
    import time

    from atlas_ml.forecast.notebook import notebooks_dir, run_model_notebook

    params = {
        "horizon": int(horizon),
        "window": int(window),
        "seed": int(seed),
        "pipeline_run": pipeline_run,
        "data_version_esperada": data_version,
        "fonte": fonte or "",
    }
    if base_runs:
        # ensemble: as runs dos modelos empilhados deste horizonte (as previsões deles viram features)
        params["base_runs"] = dict(base_runs)
    nome = f"train-{model}-h{horizon}"
    print(f"=== {model}, horizonte {horizon} semana(s) à frente", flush=True)
    print(f"notebook: {notebooks_dir() / model / (model + '.ipynb')} (versão {notebook_sha})", flush=True)
    print(f"parâmetros enviados ao notebook: {params}", flush=True)
    print(
        f"dados esperados: {data_version} | threads: {os.environ.get('ATLAS_THREADS', '-')} | "
        f"notebook executado: {out_dir}/{nome}.ipynb",
        flush=True,
    )
    t0 = time.perf_counter()
    try:
        resultado = run_model_notebook(model, params, out_dir, nome, notebook_sha)
    except Exception as exc:
        # papermill traz a célula que falhou no erro; o notebook parcial fica na pasta da execução
        minutos = (time.perf_counter() - t0) / 60
        print(
            f"FALHOU {model} h{horizon} depois de {minutos:.1f} min: {type(exc).__name__}: {str(exc)[:2000]}",
            flush=True,
        )
        print(f"notebook parcial (até a célula que falhou): {out_dir}/{nome}.ipynb", flush=True)
        raise
    minutos = (time.perf_counter() - t0) / 60
    metricas = resultado.get("metrics") or {}
    print(f"concluído em {minutos:.1f} min | run do MLflow: {resultado['run_id']}", flush=True)
    print(
        f"versão registrada no Model Registry: {resultado.get('model_version') or '(não registrou)'}",
        flush=True,
    )
    if metricas:
        largura = max(len(k) for k in metricas)
        print("métricas de teste:", flush=True)
        for chave, valor in sorted(metricas.items()):
            print(
                f"  {chave.ljust(largura)}  {valor:.6g}" if valor is not None else f"  {chave}  -", flush=True
            )
    else:
        print("AVISO: o notebook não devolveu métricas de teste", flush=True)
    return resultado["run_id"]


# ---------------------------------------------------------------------------------------
# 3) Fim
# ---------------------------------------------------------------------------------------
@task(trigger_rule="all_success", retries=0)
def concluir(runs=None) -> None:
    """Só roda se todos os horizontes treinaram: sem ela, a run da DAG terminaria com sucesso."""
    log.info("todos os horizontes concluíram: runs %s", list(runs or []))


@task.external_python(
    python="/opt/atlas-ml/bin/python", expect_airflow=False, retries=0, trigger_rule="all_done"
)
def limpar(out_dir, _depende_de=None):
    """Remove a pasta desta execução do modelo, com sucesso ou falha."""
    from pathlib import Path

    from atlas_ml.forecast.notebook import clean_dir

    pasta = Path(out_dir)
    if pasta.is_dir():
        arquivos = [p for p in pasta.rglob("*") if p.is_file()]
        total = sum(p.stat().st_size for p in arquivos)
        print(f"pasta {pasta}: {len(arquivos)} arquivo(s), {total / 1024 / 1024:.1f} MB", flush=True)
        for p in sorted(arquivos)[:50]:
            print(f"  {p.relative_to(pasta)} ({p.stat().st_size / 1024:.0f} KB)", flush=True)
        # os notebooks executados já foram anexados às runs do MLflow (artefato notebook/)
    else:
        print(f"pasta {pasta} já não existe", flush=True)
    clean_dir(out_dir)
    print(f"pasta {pasta} removida", flush=True)


def criar_dag_modelo(modelo: str) -> DAG:
    """A DAG `atlas_forecast_<modelo>`: treina e registra o modelo nos horizontes pedidos."""
    if modelo not in MODELOS:
        raise ValueError(f"Modelo desconhecido: {modelo!r} (use {', '.join(MODELOS)})")

    @task_group(group_id="horizonte")
    def por_horizonte(
        horizon, pipeline_run, pelo_orquestrador, window, seed, out_dir, notebook_sha, data_version, fonte
    ):
        base_runs = None
        if modelo == "ensemble":
            base_runs = bases(horizon, pipeline_run, pelo_orquestrador, data_version)
        return treinar.override(task_id="treinar", **recursos(modelo))(
            modelo, horizon, pipeline_run, window, seed, out_dir, notebook_sha, data_version, fonte, base_runs
        )

    params = params_comuns()
    params.update(
        {
            "pipeline_run": Param(
                "",
                type=["null", "string"],
                description="Opcional (o orquestrador preenche). Vazio: o run_id desta execução.",
            ),
            "data_version": Param(
                "",
                type=["null", "string"],
                description="Opcional (o orquestrador preenche). Vazio: a versão atual da gold.",
            ),
            "notebook_sha": Param(
                "",
                type=["null", "string"],
                description="Opcional (o orquestrador preenche). Vazio: a versão atual dos notebooks.",
            ),
        }
    )
    with DAG(
        dag_id=dag_id_do_modelo(modelo),
        description=f"Treina o {modelo} e registra no MLflow (não compara nem exporta).",
        doc_md=__doc__,
        schedule=None,  # só por disparo: o orquestrador atlas_dengue_forecast_br ou à mão
        start_date=datetime(2026, 1, 1),
        catchup=False,
        max_active_runs=1,
        max_active_tasks=2,
        dagrun_timeout=TEMPO_MAX_EXECUCAO,
        is_paused_upon_creation=False,  # sem agendamento: despausada só fica pronta para o disparo
        tags=["atlas", "ml", "forecast", modelo],
        params=params,
        default_args={"owner": "atlas", "retries": 1, "retry_delay": timedelta(minutes=2)},
    ) as dag:
        cfg = configuracao()
        horizontes = lista_de_horizontes()
        inicio = iniciar(modelo, cfg["pipeline_run"], cfg["fonte"], cfg["data_version"], cfg["notebook_sha"])
        grupos = por_horizonte.partial(
            pipeline_run=cfg["pipeline_run"],
            pelo_orquestrador=cfg["pelo_orquestrador"],
            window=cfg["window"],
            seed=cfg["seed"],
            out_dir=inicio["out_dir"],
            notebook_sha=inicio["notebook_sha"],
            data_version=inicio["data_version"],
            fonte=cfg["fonte"],
        ).expand(horizon=horizontes)
        concluir(grupos)
        limpar(inicio["out_dir"], grupos)
    return dag
