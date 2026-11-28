"""SINAN (dengue) do OpenDataSUS: sync dos arquivos anuais com o landing e carga na bronze.

Origem (pública):  https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/SINAN/Dengue/csv/DENGBR<aa>.csv.zip
Landing (espelho): gs://<bucket>/<prefixo do ambiente>DENGBR<aa>.csv.zip  (+ .csv descompactado)
                   (landing/sinan/dengue/ em dev; landing/<ambiente>/sinan/dengue/ em hml e prod;
                    a bronze também é do ambiente: bronze, bronze_hml ou bronze_prod; ver ambiente.py)

O estado do sync fica na metadata do .csv.zip no landing:
    origem_etag, origem_last_modified, origem_tamanho  ← cabeçalhos da origem no download
    registros                                         ← registros contados no CSV
    bronze_etag                                       ← versão já carregada e validada na bronze

O ETag da origem é de upload multipart do S3 (ex.: "77c3…-5"), não o MD5 do conteúdo:
a comparação é sempre contra a metadata gravada, nunca contra o hash do objeto no GCS.

As funções de plano são puras (testáveis sem rede); as de I/O recebem clientes prontos.

Logs: tudo vai pelo logger deste módulo (`atlas_ingest.sinan`), que o Airflow junta ao log da
tarefa. A ideia é que o log de uma execução conte, sozinho, o que aconteceu com os dados: por que
cada arquivo entrou (ou não) no plano, quanto foi baixado, quantos registros cada ano tinha antes e
passou a ter, por UF, quais colunas apareceram e quanto o BigQuery processou. As funções que montam
esses textos (explicar_plano, perfil/comparar_perfis, formatar_tabela) são puras e testadas.
"""

from __future__ import annotations

import csv
import logging
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import date

from atlas_ingest import ambiente

log = logging.getLogger(__name__)

BASE_URL = "https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/SINAN/Dengue/csv"
PRIMEIRO_ANO = 2000
TABELA_BRONZE = ambiente.TABELA_BRONZE_SINAN
# O prefixo do landing e o dataset da bronze dependem do ambiente (ATLAS_ENV) e são lidos
# a cada chamada: ambiente.prefixo_landing() e ambiente.dataset("bronze").
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


# ---------------------------------------------------------------------------------------
# Formatação para o log (puras)
# ---------------------------------------------------------------------------------------


def fmt_int(n: int | str | None) -> str:
    """1234567 → '1.234.567' (separador de milhar brasileiro); None/'' → '-'."""
    if n is None or n == "":
        return "-"
    try:
        return f"{int(n):,}".replace(",", ".")
    except (TypeError, ValueError):
        return str(n)


def fmt_delta(antes: int | None, depois: int | None) -> str:
    """Variação com sinal e percentual: '+5.433 (+0,4%)'. Sem 'antes' → 'novo'."""
    if antes is None:
        return "novo"
    if depois is None:
        return "removido"
    d = int(depois) - int(antes)
    pct = f" ({d / int(antes) * 100:+.1f}%)".replace(".", ",") if antes else ""
    return f"{'+' if d > 0 else ''}{fmt_int(d)}{pct}" if d else "sem variação"


def fmt_bytes(n: int | str | None) -> str:
    """Tamanho legível: 123456789 → '117,7 MB'."""
    if n in (None, ""):
        return "-"
    v = float(n)
    for unidade in ("B", "KB", "MB", "GB", "TB"):
        if v < 1024 or unidade == "TB":
            return (f"{v:.0f} {unidade}" if unidade == "B" else f"{v:.1f} {unidade}").replace(".", ",")
        v /= 1024
    return str(n)  # pragma: no cover


