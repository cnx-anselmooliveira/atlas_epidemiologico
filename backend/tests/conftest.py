import datetime as dt

import fakeredis
import pytest
from fastapi.testclient import TestClient

from app.cache import Cache
from app.config import Settings
from app.main import create_app
from app.repository import GoldRepository


class FakeRepo(GoldRepository):
    """Repositório sem BigQuery: aplica filtros/paginação sobre linhas em memória e conta chamadas."""

    def __init__(self, linhas: dict[str, list[dict]]):
        super().__init__(client=None, project="p", dataset="gold", max_bytes_billed=1)
        self.linhas = linhas
        self.consultas = 0
        self.geracoes = {}
        self.falhar = None  # exceção a levantar em consultar/verificar

    def consultar(self, t, filtros, limit, offset):
        self.montar_consulta(t, filtros, limit, offset)  # mesma validação de filtro do real
        if self.falhar:
            raise self.falhar
        self.consultas += 1
        linhas = [
            {c: r.get(c) for c in t.columns}
            for r in self.linhas.get(t.table, [])
            if all(v is None or r.get(k) == v for k, v in filtros.items())
        ]
        linhas.sort(key=lambda r: tuple(r[c] for c in t.order_by))
        return linhas[offset : offset + limit]

    def geracao(self, t):
        return self.geracoes.get(t.table, "g1")

    def verificar(self):
        if self.falhar:
            raise self.falhar


def _semana(uf, inicio, ano, semana, casos):
    return {
        "uf": uf,
        "week_start": inicio,
        "epi_year": ano,
        "epi_week": semana,
        "notified_cases": casos + 1,
        "probable_cases": casos,
        "confirmed_cases": 0,
        "alarm_cases": 0,
        "severe_cases": 0,
        "deaths": 0,
        "population": 1000,
        "incidence": casos / 1000 * 100000,
        "gold_generated_at": dt.datetime(2026, 11, 17, tzinfo=dt.UTC),
    }


@pytest.fixture
def repo():
    semanas = [
        (dt.date(2023, 12, 31), 2024, 1),
        (dt.date(2024, 1, 7), 2024, 2),
        (dt.date(2025, 1, 5), 2025, 1),
    ]
    ufs = [
        _semana(uf, d, a, s, i * 10 + n)
        for n, uf in enumerate(["SP", "MG"])
        for i, (d, a, s) in enumerate(semanas)
    ]
    brasil = [
        {k: v for k, v in _semana(None, d, a, s, i).items() if k != "uf"}
        for i, (d, a, s) in enumerate(semanas)
    ]
    return FakeRepo(
        {
            "gold_dengue_casos_provaveis_uf_semanal": ufs,
            "gold_dengue_casos_provaveis_brasil_semanal": brasil,
        }
    )


@pytest.fixture
def redis_fake():
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture
def settings():
    return Settings(redis_url=None)


@pytest.fixture
def client(repo, redis_fake, settings):
    return TestClient(create_app(repo=repo, cache=Cache(redis_fake), settings=settings))
