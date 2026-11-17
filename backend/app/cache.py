"""Cache de leitura no Redis, opcional e tolerante a falha.

Chaves:
- atlas:gen:{tabela}                           geração da tabela (last_modified), TTL curto
- atlas:gold:{tabela}:{geração}:{hash do pedido}  corpo JSON da resposta, TTL longo

Quando o dbt reconstrói a tabela, a geração muda e as chaves antigas deixam de ser lidas
(expiram sozinhas). Se o Redis falhar, o cache se desliga por alguns segundos e a API segue
consultando o BigQuery direto.
"""

from __future__ import annotations

import logging
import time

import redis

log = logging.getLogger(__name__)

PREFIXO = "atlas:"


class Cache:
    def __init__(self, client: redis.Redis | None, pausa_apos_falha: float = 30.0):
        self.client = client
        self.pausa_apos_falha = pausa_apos_falha
        self._desligado_ate = 0.0

    @classmethod
    def from_url(cls, url: str | None, timeout: float) -> Cache:
        if not url:
            return cls(None)
        client = redis.Redis.from_url(
            url, socket_timeout=timeout, socket_connect_timeout=timeout, decode_responses=True
        )
        return cls(client)

    @property
    def ativo(self) -> bool:
        return self.client is not None and time.monotonic() >= self._desligado_ate

    def _falhou(self, exc: Exception) -> None:
        log.warning("Redis indisponível (%s); consultando o BigQuery direto", exc)
        self._desligado_ate = time.monotonic() + self.pausa_apos_falha

    def get(self, chave: str) -> str | None:
        if not self.ativo:
            return None
        try:
            return self.client.get(chave)
        except redis.RedisError as exc:
            self._falhou(exc)
            return None

    def set(self, chave: str, valor: str, ttl: int) -> None:
        if not self.ativo:
            return
        try:
            self.client.set(chave, valor, ex=ttl)
        except redis.RedisError as exc:
            self._falhou(exc)

    def estado(self) -> str:
        """Para o /health: desligado (sem REDIS_URL), ok ou indisponivel."""
        if self.client is None:
            return "desligado"
        try:
            self.client.ping()
            return "ok"
        except redis.RedisError:
            return "indisponivel"
