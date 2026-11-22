"""Ingestão no BigQuery de um arquivo que o notebook do pipeline deixou na pasta da execução.

O notebook grava uma tabela (parquet ou JSON) em ATLAS_PIPELINE_DIR/<run_id>/; uma tarefa seguinte
do Airflow a lê e a carrega com `ingerir_bigquery`. A carga é idempotente, como a da exportação das
previsões: vai para uma tabela de apoio e uma transação troca, no destino, as linhas da chave que o
arquivo traz (por padrão `mlflow_run_id`). Repetir a tarefa regrava as mesmas linhas, sem duplicar.

Para o MLflow, a mesma ideia está em atlas_ml.forecast.notebook.ingest_to_mlflow (o MLflow só existe
no venv do atlas_ml). Os imports de Google ficam dentro das funções: a leitura das DAGs continua leve.
"""

from __future__ import annotations

import json
import os
from typing import Any

import pandas as pd

CHAVE_PADRAO = "mlflow_run_id"


def ler_arquivo(caminho: str | os.PathLike[str]) -> pd.DataFrame:
    """Lê o parquet ou o JSON (lista de objetos, ou {"linhas": [...]}) como tabela.

    Falha, sem tocar em nenhum destino, se o arquivo não existe ou está vazio.
    """
    caminho = os.fspath(caminho)
    if not os.path.isfile(caminho):
        raise FileNotFoundError(f"Arquivo de ingestão não encontrado: {caminho}")
    if caminho.endswith(".parquet"):
        frame = pd.read_parquet(caminho)
    elif caminho.endswith(".json"):
        with open(caminho, encoding="utf-8") as f:
            dados = json.load(f)
        linhas = dados["linhas"] if isinstance(dados, dict) else dados
        frame = pd.DataFrame(linhas)
    else:
        raise ValueError(f"Formato não suportado (use .parquet ou .json): {caminho}")
    if frame.empty:
        raise ValueError(f"O arquivo de ingestão está vazio: {caminho}")
    return frame


def _partes(destino: str) -> tuple[str, str, str]:
    partes = destino.split(".")
    if len(partes) != 3 or not all(partes):
        raise ValueError(f"Destino deve ser projeto.dataset.tabela: {destino!r}")
    return partes[0], partes[1], partes[2]


def comandos_de_troca(destino: str, apoio: str, colunas: list[str], chave: str) -> str:
    """A transação que troca, no destino, as linhas da chave presente na tabela de apoio."""
    cols = ", ".join(f"`{c}`" for c in colunas)
    return (
        "BEGIN TRANSACTION;\n"
        f"DELETE FROM `{destino}` WHERE `{chave}` IN (SELECT DISTINCT `{chave}` FROM `{apoio}`);\n"
        f"INSERT INTO `{destino}` ({cols}) SELECT {cols} FROM `{apoio}`;\n"
        "COMMIT TRANSACTION;"
    )


def ingerir_bigquery(
    client: Any,
    caminho: str | os.PathLike[str],
    destino: str,
    chave: str = CHAVE_PADRAO,
    schema: list[Any] | None = None,
) -> int:
    """Carrega o arquivo em `destino` (projeto.dataset.tabela), trocando as linhas da `chave`.

    Idempotente. Tudo o que pode falhar de antemão (arquivo, formato, destino, coluna da chave)
    falha antes de qualquer escrita. A tabela de destino precisa existir com as colunas do arquivo.
    Devolve o número de linhas carregadas.
    """
    frame = ler_arquivo(caminho)
    projeto, dataset, tabela = _partes(destino)
    if chave not in frame.columns:
        raise ValueError(f"O arquivo não tem a coluna da chave {chave!r}: {list(frame.columns)}")

    from google.cloud import bigquery

    apoio = f"{projeto}.{dataset}._apoio_{tabela}"
    job_config = bigquery.LoadJobConfig(
        write_disposition="WRITE_TRUNCATE", **({"schema": schema} if schema else {})
    )
    client.load_table_from_dataframe(frame, apoio, job_config=job_config).result()
    try:
        client.query(comandos_de_troca(destino, apoio, list(frame.columns), chave)).result()
    finally:
        client.delete_table(apoio, not_found_ok=True)
    return len(frame)
