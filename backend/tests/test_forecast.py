"""Rotas /forecast/*: filtros, ordem, figuras seguras, cache e estados sem exportação."""

import datetime as dt

import pytest
from fastapi.testclient import TestClient
from google.api_core import exceptions as google_exceptions

from app.cache import Cache
from app.figures import FigureStore
from app.main import create_app

from .conftest import FakeRepo

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32
BUCKET, PREFIXO = "bucket-teste", "forecast/"


class FakeBlob:
    generation = 7

    def download_as_bytes(self):
        return PNG


class FakeBucket:
    def __init__(self, objetos):
        self.objetos = objetos

    def get_blob(self, nome):
        return FakeBlob() if nome in self.objetos else None


class FakeStorage:
    def __init__(self, objetos):
        self.objetos = objetos

    def bucket(self, nome):
        assert nome == BUCKET
        return FakeBucket(self.objetos)


def _linhas():
    def pred(model, horizon, uf, split, alvo, y_pred):
        return {
            "model": model,
            "horizon": horizon,
            "split": split,
            "uf": uf,
            "origin_date": dt.date(2026, 8, 30),
            "target_date": alvo,
            "y_true": None if split == "future" else y_pred + 1,
            "y_pred": y_pred,
            "lower": None,
            "upper": None,
            "population": 1000.0,
        }

    return {
        "forecast_current_models": [
            {"model": "catboost", "horizon": 1, "family": "gbm", "nrmse": 0.2, "model_version": "3"},
            {"model": "catboost", "horizon": 2, "family": "gbm", "nrmse": 0.3, "model_version": "3"},
            {"model": "svr", "horizon": 1, "family": "kernel", "nrmse": 0.25, "model_version": "1"},
        ],
        "forecast_current_predictions": [
            pred("catboost", 2, "SP", "future", dt.date(2026, 9, 13), 5.0),
            pred("catboost", 2, "SP", "test", dt.date(2026, 5, 3), 4.0),
            pred("catboost", 2, "MG", "future", dt.date(2026, 9, 13), 6.0),
            pred("svr", 1, "SP", "future", dt.date(2026, 9, 6), 7.0),
        ],
        "forecast_current_metrics_uf": [
            {"model": "svr", "horizon": 1, "split": "test", "uf": "SP", "n": 52, "nrmse": 0.1},
            {"model": "svr", "horizon": 1, "split": "test", "uf": "BR", "n": 52, "nrmse": 0.15},
        ],
        "forecast_current_figures": [
            {
                "model": "svr",
                "horizon": 1,
                "name": "error_by_uf.png",
                "caption": "Erro por UF.",
                "gcs_path": f"gs://{BUCKET}/{PREFIXO}dev/svr/h1/run/error_by_uf.png",
            },
            {
                "model": "svr",
                "horizon": 1,
                "name": "fora.png",
                "caption": "Fora do prefixo.",
                "gcs_path": f"gs://{BUCKET}/outro/segredo.png",
            },
        ],
    }


@pytest.fixture
def api(settings):
    repo = FakeRepo(_linhas())
    storage = FakeStorage({f"{PREFIXO}dev/svr/h1/run/error_by_uf.png", "outro/segredo.png"})
    figuras = FigureStore(BUCKET, PREFIXO, "p", client=storage)
    return TestClient(create_app(repo=repo, cache=Cache(None), settings=settings, figures=figuras)), repo


def test_modelos_com_metricas(api):
    client, _ = api
    linhas = client.get("/forecast/models").json()
    assert [(m["model"], m["horizon"]) for m in linhas] == [("catboost", 1), ("catboost", 2), ("svr", 1)]
    assert client.get("/forecast/models", params={"model": "svr"}).json()[0]["family"] == "kernel"


def test_previsao_filtrada_e_ordenada_por_semana(api):
    client, _ = api
    r = client.get(
        "/forecast/predictions", params={"model": "catboost", "horizon": 2, "uf": "SP", "split": "future"}
    )
    linhas = r.json()
    assert r.status_code == 200 and len(linhas) == 1
    assert linhas[0]["uf"] == "SP" and linhas[0]["split"] == "future" and linhas[0]["y_pred"] == 5.0
    todas = client.get("/forecast/predictions", params={"model": "catboost", "horizon": 2}).json()
    datas = [x["target_date"] for x in todas]
    assert datas == sorted(datas)


