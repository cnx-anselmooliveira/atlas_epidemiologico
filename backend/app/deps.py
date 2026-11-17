"""Dependências das rotas: repositório e cache ficam em app.state (os testes trocam por fakes)."""

from fastapi import Request

from app.cache import Cache
from app.repository import GoldRepository


def get_repo(request: Request) -> GoldRepository:
    return request.app.state.repo


def get_cache(request: Request) -> Cache:
    return request.app.state.cache
