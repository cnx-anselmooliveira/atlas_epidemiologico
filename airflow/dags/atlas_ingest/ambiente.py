"""Onde cada ambiente lê e escreve os dados do Atlas (mudança add-env-data-isolation).

Uma só configuração, `ATLAS_ENV` (dev, hml ou prod), decide:
- o landing do SINAN no bucket: `landing/sinan/dengue/` em dev (caminho histórico, mantido por
  compatibilidade com os arquivos e o estado já gravados) e `landing/<ambiente>/sinan/dengue/`
  em hml e prod;
- os datasets do BigQuery escritos pelo Atlas: `bronze`, `silver`, `gold` e `forecast` em dev e
  `<camada>_<ambiente>` em hml e prod. Os datasets de origem só de leitura (microdados) não mudam.

Ambiente desconhecido é erro: nada é lido ou escrito sem saber de quem são os dados.
A mesma regra existe no dbt (macro generate_schema_name e fonte sinan_opendatasus) e no atlas_ml.
"""

from __future__ import annotations

import os

AMBIENTES = ("dev", "hml", "prod")
TABELA_BRONZE_SINAN = "sinan_dengue_opendatasus"
TABELA_GOLD_CASOS = "gold_dengue_casos_provaveis_uf_semanal"


class AmbienteInvalido(ValueError):
    pass


def ambiente(valor: str | None = None) -> str:
    """O ambiente em uso (`valor` ou `ATLAS_ENV`, padrão dev)."""
    bruto = os.environ.get("ATLAS_ENV", "dev") if valor is None else valor
    amb = (bruto or "").strip().lower()
    if amb not in AMBIENTES:
        raise AmbienteInvalido(f"ATLAS_ENV inválido: {bruto!r} (use {', '.join(AMBIENTES)})")
    return amb


def sufixo(valor: str | None = None) -> str:
    amb = ambiente(valor)
    return "" if amb == "dev" else f"_{amb}"


def dataset(camada: str, valor: str | None = None) -> str:
    """Dataset da camada no ambiente (ex.: gold → gold_hml em hml)."""
    return f"{camada}{sufixo(valor)}"


def prefixo_landing(valor: str | None = None) -> str:
    amb = ambiente(valor)
    return "landing/sinan/dengue/" if amb == "dev" else f"landing/{amb}/sinan/dengue/"


def bronze_sinan(valor: str | None = None) -> str:
    """`dataset.tabela` da bronze do SINAN no ambiente."""
    return f"{dataset('bronze', valor)}.{TABELA_BRONZE_SINAN}"


def gold_casos(valor: str | None = None) -> str:
    """`dataset.tabela` da gold de casos prováveis por UF e semana no ambiente."""
    return f"{dataset('gold', valor)}.{TABELA_GOLD_CASOS}"


def descrever(valor: str | None = None) -> str:
    """Linha para o log das tarefas: de onde e para onde os dados vão."""
    amb = ambiente(valor)
    return (
        f"ambiente={amb} landing={prefixo_landing(amb)} bronze={dataset('bronze', amb)} "
        f"gold={dataset('gold', amb)} forecast={dataset('forecast', amb)}"
    )
