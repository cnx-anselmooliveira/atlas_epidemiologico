"""Consulta de uma tabela gold passando pelo cache. Devolve o corpo JSON pronto."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from fastapi.encoders import jsonable_encoder

from app.cache import PREFIXO, Cache
from app.config import Settings
from app.repository import GoldRepository
from app.tables import GoldTable


def _geracao(t: GoldTable, repo: GoldRepository, cache: Cache, settings: Settings) -> str:
    chave = f"{PREFIXO}gen:{t.table}"
    geracao = cache.get(chave)
    if geracao is None:
        geracao = repo.geracao(t)
        cache.set(chave, geracao, settings.generation_ttl_seconds)
    return geracao


def consultar_json(
    t: GoldTable,
    filtros: dict[str, Any],
    limit: int,
    offset: int,
    repo: GoldRepository,
    cache: Cache,
    settings: Settings,
) -> str:
    pedido = json.dumps(
        {"f": {k: v for k, v in filtros.items() if v is not None}, "l": limit, "o": offset}, sort_keys=True
    )
    if cache.ativo:
        geracao = _geracao(t, repo, cache, settings)
        chave = f"{PREFIXO}gold:{t.table}:{geracao}:{hashlib.sha1(pedido.encode()).hexdigest()}"
        corpo = cache.get(chave)
        if corpo is not None:
            return corpo
    linhas = repo.consultar(t, filtros, limit, offset)
    corpo = json.dumps(jsonable_encoder(linhas), ensure_ascii=False)
    if cache.ativo:
        cache.set(chave, corpo, settings.cache_ttl_seconds)
    return corpo
