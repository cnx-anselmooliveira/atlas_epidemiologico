"""Plano de sync do SINAN (sem rede). Roda dentro da imagem do Airflow, sem banco nem pytest:

    docker run --rm --entrypoint python atlas-epidemiologia-airflow:local \
        /opt/atlas/tests/test_sinan_ingest.py

Também é compatível com pytest (funções test_*).
"""

import os
import sys
import tempfile

DAGS_FOLDER = os.environ.get("ATLAS_DAGS_FOLDER", "/opt/airflow/dags")
sys.path.insert(0, DAGS_FOLDER)

from atlas_ingest.sinan import (  # noqa: E402
    Origem,
    OrigemIndisponivel,
    Versao,
    ano_do_nome,
    contar_registros_csv,
    listar_origem,
    nome_arquivo,
    planejar_sync,
)

LM = "Sat, 14 Nov 2026 08:38:22 GMT"


def _origem(*versoes, ausentes=(), fim=2026):
    o = Origem(anos_consultados=(2000, fim))
    for ano, etag, lm in versoes:
        o.versoes[nome_arquivo(ano)] = Versao(nome_arquivo(ano), ano, etag, lm, 10)
    o.ausentes = {nome_arquivo(a) for a in ausentes}
    return o


def _meta(etag, lm=LM, bronze=None):
    m = {"origem_etag": etag, "origem_last_modified": lm, "registros": "5"}
    if bronze:
        m["bronze_etag"] = bronze
    return m


def test_nomes():
    assert nome_arquivo(2026) == "DENGBR26.csv.zip" and nome_arquivo(2000) == "DENGBR00.csv.zip"
    assert ano_do_nome("landing/sinan/dengue/DENGBR07.csv.zip") == 2007
    assert ano_do_nome("DENGBR26.csv") is None


def test_bucket_vazio_baixa_tudo():
    p = planejar_sync(_origem((2025, "a", LM), (2026, "b", LM)), {})
    assert [d["ano"] for d in p.baixar] == [2025, 2026]
    assert p.carregar == [2025, 2026] and not p.apagar and not p.remover_da_bronze


def test_etag_igual_e_bronze_em_dia_nao_faz_nada():
    p = planejar_sync(_origem((2026, "b", LM)), {"DENGBR26.csv.zip": _meta("b", bronze="b")})
    assert p.vazio()


def test_etag_diferente_baixa_e_carrega():
    p = planejar_sync(_origem((2026, "novo", LM)), {"DENGBR26.csv.zip": _meta("velho", bronze="velho")})
    assert [d["etag"] for d in p.baixar] == ["novo"] and p.carregar == [2026]


def test_so_a_data_diferente_tambem_baixa():
    outra = "Sun, 15 Nov 2026 08:00:00 GMT"
    p = planejar_sync(_origem((2026, "b", outra)), {"DENGBR26.csv.zip": _meta("b", bronze="b")})
    assert [d["nome"] for d in p.baixar] == ["DENGBR26.csv.zip"]


def test_removido_da_origem_apaga_e_tira_da_bronze():
    landing = {"DENGBR25.csv.zip": _meta("a", bronze="a"), "DENGBR26.csv.zip": _meta("b", bronze="b")}
    p = planejar_sync(_origem((2026, "b", LM), ausentes=[2025]), landing)
    assert p.apagar == ["DENGBR25.csv.zip"] and p.remover_da_bronze == [2025]
    assert not p.baixar and not p.carregar


def test_fora_do_intervalo_consultado_apaga():
    p = planejar_sync(
        _origem((2026, "b", LM)), {"DENGBR99.csv.zip": _meta("x"), "DENGBR26.csv.zip": _meta("b", bronze="b")}
    )
    assert p.apagar == ["DENGBR99.csv.zip"] and p.remover_da_bronze == [2099]


def test_falha_de_rede_num_arquivo_nao_apaga():
    # 2025 não respondeu (nem 200 nem 404): não está em versoes nem em ausentes
    landing = {"DENGBR25.csv.zip": _meta("a", bronze="a")}
    p = planejar_sync(_origem((2026, "b", LM)), landing)
    assert not p.apagar and [d["ano"] for d in p.baixar] == [2026]


