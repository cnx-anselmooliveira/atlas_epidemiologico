"""Decisões do fluxo diário do Brasil (funções puras, sem rede nem Airflow).

    docker run --rm --entrypoint python <imagem do Airflow> /opt/atlas/tests/test_etl_brasil.py

Também compatível com pytest.
"""

import os
import sys
from datetime import UTC, datetime, timedelta

sys.path.insert(0, os.environ.get("ATLAS_DAGS_FOLDER", "/opt/airflow/dags"))

from atlas_ingest import etl_brasil as eb  # noqa: E402

T0 = datetime(2026, 11, 18, 3, 0, tzinfo=UTC)
GOLD = "ppgcc-dengue-project.gold.gold_dengue_casos_provaveis_uf_semanal"


# --- dbt ---------------------------------------------------------------------------------------


def test_dbt_bronze_mais_nova_roda():
    assert eb.dbt_precisa_rodar(T0 + timedelta(minutes=1), T0).rodar is True


def test_dbt_gold_em_dia_pula():
    d = eb.dbt_precisa_rodar(T0, T0 + timedelta(hours=1))
    assert d.rodar is False and "já reflete" in d.motivo
    assert eb.dbt_precisa_rodar(T0, T0).rodar is False  # mesmo instante: nada novo


def test_dbt_forcado_ou_sem_gold_roda():
    assert eb.dbt_precisa_rodar(T0, T0 + timedelta(hours=1), forcar=True).rodar is True
    assert eb.dbt_precisa_rodar(T0, None).rodar is True


def test_dbt_sem_bronze_pula():
    assert eb.dbt_precisa_rodar(None, T0).rodar is False


# --- treino ------------------------------------------------------------------------------------


def _vigentes(versao):
    return {n: versao for n in eb.nomes_registrados()}


def test_nomes_registrados_seguem_o_treino():
    nomes = eb.nomes_registrados()
    assert len(nomes) == 24 and "atlas-br-lstm-h3" in nomes and "atlas-br-ensemble-h1" in nomes


def test_versao_no_formato_do_treino():
    assert eb.versao_tabela(GOLD, T0) == f"{GOLD}@2026-11-18T03:00:00+00:00"


def test_treino_gold_igual_pula():
    versao = eb.versao_tabela(GOLD, T0)
    # o treino grava "query:<hash>+<tabela>@<ISO>"
    d = eb.treino_precisa_rodar(versao, _vigentes(f"query:abc123+{versao}"))
    assert d.rodar is False and "24" in d.motivo


def test_treino_gold_nova_roda():
    antiga = eb.versao_tabela(GOLD, T0)
    nova = eb.versao_tabela(GOLD, T0 + timedelta(days=1))
    assert eb.treino_precisa_rodar(nova, _vigentes(f"query:abc+{antiga}")).rodar is True


def test_treino_com_amostra_avulsa_roda():
    amostra = (
        "query:x+ppgcc-dengue-project.adhoc."
        "gold_dengue_casos_provaveis_uf_semanal_amostra@2026-11-18T00:32:01+00:00"
    )
    assert eb.treino_precisa_rodar(eb.versao_tabela(GOLD, T0), _vigentes(amostra)).rodar is True


def test_treino_sem_modelo_vigente_roda():
    versao = eb.versao_tabela(GOLD, T0)
    vig = _vigentes(f"query:abc+{versao}")
    vig["atlas-br-lstm-h2"] = None
    d = eb.treino_precisa_rodar(versao, vig)
    assert d.rodar is True and "atlas-br-lstm-h2" in d.motivo
    assert eb.treino_precisa_rodar(versao, {}).rodar is True


def test_treino_forcado_roda():
    versao = eb.versao_tabela(GOLD, T0)
    assert eb.treino_precisa_rodar(versao, _vigentes(f"q+{versao}"), forcar=True).rodar is True


# --- janela do sensor ------------------------------------------------------------------------


def test_janela_do_sensor():
    assert eb.dentro_da_janela(T0, T0 + timedelta(hours=2), 3) is True
    assert eb.dentro_da_janela(T0, T0 + timedelta(hours=3), 3) is False
    assert eb.dentro_da_janela(T0, T0, 0) is False  # à mão: uma verificação


# --- leitura do MLflow (sessão falsa) ---------------------------------------------------------


class _Resp:
    def __init__(self, status, corpo, texto=""):
        self.status_code, self._corpo, self.text = status, corpo, texto

    def json(self):
        return self._corpo

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _Sessao:
    def __init__(self, registrados):
        self.registrados = registrados  # nome -> (run_id, data_version)
        self.chamadas = []

    def get(self, url, params=None, timeout=None):
        self.chamadas.append((url, dict(params or {})))
        if url.endswith("/registered-models/alias"):
            if params["alias"] != "hml":
                return _Resp(404, {}, "RESOURCE_DOES_NOT_EXIST")
            if params["name"] not in self.registrados:
                return _Resp(404, {"error_code": "RESOURCE_DOES_NOT_EXIST"}, "RESOURCE_DOES_NOT_EXIST")
            return _Resp(200, {"model_version": {"run_id": self.registrados[params["name"]][0]}})
        if url.endswith("/runs/get"):
            dv = next(v for r, v in self.registrados.values() if r == params["run_id"])
            return _Resp(200, {"run": {"data": {"tags": [{"key": "atlas.data_version", "value": dv}]}}})
        return _Resp(500, {})


def test_data_versions_vigentes():
    sessao = _Sessao({"atlas-br-svr-h1": ("r1", "query:a+g@1"), "atlas-br-lstm-h1": ("r2", "query:a+g@2")})
    res = eb.data_versions_vigentes(
        sessao, "http://mlflow:5000/", "hml", ["atlas-br-svr-h1", "atlas-br-lstm-h1", "atlas-br-chronos-h1"]
    )
    assert res == {
        "atlas-br-svr-h1": "query:a+g@1",
        "atlas-br-lstm-h1": "query:a+g@2",
        "atlas-br-chronos-h1": None,
    }
    assert all(url.startswith("http://mlflow:5000/api/2.0/mlflow/") for url, _ in sessao.chamadas)


def test_data_versions_erro_de_servidor_sobe():
    class _Quebrada:
        def get(self, *a, **k):
            return _Resp(500, {}, "erro")

    try:
        eb.data_versions_vigentes(_Quebrada(), "http://mlflow:5000", "hml", ["atlas-br-svr-h1"])
    except RuntimeError:
        return
    raise AssertionError("erro do MLflow não pode virar 'sem modelo' (treinaria às cegas)")


if __name__ == "__main__":
    falhas = 0
    for nome, fn in list(globals().items()):
        if nome.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"ok   {nome}")
            except Exception as exc:  # noqa: BLE001
                falhas += 1
                print(f"FAIL {nome}: {exc}")
    sys.exit(1 if falhas else 0)