def test_metricas_por_uf_incluem_o_brasil(api):
    client, _ = api
    r = client.get("/forecast/metrics-uf", params={"model": "svr", "horizon": 1, "split": "test"}).json()
    assert {x["uf"] for x in r} == {"SP", "BR"}


def test_paginacao_e_filtro_malicioso(api):
    client, _ = api
    assert client.get("/forecast/predictions", params={"limit": 5000}).status_code == 422
    assert client.get("/forecast/predictions", params={"horizon": "x"}).status_code == 422
    r = client.get("/forecast/predictions", params={"model": "' OR 1=1 --"})
    assert r.status_code == 200 and r.json() == []


def test_lista_de_figuras_nao_expoe_o_caminho_do_bucket(api):
    client, _ = api
    r = client.get("/forecast/figures/svr")
    corpo = r.text
    assert r.status_code == 200 and "gs://" not in corpo and "gcs_path" not in corpo and BUCKET not in corpo
    nomes = {f["name"] for f in r.json()}
    assert "error_by_uf.png" in nomes


def test_figura_png_com_cache_e_etag(api):
    client, _ = api
    r = client.get("/forecast/figures/svr/error_by_uf.png", params={"horizon": 1})
    assert r.status_code == 200 and r.content == PNG and r.headers["content-type"] == "image/png"
    assert "max-age=86400" in r.headers["cache-control"] and "gs://" not in str(r.headers)
    etag = r.headers["etag"]
    assert (
        client.get("/forecast/figures/svr/error_by_uf.png", headers={"if-none-match": etag}).status_code
        == 304
    )


@pytest.mark.parametrize(
    "caminho",
    [
        "/forecast/figures/svr/..%2F..%2Fsegredo.png",
        "/forecast/figures/svr/nao_registrada.png",
        "/forecast/figures/catboost/error_by_uf.png",  # figura de outro modelo
        "/forecast/figures/svr/fora.png",  # registrada, mas fora do prefixo permitido
    ],
)
def test_figura_fora_da_lista_ou_do_prefixo_e_404(api, caminho):
    client, _ = api
    assert client.get(caminho).status_code == 404


def test_antes_da_primeira_exportacao_devolve_lista_vazia(settings):
    client = TestClient(create_app(repo=FakeRepo({}), cache=Cache(None), settings=settings))
    for rota in (
        "/forecast/models",
        "/forecast/predictions",
        "/forecast/metrics-uf",
        "/forecast/figures/svr",
    ):
        r = client.get(rota)
        assert r.status_code == 200 and r.json() == [], rota


def test_bigquery_fora_vira_503(api):
    client, repo = api
    repo.falhar = google_exceptions.Forbidden("sem acesso")
    assert client.get("/forecast/models").status_code == 503


def test_figuras_so_do_bucket_e_prefixo_configurados():
    f = FigureStore(BUCKET, PREFIXO, "p", client=FakeStorage(set()))
    assert f.objeto(f"gs://{BUCKET}/{PREFIXO}x.png") == f"{PREFIXO}x.png"
    assert f.objeto(f"gs://outro-bucket/{PREFIXO}x.png") is None
    assert f.objeto(f"gs://{BUCKET}/privado/x.png") is None
    assert f.objeto(f"gs://{BUCKET}/{PREFIXO}../privado/x.png") is None


def test_geracao_da_visao_invalida_o_cache(settings):
    import fakeredis

    repo = FakeRepo(_linhas())
    client = TestClient(
        create_app(repo=repo, cache=Cache(fakeredis.FakeRedis(decode_responses=True)), settings=settings)
    )
    client.get("/forecast/models")
    client.get("/forecast/models")
    assert repo.consultas == 1  # segunda vem do cache
    repo.geracoes["forecast_current_models"] = "g2"  # nova exportação recria a visão
    import time

    time.sleep(0)  # (a geração é relida quando a chave de geração expira; aqui a removemos)
    client.app.state.cache.client.delete("atlas:gen:forecast_current_models")
    client.get("/forecast/models")
    assert repo.consultas == 2
