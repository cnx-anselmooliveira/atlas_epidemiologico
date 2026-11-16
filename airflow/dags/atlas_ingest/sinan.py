"""SINAN (dengue) do OpenDataSUS: sync dos arquivos anuais com o landing e carga na bronze.

Origem (pública):  https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/SINAN/Dengue/csv/DENGBR<aa>.csv.zip
Landing (espelho): gs://<bucket>/landing/sinan/dengue/DENGBR<aa>.csv.zip  (+ .csv descompactado)

O estado do sync fica na metadata do .csv.zip no landing:
    origem_etag, origem_last_modified, origem_tamanho  ← cabeçalhos da origem no download
    registros                                         ← registros contados no CSV
    bronze_etag                                       ← versão já carregada e validada na bronze

O ETag da origem é de upload multipart do S3 (ex.: "77c3…-5"), não o MD5 do conteúdo:
a comparação é sempre contra a metadata gravada, nunca contra o hash do objeto no GCS.

As funções de plano são puras (testáveis sem rede); as de I/O recebem clientes prontos.
"""

from __future__ import annotations

import csv
import re
from dataclasses import asdict, dataclass, field
from datetime import date

BASE_URL = "https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/SINAN/Dengue/csv"
PRIMEIRO_ANO = 2000
PREFIXO_LANDING = "landing/sinan/dengue/"
TABELA_BRONZE = "sinan_dengue_opendatasus"
# Colunas que a modelagem (bronze_dengue_brasil) usa; a validação exige todas
COLUNAS_OBRIGATORIAS = (
    "DT_NOTIFIC",
    "SG_UF_NOT",
    "ID_MUNICIP",
    "SG_UF",
    "ID_MN_RESI",
    "DT_SIN_PRI",
    "CLASSI_FIN",
    "EVOLUCAO",
)
_NOME = re.compile(r"^DENGBR(\d{2})\.csv\.zip$")


class OrigemIndisponivel(RuntimeError):
    """A origem não respondeu (nenhum arquivo consultado com sucesso): nada pode ser apagado."""


def nome_arquivo(ano: int) -> str:
    return f"DENGBR{ano % 100:02d}.csv.zip"


def url_arquivo(ano: int) -> str:
    return f"{BASE_URL}/{nome_arquivo(ano)}"


def ano_do_nome(nome: str) -> int | None:
    """`DENGBR26.csv.zip` → 2026 (aceita o caminho completo no landing)."""
    m = _NOME.match(nome.rsplit("/", 1)[-1])
    return 2000 + int(m.group(1)) if m else None


@dataclass(frozen=True)
class Versao:
    """Versão de um arquivo na origem, pelos cabeçalhos do HEAD."""

    nome: str
    ano: int
    etag: str
    last_modified: str
    tamanho: int


@dataclass
class Origem:
    """Resultado da consulta à origem."""

    versoes: dict[str, Versao] = field(default_factory=dict)  # arquivos existentes
    ausentes: set[str] = field(default_factory=set)  # responderam 404
    anos_consultados: tuple[int, int] = (PRIMEIRO_ANO, PRIMEIRO_ANO)


def listar_origem(session, ano_final: int | None = None, timeout: int = 60) -> Origem:
    """HEAD de DENGBR<PRIMEIRO_ANO..ano_final>. 404 = ausente; outras falhas não contam como
    ausência. Se nenhum arquivo respondeu (rede/origem fora do ar), levanta OrigemIndisponivel."""
    ano_final = ano_final or date.today().year
    origem = Origem(anos_consultados=(PRIMEIRO_ANO, ano_final))
    falhas = []
    for ano in range(PRIMEIRO_ANO, ano_final + 1):
        nome = nome_arquivo(ano)
        try:
            r = session.head(url_arquivo(ano), timeout=timeout, allow_redirects=True)
        except Exception as exc:  # noqa: BLE001 (rede: registra e segue com os outros anos)
            falhas.append(f"{nome}: {exc}")
            continue
        if r.status_code == 404:
            origem.ausentes.add(nome)
        elif r.status_code == 200:
            origem.versoes[nome] = Versao(
                nome=nome,
                ano=ano,
                etag=r.headers.get("ETag", "").strip('"'),
                last_modified=r.headers.get("Last-Modified", ""),
                tamanho=int(r.headers.get("Content-Length") or 0),
            )
        else:
            falhas.append(f"{nome}: HTTP {r.status_code}")
    if not origem.versoes and not origem.ausentes:
        raise OrigemIndisponivel("; ".join(falhas) or "nenhum arquivo consultado")
    return origem


def listar_landing(bucket) -> dict[str, dict[str, str]]:
    """Objetos .csv.zip do landing → metadata customizada (`bucket` = google.cloud.storage.Bucket)."""
    out = {}
    for blob in bucket.list_blobs(prefix=PREFIXO_LANDING):
        nome = blob.name.rsplit("/", 1)[-1]
        if _NOME.match(nome):
            out[nome] = dict(blob.metadata or {})
    return out


@dataclass
class Plano:
    baixar: list[dict] = field(default_factory=list)  # Versao como dict (vai por XCom)
    apagar: list[str] = field(default_factory=list)  # nomes no landing
    carregar: list[int] = field(default_factory=list)  # anos
    remover_da_bronze: list[int] = field(default_factory=list)  # anos

    def vazio(self) -> bool:
        return not (self.baixar or self.apagar or self.carregar or self.remover_da_bronze)

    def as_dict(self) -> dict:
        return asdict(self)


