"""Ingestão do SINAN (dengue, Brasil): OpenDataSUS → landing no bucket → bronze no BigQuery.

Sem agendamento: disparada pela etl_brasil (todo dia às 03h00) ou à mão.

    detectar_diferencas (sensor)
       ├─► baixar[arquivo] ─┐
       └─► apagar[arquivo] ─┴─► carga_ano[ano]: carregar_bronze ─► validar ─► marcar_carregado ─┐
                            └─► remover_da_bronze[ano] ──────────────────────────────────────────┴─► resumo

- detectar_diferencas: HEAD dos arquivos anuais DENGBR<aa>.csv.zip no OpenDataSUS × metadata dos
  objetos no landing (gs://<bucket>/landing/sinan/dengue/). Com `janela_horas` > 0 espera (modo
  reschedule) até aparecer diferença ou a janela acabar; com 0 (padrão, disparo à mão) verifica uma vez.
  Sem diferença, o plano sai vazio e a DAG termina com sucesso, "sem dados novos".
- O landing é espelho exato da origem: arquivo alterado é substituído, arquivo que sumiu é apagado
  (e sai da bronze). A bronze (bronze.sinan_dengue_opendatasus) tem uma partição por ano, substituída
  inteira; só depois da validação o ano é marcado (bronze_etag) e sai do plano dos próximos dias.

Onde ler o que aconteceu (logs de cada tarefa na UI do Airflow):
- detectar_diferencas: tabela com a decisão de cada arquivo e o motivo (novo, alterado e o que mudou,
  bronze atrasada, removido, em dia) e o resumo do plano;
- baixar[ano]: versão anterior × nova, tamanho e velocidade do download, registros, colunas, encoding;
- carga_ano.carregar_bronze[ano]: a partição antes × depois (total, UF a UF, intervalo de DT_NOTIFIC),
  colunas novas ou ausentes no ano e o volume processado pelo BigQuery;
- carga_ano.validar[ano]: cada verificação (contagens e colunas obrigatórias);
- resumo: relatório final da execução, ano a ano.

A lógica está em atlas_ingest/sinan.py (testada sem rede em airflow/tests/test_sinan_ingest.py).
"""

from __future__ import annotations

import logging
import tempfile
from datetime import UTC, datetime, timedelta

from airflow.sdk import DAG, Param, PokeReturnValue, get_current_context, task, task_group

# Mensagens das tarefas; as de atlas_ingest.sinan saem pelo logger daquele módulo. As duas
# aparecem juntas no log da tarefa.
log = logging.getLogger(__name__)

# Os imports de atlas_ingest e das bibliotecas do Google ficam dentro das tarefas: o dag-processor
# lê este arquivo a cada poucos segundos e não precisa carregar nada disso só para montar o grafo.


# ---------------------------------------------------------------------------------------
# 1) O que mudou na origem?
# ---------------------------------------------------------------------------------------
@task.sensor(
    task_id="detectar_diferencas",
    # reschedule: entre uma verificação e outra o worker fica livre (a espera pode durar horas)
    mode="reschedule",
    poke_interval=timedelta(minutes=30),
    # teto de segurança; quem manda é a janela_horas (a etl_brasil pede 3 h)
    timeout=timedelta(hours=8),
    retries=2,
    retry_delay=timedelta(minutes=5),
)
def detectar_diferencas() -> PokeReturnValue:
    """Monta o plano do dia comparando a origem com o landing. Devolve o plano por XCom."""
    from atlas_ingest import ambiente, gcp
    from atlas_ingest.etl_brasil import dentro_da_janela
    from atlas_ingest.sinan import listar_landing, listar_origem, planejar_sync, tabela_plano

    log.info(ambiente.descrever())
    ctx = get_current_context()
    origem = listar_origem(gcp.http())  # só HEAD: nada é baixado aqui
    landing = listar_landing(gcp.bucket())
    plano = planejar_sync(origem, landing)

    if not plano.vazio():
        # Achou trabalho: registra a decisão arquivo a arquivo e libera as próximas tarefas.
        log.info("diferenças encontradas\n%s", tabela_plano(origem, landing, plano))
        return PokeReturnValue(is_done=True, xcom_value=plano.as_dict())

    # Nada mudou. Dentro da janela, tenta de novo daqui a poke_interval (a origem costuma
    # publicar de madrugada); fora dela, termina com o plano vazio ("sem dados novos").
    janela = float(ctx["params"].get("janela_horas") or 0)
    inicio = ctx["dag_run"].start_date or datetime.now(UTC)
    if dentro_da_janela(inicio, datetime.now(UTC), janela):
        fim = inicio + timedelta(hours=janela)
        log.info(
            "nenhuma diferença ainda (%d arquivos em dia); nova verificação em 30 min, janela até %s UTC",
            len(landing),
            fim.strftime("%H:%M"),
        )
        return PokeReturnValue(is_done=False)
    log.info(
        "sem diferença entre o OpenDataSUS e o landing (janela de %s h)\n%s",
        janela,
        tabela_plano(origem, landing, plano),
    )
    return PokeReturnValue(is_done=True, xcom_value=plano.as_dict())


