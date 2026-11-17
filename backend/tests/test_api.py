import redis
from fastapi.testclient import TestClient
from google.api_core import exceptions as google_exceptions

from app.cache import Cache
from app.main import create_app

CAMPOS = {
    "week_start",
    "epi_year",
    "epi_week",
    "probable_cases",
    "population",
    "incidence",
    "gold_generated_at",
}


def test_uf_filtrada_e_ordenada(client):
    r = client.get("/gold/casos-provaveis-uf-semanal", params={"uf": "SP", "limit": 1000})
    assert r.status_code == 200
    linhas = r.json()
    assert {x["uf"] for x in linhas} == {"SP"}
    assert [x["week_start"] for x in linhas] == ["2023-12-31", "2024-01-07", "2025-01-05"]
    assert CAMPOS | {"uf"} <= set(linhas[0])


def test_ano_para_o_mapa(client):
    linhas = client.get("/gold/casos-provaveis-uf-semanal", params={"epi_year": 2024}).json()
    assert {x["uf"] for x in linhas} == {"SP", "MG"}
    assert {x["epi_year"] for x in linhas} == {2024}
    # ordem: semana, depois UF
    assert [(x["week_start"], x["uf"]) for x in linhas][:2] == [("2023-12-31", "MG"), ("2023-12-31", "SP")]


def test_brasil(client):
    linhas = client.get("/gold/casos-provaveis-brasil-semanal").json()
    assert len(linhas) == 3 and "uf" not in linhas[0]
    assert set(linhas[0]) >= CAMPOS
    assert linhas[0]["gold_generated_at"].startswith("2026-11-17T00:00:00")


def test_filtro_malicioso_devolve_vazio(client):
    r = client.get("/gold/casos-provaveis-uf-semanal", params={"uf": "' OR 1=1 --"})
    assert r.status_code == 200 and r.json() == []


def test_paginacao(client):
    r = client.get("/gold/casos-provaveis-uf-semanal", params={"limit": 2, "offset": 4})
    assert len(r.json()) == 2
    assert client.get("/gold/casos-provaveis-uf-semanal", params={"limit": 5000}).status_code == 422
    assert client.get("/gold/casos-provaveis-uf-semanal", params={"offset": -1}).status_code == 422
    assert client.get("/gold/casos-provaveis-uf-semanal", params={"epi_year": "abc"}).status_code == 422


def test_requisicao_repetida_vem_do_cache(client, repo):
    a = client.get("/gold/casos-provaveis-uf-semanal", params={"uf": "MG"})
    b = client.get("/gold/casos-provaveis-uf-semanal", params={"uf": "MG"})
    assert a.content == b.content
    assert repo.consultas == 1


def test_nova_geracao_invalida_o_cache(client, repo, redis_fake):
    client.get("/gold/casos-provaveis-brasil-semanal")
    # dbt reconstruiu a tabela e a geração guardada expirou
    repo.geracoes["gold_dengue_casos_provaveis_brasil_semanal"] = "g2"
    redis_fake.delete("atlas:gen:gold_dengue_casos_provaveis_brasil_semanal")
    client.get("/gold/casos-provaveis-brasil-semanal")
    assert repo.consultas == 2
    # outra tabela continua no cache
    client.get("/gold/casos-provaveis-uf-semanal")
    client.get("/gold/casos-provaveis-uf-semanal")
    assert repo.consultas == 3


class RedisFora:
    def __getattr__(self, name):
        def falha(*args, **kwargs):
            raise redis.ConnectionError("fora do ar")

        return falha


def test_sem_redis_continua_respondendo(repo, settings):
    client = TestClient(create_app(repo=repo, cache=Cache(RedisFora()), settings=settings))
    r = client.get("/gold/casos-provaveis-uf-semanal", params={"uf": "SP"})
    assert r.status_code == 200 and len(r.json()) == 3
    assert client.get("/health").json() == {"bigquery": "ok", "cache": "indisponivel"}


def test_sem_redis_configurado(repo, settings):
    client = TestClient(create_app(repo=repo, cache=Cache(None), settings=settings))
    client.get("/gold/casos-provaveis-brasil-semanal")
    client.get("/gold/casos-provaveis-brasil-semanal")
    assert repo.consultas == 2
    assert client.get("/health").json()["cache"] == "desligado"


def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json() == {"bigquery": "ok", "cache": "ok"}


def test_bigquery_fora(client, repo):
    repo.falhar = google_exceptions.Forbidden("credencial inválida")
    assert client.get("/health").status_code == 503
    r = client.get("/gold/casos-provaveis-brasil-semanal")
    assert r.status_code == 503 and "indisponíveis" in r.json()["detail"]


def test_so_get(client):
    assert client.post("/gold/casos-provaveis-brasil-semanal").status_code == 405