def formatar_tabela(cabecalho: list[str], linhas: list[list], titulo: str = "") -> str:
    """Tabela de texto alinhada (monoespaçada) para o log da tarefa."""
    dados = [[str(c) for c in cabecalho]] + [[str(c) for c in linha] for linha in linhas]
    larguras = [max(len(linha[i]) for linha in dados) for i in range(len(cabecalho))]

    def fmt(linha):
        return "  ".join(c.ljust(larguras[i]) for i, c in enumerate(linha)).rstrip()

    out = [titulo] if titulo else []
    out += [fmt(dados[0]), "  ".join("-" * w for w in larguras)]
    out += [fmt(linha) for linha in dados[1:]] or ["(nenhuma linha)"]
    return "\n".join(out)


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
    # Falha num arquivo não é ausência: o arquivo fica de fora do plano hoje (nem baixa nem apaga)
    # e volta a ser consultado na próxima execução. Vale registrar cada uma para não passar batido.
    for falha in falhas:
        log.warning("origem: consulta falhou (o arquivo fica como está até a próxima execução) - %s", falha)
    if not origem.versoes and not origem.ausentes:
        raise OrigemIndisponivel("; ".join(falhas) or "nenhum arquivo consultado")
    log.info(
        "origem (OpenDataSUS): anos %s-%s consultados | %d arquivos publicados (%s no total) | "
        "%d ausentes (404) | %d falhas de consulta",
        PRIMEIRO_ANO,
        ano_final,
        len(origem.versoes),
        fmt_bytes(sum(v.tamanho for v in origem.versoes.values())),
        len(origem.ausentes),
        len(falhas),
    )
    return origem


def listar_landing(bucket) -> dict[str, dict[str, str]]:
    """Objetos .csv.zip do landing → metadata customizada (`bucket` = google.cloud.storage.Bucket)."""
    out = {}
    for blob in bucket.list_blobs(prefix=ambiente.prefixo_landing()):
        nome = blob.name.rsplit("/", 1)[-1]
        if _NOME.match(nome):
            out[nome] = dict(blob.metadata or {})
    em_dia = sum(
        1 for m in out.values() if m.get("bronze_etag") and m.get("bronze_etag") == m.get("origem_etag")
    )
    log.info(
        "landing (gs://%s/%s): %d arquivos | %d com a bronze em dia | %s registros somados",
        getattr(bucket, "name", "?"),
        ambiente.prefixo_landing(),
        len(out),
        em_dia,
        fmt_int(sum(int(m.get("registros") or 0) for m in out.values())),
    )
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


def _curto(etag: str | None) -> str:
    """ETag encurtado para caber na tabela do log ('77c3a1b2…-5')."""
    if not etag:
        return "-"
    base, _, partes = etag.partition("-")
    return (base[:8] + "…" if len(base) > 9 else base) + (f"-{partes}" if partes else "")