@task
def lista_do_plano(plano: dict, chave: str) -> list:
    """Uma lista do plano (baixar, apagar, carregar, remover_da_bronze), para mapear as tarefas.

    Lista vazia = a tarefa mapeada correspondente fica "skipped" (nada a fazer naquela frente)."""
    itens = plano.get(chave, [])
    log.info(
        "%s: %d item(ns) %s",
        chave,
        len(itens),
        [i.get("nome", i) if isinstance(i, dict) else i for i in itens],
    )
    return itens


# ---------------------------------------------------------------------------------------
# 2) Landing: espelhar a origem no bucket
# ---------------------------------------------------------------------------------------
@task(
    retries=2, retry_delay=timedelta(minutes=5), map_index_template="{{ task.op_kwargs['versao']['nome'] }}"
)
def baixar(versao: dict) -> dict:
    """Uma instância por arquivo novo ou alterado: baixa o zip, conta os registros e envia
    CSV + zip ao landing (o estado vai na metadata do zip, sem bronze_etag ainda)."""
    from atlas_ingest import gcp
    from atlas_ingest.sinan import baixar_para_landing

    # pasta temporária no disco do worker; some ao fim da tarefa (o CSV de um ano tem centenas de MB)
    with tempfile.TemporaryDirectory() as tmp:
        return baixar_para_landing(gcp.http(), gcp.bucket(), versao, tmp)


@task(retries=2, retry_delay=timedelta(minutes=5))
def apagar(nome: str) -> list[str]:
    """Uma instância por arquivo que a origem deixou de publicar (404): sai do landing."""
    from atlas_ingest import gcp
    from atlas_ingest.sinan import apagar_do_landing

    return apagar_do_landing(gcp.bucket(), nome)


# ---------------------------------------------------------------------------------------
# 3) Bronze: carregar, validar e só então marcar
# ---------------------------------------------------------------------------------------
# none_failed: roda mesmo quando baixar/apagar foram "skipped" (ex.: só recarregar um ano cuja
# carga anterior falhou, sem nada para baixar), mas não roda se algum download falhou.
@task(trigger_rule="none_failed", retries=1)
def carregar_bronze(ano: int) -> dict:
    """Substitui a partição do ano pelo CSV do landing e devolve as contagens para a validação."""
    from atlas_ingest import gcp
    from atlas_ingest.sinan import carregar_ano_na_bronze

    return carregar_ano_na_bronze(gcp.bigquery(), gcp.bucket(), ano, gcp.PROJETO)


@task
def validar(resultado: dict) -> dict:
    """Arquivo, load job e partição precisam ter o mesmo número de linhas, e as colunas que a
    modelagem usa precisam existir. Se reprovar, o ano não é marcado e volta amanhã."""
    from atlas_ingest.sinan import validar_contagens

    validar_contagens(
        resultado["ano"],
        resultado["registros"],
        resultado["output_rows"],
        resultado["linhas_particao"],
        resultado["colunas"],
    )
    return {"ano": resultado["ano"], "etag": resultado["etag"]}


@task
def marcar_carregado(validado: dict) -> int:
    """Grava bronze_etag = ETag carregado: o ano sai do plano dos próximos dias."""
    from atlas_ingest import gcp
    from atlas_ingest.sinan import marcar_carregado as marcar

    marcar(gcp.bucket(), validado["ano"], validado["etag"])
    return validado["ano"]


@task_group(group_id="carga_ano")
def carga_ano(ano: int):
    """Uma cadeia por ano (grupo mapeado): a falha de um ano não impede os outros de serem
    validados e marcados; o ano que falhou volta no plano do dia seguinte."""
    marcar_carregado(validar(carregar_bronze(ano)))


@task(trigger_rule="none_failed", retries=1)
def remover_da_bronze(ano: int) -> int:
    """Apaga da bronze a partição de um ano que saiu da origem (depois de sair do landing)."""
    from atlas_ingest import gcp
    from atlas_ingest.sinan import remover_ano_da_bronze

    return remover_ano_da_bronze(gcp.bigquery(), ano, gcp.PROJETO)


