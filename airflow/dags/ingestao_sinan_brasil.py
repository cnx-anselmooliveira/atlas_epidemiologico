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

A lógica está em atlas_ingest/sinan.py (testada sem rede em airflow/tests/test_sinan_ingest.py).
"""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime, timedelta

from airflow.sdk import DAG, Param, PokeReturnValue, get_current_context, task, task_group


@task.sensor(
    task_id="detectar_diferencas",
    mode="reschedule",
    poke_interval=timedelta(minutes=30),
    # teto de segurança; quem manda é a janela_horas (a etl_brasil pede 3 h)
    timeout=timedelta(hours=8),
    retries=2,
    retry_delay=timedelta(minutes=5),
)
def detectar_diferencas() -> PokeReturnValue:
    from atlas_ingest import gcp
    from atlas_ingest.etl_brasil import dentro_da_janela
    from atlas_ingest.sinan import listar_landing, listar_origem, planejar_sync

    ctx = get_current_context()
    plano = planejar_sync(listar_origem(gcp.http()), listar_landing(gcp.bucket()))
    if not plano.vazio():
        return PokeReturnValue(is_done=True, xcom_value=plano.as_dict())
    janela = float(ctx["params"].get("janela_horas") or 0)
    inicio = ctx["dag_run"].start_date or datetime.now(UTC)
    if dentro_da_janela(inicio, datetime.now(UTC), janela):
        return PokeReturnValue(is_done=False)
    print(f"sem diferença entre o OpenDataSUS e o landing (janela de {janela} h)")
    return PokeReturnValue(is_done=True, xcom_value=plano.as_dict())


@task
def lista_do_plano(plano: dict, chave: str) -> list:
    """Uma lista do plano (baixar, apagar, carregar, remover_da_bronze), para mapear as tarefas."""
    return plano.get(chave, [])


@task(
    retries=2, retry_delay=timedelta(minutes=5), map_index_template="{{ task.op_kwargs['versao']['nome'] }}"
)
def baixar(versao: dict) -> dict:
    from atlas_ingest import gcp
    from atlas_ingest.sinan import baixar_para_landing

    with tempfile.TemporaryDirectory() as tmp:
        return baixar_para_landing(gcp.http(), gcp.bucket(), versao, tmp)


@task(retries=2, retry_delay=timedelta(minutes=5))
def apagar(nome: str) -> list[str]:
    from atlas_ingest import gcp
    from atlas_ingest.sinan import apagar_do_landing

    return apagar_do_landing(gcp.bucket(), nome)


@task(trigger_rule="none_failed", retries=1)
def carregar_bronze(ano: int) -> dict:
    from atlas_ingest import gcp
    from atlas_ingest.sinan import carregar_ano_na_bronze

    return carregar_ano_na_bronze(gcp.bigquery(), gcp.bucket(), ano, gcp.PROJETO)


@task
def validar(resultado: dict) -> dict:
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
    from atlas_ingest import gcp
    from atlas_ingest.sinan import remover_ano_da_bronze

    return remover_ano_da_bronze(gcp.bigquery(), ano, gcp.PROJETO)


@task(trigger_rule="none_failed")
def resumo() -> dict:
    """O que a ingestão mudou (informativo: as decisões seguintes olham o estado das tabelas)."""
    ti = get_current_context()["ti"]
    carregados = [a for a in (ti.xcom_pull(task_ids="carga_ano.marcar_carregado", default=None) or []) if a]
    removidos = [a for a in (ti.xcom_pull(task_ids="remover_da_bronze", default=None) or []) if a is not None]
    novos = bool(carregados or removidos)
    print(
        "dados novos na bronze:" if novos else "sem dados novos",
        f"carregados={carregados} removidos={removidos}",
    )
    return {"novos": novos, "carregados": carregados, "removidos": removidos}


with DAG(
    dag_id="ingestao_sinan_brasil",
    description="Ingestão do SINAN: OpenDataSUS → landing no bucket → bronze (disparada pela etl_brasil).",
    schedule=None,
    start_date=datetime(2026, 11, 1),
    catchup=False,
    max_active_runs=1,
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

    baixados = baixar.expand(versao=lista("baixar"))
    apagados = apagar.expand(nome=lista("apagar"))
    cargas = carga_ano.expand(ano=lista("carregar"))
    removidos = remover_da_bronze.expand(ano=lista("remover_da_bronze"))
    # landing primeiro; bronze depois (cargas e remoções esperam baixar/apagar terminarem)
    [baixados, apagados] >> cargas
    apagados >> removidos
    [cargas, removidos] >> resumo()