def planejar_sync(origem: Origem, landing: dict[str, dict[str, str]]) -> Plano:
    """Compara origem × landing (espelho exato).

    - baixar: novo na origem, ou ETag OU Last-Modified diferente do registrado no landing;
    - apagar: no landing e confirmadamente fora da origem (404, ou ano fora do intervalo
      consultado). Falha de rede num arquivo NÃO conta como remoção;
    - carregar: anos baixados + anos cujo landing está à frente da bronze
      (bronze_etag ≠ origem_etag: carga anterior que falhou);
    - remover_da_bronze: anos apagados.
    """
    plano = Plano()
    inicio, fim = origem.anos_consultados
    for nome, v in sorted(origem.versoes.items()):
        meta = landing.get(nome)
        if (
            meta is None
            or meta.get("origem_etag") != v.etag
            or meta.get("origem_last_modified") != v.last_modified
        ):
            plano.baixar.append(asdict(v))
    baixar = {d["nome"] for d in plano.baixar}
    for nome in sorted(landing):
        ano = ano_do_nome(nome)
        fora_do_intervalo = ano is None or not inicio <= ano <= fim
        if nome in origem.ausentes or (fora_do_intervalo and nome not in origem.versoes):
            plano.apagar.append(nome)
            if ano is not None:
                plano.remover_da_bronze.append(ano)
    apagar = set(plano.apagar)
    carregar = {d["ano"] for d in plano.baixar}
    for nome, meta in landing.items():
        if nome in baixar or nome in apagar or nome not in origem.versoes:
            continue
        if meta.get("bronze_etag") != meta.get("origem_etag"):
            carregar.add(ano_do_nome(nome))
    plano.carregar = sorted(carregar)
    plano.remover_da_bronze = sorted(set(plano.remover_da_bronze))
    return plano


def contar_registros_csv(caminho: str, encoding: str = "utf-8") -> tuple[int, list[str]]:
    """(registros sem o cabeçalho, colunas). Usa o leitor de CSV: campos entre aspas com
    quebra de linha contam como um registro só."""
    with open(caminho, newline="", encoding=encoding, errors="strict") as f:
        leitor = csv.reader(f)
        colunas = [c.strip() for c in next(leitor)]
        return sum(1 for _ in leitor), colunas


def contar_com_encoding(caminho: str) -> tuple[int, list[str], str]:
    """Tenta UTF-8 e cai para latin-1 (anos antigos do DATASUS). Devolve (registros, colunas, encoding)."""
    try:
        n, colunas = contar_registros_csv(caminho, "utf-8")
        return n, colunas, "UTF-8"
    except UnicodeDecodeError:
        n, colunas = contar_registros_csv(caminho, "latin-1")
        return n, colunas, "ISO-8859-1"


def blob_zip(bucket, nome: str):
    return bucket.blob(PREFIXO_LANDING + nome)


def blob_csv(bucket, nome: str):
    return bucket.blob(PREFIXO_LANDING + nome.removesuffix(".zip"))


def baixar_para_landing(session, bucket, versao: dict, tmpdir: str, timeout: int = 600) -> dict:
    """Baixa a versão da origem e substitui o arquivo no landing (zip original + CSV).

    Ordem: CSV primeiro, depois o zip com a metadata. O estado (metadata do zip) só muda
    quando os dois objetos já estão no lugar. Se o zip já tem o mesmo origem_etag
    (retentativa), não envia de novo. Devolve o resumo da versão no landing.
    """
    import os
    import time
    import zipfile

    nome, etag = versao["nome"], versao["etag"]
    destino_zip = blob_zip(bucket, nome)
    if destino_zip.exists():
        destino_zip.reload()
        meta = destino_zip.metadata or {}
        if meta.get("origem_etag") == etag and meta.get("origem_last_modified") == versao["last_modified"]:
            return {"nome": nome, "ano": versao["ano"], "reenviado": False, **meta}

    t0 = time.perf_counter()
    caminho_zip = os.path.join(tmpdir, nome)
    with session.get(url_arquivo(versao["ano"]), stream=True, timeout=timeout) as r:
        r.raise_for_status()
        with open(caminho_zip, "wb") as f:
            for chunk in r.iter_content(chunk_size=8 * 1024 * 1024):
                f.write(chunk)
    with zipfile.ZipFile(caminho_zip) as z:
        membros = [m for m in z.namelist() if m.lower().endswith(".csv")]
        if len(membros) != 1:
            raise ValueError(f"{nome}: esperado 1 CSV no zip, encontrado {z.namelist()}")
        caminho_csv = z.extract(membros[0], tmpdir)
    registros, colunas, encoding = contar_com_encoding(caminho_csv)

    blob_csv(bucket, nome).upload_from_filename(caminho_csv, content_type="text/csv", timeout=timeout)
    meta = {
        "origem_etag": etag,
        "origem_last_modified": versao["last_modified"],
        "origem_tamanho": str(versao["tamanho"]),
        "registros": str(registros),
        "colunas": str(len(colunas)),
        "encoding": encoding,
    }
    destino_zip.metadata = meta  # sem bronze_etag: a versão nova ainda não foi carregada
    destino_zip.upload_from_filename(caminho_zip, content_type="application/zip", timeout=timeout)
    return {
        "nome": nome,
        "ano": versao["ano"],
        "reenviado": True,
        "segundos": round(time.perf_counter() - t0, 1),
        "bytes_zip": os.path.getsize(caminho_zip),
        "bytes_csv": os.path.getsize(caminho_csv),
        **meta,
    }


def apagar_do_landing(bucket, nome: str) -> list[str]:
    """Remove o zip e o CSV de um arquivo que saiu da origem. Devolve os objetos apagados."""
    apagados = []
    for blob in (blob_zip(bucket, nome), blob_csv(bucket, nome)):
        if blob.exists():
            blob.delete()
            apagados.append(blob.name)
    return apagados
