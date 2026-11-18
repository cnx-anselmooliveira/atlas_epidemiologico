"""Leitura das figuras dos modelos no bucket.

Só lê objetos de `gs://<forecast_bucket>/<forecast_prefix>...`: o caminho vem da tabela
`forecast_current_figures` (nunca do pedido) e, mesmo assim, é conferido contra o bucket e o
prefixo configurados. O caminho do bucket nunca vai para a resposta.
"""

from __future__ import annotations

import json
from typing import Any


class FigureStore:
    def __init__(
        self,
        bucket: str,
        prefix: str,
        project: str,
        credentials_json: str | None = None,
        client: Any = None,
    ):
        self.bucket = bucket
        self.prefix = prefix
        self.project = project
        self.credentials_json = credentials_json
        self._client = client

    @property
    def client(self):
        if self._client is None:
            from google.cloud import storage

            credentials = None
            if self.credentials_json:
                from google.oauth2 import service_account

                credentials = service_account.Credentials.from_service_account_info(
                    json.loads(self.credentials_json)
                )
            self._client = storage.Client(project=self.project, credentials=credentials)
        return self._client

    def objeto(self, gcs_path: str) -> str | None:
        """Nome do objeto se o caminho estiver no bucket e no prefixo permitidos; senão, None."""
        esperado = f"gs://{self.bucket}/{self.prefix}"
        if not gcs_path.startswith(esperado) or ".." in gcs_path:
            return None
        return gcs_path.removeprefix(f"gs://{self.bucket}/")

    def ler(self, gcs_path: str) -> tuple[bytes, str] | None:
        """Bytes do PNG e um ETag (geração do objeto), ou None se não existir ou não for permitido."""
        nome = self.objeto(gcs_path)
        if nome is None:
            return None
        blob = self.client.bucket(self.bucket).get_blob(nome)
        if blob is None:
            return None
        return blob.download_as_bytes(), str(blob.generation)