def explicar_plano(origem: Origem, landing: dict[str, dict[str, str]], plano: Plano) -> list[dict]:
    """Uma linha por arquivo (origem ∪ landing) dizendo o que o plano faz com ele e por quê.

    Repete as regras de planejar_sync só para explicar; quem decide é o plano (as ações saem dele).
    """
    baixar = {d["nome"] for d in plano.baixar}
    apagar = set(plano.apagar)
    carregar = set(plano.carregar)
    linhas = []
    for nome in sorted(set(origem.versoes) | set(landing)):
        v = origem.versoes.get(nome)
        meta = landing.get(nome) or {}
        ano = ano_do_nome(nome)
        if nome in baixar:
            if not meta:
                acao, motivo = "baixar + carregar", "novo na origem (não existe no landing)"
            else:
                mudou = []
                if meta.get("origem_etag") != v.etag:
                    mudou.append(f"ETag {_curto(meta.get('origem_etag'))} → {_curto(v.etag)}")
                if meta.get("origem_last_modified") != v.last_modified:
                    mudou.append(
                        f"publicado em {meta.get('origem_last_modified') or '-'} → {v.last_modified}"
                    )
                if str(v.tamanho) != (meta.get("origem_tamanho") or str(v.tamanho)):
                    mudou.append(f"tamanho {fmt_bytes(meta.get('origem_tamanho'))} → {fmt_bytes(v.tamanho)}")
                acao, motivo = "baixar + carregar", "alterado na origem: " + "; ".join(mudou)
        elif nome in apagar:
            acao = "apagar + remover da bronze"
            motivo = (
                "a origem respondeu 404" if nome in origem.ausentes else "ano fora do intervalo consultado"
            )
        elif ano in carregar:
            acao = "carregar (sem baixar)"
            motivo = (
                "nunca carregado na bronze"
                if not meta.get("bronze_etag")
                else f"bronze atrás do landing (bronze {_curto(meta.get('bronze_etag'))}, "
                f"landing {_curto(meta.get('origem_etag'))}): carga anterior falhou ou não terminou"
            )
        elif v is None and meta:
            acao, motivo = "nada", "consulta à origem falhou hoje: mantido como está"
        else:
            acao, motivo = "nada", "em dia (mesma versão na origem, no landing e na bronze)"
        linhas.append(
            {
                "arquivo": nome,
                "ano": ano,
                "acao": acao,
                "motivo": motivo,
                "tamanho_origem": v.tamanho if v else None,
                "registros_landing": meta.get("registros"),
            }
        )
    return linhas


def tabela_plano(origem: Origem, landing: dict[str, dict[str, str]], plano: Plano) -> str:
    """Texto do log com a decisão por arquivo e o resumo do plano."""
    linhas = explicar_plano(origem, landing, plano)
    corpo = formatar_tabela(
        ["arquivo", "ação", "tamanho na origem", "registros no landing", "motivo"],
        [
            [
                x["arquivo"],
                x["acao"],
                fmt_bytes(x["tamanho_origem"]),
                fmt_int(x["registros_landing"]),
                x["motivo"],
            ]
            for x in linhas
        ],
        titulo="Decisão por arquivo (OpenDataSUS × landing × bronze):",
    )
    resumo = (
        f"Plano: baixar {len(plano.baixar)} "
        f"({fmt_bytes(sum(d['tamanho'] for d in plano.baixar))}: {[d['ano'] for d in plano.baixar]}) | "
        f"apagar {len(plano.apagar)} {plano.apagar} | carregar {len(plano.carregar)} {plano.carregar} | "
        f"remover da bronze {len(plano.remover_da_bronze)} {plano.remover_da_bronze} | "
        f"em dia {sum(1 for x in linhas if x['acao'] == 'nada')}"
    )
    return corpo + "\n" + resumo


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
    return bucket.blob(ambiente.prefixo_landing() + nome)


def blob_csv(bucket, nome: str):
    return bucket.blob(ambiente.prefixo_landing() + nome.removesuffix(".zip"))


