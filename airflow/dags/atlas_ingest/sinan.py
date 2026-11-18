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
DATASET_BRONZE = "bronze"
COLUNAS_LINHAGEM = ("ano_arquivo", "arquivo_etag", "arquivo_uri", "carregado_em")
# Colunas que a modelagem (bronze_dengue_brasil) usa; a validação exige todas. Cada item
# aceita nomes alternativos: o layout do SINAN Windows (2000-2006) usa CON_CLASSI/CON_EVOLUC
# no lugar de CLASSI_FIN/EVOLUCAO (SINAN Net, 2007+).
COLUNAS_OBRIGATORIAS = (
    ("DT_NOTIFIC",),
    ("SG_UF_NOT",),
    ("ID_MUNICIP",),
    ("SG_UF",),
    ("ID_MN_RESI",),
    ("DT_SIN_PRI",),
    ("CLASSI_FIN", "CON_CLASSI"),
    ("EVOLUCAO", "CON_EVOLUC"),
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


# ---------------------------------------------------------------------------------------
# Tabela bronze (BigQuery)
# ---------------------------------------------------------------------------------------


def colunas_faltando(colunas: list[str]) -> list[str]:
    """Colunas obrigatórias ausentes (cada item aceita os nomes alternativos)."""
    presentes = set(colunas)
    return ["|".join(alts) for alts in COLUNAS_OBRIGATORIAS if not presentes.intersection(alts)]


def validar_contagens(ano: int, registros: int, output_rows: int, linhas_particao: int, colunas: list[str]):
    """Levanta ValueError se a carga do ano não bate com o arquivo do landing."""
    problemas = []
    if not registros == output_rows == linhas_particao:
        problemas.append(
            f"contagens divergentes: arquivo={registros} load={output_rows} partição={linhas_particao}"
        )
    faltando = colunas_faltando(colunas)
    if faltando:
        problemas.append(f"colunas obrigatórias ausentes: {', '.join(faltando)}")
    if problemas:
        raise ValueError(f"Ano {ano}: " + "; ".join(problemas))


def ddl_tabela_bronze(projeto: str, dataset: str = DATASET_BRONZE, tabela: str = TABELA_BRONZE) -> str:
    """Cria a tabela se não existir: partição por ano do arquivo, cluster pela UF de notificação.
    As colunas da origem entram depois, por ALLOW_FIELD_ADDITION, conforme cada ano."""
    return f"""
CREATE TABLE IF NOT EXISTS `{projeto}.{dataset}.{tabela}` (
  ano_arquivo INT64 NOT NULL OPTIONS(description="Ano do arquivo DENGBR<aa> de origem"),
  arquivo_etag STRING OPTIONS(description="ETag da versão do arquivo na origem (OpenDataSUS)"),
  arquivo_uri STRING OPTIONS(description="Arquivo CSV no landing que gerou a partição"),
  carregado_em TIMESTAMP OPTIONS(description="Momento da carga da partição"),
  SG_UF_NOT STRING
)
PARTITION BY RANGE_BUCKET(ano_arquivo, GENERATE_ARRAY(2000, 2101, 1))
CLUSTER BY SG_UF_NOT
OPTIONS(description="{_DESCRICAO_TABELA}")
""".strip()


_DESCRICAO_TABELA = (
    "Microdados de dengue do SINAN (OpenDataSUS), sem transformação: colunas de origem como texto, "
    "uma partição por ano de arquivo. Carregada pela ingestao_sinan_brasil a partir de "
    "gs://<bucket>/landing/sinan/dengue/."
)


def sql_carga(staging: str, colunas_staging: list[str], colunas_destino: list[str]) -> str:
    """SELECT da staging para a partição do ano: todas as colunas que a tabela já tem ou passa a
    ter (as ausentes no ano viram NULL), mais as colunas de linhagem (parâmetros @ano, @etag, @uri).
    Não depende de o BigQuery aceitar uma partição com schema menor que o da tabela."""
    origem = [c for c in colunas_destino if c not in COLUNAS_LINHAGEM]
    todas = origem + [c for c in colunas_staging if c not in origem]
    stg = set(colunas_staging)
    selects = [f"`{c}`" if c in stg else f"CAST(NULL AS STRING) AS `{c}`" for c in todas]
    selects += [
        "@ano AS ano_arquivo",
        "@etag AS arquivo_etag",
        "@uri AS arquivo_uri",
        "CURRENT_TIMESTAMP() AS carregado_em",
    ]
    return "SELECT\n  " + ",\n  ".join(selects) + f"\nFROM `{staging}`"


def ler_cabecalho_csv(blob, encoding: str = "UTF-8") -> list[str]:
    """Primeira linha do CSV no landing, sem baixar o arquivo inteiro."""
    trecho = blob.download_as_bytes(start=0, end=64 * 1024)
    texto = trecho.decode("latin-1" if encoding.upper().startswith("ISO") else "utf-8", errors="replace")
    return [c.strip().strip('"') for c in next(csv.reader([texto.splitlines()[0]]))]


def carregar_ano_na_bronze(bq, bucket, ano: int, projeto: str) -> dict:
    """Landing → staging (load job) → partição do ano (query job atômico) → apaga a staging.
    `bq` = google.cloud.bigquery.Client; devolve as contagens para a validação."""
    from google.cloud import bigquery

    nome = nome_arquivo(ano)
    zip_blob = blob_zip(bucket, nome)
    zip_blob.reload()
    meta = zip_blob.metadata or {}
    csv_blob = blob_csv(bucket, nome)
    uri = f"gs://{bucket.name}/{csv_blob.name}"
    colunas = ler_cabecalho_csv(csv_blob, meta.get("encoding", "UTF-8"))
    destino = f"{projeto}.{DATASET_BRONZE}.{TABELA_BRONZE}"
    staging = f"{projeto}.{DATASET_BRONZE}._stg_sinan_dengue_{ano}"

    bq.query(ddl_tabela_bronze(projeto)).result()
    load = bq.load_table_from_uri(
        uri,
        staging,
        job_config=bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.CSV,
            schema=[bigquery.SchemaField(c, "STRING") for c in colunas],
            skip_leading_rows=1,
            allow_quoted_newlines=True,
            # há bytes de controle nos arquivos (ex.: \x00 em DT_OBITO de DENGBR08): a bronze guarda o
            # dado como veio da origem, em vez de rejeitar o arquivo inteiro
            preserve_ascii_control_characters=True,
            encoding=meta.get("encoding", "UTF-8"),
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        ),
    )
    load.result()
    try:
        colunas_destino = [f.name for f in bq.get_table(destino).schema]
        sql = sql_carga(staging, colunas, colunas_destino)
        cfg = bigquery.QueryJobConfig(
            destination=f"{destino}${ano}",
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
            schema_update_options=[bigquery.SchemaUpdateOption.ALLOW_FIELD_ADDITION],
            query_parameters=[
                bigquery.ScalarQueryParameter("ano", "INT64", ano),
                bigquery.ScalarQueryParameter("etag", "STRING", meta.get("origem_etag")),
                bigquery.ScalarQueryParameter("uri", "STRING", uri),
            ],
        )
        bq.query(sql, job_config=cfg).result()
    finally:
        bq.delete_table(staging, not_found_ok=True)
    linhas = next(
        iter(bq.query(f"SELECT COUNT(*) AS n FROM `{destino}` WHERE ano_arquivo = {int(ano)}").result())
    ).n
    return {
        "ano": ano,
        "nome": nome,
        "etag": meta.get("origem_etag"),
        "registros": int(meta.get("registros", -1)),
        "output_rows": int(load.output_rows or 0),
        "linhas_particao": int(linhas),
        "colunas": colunas,
    }


def marcar_carregado(bucket, ano: int, etag: str) -> None:
    """Grava bronze_etag na metadata do zip: a versão saiu do plano dos próximos dias."""
    blob = blob_zip(bucket, nome_arquivo(ano))
    blob.reload()
    meta = dict(blob.metadata or {})
    if meta.get("origem_etag") != etag:
        raise ValueError(
            f"{blob.name}: o landing mudou durante a carga ({meta.get('origem_etag')} != {etag})"
        )
    meta["bronze_etag"] = etag
    blob.metadata = meta
    blob.patch()


def remover_ano_da_bronze(bq, ano: int, projeto: str) -> int:
    """Apaga a partição de um ano que saiu da origem. Devolve as linhas removidas."""
    destino = f"{projeto}.{DATASET_BRONZE}.{TABELA_BRONZE}"
    job = bq.query(f"DELETE FROM `{destino}` WHERE ano_arquivo = {int(ano)}")
    job.result()
    return int(job.num_dml_affected_rows or 0)
