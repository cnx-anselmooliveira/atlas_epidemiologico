"""Ferramentas dos notebooks de modelo: sincronizar, verificar as células comuns e os requirements.

Não executam nenhum notebook: leem e comparam o JSON, então rodam sem o grupo `models`.
"""

import sys
from pathlib import Path

import pytest

nbformat = pytest.importorskip("nbformat")  # vem com o grupo `models` (papermill)

from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook  # noqa: E402

FERRAMENTAS = Path(__file__).resolve().parents[2] / "notebooks" / "_ferramentas"
sys.path.insert(0, str(FERRAMENTAS))

import comum  # noqa: E402
import sincronizar_comum as sinc  # noqa: E402
import verificar_comum as vc  # noqa: E402
import verificar_requirements as vr  # noqa: E402


def _notebook(pasta: Path, modelo: str, modelo_extra: str = "x = 1", pacotes=("pandas",)) -> Path:
    """Notebook de exemplo: cabeçalho do modelo, células comuns da fonte e uma célula do modelo."""
    nb = new_notebook()
    pac = new_code_cell(f"PACOTES = {list(pacotes)!r}")
    pac.metadata["tags"] = ["pacotes"]
    cells = [new_markdown_cell("# exemplo"), pac]
    for secao in comum.ANTES_DO_MODELO:
        c = new_code_cell(comum.CELULAS[secao])
        c.metadata.update({"tags": ["comum"], "secao": secao})
        cells.append(c)
    mod = new_code_cell(modelo_extra)
    mod.metadata["tags"] = ["modelo"]
    cells.append(mod)
    for secao in comum.DEPOIS_DO_MODELO:
        c = new_code_cell(comum.CELULAS[secao])
        c.metadata.update({"tags": ["comum"], "secao": secao})
        cells.append(c)
    nb.cells = cells
    pasta = pasta / modelo
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / f"{modelo}.ipynb"
    nbformat.write(nb, caminho)
    return caminho


def _alterar(caminho: Path, secao: str, novo: str) -> None:
    nb = nbformat.read(caminho, as_version=4)
    for c in nb.cells:
        if c.metadata.get("secao") == secao:
            c.source = novo
    nbformat.write(nb, caminho)


# ---------------------------------------------------------------- fonte e sincronização (1.2)


def test_fonte_tem_uma_celula_por_secao_na_ordem():
    assert set(comum.CELULAS) == set(comum.ORDEM)
    assert comum.ANTES_DO_MODELO + comum.DEPOIS_DO_MODELO == comum.ORDEM
    assert comum.ANTES_DO_MODELO[-1] == "janelas_montar"
    for secao, codigo in comum.CELULAS.items():
        compile(codigo, secao, "exec")  # cada célula é Python válido


def test_sincronizar_muda_so_as_celulas_comuns(tmp_path):
    a = _notebook(tmp_path, "alfa", modelo_extra="y = 'so do alfa'")
    _alterar(a, "dados_ler", "# editada à mão\n")
    _alterar(a, "registro", "# outra edição\n")
    antes = nbformat.read(a, as_version=4)
    texto_do_modelo = [c.source for c in antes.cells if "modelo" in c.metadata.get("tags", [])]

    alteradas = sinc.sincronizar(a)
    assert sorted(alteradas) == ["dados_ler", "registro"]
    depois = nbformat.read(a, as_version=4)
    assert [c.source for c in depois.cells if "modelo" in c.metadata.get("tags", [])] == texto_do_modelo
    assert sinc.diferencas(a) == []
    # rodar de novo não muda nada
    assert sinc.sincronizar(a) == []


def test_alterar_a_fonte_e_sincronizar_propaga_para_os_notebooks(tmp_path):
    a, b = _notebook(tmp_path, "alfa"), _notebook(tmp_path, "beta")
    fonte = {**comum.CELULAS, "futuro": "# novo código comum\n"}
    assert sinc.sincronizar(a, fonte) == ["futuro"] and sinc.sincronizar(b, fonte) == ["futuro"]
    for caminho in (a, b):
        nb = nbformat.read(caminho, as_version=4)
        fut = [c for c in nb.cells if c.metadata.get("secao") == "futuro"][0]
        assert fut.source == "# novo código comum\n"


def test_descobre_so_os_notebooks_de_modelo(tmp_path, monkeypatch):
    _notebook(tmp_path, "alfa")
    (tmp_path / "_ferramentas").mkdir()
    (tmp_path / "_ferramentas" / "_ferramentas.ipynb").write_text("{}")
    (tmp_path / "alfa" / "rascunho.ipynb").write_text("{}")  # nome diferente da pasta: não é de modelo
    monkeypatch.setattr(sinc, "PASTA_NOTEBOOKS", tmp_path)
    assert [p.name for p in sinc.notebooks_dos_modelos()] == ["alfa.ipynb"]


# ---------------------------------------------------------------- células comuns e imports (1.3)


def test_celula_comum_alterada_em_um_so_notebook_falha_apontando_celula_e_notebook(tmp_path):
    a, b = _notebook(tmp_path, "alfa"), _notebook(tmp_path, "beta")
    _alterar(b, "oof_funcoes", "# só no beta\n")
    erros = vc.verificar([a, b])
    assert erros == ["beta: célula comum 'oof_funcoes' difere da fonte"]