def baixar_para_landing(session, bucket, versao: dict, tmpdir: str, timeout: int = 600) -> dict:
    """Baixa a versão da origem e substitui o arquivo no landing (zip original + CSV).

    Ordem: CSV primeiro, depois o zip com a metadata. O estado (metadata do zip) só muda
    quando os dois objetos já estão no lugar. Se o zip já tem o mesmo origem_etag
    (retentativa), não envia de novo. Devolve o resumo da versão no landing.
    """
    import os
    import zipfile

    nome, etag = versao["nome"], versao["etag"]
    log.info(
        "%s: versão na origem ETag=%s, publicada em %s, %s",
        nome,
        etag,
        versao["last_modified"],
        fmt_bytes(versao["tamanho"]),
    )
    destino_zip = blob_zip(bucket, nome)
    anterior: dict = {}
    if destino_zip.exists():
        destino_zip.reload()
        anterior = dict(destino_zip.metadata or {})
        if (
            anterior.get("origem_etag") == etag
            and anterior.get("origem_last_modified") == versao["last_modified"]
        ):
            # Retentativa depois de uma falha mais adiante: o landing já tem esta versão.
            log.info("%s: o landing já tem esta versão (retentativa); nada foi enviado de novo", nome)
            return {"nome": nome, "ano": versao["ano"], "reenviado": False, **anterior}
        log.info(
            "%s: versão anterior no landing ETag=%s, publicada em %s, %s registros, %s colunas, %s",
            nome,
            anterior.get("origem_etag"),
            anterior.get("origem_last_modified"),
            fmt_int(anterior.get("registros")),
            anterior.get("colunas", "-"),
            anterior.get("encoding", "-"),
        )
    else:
        log.info("%s: arquivo novo, ainda não existe no landing", nome)

    # 1) download em streaming (o arquivo de um ano chega a centenas de MB)
    t0 = time.perf_counter()
    caminho_zip = os.path.join(tmpdir, nome)
    with session.get(url_arquivo(versao["ano"]), stream=True, timeout=timeout) as r:
        r.raise_for_status()
        with open(caminho_zip, "wb") as f:
            for chunk in r.iter_content(chunk_size=8 * 1024 * 1024):
                f.write(chunk)
    bytes_zip = os.path.getsize(caminho_zip)
    t_download = time.perf_counter() - t0
    log.info(
        "%s: download concluído, %s em %.1f s (%s/s)",
        nome,
        fmt_bytes(bytes_zip),
        t_download,
        fmt_bytes(bytes_zip / t_download if t_download else 0),
    )
    if versao["tamanho"] and bytes_zip != versao["tamanho"]:
        log.warning(
            "%s: tamanho baixado (%s) difere do Content-Length do HEAD (%s): a origem pode ter mudado",
            nome,
            fmt_int(bytes_zip),
            fmt_int(versao["tamanho"]),
        )

    # 2) descompacta e conta os registros com o leitor de CSV (é a contagem que a validação usa)
    with zipfile.ZipFile(caminho_zip) as z:
        membros = [m for m in z.namelist() if m.lower().endswith(".csv")]
        if len(membros) != 1:
            raise ValueError(f"{nome}: esperado 1 CSV no zip, encontrado {z.namelist()}")
        caminho_csv = z.extract(membros[0], tmpdir)
    registros, colunas, encoding = contar_com_encoding(caminho_csv)
    log.info(
        "%s: CSV %s descompactado (%s) | %s registros | %d colunas | encoding %s",
        nome,
        membros[0],
        fmt_bytes(os.path.getsize(caminho_csv)),
        fmt_int(registros),
        len(colunas),
        encoding,
    )
    if anterior:
        log.info(
            "%s: registros no landing %s → %s (%s) | colunas %s → %d",
            nome,
            fmt_int(anterior.get("registros")),
            fmt_int(registros),
            fmt_delta(int(anterior["registros"]) if anterior.get("registros") else None, registros),
            anterior.get("colunas", "-"),
            len(colunas),
        )
        if anterior.get("registros") and registros < int(anterior["registros"]):
            log.warning(
                "%s: a nova versão tem MENOS registros que a anterior (%s): o SINAN pode ter "
                "excluído ou deduplicado notificações; a bronze vai refletir isso",
                nome,
                fmt_delta(int(anterior["registros"]), registros),
            )
    faltando = colunas_faltando(colunas)
    if faltando:
        # Não para aqui: a validação da carga é que reprova. O aviso adianta o diagnóstico.
        log.warning("%s: colunas obrigatórias ausentes no CSV: %s", nome, ", ".join(faltando))

    # 3) envia: CSV primeiro, zip (com o estado na metadata) por último
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
    segundos = round(time.perf_counter() - t0, 1)
    log.info(
        "%s: landing atualizado em gs://%s/%s (+ .csv) em %.1f s no total; a bronze ainda não tem "
        "esta versão (sem bronze_etag até a carga ser validada)",
        nome,
        getattr(bucket, "name", "?"),
        destino_zip.name,
        segundos,
    )
    return {
        "nome": nome,
        "ano": versao["ano"],
        "reenviado": True,
        "segundos": segundos,
        "bytes_zip": bytes_zip,
        "bytes_csv": os.path.getsize(caminho_csv),
        "registros_anteriores": anterior.get("registros"),
        **meta,
    }


