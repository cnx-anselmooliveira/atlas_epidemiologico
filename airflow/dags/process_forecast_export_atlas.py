"""Exporta as previsões do MLflow para o BigQuery e o bucket (o site lê só de lá).

Sem agendamento: disparada ao fim da atlas_dengue_forecast_br e, quando preciso, à mão.
Idempotente: reexportar a mesma versão sobrescreve as linhas daquela run, sem duplicar.

    configuracao ─► listar_versoes (venv atlas_ml: lê o MLflow) ─► montar[modelo×horizonte]
                 ─► consolidar ─► publicar_figuras ─► carregar_bigquery ─► atualizar_visoes

- listar_versoes: para cada modelo e horizonte, a versão registrada no alias do ambiente
  (@dev, @hml ou @prod, conforme ATLAS_ENV) e os artefatos da run de origem (previsões,
  métricas, figuras), baixados para /opt/airflow/shared. Modelo sem versão no alias não
  derruba a execução: aparece em `ausentes`.
- montar: monta os DataFrames de cada tabela (linha BR ponderada pela população, split futuro).
- consolidar: descarta horizontes com origem diferente da de referência (mesmo snapshot).
- publicar_figuras: copia só PNG de até 500 KB para o bucket, em forecast/<ambiente>/<modelo>/….
- carregar_bigquery: carga em tabelas de apoio e uma transação única troca as linhas das runs
  exportadas; o que o site mostra só muda em atualizar_visoes.
- atualizar_visoes: aponta o "vigente" de cada modelo e horizonte para a run exportada e recria
  as visões forecast_current_* (a API lê estas). Uma falha antes deixa o site como estava.

Acesso: BigQuery e bucket pela Connection `google_cloud_default`; o MLflow pelo
MLFLOW_TRACKING_URI do ambiente (e MLFLOW_TRACKING_USERNAME/PASSWORD, se o servidor tiver
login, como variáveis de stack). Nenhuma chave em código, imagem ou XCom.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

from airflow.sdk import DAG, get_current_context, task

log = logging.getLogger(__name__)

GCP_CONN_ID = "google_cloud_default"
PROJETO = os.environ.get("GCP_PROJECT") or "ppgcc-dengue-project"
DATASET = os.environ.get("ATLAS_FORECAST_DATASET", "forecast")
BUCKET = os.environ.get("ATLAS_LANDING_BUCKET", "ppgcc-bucket")
SHARED = "/opt/airflow/shared/forecast_export"
MODELOS = ["baseline_bayes", "chronos", "catboost", "svr", "lstm", "ensemble"]
HORIZONTES = [1, 2, 3, 4]


@task
def configuracao() -> dict:
    """Ambiente, modelos, horizontes e pasta de trabalho desta execução."""
    ctx = get_current_context()
    run = ctx["run_id"].replace(":", "-").replace("+", "-")
    return {
        "env": os.environ.get("ATLAS_ENV", "dev"),
        "models": MODELOS,
        "horizons": HORIZONTES,
        "out_dir": f"{SHARED}/{run}",
        "tracking_uri": os.environ["MLFLOW_TRACKING_URI"],
    }


@task.external_python(python="/opt/atlas-ml/bin/python", expect_airflow=False)
def listar_versoes(config):
    from atlas_ml.forecast.export_read import read_versions_from_environment

    return read_versions_from_environment(
        config["env"], config["models"], config["horizons"], config["out_dir"], config["tracking_uri"]
    )


@task
def entradas(manifesto: dict) -> list:
    """Uma entrada por modelo e horizonte com versão no alias, para mapear a montagem."""
    for aviso in manifesto["warnings"]:
        log.warning("MLflow: %s", aviso)
    if manifesto["missing"]:
        log.warning("Sem versão no alias %s: %s", manifesto["env"], ", ".join(manifesto["missing"]))
    if not manifesto["entries"]:
        raise ValueError(f"Nenhum modelo com versão no alias {manifesto['env']!r} no MLflow")
    return manifesto["entries"]


@task(
    map_index_template="{{ task.op_kwargs['entrada']['model'] }}-h{{ task.op_kwargs['entrada']['horizon'] }}"
)
def montar(entrada: dict) -> dict:
    """DataFrames de cada tabela para uma run, gravados em parquet ao lado dos artefatos."""
    import pandas as pd
    from atlas_ingest import forecast_export as fe

    pred = pd.read_parquet(entrada["files"]["predictions"])
    future = pd.read_parquet(entrada["files"]["future"])
    by_uf = pd.read_csv(entrada["files"]["metrics_uf"])
    preds = fe.predictions_frame(entrada, pred, future)
    br = fe.brazil_metrics(preds)
    base = Path(entrada["files"]["predictions"]).parent / "frames"
    base.mkdir(parents=True, exist_ok=True)
    arquivos = {
        "forecast_predictions": preds,
        "forecast_metrics": fe.metrics_frame(entrada, br),
        "forecast_metrics_uf": fe.metrics_uf_frame(entrada, by_uf, br),
        "forecast_model_runs": pd.DataFrame([fe.model_runs_row(entrada)]),
    }
    caminhos = {}
    for tabela, frame in arquivos.items():
        caminhos[tabela] = str(base / f"{tabela}.parquet")
        frame.to_parquet(caminhos[tabela], index=False)
    return {
        "key": f"{entrada['model']}-h{entrada['horizon']}",
        "model": entrada["model"],
        "horizon": int(entrada["horizon"]),
        "mlflow_run_id": entrada["mlflow_run_id"],
        "frames": caminhos,
        "future": entrada["files"]["future"],
        "figures": entrada["figures"],
    }


@task
def consolidar(montados: list, manifesto: dict) -> dict:
    """Mantém só os horizontes com a mesma origem de previsão (mesmo snapshot)."""
    import pandas as pd
    from atlas_ingest import forecast_export as fe

    futuros = {m["key"]: pd.read_parquet(m["future"]) for m in montados}
    mantidos, avisos = fe.consistent_origins(futuros)
    for chave, aviso in avisos.items():
        log.warning("%s: %s", chave, aviso)
    validos = [m for m in montados if m["key"] in mantidos]
    return {
        "validos": validos,
        "avisos": list(avisos.values()),
        "ausentes": manifesto["missing"],
        "env": manifesto["env"],
    }


@task
def publicar_figuras(consolidado: dict) -> list:
    """Copia as figuras válidas para o bucket e devolve as linhas de forecast_figures."""
    from airflow.providers.google.cloud.hooks.gcs import GCSHook
    from atlas_ingest import forecast_export as fe

    hook = GCSHook(gcp_conn_id=GCP_CONN_ID)
    linhas = []
    for m in consolidado["validos"]:
        for fig in m["figures"]:
            tamanho = Path(fig["path"]).stat().st_size
            if not fe.valid_figure(fig["name"], tamanho):
                log.warning("%s: figura %s fora do padrão; ignorada", m["key"], fig["name"])
                continue
            objeto = fe.figure_object(
                consolidado["env"], m["model"], m["horizon"], m["mlflow_run_id"], fig["name"]
            )
            hook.upload(bucket_name=BUCKET, object_name=objeto, filename=fig["path"], mime_type="image/png")
            linhas.append(
                {
                    "model": m["model"],
                    "horizon": m["horizon"],
                    "mlflow_run_id": m["mlflow_run_id"],
                    "name": fig["name"],
                    "caption": fig["caption"] or None,
                    "gcs_path": f"gs://{BUCKET}/{objeto}",
                    "size_bytes": tamanho,
                }
            )
    return linhas


@task
def carregar_bigquery(consolidado: dict, figuras: list) -> dict:
    """Carga idempotente: tabelas de apoio + uma transação que troca as linhas das runs."""
    import pandas as pd
    from airflow.providers.google.cloud.hooks.bigquery import BigQueryHook
    from atlas_ingest import forecast_ddl as ddl
    from google.cloud import bigquery

    client = BigQueryHook(gcp_conn_id=GCP_CONN_ID, use_legacy_sql=False).get_client(project_id=PROJETO)
    ddl.garantir_dataset(client, PROJETO, DATASET, os.environ.get("BQ_LOCATION") or "US")
    agora = pd.Timestamp.now(tz="UTC")
    quadros: dict[str, pd.DataFrame] = {}
    for tabela in ("forecast_predictions", "forecast_metrics", "forecast_metrics_uf", "forecast_model_runs"):
        quadros[tabela] = pd.concat(
            [pd.read_parquet(m["frames"][tabela]) for m in consolidado["validos"]], ignore_index=True
        )
    quadros["forecast_figures"] = pd.DataFrame(figuras, columns=ddl.colunas("forecast_figures"))
    quadros["forecast_model_runs"]["trained_at"] = pd.to_datetime(
        quadros["forecast_model_runs"]["trained_at"], utc=True
    )
    comandos = ["BEGIN TRANSACTION;"]
    for tabela, frame in quadros.items():
        frame = frame.copy()
        frame["exported_at"] = agora
        apoio = f"{PROJETO}.{DATASET}._apoio_{tabela}"
        schema = [f for f in ddl.TABELAS[tabela]]
        client.load_table_from_dataframe(
            frame[[f.name for f in schema]],
            apoio,
            job_config=bigquery.LoadJobConfig(schema=schema, write_disposition="WRITE_TRUNCATE"),
        ).result()
        cols = ", ".join(f.name for f in schema)
        runs = f"SELECT DISTINCT mlflow_run_id FROM `{apoio}`"
        if tabela == "forecast_figures":  # runs sem figura também devem limpar as antigas
            runs = ", ".join(f"'{m['mlflow_run_id']}'" for m in consolidado["validos"])
            runs = f"SELECT run FROM UNNEST([{runs}]) AS run"
        comandos.append(
            f"DELETE FROM `{PROJETO}.{DATASET}.{tabela}` WHERE mlflow_run_id IN ({runs});\n"
            f"INSERT INTO `{PROJETO}.{DATASET}.{tabela}` ({cols}) SELECT {cols} FROM `{apoio}`;"
        )
    comandos.append("COMMIT TRANSACTION;")
    client.query("\n".join(comandos)).result()
    for tabela in quadros:
        client.delete_table(f"{PROJETO}.{DATASET}._apoio_{tabela}", not_found_ok=True)
    return {tabela: len(frame) for tabela, frame in quadros.items()}


@task
def atualizar_visoes(consolidado: dict, carregadas: dict) -> dict:
    """Aponta o vigente para as runs exportadas (sem apagar os outros modelos) e recria as visões."""
    from airflow.providers.google.cloud.hooks.bigquery import BigQueryHook
    from atlas_ingest import forecast_ddl as ddl

    client = BigQueryHook(gcp_conn_id=GCP_CONN_ID, use_legacy_sql=False).get_client(project_id=PROJETO)
    valores = ", ".join(
        f"STRUCT('{m['model']}' AS model, {m['horizon']} AS horizon, '{m['mlflow_run_id']}' AS mlflow_run_id)"
        for m in consolidado["validos"]
    )
    ponteiro = f"`{PROJETO}.{DATASET}.{ddl.POINTER}`"
    client.query(
        f"MERGE {ponteiro} AS p USING (SELECT * FROM UNNEST([{valores}])) AS n\n"
        "ON p.model = n.model AND p.horizon = n.horizon\n"
        "WHEN MATCHED THEN UPDATE SET mlflow_run_id = n.mlflow_run_id, exported_at = CURRENT_TIMESTAMP()\n"
        "WHEN NOT MATCHED THEN INSERT (model, horizon, mlflow_run_id, exported_at)\n"
        "  VALUES (n.model, n.horizon, n.mlflow_run_id, CURRENT_TIMESTAMP())"
    ).result()
    for tabela in ddl.TABELAS:
        client.query(ddl.sql_visao(PROJETO, DATASET, tabela)).result()
    client.query(ddl.sql_visao_modelos(PROJETO, DATASET)).result()
    resultado = {
        "runs_exportadas": len(consolidado["validos"]),
        "linhas": carregadas,
        "ausentes": consolidado["ausentes"],
        "avisos": consolidado["avisos"],
    }
    if consolidado["ausentes"] or consolidado["avisos"]:
        log.warning("Exportação concluída com avisos: %s", resultado)
    return resultado


with DAG(
    dag_id="process_forecast_export_atlas",
    description="Exporta as previsões do MLflow para o BigQuery e o bucket, para o site.",
    schedule=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["atlas", "ml", "forecast", "export"],
    default_args={"owner": "atlas", "retries": 1, "retry_delay": timedelta(minutes=2)},
) as dag:
    config = configuracao()
    manifesto = listar_versoes(config)
    montados = montar.expand(entrada=entradas(manifesto))
    consolidado = consolidar(montados, manifesto)
    figuras = publicar_figuras(consolidado)
    carregadas = carregar_bigquery(consolidado, figuras)
    atualizar_visoes(consolidado, carregadas)