# ---------------------------------------------------------------------------------------
# 4) Relatório da execução
# ---------------------------------------------------------------------------------------
def _lista(ti, task_ids: str) -> list:
    """XCom de uma tarefa mapeada como lista (sem as instâncias que não devolveram nada)."""
    valor = ti.xcom_pull(task_ids=task_ids, default=None)
    if valor is None:
        return []
    # uma instância só pode vir como o próprio valor; várias vêm como sequência (list ou lazy)
    itens = [valor] if isinstance(valor, dict | str | int) else list(valor)
    return [v for v in itens if v is not None]


@task(trigger_rule="none_failed")
def resumo() -> dict:
    """O que a ingestão mudou (informativo: as decisões seguintes olham o estado das tabelas)."""
    from atlas_ingest.sinan import fmt_bytes, fmt_delta, fmt_int, formatar_tabela

    ti = get_current_context()["ti"]
    carregados = _lista(ti, "carga_ano.marcar_carregado")
    removidos = _lista(ti, "remover_da_bronze")
    downloads = {d["ano"]: d for d in _lista(ti, "baixar")}
    cargas = {c["ano"]: c for c in _lista(ti, "carga_ano.carregar_bronze")}
    novos = bool(carregados or removidos)

    # Uma linha por ano tocado nesta execução. "carregado e validado" = bronze_etag gravado.
    linhas = []
    for ano in sorted(set(downloads) | set(cargas) | set(carregados)):
        d, c = downloads.get(ano, {}), cargas.get(ano, {})
        if ano in carregados:
            situacao = "carregado e validado"
        elif c:
            situacao = "carregado, mas NÃO validado (volta amanhã)"
        else:
            situacao = "baixado, carga não concluída (volta amanhã)"
        linhas.append(
            [
                ano,
                situacao,
                ("baixado " + fmt_bytes(d.get("bytes_zip")))
                if d.get("reenviado")
                else ("já no landing" if d else "-"),
                fmt_int(c.get("linhas_antes")) if c else "-",
                fmt_int(c.get("linhas_particao")) if c else "-",
                fmt_delta(c.get("linhas_antes"), c.get("linhas_particao")) if c else "-",
                len(c.get("colunas_novas") or []) if c else "-",
            ]
        )
    linhas += [
        [f"(removido) linhas={fmt_int(n)}", "partição apagada", "-", "-", "-", "-", "-"] for n in removidos
    ]
    if linhas:
        log.info(
            "%s",
            formatar_tabela(
                ["ano", "situação", "landing", "linhas antes", "linhas depois", "variação", "colunas novas"],
                linhas,
                titulo="Resumo da ingestão do SINAN:",
            ),
        )
    total_antes = sum(c.get("linhas_antes") or 0 for c in cargas.values())
    total_depois = sum(c.get("linhas_particao") or 0 for c in cargas.values())
    log.info(
        "%s carregados=%s removidos(linhas)=%s | anos recarregados: %s → %s linhas (%s)",
        "dados novos na bronze:" if novos else "sem dados novos",
        carregados,
        removidos,
        fmt_int(total_antes),
        fmt_int(total_depois),
        fmt_delta(total_antes, total_depois) if cargas else "-",
    )
    # Mantém o formato antigo do XCom (quem consome olha "novos", "carregados" e "removidos").
    return {"novos": novos, "carregados": carregados, "removidos": removidos}


with DAG(
    dag_id="ingestao_sinan_brasil",
    description="Ingestão do SINAN: OpenDataSUS → landing no bucket → bronze (disparada pela etl_brasil).",
    schedule=None,  # só por disparo: etl_brasil (03h00) ou à mão
    start_date=datetime(2026, 11, 1),
    catchup=False,
    max_active_runs=1,  # duas execuções nunca disputam o mesmo landing
    tags=["atlas", "etl", "sinan", "brasil"],
    params={
        "janela_horas": Param(
            0,
            type="number",
            minimum=0,
            maximum=8,
            description="Opcional. Horas esperando dados novos no OpenDataSUS (0 = verifica uma vez).",
        ),
    },
    default_args={"owner": "atlas", "retries": 0},
) as dag:
    plano = detectar_diferencas()

    def lista(chave):
        return lista_do_plano.override(task_id=f"lista_{chave}")(plano, chave)

    # Uma instância por item do plano (dynamic task mapping).
    baixados = baixar.expand(versao=lista("baixar"))
    apagados = apagar.expand(nome=lista("apagar"))
    cargas = carga_ano.expand(ano=lista("carregar"))
    removidos = remover_da_bronze.expand(ano=lista("remover_da_bronze"))
    # landing primeiro; bronze depois (cargas e remoções esperam baixar/apagar terminarem)
    [baixados, apagados] >> cargas
    apagados >> removidos
    [cargas, removidos] >> resumo()