def apagar_do_landing(bucket, nome: str) -> list[str]:
    """Remove o zip e o CSV de um arquivo que saiu da origem. Devolve os objetos apagados."""
    apagados = []
    zip_blob = blob_zip(bucket, nome)
    if zip_blob.exists():
        zip_blob.reload()
        meta = zip_blob.metadata or {}
        log.info(
            "%s: saiu da origem; o landing tinha ETag=%s, publicada em %s, %s registros",
            nome,
            meta.get("origem_etag"),
            meta.get("origem_last_modified"),
            fmt_int(meta.get("registros")),
        )
    for blob in (zip_blob, blob_csv(bucket, nome)):
        if blob.exists():
            blob.delete()
            apagados.append(blob.name)
            log.info("%s: apagado gs://%s/%s", nome, getattr(bucket, "name", "?"), blob.name)
    if not apagados:
        log.info("%s: nada a apagar (os objetos já não existiam no landing)", nome)
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
    else:
        log.info(
            "ano %s: contagens batem - arquivo=%s, load job=%s, partição=%s",
            ano,
            fmt_int(registros),
            fmt_int(output_rows),
            fmt_int(linhas_particao),
        )
    faltando = colunas_faltando(colunas)
    if faltando:
        problemas.append(f"colunas obrigatórias ausentes: {', '.join(faltando)}")
    else:
        presentes = set(colunas)
        usadas = [next(a for a in alts if a in presentes) for alts in COLUNAS_OBRIGATORIAS]
        log.info(
            "ano %s: as %d colunas obrigatórias estão presentes (%s)", ano, len(usadas), ", ".join(usadas)
        )
    if problemas:
        log.error("ano %s: validação REPROVADA - %s", ano, "; ".join(problemas))
        raise ValueError(f"Ano {ano}: " + "; ".join(problemas))
    log.info("ano %s: validação aprovada", ano)


def ddl_dataset_bronze(projeto: str, dataset: str | None = None, location: str = "US") -> str:
    """Cria o dataset da bronze do ambiente se não existir (mesma location dos demais)."""
    dataset = dataset or ambiente.dataset("bronze")
    return f'CREATE SCHEMA IF NOT EXISTS `{projeto}.{dataset}` OPTIONS(location="{location}")'


def ddl_tabela_bronze(projeto: str, dataset: str | None = None, tabela: str = TABELA_BRONZE) -> str:
    """Cria a tabela se não existir: partição por ano do arquivo, cluster pela UF de notificação.
    As colunas da origem entram depois, por ALLOW_FIELD_ADDITION, conforme cada ano."""
    dataset = dataset or ambiente.dataset("bronze")
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
    "gs://<bucket>/landing/<ambiente>/sinan/dengue/ (em dev, landing/sinan/dengue/)."
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


# ---------------------------------------------------------------------------------------
# Perfil de uma partição (antes × depois da carga), só para o log
# ---------------------------------------------------------------------------------------

# SG_UF_NOT/SG_UF vêm com o código IBGE da UF; a sigla deixa o log legível.
UF_IBGE = {
    "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP", "17": "TO",
    "21": "MA", "22": "PI", "23": "CE", "24": "RN", "25": "PB",
    "26": "PE", "27": "AL", "28": "SE", "29": "BA",
    "31": "MG", "32": "ES", "33": "RJ", "35": "SP",
    "41": "PR", "42": "SC", "43": "RS",
    "50": "MS", "51": "MT", "52": "GO", "53": "DF",
}  # fmt: skip