def test_bronze_atras_do_landing_carrega_sem_baixar():
    p = planejar_sync(_origem((2026, "b", LM)), {"DENGBR26.csv.zip": _meta("b", bronze="velho")})
    assert not p.baixar and p.carregar == [2026]
    p = planejar_sync(_origem((2026, "b", LM)), {"DENGBR26.csv.zip": _meta("b")})  # nunca carregado
    assert p.carregar == [2026]


class _Resp:
    def __init__(self, status, headers=None):
        self.status_code, self.headers = status, headers or {}


class _Session:
    def __init__(self, respostas):
        self.respostas = respostas

    def head(self, url, timeout, allow_redirects):
        r = self.respostas.get(url.rsplit("/", 1)[-1])
        if isinstance(r, Exception):
            raise r
        return r or _Resp(404)


def test_listar_origem_404_e_falhas():
    s = _Session(
        {
            "DENGBR00.csv.zip": _Resp(200, {"ETag": '"abc-5"', "Last-Modified": LM, "Content-Length": "7"}),
            "DENGBR01.csv.zip": ConnectionError("timeout"),
            "DENGBR02.csv.zip": _Resp(503),
        }
    )
    o = listar_origem(s, ano_final=2003)
    assert o.versoes["DENGBR00.csv.zip"].etag == "abc-5" and o.versoes["DENGBR00.csv.zip"].tamanho == 7
    assert o.ausentes == {"DENGBR03.csv.zip"}  # falha e 503 não são ausência
    assert o.anos_consultados == (2000, 2003)


def test_origem_toda_indisponivel_levanta_erro():
    s = _Session({nome_arquivo(a): ConnectionError("dns") for a in range(2000, 2004)})
    try:
        listar_origem(s, ano_final=2003)
    except OrigemIndisponivel:
        return
    raise AssertionError("deveria levantar OrigemIndisponivel")


def test_contar_registros_com_quebra_de_linha_entre_aspas():
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8", newline="") as f:
        f.write('DT_NOTIFIC,OBS\n2026-01-01,"linha 1\nlinha 2"\n2026-01-02,simples\n')
    try:
        n, colunas = contar_registros_csv(f.name)
    finally:
        os.unlink(f.name)
    assert n == 2 and colunas == ["DT_NOTIFIC", "OBS"]


NET = ["DT_NOTIFIC", "SG_UF_NOT", "ID_MUNICIP", "SG_UF", "ID_MN_RESI", "DT_SIN_PRI", "CLASSI_FIN", "EVOLUCAO"]
WINDOWS = [c.replace("CLASSI_FIN", "CON_CLASSI").replace("EVOLUCAO", "CON_EVOLUC") for c in NET]


def test_validacao_aceita_os_dois_layouts():
    from atlas_ingest.sinan import validar_contagens

    validar_contagens(2026, 10, 10, 10, NET)
    validar_contagens(2000, 10, 10, 10, WINDOWS)


def test_validacao_falha_por_contagem_ou_coluna():
    from atlas_ingest.sinan import validar_contagens

    for args, trecho in (
        ((2026, 10, 10, 9, NET), "contagens divergentes"),
        ((2026, 10, 10, 10, [c for c in NET if c != "CLASSI_FIN"]), "CLASSI_FIN|CON_CLASSI"),
    ):
        try:
            validar_contagens(*args)
        except ValueError as exc:
            assert trecho in str(exc), exc
        else:
            raise AssertionError(f"deveria falhar: {trecho}")


def test_sql_carga_completa_colunas_e_linhagem():
    from atlas_ingest.sinan import sql_carga

    destino = ["ano_arquivo", "arquivo_etag", "arquivo_uri", "carregado_em", "SG_UF_NOT", "CLASSI_FIN"]
    sql = sql_carga("p.bronze._stg_2000", ["SG_UF_NOT", "CON_CLASSI"], destino)
    assert "`SG_UF_NOT`" in sql and "`CON_CLASSI`" in sql  # coluna nova do ano entra
    assert "CAST(NULL AS STRING) AS `CLASSI_FIN`" in sql  # coluna da tabela ausente no ano
    assert "@ano AS ano_arquivo" in sql and "@etag AS arquivo_etag" in sql
    assert sql.count("ano_arquivo") == 1  # linhagem não é copiada da staging


