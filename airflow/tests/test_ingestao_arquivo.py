"""Ingestão no BigQuery de arquivos do notebook do pipeline (sem rede, com cliente simulado).

    docker run --rm --entrypoint python <imagem do Airflow> /opt/atlas/tests/test_ingestao_arquivo.py

Também compatível com pytest.
"""

import json
import os
import re
import sys
import tempfile

import pandas as pd

sys.path.insert(0, os.environ.get("ATLAS_DAGS_FOLDER", "/opt/airflow/dags"))

from atlas_ingest import arquivo  # noqa: E402

DESTINO = "p.forecast.tabela"
APOIO = "p.forecast._apoio_tabela"


class _Job:
    def result(self):
        return None


class FakeBigQuery:
    """Cliente simulado: guarda as tabelas em memória e aplica a transação de troca."""

    def __init__(self, destino: pd.DataFrame | None = None):
        self.tabelas = {DESTINO: destino if destino is not None else pd.DataFrame()}
        self.consultas: list[str] = []
        self.apagadas: list[str] = []

    def load_table_from_dataframe(self, frame, tabela, job_config=None):
        assert job_config.write_disposition == "WRITE_TRUNCATE"  # o apoio é sempre recriado
        self.tabelas[tabela] = frame.copy()
        return _Job()

    def query(self, sql):
        self.consultas.append(sql)
        assert sql.startswith("BEGIN TRANSACTION;") and sql.endswith("COMMIT TRANSACTION;")
        chave = re.search(r"WHERE `(\w+)` IN \(SELECT DISTINCT", sql).group(1)
        apoio = self.tabelas[APOIO]
        destino = self.tabelas[DESTINO]
        if not destino.empty:  # DELETE ... WHERE chave IN (chaves do apoio)
            destino = destino[~destino[chave].isin(apoio[chave].unique())]
        self.tabelas[DESTINO] = pd.concat([destino, apoio], ignore_index=True)  # INSERT ... SELECT
        return _Job()

    def delete_table(self, tabela, not_found_ok=False):
        self.apagadas.append(tabela)
        self.tabelas.pop(tabela, None)


def _arquivo(pasta, nome="tabela.parquet", linhas=None):
    linhas = linhas or [
        {"mlflow_run_id": "run1", "uf": "RJ", "valor": 1.5},
        {"mlflow_run_id": "run1", "uf": "SP", "valor": 2.5},
    ]
    caminho = os.path.join(pasta, nome)
    frame = pd.DataFrame(linhas)
    if nome.endswith(".json"):
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(linhas, f)
    else:
        frame.to_parquet(caminho, index=False)
    return caminho


def test_carrega_o_arquivo_e_apaga_a_tabela_de_apoio():
    with tempfile.TemporaryDirectory() as pasta:
        client = FakeBigQuery()
        n = arquivo.ingerir_bigquery(client, _arquivo(pasta), DESTINO)
        assert n == 2
        assert sorted(client.tabelas[DESTINO]["uf"]) == ["RJ", "SP"]
        assert client.apagadas == [APOIO] and APOIO not in client.tabelas


def test_reexecutar_a_ingestao_nao_duplica_linhas():
    with tempfile.TemporaryDirectory() as pasta:
        client = FakeBigQuery()
        caminho = _arquivo(pasta)
        arquivo.ingerir_bigquery(client, caminho, DESTINO)
        arquivo.ingerir_bigquery(client, caminho, DESTINO)
        arquivo.ingerir_bigquery(client, caminho, DESTINO)
        assert len(client.tabelas[DESTINO]) == 2


def test_so_troca_as_linhas_da_chave_do_arquivo():
    with tempfile.TemporaryDirectory() as pasta:
        outra = pd.DataFrame([{"mlflow_run_id": "run0", "uf": "MG", "valor": 9.0}])
        client = FakeBigQuery(destino=outra)
        arquivo.ingerir_bigquery(client, _arquivo(pasta), DESTINO)
        runs = sorted(client.tabelas[DESTINO]["mlflow_run_id"])
        assert runs == ["run0", "run1", "run1"]  # a run0, de outra execução, fica como estava
        novo = _arquivo(pasta, linhas=[{"mlflow_run_id": "run1", "uf": "RJ", "valor": 7.0}])
        arquivo.ingerir_bigquery(client, novo, DESTINO)
        destino = client.tabelas[DESTINO]
        assert sorted(destino["mlflow_run_id"]) == ["run0", "run1"]  # run1 foi substituída
        assert destino.loc[destino.mlflow_run_id == "run1", "valor"].tolist() == [7.0]


def test_aceita_json():
    with tempfile.TemporaryDirectory() as pasta:
        client = FakeBigQuery()
        assert arquivo.ingerir_bigquery(client, _arquivo(pasta, "tabela.json"), DESTINO) == 2


def test_arquivo_ausente_falha_sem_escrever_nada():
    client = FakeBigQuery()
    try:
        arquivo.ingerir_bigquery(client, "/nao/existe/tabela.parquet", DESTINO)
    except FileNotFoundError as exc:
        assert "não encontrado" in str(exc)
    else:
        raise AssertionError("deveria falhar")
    assert client.consultas == [] and list(client.tabelas) == [DESTINO]


def test_falhas_de_antemao_nao_tocam_no_bigquery():
    with tempfile.TemporaryDirectory() as pasta:
        client = FakeBigQuery()
        casos = [
            (lambda: arquivo.ingerir_bigquery(client, _arquivo(pasta), "so.dois"), "projeto.dataset.tabela"),
            (
                lambda: arquivo.ingerir_bigquery(client, _arquivo(pasta), DESTINO, chave="outra"),
                "coluna da chave",
            ),
            (
                lambda: arquivo.ingerir_bigquery(client, os.path.join(pasta, "x.csv"), DESTINO),
                "não encontrado",
            ),
        ]
        for chamada, mensagem in casos:
            try:
                chamada()
            except (ValueError, FileNotFoundError) as exc:
                assert mensagem in str(exc), (mensagem, str(exc))
            else:
                raise AssertionError(f"deveria falhar: {mensagem}")
        assert client.consultas == [] and list(client.tabelas) == [DESTINO]


def test_arquivo_vazio_falha():
    with tempfile.TemporaryDirectory() as pasta:
        caminho = os.path.join(pasta, "vazio.parquet")
        pd.DataFrame({"mlflow_run_id": []}).to_parquet(caminho, index=False)
        try:
            arquivo.ingerir_bigquery(FakeBigQuery(), caminho, DESTINO)
        except ValueError as exc:
            assert "vazio" in str(exc)
        else:
            raise AssertionError("deveria falhar")


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