def perfil_de_linhas(linhas) -> dict:
    """Linhas (uf, n, dt_min, dt_max, etag) da consulta de perfil → resumo da partição."""
    por_uf, dt_min, dt_max, etags = {}, None, None, set()
    for uf, n, dmin, dmax, etag in linhas:
        por_uf[str(uf) if uf is not None else "(vazio)"] = int(n)
        dt_min = min(filter(None, (dt_min, dmin)), default=None)
        dt_max = max(filter(None, (dt_max, dmax)), default=None)
        if etag:
            etags.add(etag)
    return {
        "total": sum(por_uf.values()),
        "por_uf": por_uf,
        "dt_notific_min": dt_min,
        "dt_notific_max": dt_max,
        "etags": sorted(etags),
    }


def _uf(codigo: str) -> str:
    return f"{codigo} {UF_IBGE[codigo]}" if codigo in UF_IBGE else codigo


def comparar_perfis(ano: int, antes: dict | None, depois: dict | None) -> str:
    """Texto do log com o que mudou na partição do ano: total, intervalo de datas e UF a UF."""
    a = (antes or {}).get("por_uf", {})
    d = (depois or {}).get("por_uf", {})
    total_a = (antes or {}).get("total")
    total_d = (depois or {}).get("total")
    variacao = fmt_delta(total_a if antes else None, total_d)
    linhas = [
        f"Partição {ano} da bronze: {fmt_int(total_a) if antes else 'não existia'} → "
        f"{fmt_int(total_d) if depois else 'removida'} linhas ({variacao})"
    ]
    for rotulo, chave in (("DT_NOTIFIC mínima", "dt_notific_min"), ("DT_NOTIFIC máxima", "dt_notific_max")):
        va, vd = (antes or {}).get(chave), (depois or {}).get(chave)
        if va or vd:
            linhas.append(f"  {rotulo}: {va or '-'} → {vd or '-'}" + ("" if va != vd else " (igual)"))
    ufs = sorted(set(a) | set(d))
    if ufs:
        corpo = [
            [_uf(uf), fmt_int(a.get(uf)), fmt_int(d.get(uf)), fmt_delta(a.get(uf), d.get(uf))] for uf in ufs
        ]
        linhas.append(formatar_tabela(["UF notificação", "antes", "depois", "variação"], corpo))
        maiores = sorted(
            (uf for uf in ufs if uf in a and uf in d and d[uf] != a[uf]),
            key=lambda uf: abs(d[uf] - a[uf]),
            reverse=True,
        )[:5]
        if maiores:
            linhas.append(
                "  maiores variações: " + ", ".join(f"{_uf(uf)} {fmt_delta(a[uf], d[uf])}" for uf in maiores)
            )
        if novas := [uf for uf in ufs if uf not in a and antes]:
            linhas.append(f"  UFs que não existiam antes: {', '.join(_uf(u) for u in novas)}")
        if sumiram := [uf for uf in ufs if uf not in d and depois]:
            linhas.append(f"  UFs que sumiram: {', '.join(_uf(u) for u in sumiram)}")
    return "\n".join(linhas)


def perfil_particao(bq, destino: str, ano: int, colunas_tabela: list[str]) -> dict | None:
    """Contagem por UF, intervalo de DT_NOTIFIC e ETag da partição do ano (None se vazia).

    É só informação para o log: qualquer erro vira aviso e a carga segue. A consulta lê poucas
    colunas de uma partição só (custo baixo; a tabela é particionada por ano e clusterizada por UF).
    """
    cols = set(colunas_tabela)
    uf = "SG_UF_NOT" if "SG_UF_NOT" in cols else "CAST(NULL AS STRING)"
    dts = "MIN(DT_NOTIFIC), MAX(DT_NOTIFIC)" if "DT_NOTIFIC" in cols else "NULL, NULL"
    etag = "ANY_VALUE(arquivo_etag)" if "arquivo_etag" in cols else "NULL"
    sql = (
        f"SELECT {uf} AS uf, COUNT(*) AS n, {dts}, {etag} "
        f"FROM `{destino}` WHERE ano_arquivo = {int(ano)} GROUP BY 1"
    )
    try:
        perfil = perfil_de_linhas(tuple(r.values()) for r in bq.query(sql).result())
    except Exception as exc:  # noqa: BLE001 (perfil é informativo; não derruba a carga)
        log.warning("ano %s: não foi possível montar o perfil da partição (%s)", ano, exc)
        return None
    return perfil if perfil["total"] else None