def test_formatadores():
    from atlas_ingest.sinan import fmt_bytes, fmt_delta, fmt_int

    assert fmt_int(1234567) == "1.234.567" and fmt_int(None) == "-" and fmt_int("12") == "12"
    assert fmt_delta(1000, 1050) == "+50 (+5,0%)" and fmt_delta(1000, 900) == "-100 (-10,0%)"
    assert (
        fmt_delta(None, 5) == "novo"
        and fmt_delta(5, None) == "removido"
        and fmt_delta(3, 3) == "sem variação"
    )
    assert fmt_bytes(512) == "512 B" and fmt_bytes(123456789) == "117,7 MB" and fmt_bytes(None) == "-"


def test_explicar_plano_da_o_motivo_de_cada_arquivo():
    from atlas_ingest.sinan import explicar_plano, tabela_plano

    outra = "Sun, 15 Nov 2026 08:00:00 GMT"
    origem = _origem(
        (2023, "a", LM), (2024, "novo", outra), (2025, "c", LM), (2026, "d", LM), ausentes=[2022]
    )
    landing = {
        "DENGBR22.csv.zip": _meta("x", bronze="x"),  # saiu da origem
        "DENGBR23.csv.zip": _meta("a", bronze="a"),  # em dia
        "DENGBR24.csv.zip": _meta("velho", bronze="velho"),  # alterado
        "DENGBR25.csv.zip": _meta("c", bronze="antigo"),  # bronze atrasada
        "DENGBR21.csv.zip": _meta("y", bronze="y"),  # consulta falhou hoje (nem 200 nem 404)
    }
    plano = planejar_sync(origem, landing)
    por_ano = {x["ano"]: x for x in explicar_plano(origem, landing, plano)}
    assert por_ano[2026]["acao"] == "baixar + carregar" and "novo na origem" in por_ano[2026]["motivo"]
    assert "alterado" in por_ano[2024]["motivo"] and "ETag velho → novo" in por_ano[2024]["motivo"]
    assert outra in por_ano[2024]["motivo"]
    assert por_ano[2025]["acao"] == "carregar (sem baixar)" and "bronze atrás" in por_ano[2025]["motivo"]
    assert por_ano[2022]["acao"].startswith("apagar") and "404" in por_ano[2022]["motivo"]
    assert por_ano[2023]["acao"] == "nada" and "em dia" in por_ano[2023]["motivo"]
    assert por_ano[2021]["acao"] == "nada" and "falhou" in por_ano[2021]["motivo"]
    texto = tabela_plano(origem, landing, plano)
    assert "DENGBR24.csv.zip" in texto and "Plano: baixar 2" in texto and "em dia 2" in texto


def test_perfil_e_comparacao_da_particao():
    from atlas_ingest.sinan import comparar_perfis, perfil_de_linhas

    antes = perfil_de_linhas(
        [("35", 100, "2026-01-02", "2026-11-01", "e1"), ("33", 50, "2026-01-01", "2026-10-30", "e1")]
    )
    assert antes["total"] == 150 and antes["dt_notific_min"] == "2026-01-01" and antes["etags"] == ["e1"]
    depois = perfil_de_linhas(
        [("35", 120, "2026-01-01", "2026-11-14", "e2"), ("33", 50, "2026-01-01", "2026-11-10", "e2"),
         ("53", 7, "2026-02-01", "2026-11-12", "e2")]
    )  # fmt: skip
    texto = comparar_perfis(2026, antes, depois)
    assert "150 → 177 linhas (+27 (+18,0%))" in texto
    assert "35 SP" in texto and "+20 (+20,0%)" in texto and "53 DF" in texto
    assert "UFs que não existiam antes: 53 DF" in texto
    assert "2026-11-01 → 2026-11-14" in texto
    assert "não existia" in comparar_perfis(2026, None, depois)


def test_formatar_tabela_alinha_colunas():
    from atlas_ingest.sinan import formatar_tabela

    t = formatar_tabela(["a", "coluna"], [["xxx", 1], ["y", 22]]).splitlines()
    assert t[0] == "a    coluna" and t[1] == "---  ------" and t[2] == "xxx  1"
    assert "(nenhuma linha)" in formatar_tabela(["a"], [])


if __name__ == "__main__":
    failures = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"ok   {name}")
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print(f"FAIL {name}: {exc!r}")
    sys.exit(1 if failures else 0)
