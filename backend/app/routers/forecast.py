"""Rotas das previsões dos modelos (dataset `forecast`, exportado do MLflow). Só GET."""

import hashlib
import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from app.cache import Cache
from app.config import Settings, get_settings
from app.deps import get_cache, get_repo
from app.repository import GoldRepository
from app.service import consultar_json
from app.tables import (
    FORECAST_FIGURES,
    FORECAST_METRICS_UF,
    FORECAST_MODELS,
    FORECAST_PREDICTIONS,
)

DEFAULT_LIMIT = 200
MAX_LIMIT = 1000
CACHE_FIGURAS = "public, max-age=86400"

router = APIRouter(prefix="/forecast", tags=["forecast"])


def _json(corpo: str) -> Response:
    return Response(content=corpo, media_type="application/json")


@router.get("/models")
def modelos(
    model: str | None = None,
    horizon: int | None = None,
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
    repo: GoldRepository = Depends(get_repo),
    cache: Cache = Depends(get_cache),
    settings: Settings = Depends(get_settings),
):
    """Modelos e horizontes vigentes, com versão, dados do treino e métricas de teste."""
    filtros = {"model": model, "horizon": horizon}
    return _json(consultar_json(FORECAST_MODELS, filtros, limit, offset, repo, cache, settings))


@router.get("/metrics-uf")
def metricas_uf(
    model: str | None = None,
    horizon: int | None = None,
    split: str | None = None,
    uf: str | None = None,
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
    repo: GoldRepository = Depends(get_repo),
    cache: Cache = Depends(get_cache),
    settings: Settings = Depends(get_settings),
):
    filtros = {"model": model, "horizon": horizon, "split": split, "uf": uf}
    return _json(consultar_json(FORECAST_METRICS_UF, filtros, limit, offset, repo, cache, settings))


@router.get("/predictions")
def previsoes(
    model: str | None = None,
    horizon: int | None = None,
    uf: str | None = None,
    split: str | None = None,
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
    repo: GoldRepository = Depends(get_repo),
    cache: Cache = Depends(get_cache),
    settings: Settings = Depends(get_settings),
):
    """Previsões (val, test e future), ordenadas por semana alvo."""
    filtros = {"model": model, "horizon": horizon, "uf": uf, "split": split}
    return _json(consultar_json(FORECAST_PREDICTIONS, filtros, limit, offset, repo, cache, settings))


@router.get("/figures/{model}")
def figuras_do_modelo(
    model: str,
    horizon: int | None = None,
    repo: GoldRepository = Depends(get_repo),
):
    """Figuras do modelo (nome, legenda e horizonte), sem o caminho do bucket."""
    linhas = repo.consultar(FORECAST_FIGURES, {"model": model, "horizon": horizon}, MAX_LIMIT, 0)
    publico = [{k: r[k] for k in ("model", "horizon", "name", "caption")} for r in linhas]
    return _json(json.dumps(publico, ensure_ascii=False))


@router.get("/figures/{model}/{arquivo}")
def figura(
    model: str,
    arquivo: str,
    request: Request,
    horizon: int = Query(1, ge=1),
    repo: GoldRepository = Depends(get_repo),
):
    """O PNG de uma figura registrada. O nome nunca monta caminho: só a linha encontrada o faz."""
    linhas = repo.consultar(FORECAST_FIGURES, {"model": model, "horizon": horizon, "name": arquivo}, 1, 0)
    if not linhas:
        raise HTTPException(status_code=404, detail="figura não encontrada")
    lido = request.app.state.figures.ler(linhas[0]["gcs_path"])
    if lido is None:
        raise HTTPException(status_code=404, detail="figura não encontrada")
    conteudo, geracao = lido
    etag = '"' + hashlib.sha1(f"{geracao}:{len(conteudo)}".encode()).hexdigest() + '"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag, "Cache-Control": CACHE_FIGURAS})
    return Response(
        content=conteudo,
        media_type="image/png",
        headers={"Cache-Control": CACHE_FIGURAS, "ETag": etag},
    )
