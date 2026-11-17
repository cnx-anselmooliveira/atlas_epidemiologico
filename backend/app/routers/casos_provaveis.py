"""Rotas dos casos prováveis de dengue no Brasil (golds do site: série histórica e mapa por UF)."""

from fastapi import APIRouter, Depends, Query, Response

from app.cache import Cache
from app.config import Settings, get_settings
from app.deps import get_cache, get_repo
from app.repository import GoldRepository
from app.service import consultar_json
from app.tables import CASOS_PROVAVEIS_BRASIL_SEMANAL, CASOS_PROVAVEIS_UF_SEMANAL

DEFAULT_LIMIT = 200
MAX_LIMIT = 1000

router = APIRouter(prefix="/gold", tags=["casos-provaveis"])


def _json(corpo: str) -> Response:
    return Response(content=corpo, media_type="application/json")


@router.get("/casos-provaveis-brasil-semanal")
def casos_provaveis_brasil_semanal(
    epi_year: int | None = None,
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
    repo: GoldRepository = Depends(get_repo),
    cache: Cache = Depends(get_cache),
    settings: Settings = Depends(get_settings),
):
    """Brasil (soma das 27 UFs) por semana epidemiológica, da mais antiga para a mais recente."""
    return _json(
        consultar_json(
            CASOS_PROVAVEIS_BRASIL_SEMANAL, {"epi_year": epi_year}, limit, offset, repo, cache, settings
        )
    )


@router.get("/casos-provaveis-uf-semanal")
def casos_provaveis_uf_semanal(
    uf: str | None = None,
    epi_year: int | None = None,
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
    repo: GoldRepository = Depends(get_repo),
    cache: Cache = Depends(get_cache),
    settings: Settings = Depends(get_settings),
):
    """UF × semana epidemiológica, ordenado por semana e UF."""
    return _json(
        consultar_json(
            CASOS_PROVAVEIS_UF_SEMANAL,
            {"uf": uf, "epi_year": epi_year},
            limit,
            offset,
            repo,
            cache,
            settings,
        )
    )
