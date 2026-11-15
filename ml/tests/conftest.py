import os

import pytest

# Silencia a dica de agente que o MLflow imprime ao importar
os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")
# Testes usam o backend em arquivo (sem rede, sem banco). O MLflow 3 o mantém só em
# modo de manutenção e exige opt-in; os servidores reais usam Postgres.
os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")

ATLAS_VARS = ("ATLAS_ENV", "MLFLOW_TRACKING_URI", "GCP_PROJECT", "ATLAS_GIT_SHA", "ATLAS_IMAGE_TAG")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Cada teste começa sem as variáveis do projeto herdadas do ambiente."""
    for var in ATLAS_VARS:
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def tracking_uri(tmp_path, monkeypatch):
    """MLflow local num diretório temporário (sem rede)."""
    uri = (tmp_path / "mlruns").as_uri()
    monkeypatch.setenv("MLFLOW_TRACKING_URI", uri)
    monkeypatch.setenv("ATLAS_GIT_SHA", "abc1234")
    import mlflow

    mlflow.set_tracking_uri(uri)
    mlflow.set_registry_uri(uri)
    yield uri
    mlflow.set_tracking_uri(None)