def _job_resumo(job) -> str:
    """Id, duração e volume de um job do BigQuery para o log."""
    partes = [f"job={getattr(job, 'job_id', '?')}"]
    ini, fim = getattr(job, "started", None), getattr(job, "ended", None)
    if ini and fim:
        partes.append(f"{(fim - ini).total_seconds():.1f} s")
    for rotulo, attr in (
        ("processados", "total_bytes_processed"),
        ("faturados", "total_bytes_billed"),
        ("lidos do GCS", "input_file_bytes"),
        ("gravados", "output_bytes"),
    ):
        v = getattr(job, attr, None)
        if isinstance(v, int):
            partes.append(f"{rotulo} {fmt_bytes(v)}")
    slot_ms = getattr(job, "slot_millis", None)
    if isinstance(slot_ms, int):
        partes.append(f"{slot_ms / 1000:.1f} slot·s")
    return " | ".join(partes)


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
    dataset = ambiente.dataset("bronze")
    destino = f"{projeto}.{dataset}.{TABELA_BRONZE}"
    staging = f"{projeto}.{dataset}._stg_sinan_dengue_{ano}"
    log.info(
        "ano %s: carga %s → %s (partição %s) | versão ETag=%s publicada em %s | %s registros, %d colunas, %s",
        ano,
        uri,
        destino,
        ano,
        meta.get("origem_etag"),
        meta.get("origem_last_modified"),
        fmt_int(meta.get("registros")),
        len(colunas),
        meta.get("encoding", "UTF-8"),
    )

    # Dataset e tabela são criados na primeira carga do ambiente (idempotente).
    bq.query(ddl_dataset_bronze(projeto, dataset)).result()
    bq.query(ddl_tabela_bronze(projeto, dataset)).result()

    # Foto da partição antes de substituí-la, para o log mostrar o que a carga mudou.
    colunas_antes = [f.name for f in bq.get_table(destino).schema]
    perfil_antes = perfil_particao(bq, destino, ano, colunas_antes)
    if perfil_antes:
        log.info(
            "ano %s: partição atual tem %s linhas (versão %s)",
            ano,
            fmt_int(perfil_antes["total"]),
            ", ".join(perfil_antes["etags"]) or "-",
        )
    else:
        log.info("ano %s: a partição ainda não existe na bronze (primeira carga do ano)", ano)

    # 1) CSV do landing → staging, tudo como STRING (a bronze não interpreta tipos)
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
    log.info(
        "ano %s: staging %s carregada com %s linhas (%s)",
        ano,
        staging,
        fmt_int(load.output_rows),
        _job_resumo(load),
    )
    if load.output_rows is not None and str(load.output_rows) != str(meta.get("registros")):
        log.warning(
            "ano %s: o load job leu %s linhas, mas o CSV tem %s registros (a validação vai reprovar)",
            ano,
            fmt_int(load.output_rows),
            fmt_int(meta.get("registros")),
        )

    # 2) staging → partição do ano, num único query job (WRITE_TRUNCATE na partição: atômico;
    #    se falhar, a partição antiga continua lá). A staging é apagada mesmo com erro.
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
        job = bq.query(sql, job_config=cfg)
        job.result()
        log.info("ano %s: partição %s$%s substituída (%s)", ano, destino, ano, _job_resumo(job))
    finally:
        bq.delete_table(staging, not_found_ok=True)
        log.info("ano %s: staging %s apagada", ano, staging)

    # 3) o que mudou no schema: colunas que a tabela ganhou e colunas da tabela ausentes neste ano
    colunas_depois = [f.name for f in bq.get_table(destino).schema]
    novas = [c for c in colunas_depois if c not in colunas_antes]
    nulas = [c for c in colunas_depois if c not in colunas and c not in COLUNAS_LINHAGEM]
    if novas:
        log.info("ano %s: a tabela ganhou %d colunas novas: %s", ano, len(novas), ", ".join(novas))
    if nulas:
        log.info(
            "ano %s: %d colunas da tabela não existem no arquivo deste ano e ficaram NULL: %s",
            ano,
            len(nulas),
            ", ".join(nulas),
        )
    log.info(
        "ano %s: o arquivo deste ano tem %d colunas; a tabela tem %d (todos os anos + %d de linhagem)",
        ano,
        len(colunas),
        len(colunas_depois),
        len(COLUNAS_LINHAGEM),
    )

    # 4) contagem final (usada na validação) e comparação com a foto de antes
    linhas = next(
        iter(bq.query(f"SELECT COUNT(*) AS n FROM `{destino}` WHERE ano_arquivo = {int(ano)}").result())
    ).n
    perfil_depois = perfil_particao(bq, destino, ano, colunas_depois)
    log.info("ano %s: o que mudou nos dados\n%s", ano, comparar_perfis(ano, perfil_antes, perfil_depois))
    return {
        "ano": ano,
        "nome": nome,
        "etag": meta.get("origem_etag"),
        "registros": int(meta.get("registros", -1)),
        "output_rows": int(load.output_rows or 0),
        "linhas_particao": int(linhas),
        "colunas": colunas,
        # só para o resumo da DAG (a validação não usa)
        "linhas_antes": perfil_antes["total"] if perfil_antes else None,
        "etag_anterior": ", ".join(perfil_antes["etags"]) if perfil_antes else None,
        "colunas_novas": novas,
    }


