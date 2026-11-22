"""Leitura da gold e versão dos dados (células comuns), com um BigQuery simulado.

As células `dados_funcoes` e `dados_ler` da fonte comum são executadas aqui no mesmo processo, com um
cliente do BigQuery falso: a versão `atlas.data_version` precisa ter `<tabela>@<última modificação>`
(o formato que a decisão de treino do `etl_brasil` procura) e `data_version_esperada` precisa falhar
antes de qualquer run quando a gold mudou.
"""

import hashlib
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("google.cloud.bigquery")

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "notebooks" / "_ferramentas"))

import comum  # noqa: E402

from atlas_ml.forecast.synthetic import synthetic_panel  # noqa: E402

MODIFICADA = datetime(2026, 11, 20, 10, 0, tzinfo=UTC)
GOLD_DEV = "ppgcc-dengue-project.gold.gold_dengue_casos_provaveis_uf_semanal"


class _Resultado:
    def __init__(self, df):
        self.df = df

    def to_dataframe(self):
        return self.df


class BigQueryFalso:
    consultas: list[str] = []
    tabelas: list[str] = []

    def __init__(self, project=None):
        self.project = project

    def get_table(self, tabela):
        BigQueryFalso.tabelas.append(tabela)
        return SimpleNamespace(modified=MODIFICADA)

    def query(self, sql):
        BigQueryFalso.consultas.append(sql)
        return _Resultado(synthetic_panel(n_weeks=30))


def executar_dados(monkeypatch, env="dev", **parametros):
    """Executa as duas células de dados com os parâmetros dados e devolve o namespace."""
    from google.cloud import bigquery

    monkeypatch.setattr(bigquery, "Client", BigQueryFalso)
    BigQueryFalso.consultas, BigQueryFalso.tabelas = [], []
    ns = {
        "pd": pd,
        "np": np,
        "re": re,
        "hashlib": hashlib,
        "Path": Path,
        "settings": SimpleNamespace(atlas_env=env, gcp_project="ppgcc-dengue-project"),
        "painel_parquet": "",
        "fonte": "",
        "data_version_esperada": "",
        **parametros,
    }
    exec(comum.CELULAS["dados_funcoes"], ns)  # noqa: S102
    exec(comum.CELULAS["dados_ler"], ns)  # noqa: S102
    return ns


def test_versao_traz_tabela_e_ultima_modificacao_no_formato_do_etl_brasil(monkeypatch):
    ns = executar_dados(monkeypatch)
    esperado = f"{GOLD_DEV}@{MODIFICADA.isoformat()}"
    assert esperado in ns["data_version"]  # o etl_brasil procura a versão da gold dentro da tag
    assert ns["data_version"].startswith("query:")
    assert BigQueryFalso.tabelas == [GOLD_DEV]
    assert "probable_cases AS cases" in BigQueryFalso.consultas[0]
    assert set(comum.CELULAS) and ns["painel_bruto"]["uf"].nunique() == 3


@pytest.mark.parametrize(("env", "dataset"), [("dev", "gold"), ("hml", "gold_hml"), ("prod", "gold_prod")])
def test_a_gold_lida_e_a_do_ambiente(monkeypatch, env, dataset):
    executar_dados(monkeypatch, env=env)
    assert BigQueryFalso.tabelas == [f"ppgcc-dengue-project.{dataset}.gold_dengue_casos_provaveis_uf_semanal"]


def test_versao_esperada_igual_passa_e_diferente_falha_antes_de_qualquer_run(monkeypatch):
    igual = f"{GOLD_DEV}@{MODIFICADA.isoformat()}"
    assert executar_dados(monkeypatch, data_version_esperada=igual)["data_version"]
    antiga = f"{GOLD_DEV}@2026-11-19T04:27:11+00:00"
    with pytest.raises(RuntimeError, match="A gold mudou desde o início da execução") as erro:
        executar_dados(monkeypatch, data_version_esperada=antiga)
    assert antiga in str(erro.value) and MODIFICADA.isoformat() in str(erro.value)  # indica as duas versões


def test_tabela_alternativa_e_validada(monkeypatch):
    ns = executar_dados(monkeypatch, fonte="ppgcc-dengue-project.gold.amostra")
    assert "ppgcc-dengue-project.gold.amostra@" in ns["data_version"]
    with pytest.raises(ValueError, match="Tabela de origem inválida"):
        executar_dados(monkeypatch, fonte="x; DROP TABLE y")


def test_painel_parquet_usa_o_arquivo_e_nao_toca_no_bigquery(monkeypatch, tmp_path):
    arquivo = tmp_path / "painel.parquet"
    synthetic_panel(n_weeks=30).to_parquet(arquivo, index=False)
    ns = executar_dados(monkeypatch, painel_parquet=str(arquivo))
    assert ns["data_version"].startswith("parquet:") and BigQueryFalso.tabelas == []
    sem_coluna = tmp_path / "ruim.parquet"
    synthetic_panel(n_weeks=30).drop(columns=["deaths"]).to_parquet(sem_coluna, index=False)
    with pytest.raises(ValueError, match="não tem as colunas: deaths"):
        executar_dados(monkeypatch, painel_parquet=str(sem_coluna))
