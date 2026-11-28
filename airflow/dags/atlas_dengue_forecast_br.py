"""Previsão de dengue por UF (Brasil): orquestra o processo completo dos seis modelos em 4 horizontes.

Sem agendamento: disparada pela etl_brasil (só quando a gold muda) ou à mão. Cada modelo treina na
própria DAG (atlas_forecast_<modelo>, montadas por atlas_ingest/forecast_modelo.py); esta DAG fixa as
versões, dispara cada uma individualmente, compara os modelos e dispara a exportação para o BigQuery
(process_forecast_export_atlas), de onde o site lê.

    configuracao ─► lista_de_horizontes ─► iniciar_execucao ─► conf_dos_modelos ─►
        modelo_baseline_bayes ─┐
        modelo_chronos ────────┤
        modelo_catboost ───────┼─► modelo_ensemble (all_done) ─► comparar por horizonte (all_done)
        modelo_svr ────────────┤                                 ─► algum_resultado ─► exportar
        modelo_lstm ───────────┘

- iniciar_execucao: registra a versão dos notebooks e a da gold e confere que os seis notebooks
  existem. As duas versões vão na conf de cada DAG de modelo: um notebook que começar depois de a gold
  (ou o notebook) mudar falha em vez de misturar versões.
- modelo_<modelo>: TriggerDagRunOperator adiável (a espera fica no triggerer, sem vaga de worker),
  run_id `<run_id desta execução>__<modelo>`, conf com pipeline_run = run_id desta execução. Uma DAG de
  modelo que falha não interrompe as outras; o ensemble roda depois das cinco bases, com sucesso ou
  falha, e busca no MLflow as runs de CatBoost, SVR e LSTM deste pipeline_run.
- comparar[h]: junta as runs do horizonte nesta execução (tag atlas.pipeline_run) e registra a run
  `compare`, listando os modelos que faltaram. É código desta DAG, não notebook.
- algum_resultado / exportar: a exportação só é disparada se algum horizonte teve modelo comparado;
  sem nenhum, a execução termina com falha.
- Recursos: os treinos usam o pool `atlas_treino` dentro das DAGs de modelo; aqui só há espera.

Onde ler o que aconteceu (logs de cada tarefa na UI do Airflow):
- configuracao / lista_de_horizontes: os parâmetros efetivos do disparo (janela, semente, fonte, horizontes);
- iniciar_execucao: ambiente, versão do notebook (SHA do git-sync), versão da gold, MLflow e os notebooks;
- modelo_<modelo>: o run_id disparado (o link leva à DAG do modelo, com o log de cada treino);
- comparar[h]: ranking dos modelos do horizonte por NRMSE, o melhor e os que faltaram.

As tarefas external_python rodam o corpo da função em outro Python (o venv do atlas_ml), então
o log delas é por print(flush=True), que o Airflow captura do subprocesso; nas demais, logging.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from airflow.providers.standard.operators.trigger_dagrun import TriggerDagRunOperator
from airflow.sdk import DAG, get_current_context, task
from atlas_ingest.forecast_modelo import BASES, dag_id_do_modelo, params_comuns, validar_horizontes

log = logging.getLogger(__name__)

TEMPO_MAX_MODELO = timedelta(hours=8)  # mesmo teto da execução de uma DAG de modelo


# ---------------------------------------------------------------------------------------
# 1) Parâmetros e versões da execução
# ---------------------------------------------------------------------------------------
@task(multiple_outputs=True)
def configuracao() -> dict:
    """Janela e semente desta execução (parâmetros do disparo), como números e não como texto."""
    ctx = get_current_context()
    params = ctx["params"]
    cfg = {"window": int(params["window"]), "seed": int(params["seed"]), "fonte": str(params["fonte"] or "")}
    log.info(
        "execução %s (tipo %s): janela=%d semanas de histórico | semente=%d | dados=%s",
        ctx["dag_run"].run_id,
        ctx["dag_run"].run_type,
        cfg["window"],
        cfg["seed"],
        cfg["fonte"] or "gold do ambiente (inteira)",
    )
    if ctx["dag_run"].conf:
        log.info("conf recebida no disparo: %s", dict(ctx["dag_run"].conf))
    return cfg


@task
def lista_de_horizontes() -> list[int]:
    """Horizontes desta execução (parâmetro `horizons`), de 1 a 4 semanas, sem repetição."""
    horizontes = validar_horizontes(get_current_context()["params"]["horizons"])
    log.info(
        "horizontes: %s semana(s) à frente | %d DAG(s) de modelo × %d horizonte(s) = %d treinos",
        horizontes,
        len(BASES) + 1,
        len(horizontes),
        len(horizontes) * (len(BASES) + 1),
    )
    return horizontes


# Tarefas de ML no venv do atlas_ml (o ambiente do Airflow não tem MLflow, CatBoost nem PyTorch).
# O decorador fica literal em cada função: o Airflow remove esse texto ao copiar a função para o venv.
# Pelo mesmo motivo o corpo é autocontido: nada de constantes ou funções deste arquivo lá dentro.


@task.external_python(python="/opt/atlas-ml/bin/python", expect_airflow=False, multiple_outputs=True)
def iniciar_execucao(pipeline_run, fonte="") -> dict:
    """Versões de partida desta execução: dos notebooks e da gold (passadas a cada DAG de modelo)."""
    import os

    from atlas_ml.forecast.notebook import MODEL_NOTEBOOKS, gold_version, notebook_sha, notebooks_dir

    env = os.environ.get("ATLAS_ENV", "dev")
    sha = notebook_sha()
    versao_gold = gold_version(env, fonte or "")
    print(f"ambiente: {env} | execução (atlas.pipeline_run): {pipeline_run}", flush=True)
    print(
        f"versão do notebook: {sha}"
        + (" (cópia da imagem, não do git-sync)" if sha == "local" else " (commit do clone do git-sync)"),
        flush=True,
    )
    # tabela@última modificação: se a gold mudar no meio, os notebooks falham em vez de misturar dados
    print(f"versão dos dados: {versao_gold}", flush=True)
    print(
        f"MLflow: {os.environ.get('MLFLOW_TRACKING_URI', '-')} | experimento "
        f"atlas/{os.environ.get('ATLAS_FORECAST_EXPERIMENT', 'dengue-forecast-br')}",
        flush=True,
    )
    # Conferir os notebooks agora adianta o erro: sem isso, um notebook faltando só apareceria
    # quando a vaga do pool chegasse para aquele modelo, talvez horas depois.
    raiz = notebooks_dir()
    faltando = []
    for modelo in MODEL_NOTEBOOKS:
        nb = raiz / modelo / f"{modelo}.ipynb"
        if nb.is_file():
            print(f"  notebook {modelo}: {nb} ({nb.stat().st_size / 1024:.0f} KB)", flush=True)
        else:
            faltando.append(modelo)
            print(f"  AVISO notebook {modelo}: não encontrado em {nb}", flush=True)
    if faltando:
        print(
            f"AVISO: os treinos de {', '.join(faltando)} vão falhar (ATLAS_NOTEBOOKS_DIR={raiz})", flush=True
        )
    return {"notebook_sha": sha, "data_version": versao_gold}


@task
def conf_dos_modelos(cfg: dict, horizontes: list[int], inicio: dict) -> dict:
    """A conf que cada DAG de modelo recebe: a mesma execução, os mesmos parâmetros e versões."""
    conf = {
        "pipeline_run": get_current_context()["dag_run"].run_id,
        "horizons": list(horizontes),
        "window": int(cfg["window"]),
        "seed": int(cfg["seed"]),
        "fonte": cfg["fonte"] or "",
        "data_version": inicio["data_version"],
        "notebook_sha": inicio["notebook_sha"],
    }
    log.info("conf das DAGs de modelo: %s", conf)
    return conf


def disparar_modelo(modelo: str, conf, **kwargs) -> TriggerDagRunOperator:
    """Dispara a DAG do modelo e espera o fim dela sem ocupar vaga de worker (triggerer)."""
    return TriggerDagRunOperator(
        task_id=f"modelo_{modelo}",
        trigger_dag_id=dag_id_do_modelo(modelo),
        trigger_run_id=f"{{{{ run_id }}}}__{modelo}",
        conf=conf,
        wait_for_completion=True,
        deferrable=True,
        poke_interval=60,
        allowed_states=["success"],
        failed_states=["failed"],
        reset_dag_run=True,  # limpar a tarefa dispara de novo, substituindo a run anterior do modelo
        retries=0,
        execution_timeout=TEMPO_MAX_MODELO,
        **kwargs,
    )


# ---------------------------------------------------------------------------------------
# 2) Comparação dos modelos de um horizonte
# ---------------------------------------------------------------------------------------
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
    # as runs desta execução neste horizonte (a tag atlas.pipeline_run é o run_id da DAG)
    filtro = f"tags.`atlas.pipeline_run` = '{pipeline_run}' and tags.`atlas.horizon` = '{int(horizon)}'"
    runs = mlflow.search_runs([exp.experiment_id], filter_string=filtro, output_format="list")
    print(f"=== horizonte {horizon}: {len(runs)} run(s) no MLflow para {pipeline_run}", flush=True)
    data_version, linhas = None, []
    for run in runs:
        tags = run.data.tags
        data_version = data_version or tags.get("atlas.data_version")
        nome = tags.get("atlas.forecast_model")
        if not nome or run.info.status != "FINISHED":
            # run de um treino que falhou ou ainda aberto: não entra no ranking
            print(
                f"  ignorada: run {run.info.run_id} ({nome or 'sem modelo'}, status {run.info.status})",
                flush=True,
            )
            continue
        metricas = {c: run.data.metrics.get(c) for c in colunas}
        linhas.append({"model": nome, "run_id": run.info.run_id, **metricas})
    if data_version is None:
        raise ValueError(f"Nenhuma run com atlas.pipeline_run={pipeline_run} e horizonte {horizon}.")
    tabela = pd.DataFrame(linhas, columns=["model", "run_id", *colunas])
    # se um modelo rodou mais de uma vez na mesma execução (retentativa), fica a última
    # (search_runs devolve da mais recente para a mais antiga)
    repetidos = tabela["model"][tabela["model"].duplicated()].unique().tolist()
    if repetidos:
        print(f"  modelos com mais de uma run (retentativa; vale a mais recente): {repetidos}", flush=True)
    # reset_index: sem ele, o índice fica com buracos e o `loc[len(tabela)]` abaixo sobrescreve
    # uma linha existente (um modelo concluído sumia do ranking quando havia retentativa)
    tabela = tabela.drop_duplicates("model", keep="first").reset_index(drop=True)
    for m in [m for m in modelos if m not in set(tabela["model"])]:
        tabela.loc[len(tabela)] = {"model": m, "run_id": None}
    # menor NRMSE médio no teste = melhor
    tabela = tabela.sort_values("test_nrmse_mean", na_position="last").reset_index(drop=True)
    ordenados = tabela.dropna(subset=["test_nrmse_mean"])
    ausentes = tabela.loc[tabela["test_nrmse_mean"].isna(), "model"].tolist()

    # ranking legível no log (a mesma tabela vai como comparison.csv para a run compare)
    exibir = tabela.copy()
    exibir[colunas] = exibir[colunas].apply(pd.to_numeric)  # None → NaN, para aparecer como "-"
    exibir.insert(
        0, "pos", [str(i + 1) if pd.notna(v) else "-" for i, v in enumerate(exibir["test_nrmse_mean"])]
    )
    exibir.columns = [c.replace("test_", "").replace("_mean", "") for c in exibir.columns]
    print(
        f"ranking do horizonte {horizon} (dados {data_version}):\n"
        + exibir.to_string(index=False, na_rep="-", float_format=lambda v: f"{v:.4f}"),
        flush=True,
    )
    if len(ordenados) > 1:
        melhor, segundo = ordenados.iloc[0], ordenados.iloc[1]
        print(
            f"melhor: {melhor['model']} (NRMSE {melhor['test_nrmse_mean']:.4f}), "
            f"{(segundo['test_nrmse_mean'] / melhor['test_nrmse_mean'] - 1) * 100:.1f}% à frente de "
            f"{segundo['model']} ({segundo['test_nrmse_mean']:.4f})",
            flush=True,
        )
    elif len(ordenados) == 1:
        print(f"só um modelo concluiu: {ordenados.iloc[0]['model']}", flush=True)
    if ausentes:
        print(f"AVISO: modelos sem resultado neste horizonte: {', '.join(ausentes)}", flush=True)

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
    print(
        f"run compare registrada: {run.info.run_id} "
        f"({len(ordenados)} modelo(s) ok, {len(ausentes)} faltando)",
        flush=True,
    )
    return run.info.run_id


@task(trigger_rule="all_done", retries=0)
def algum_resultado(compares=None) -> list[str]:
    """Falha se nenhum horizonte teve modelo comparado: aí não há o que exportar."""
    ok = [c for c in (compares or []) if c]
    if not ok:
        raise ValueError("Nenhum horizonte teve modelo concluído: a exportação não será disparada.")
    log.info("%d horizonte(s) com comparação registrada: %s", len(ok), ok)
    return ok


with DAG(
    dag_id="atlas_dengue_forecast_br",
    description="Orquestra os seis modelos (uma DAG cada) em 4 horizontes, compara e exporta.",
    doc_md=__doc__,
    schedule=None,  # só por disparo: etl_brasil (quando a gold muda) ou à mão
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    # os disparos esperam no triggerer; o limite real dos treinos é o pool atlas_treino
    max_active_tasks=8,
    dagrun_timeout=timedelta(hours=12),
    tags=["atlas", "ml", "forecast"],
    # Todos opcionais: disparar sem configuração usa janela 12, horizontes 1 a 4 e semente 42
    params=params_comuns(),
    default_args={"owner": "atlas", "retries": 1, "retry_delay": timedelta(minutes=2)},
) as dag:
    pipeline_run = "{{ run_id }}"  # vira a tag atlas.pipeline_run de todas as runs desta execução
    cfg = configuracao()
    horizontes = lista_de_horizontes()
    inicio = iniciar_execucao(pipeline_run, cfg["fonte"])
    conf = conf_dos_modelos(cfg, horizontes, inicio)

    # as cinco bases em paralelo (cada uma na sua DAG); o ensemble depois delas, com sucesso ou falha
    bases = [disparar_modelo(m, conf) for m in BASES]
    ensemble = disparar_modelo("ensemble", conf, trigger_rule="all_done")
    bases >> ensemble

    # all_done: compara o que deu certo mesmo se alguma DAG de modelo falhou
    compares = comparar.partial(pipeline_run=pipeline_run).expand(horizon=horizontes)
    ensemble >> compares

    exportar = TriggerDagRunOperator(
        task_id="exportar",
        trigger_dag_id="process_forecast_export_atlas",
        wait_for_completion=False,
        retries=0,
    )
    algum_resultado(compares) >> exportar