def test_celula_comum_ausente_ou_desconhecida_falha(tmp_path):
    a = _notebook(tmp_path, "alfa")
    nb = nbformat.read(a, as_version=4)
    nb.cells = [c for c in nb.cells if c.metadata.get("secao") != "futuro"]
    nbformat.write(nb, a)
    assert any("falta a célula comum 'futuro'" in e for e in vc.verificar([a]))
    nb = nbformat.read(a, as_version=4)
    nb.cells[3].metadata["secao"] = "inventada"
    nbformat.write(nb, a)
    assert any("seção desconhecida" in e for e in vc.verificar([a]))


@pytest.mark.parametrize(
    "importa",
    [
        "from atlas_ml.models.catboost.model import build",
        "import atlas_ml.models",
        "from atlas_ml.forecast.windows import build_windows",
        "from atlas_ml.forecast import base",
        "def f():\n    from atlas_ml.forecast.evaluate import metrics_by_uf",  # import dentro de função
    ],
)
def test_import_do_modelo_pronto_falha_apontando_o_notebook(tmp_path, importa):
    a = _notebook(tmp_path, "alfa", modelo_extra=importa)
    erros = vc.verificar([a])
    assert len(erros) == 1 and erros[0].startswith("alfa: célula") and "atlas_ml" in erros[0]


def test_plataforma_permitida_e_magias_nao_atrapalham(tmp_path):
    ok = "from atlas_ml.config import load_settings\nfrom atlas_ml.tracking import atlas_run\n"
    ok += "from atlas_ml.registry import register_model\n"
    ok += "from atlas_ml.data.bigquery import bigquery_client\n%matplotlib inline"
    a = _notebook(tmp_path, "alfa", modelo_extra=ok)
    assert vc.verificar([a]) == []


# ---------------------------------------------------------------- requirements (1.4)

DONOS = {"pandas": ["pandas"], "numpy": ["numpy"], "sklearn": ["scikit-learn"], "catboost": ["catboost"]}
LOCK = {"pandas": "3.1.1", "numpy": "2.5.4", "scikit-learn": "1.9.1", "catboost": "1.2.10"}


def _modelo(tmp_path, requisitos, modelo_extra="import pandas", pacotes=None):
    # notebook mínimo (célula de requisitos + código do modelo): não precisa das células comuns
    nomes = (
        pacotes if pacotes is not None else [r.split(">")[0].split("=")[0].split("<")[0] for r in requisitos]
    )
    nb = new_notebook()
    pac = new_code_cell(f"PACOTES = {list(nomes)!r}")
    pac.metadata["tags"] = ["pacotes"]
    nb.cells = [pac, new_code_cell(modelo_extra)]
    pasta = tmp_path / "alfa"
    pasta.mkdir(parents=True, exist_ok=True)
    nbformat.write(nb, pasta / "alfa.ipynb")
    (pasta / "requirements.txt").write_text("\n".join(requisitos) + "\n", encoding="utf-8")
    return pasta


def test_requirements_coerentes_passam(tmp_path):
    pasta = _modelo(
        tmp_path, ["pandas>=2.2", "numpy>=2.0"], modelo_extra="import pandas\nimport numpy\nimport json"
    )
    assert vr.verificar_modelo(pasta, LOCK, DONOS) == []


def test_import_nao_declarado_falha_apontando_notebook_e_pacote(tmp_path):
    pasta = _modelo(tmp_path, ["pandas>=2.2"], modelo_extra="import pandas\nfrom sklearn.svm import SVR")
    erros = vr.verificar_modelo(pasta, LOCK, DONOS)
    assert len(erros) == 1
    assert erros[0].startswith("alfa:") and "sklearn" in erros[0] and "scikit-learn" in erros[0]


def test_versao_fora_do_lock_falha_apontando_modelo_e_pacote(tmp_path):
    pasta = _modelo(tmp_path, ["pandas>=2.2", "catboost>=9.0"], modelo_extra="import pandas\nimport catboost")
    erros = vr.verificar_modelo(pasta, LOCK, DONOS)
    assert erros == ["alfa: 'catboost>=9.0' não é satisfeito pela versão do ml/uv.lock (1.2.10)"]


def test_pacote_fora_do_lock_falha(tmp_path):
    pasta = _modelo(tmp_path, ["pandas>=2.2", "inexistente>=1"], modelo_extra="import pandas")
    assert any("'inexistente' não está no ml/uv.lock" in e for e in vr.verificar_modelo(pasta, LOCK, DONOS))


def test_celula_de_requisitos_diferente_do_arquivo_falha(tmp_path):
    pasta = _modelo(tmp_path, ["pandas>=2.2", "numpy>=2.0"], pacotes=["pandas"], modelo_extra="import pandas")
    erros = vr.verificar_modelo(pasta, LOCK, DONOS)
    assert any("PACOTES difere do requirements.txt" in e and "numpy" in e for e in erros)


def test_sem_requirements_txt_falha(tmp_path):
    caminho = _notebook(tmp_path, "alfa")
    assert vr.verificar_modelo(caminho.parent, LOCK, DONOS) == ["alfa: falta requirements.txt"]


def test_lock_real_traz_o_que_os_notebooks_pedem():
    lock = vr.versoes_do_lock()
    assert {"mlflow-skinny", "pandas", "numpy", "pyarrow", "google-cloud-bigquery", "matplotlib"} <= set(lock)
