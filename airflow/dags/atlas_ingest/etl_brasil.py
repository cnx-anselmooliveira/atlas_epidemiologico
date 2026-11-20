"""Decisões do fluxo diário do Brasil (DAG etl_brasil): rodar o dbt? treinar os modelos?

Funções puras (sem Airflow), decididas pelo ESTADO dos dados, não pela execução anterior: uma
etapa que falhou ontem é retomada hoje, e cada DAG pode ser reexecutada sozinha.

- dbt: roda se a bronze do SINAN foi modificada depois da gold (ou se pediram forcar_dbt).
- treino: roda se a versão atual da gold não aparece na `atlas.data_version` de algum modelo
  vigente no MLflow do ambiente (alias dev/hml/prod), se falta algum modelo, ou com forcar_treino.
  A `data_version` registrada pelo treino contém `<tabela>@<última modificação ISO>` da gold.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

PROJETO_PADRAO = "ppgcc-dengue-project"
# As tabelas dependem do ambiente (ATLAS_ENV): ver atlas_ingest/ambiente.py
# (bronze.sinan_dengue_opendatasus em dev, bronze_hml.sinan_dengue_opendatasus em hml...).
MODELOS = ("baseline_bayes", "chronos", "catboost", "svr", "lstm", "ensemble")
HORIZONTES = (1, 2, 3, 4)


@dataclass(frozen=True)
class Decisao:
    rodar: bool
    motivo: str


def versao_tabela(tabela: str, modificada: datetime) -> str:
    """Mesmo formato do treino (atlas_ml.data.bigquery.table_version): `<tabela>@<ISO>`."""
    return f"{tabela}@{modificada.isoformat()}"


def dbt_precisa_rodar(bronze: datetime | None, gold: datetime | None, forcar: bool = False) -> Decisao:
    if forcar:
        return Decisao(True, "forcar_dbt pedido no disparo")
    if bronze is None:
        return Decisao(False, "bronze do SINAN não existe: nada a modelar")
    if gold is None:
        return Decisao(True, "gold ainda não existe")
    if bronze > gold:
        return Decisao(
            True, f"bronze modificada em {bronze.isoformat()}, depois da gold ({gold.isoformat()})"
        )
    return Decisao(False, f"gold ({gold.isoformat()}) já reflete a bronze ({bronze.isoformat()})")


def treino_precisa_rodar(versao_gold: str, vigentes: dict[str, str | None], forcar: bool = False) -> Decisao:
    """`vigentes`: nome registrado → data_version do modelo vigente (None se não houver modelo)."""
    if forcar:
        return Decisao(True, "forcar_treino pedido no disparo")
    if not vigentes:
        return Decisao(True, "nenhum modelo consultado")
    faltam = sorted(n for n, v in vigentes.items() if not v)
    if faltam:
        return Decisao(True, f"sem modelo vigente: {', '.join(faltam[:4])}{' …' if len(faltam) > 4 else ''}")
    antigos = sorted(n for n, v in vigentes.items() if versao_gold not in (v or ""))
    if antigos:
        return Decisao(
            True, f"{len(antigos)} modelo(s) treinado(s) com outra versão da gold (ex.: {antigos[0]})"
        )
    return Decisao(False, f"todos os {len(vigentes)} modelos vigentes já usam {versao_gold}")


# Mesmos sufixos do treino (atlas_ml.forecast.base.REGISTERED_SUFFIXES): dev e hml podem dividir o
# MLflow com prod, então levam sufixo; prod fica com o nome puro
SUFIXOS_REGISTRO = {"dev": "_dev", "hml": "_hml", "prod": ""}


def nomes_registrados(ambiente: str, modelos=MODELOS, horizontes=HORIZONTES) -> list[str]:
    """Mesmo padrão do treino (atlas_ml.forecast.base): `atlas-br-<modelo>-h<H><sufixo>`."""
    if ambiente not in SUFIXOS_REGISTRO:
        raise ValueError(f"ambiente inválido {ambiente!r}")
    sufixo = SUFIXOS_REGISTRO[ambiente]
    return [f"atlas-br-{m}-h{h}{sufixo}" for m in modelos for h in horizontes]


def data_versions_vigentes(sessao: Any, base_url: str, alias: str, nomes: list[str]) -> dict[str, str | None]:
    """data_version de cada modelo no alias do ambiente, pela API REST do MLflow.

    `sessao` é um requests.Session (com autenticação, se houver). Modelo ou alias inexistente vira
    None; qualquer outro erro sobe (a decisão não pode ser tomada às cegas).
    """
    base = base_url.rstrip("/")
    resultado: dict[str, str | None] = {}
    for nome in nomes:
        r = sessao.get(
            f"{base}/api/2.0/mlflow/registered-models/alias",
            params={"name": nome, "alias": alias},
            timeout=30,
        )
        if r.status_code == 404 or (r.status_code == 400 and "RESOURCE_DOES_NOT_EXIST" in r.text):
            resultado[nome] = None
            continue
        r.raise_for_status()
        run_id = (r.json().get("model_version") or {}).get("run_id")
        if not run_id:
            resultado[nome] = None
            continue
        rr = sessao.get(f"{base}/api/2.0/mlflow/runs/get", params={"run_id": run_id}, timeout=30)
        rr.raise_for_status()
        tags = {t["key"]: t["value"] for t in rr.json()["run"]["data"].get("tags", [])}
        resultado[nome] = tags.get("atlas.data_version")
    return resultado


def dentro_da_janela(inicio: datetime, agora: datetime, janela_horas: float) -> bool:
    """O sensor ainda espera dados novos? (janela 0 = uma verificação só)."""
    return janela_horas > 0 and (agora - inicio).total_seconds() < janela_horas * 3600
