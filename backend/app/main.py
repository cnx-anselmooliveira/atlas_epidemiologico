"""API do Atlas da Dengue.

    uvicorn app.main:create_app --factory --port 8000

(fábrica: importar o módulo não cria cliente do BigQuery, então os testes rodam sem credencial)

Somente leitura, só GET. O site (Astro SSR) chama esta API pela rede interna; o navegador
não fala com ela, então não há CORS.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from google.api_core import exceptions as google_exceptions

from app.cache import Cache
from app.config import Settings, get_settings
from app.repository import GoldRepository, criar_cliente
from app.routers import casos_provaveis

log = logging.getLogger(__name__)


def create_app(
    repo: GoldRepository | None = None, cache: Cache | None = None, settings: Settings | None = None
) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="Atlas da Dengue — API gold", version="0.1.0")

    if repo is None:
        client = criar_cliente(
            settings.gcp_project, settings.bq_location, settings.google_application_credentials_json
        )
        repo = GoldRepository(
            client, settings.gcp_project, settings.bq_dataset_gold, settings.max_bytes_billed
        )
    app.state.repo = repo
    app.state.cache = (
        cache if cache is not None else Cache.from_url(settings.redis_url, settings.redis_timeout_seconds)
    )

    app.include_router(casos_provaveis.router)

    @app.exception_handler(google_exceptions.GoogleAPIError)
    async def bigquery_indisponivel(request: Request, exc: google_exceptions.GoogleAPIError):
        log.error("BigQuery falhou em %s: %s", request.url.path, exc)
        return JSONResponse(status_code=503, content={"detail": "dados temporariamente indisponíveis"})

    @app.get("/health")
    def health():
        cache_estado = app.state.cache.estado()
        try:
            app.state.repo.verificar()
        except Exception as exc:  # noqa: BLE001 — qualquer falha de credencial/rede vira 503
            log.error("health: BigQuery inacessível: %s", exc)
            return JSONResponse(status_code=503, content={"bigquery": "indisponivel", "cache": cache_estado})
        return {"bigquery": "ok", "cache": cache_estado}

    return app
