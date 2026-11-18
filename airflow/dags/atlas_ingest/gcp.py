"""Acesso ao GCP e à rede usado pelas DAGs do fluxo do Brasil (Connection google_cloud_default).

Os imports dos providers ficam dentro das funções: a leitura das DAGs continua leve.
"""

from __future__ import annotations

import os

GCP_CONN_ID = "google_cloud_default"
PROJETO = os.environ.get("GCP_PROJECT") or "ppgcc-dengue-project"
BUCKET = os.environ.get("ATLAS_LANDING_BUCKET", "ppgcc-bucket")


def bucket():
    from airflow.providers.google.cloud.hooks.gcs import GCSHook

    return GCSHook(gcp_conn_id=GCP_CONN_ID).get_conn().bucket(BUCKET)


def bigquery():
    from airflow.providers.google.cloud.hooks.bigquery import BigQueryHook

    return BigQueryHook(gcp_conn_id=GCP_CONN_ID, use_legacy_sql=False).get_client(project_id=PROJETO)


def http():
    import requests

    sessao = requests.Session()
    sessao.headers["User-Agent"] = "atlas-etl"
    return sessao


def modificada_em(cliente, tabela: str):
    """Última modificação de `dataset.tabela` (None se não existir)."""
    from google.api_core.exceptions import NotFound

    try:
        return cliente.get_table(f"{PROJETO}.{tabela}").modified
    except NotFound:
        return None


def mlflow_sessao():
    """Sessão para a API REST do MLflow do ambiente (autenticação básica em hml e prod)."""
    import requests

    sessao = requests.Session()
    usuario, senha = os.environ.get("MLFLOW_TRACKING_USERNAME"), os.environ.get("MLFLOW_TRACKING_PASSWORD")
    if usuario and senha:
        sessao.auth = (usuario, senha)
    return sessao, os.environ.get("MLFLOW_TRACKING_URI", "http://mlflow:5000")
