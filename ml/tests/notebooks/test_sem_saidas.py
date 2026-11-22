"""Verificação de notebooks sem saídas (stdlib: roda no CI leve e no hook de commit)."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

FERRAMENTAS = Path(__file__).resolve().parents[2] / "notebooks" / "_ferramentas"
sys.path.insert(0, str(FERRAMENTAS))

import verificar_sem_saidas as vss  # noqa: E402

SCRIPT = FERRAMENTAS / "verificar_sem_saidas.py"


def notebook(caminho: Path, *, saida=False, contador=None) -> Path:
    celula = {
        "cell_type": "code",
        "metadata": {},
        "source": "print(1)",
        "outputs": [],
        "execution_count": contador,
    }
    if saida:
        celula["outputs"] = [{"output_type": "stream", "name": "stdout", "text": ["dados da gold\n"]}]
    md = {"cell_type": "markdown", "metadata": {}, "source": "# titulo"}
    caminho.write_text(
        json.dumps({"cells": [md, celula], "metadata": {}, "nbformat": 4, "nbformat_minor": 5})
    )
    return caminho


def test_notebook_limpo_passa(tmp_path):
    assert vss.verificar([notebook(tmp_path / "ok.ipynb")]) == []


def test_notebook_com_saida_falha_apontando_arquivo_e_celula(tmp_path):
    erros = vss.verificar([notebook(tmp_path / "sujo.ipynb", saida=True)])
    assert len(erros) == 1 and "sujo.ipynb" in erros[0] and "[1]" in erros[0]


def test_contador_de_execucao_tambem_conta(tmp_path):
    assert len(vss.verificar([notebook(tmp_path / "rodado.ipynb", contador=3)])) == 1


def test_arquivo_que_nao_e_notebook_e_ignorado_e_json_quebrado_falha(tmp_path):
    (tmp_path / "leia.md").write_text("texto")
    quebrado = tmp_path / "quebrado.ipynb"
    quebrado.write_text("{ não é json")
    assert vss.verificar([tmp_path / "leia.md"]) == []
    assert "não foi possível ler" in vss.verificar([quebrado])[0]


def test_limpar_tira_saidas_e_contador_e_deixa_o_resto(tmp_path):
    arquivo = notebook(tmp_path / "n.ipynb", saida=True, contador=5)
    assert vss.limpar(arquivo) is True
    assert vss.verificar([arquivo]) == []
    nb = json.loads(arquivo.read_text(encoding="utf-8"))
    assert nb["cells"][1]["source"] == "print(1)" and nb["cells"][0]["source"] == "# titulo"
    assert vss.limpar(arquivo) is False  # já limpo: não mexe


def test_os_notebooks_do_repositorio_estao_sem_saidas():
    assert vss.verificar(sorted(vss.PASTA.rglob("*.ipynb"))) == []


@pytest.mark.parametrize(("saida", "codigo"), [(False, 0), (True, 1)])
def test_script_sai_com_o_codigo_certo(tmp_path, saida, codigo):
    arquivo = notebook(tmp_path / "n.ipynb", saida=saida)
    resultado = subprocess.run(
        [sys.executable, str(SCRIPT), str(arquivo)], capture_output=True, text=True, check=False
    )
    assert resultado.returncode == codigo