def marcar_carregado(bucket, ano: int, etag: str) -> None:
    """Grava bronze_etag na metadata do zip: a versão saiu do plano dos próximos dias."""
    blob = blob_zip(bucket, nome_arquivo(ano))
    blob.reload()
    meta = dict(blob.metadata or {})
    if meta.get("origem_etag") != etag:
        log.error(
            "ano %s: o landing mudou durante a carga (landing %s, carregado %s); não marca, "
            "o ano volta no plano da próxima execução",
            ano,
            meta.get("origem_etag"),
            etag,
        )
        raise ValueError(
            f"{blob.name}: o landing mudou durante a carga ({meta.get('origem_etag')} != {etag})"
        )
    anterior = meta.get("bronze_etag")
    meta["bronze_etag"] = etag
    blob.metadata = meta
    blob.patch()
    log.info(
        "ano %s: bronze_etag %s → %s gravado em %s; o ano sai do plano até a origem mudar de novo",
        ano,
        anterior or "(nenhum)",
        etag,
        blob.name,
    )


def remover_ano_da_bronze(bq, ano: int, projeto: str) -> int:
    """Apaga a partição de um ano que saiu da origem. Devolve as linhas removidas."""
    destino = f"{projeto}.{ambiente.dataset('bronze')}.{TABELA_BRONZE}"
    log.info("ano %s: o arquivo saiu da origem; apagando a partição de %s", ano, destino)
    job = bq.query(f"DELETE FROM `{destino}` WHERE ano_arquivo = {int(ano)}")
    job.result()
    removidas = int(job.num_dml_affected_rows or 0)
    log.info("ano %s: %s linhas removidas da bronze (%s)", ano, fmt_int(removidas), _job_resumo(job))
    return removidas
