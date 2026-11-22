"""Confere os requirements de cada notebook de modelo (roda no CI, sem executar nenhuma célula).

    uv run --extra models python ml/notebooks/_ferramentas/verificar_requirements.py

Para cada `ml/notebooks/<modelo>/requirements.txt`:
1. cada requisito é satisfeito pela versão que o `ml/uv.lock` instala (o venv comum da imagem);
2. todo pacote importado pelo notebook é da biblioteca padrão, da plataforma (`atlas_ml`) ou está no
   `requirements.txt` (o import é ligado ao pacote pelas distribuições instaladas no ambiente);
3. a lista `PACOTES` da célula de requisitos do notebook é igual ao `requirements.txt`.
"""

from __future__ import annotations

import ast
import importlib.metadata as md
import sys
import tomllib
from pathlib import Path

import nbformat
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

import sincronizar_comum as sinc  # noqa: E402
import verificar_comum as vc  # noqa: E402

LOCK = AQUI.parents[1] / "uv.lock"


def ler_requirements(caminho: Path) -> list[Requirement]:
    reqs = []
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.split("#", 1)[0].strip()
        if linha:
            reqs.append(Requirement(linha))
    return reqs


def versoes_do_lock(lock: Path = LOCK) -> dict[str, str]:
    dados = tomllib.loads(lock.read_text(encoding="utf-8"))
    return {canonicalize_name(p["name"]): p["version"] for p in dados.get("package", []) if "version" in p}


def pacotes_da_celula(nb) -> list[str] | None:
    """A lista PACOTES da célula de requisitos (tag `pacotes`), lida sem executar."""
    for cell in nb.cells:
        if cell.cell_type == "code" and "pacotes" in cell.metadata.get("tags", []):
            for no in ast.walk(ast.parse(cell.source)):
                if isinstance(no, ast.Assign) and any(getattr(t, "id", "") == "PACOTES" for t in no.targets):
                    return list(ast.literal_eval(no.value))
    return None


def verificar_modelo(pasta: Path, lock: dict[str, str], donos: dict[str, list[str]]) -> list[str]:
    nome = pasta.name
    arquivo = pasta / "requirements.txt"
    if not arquivo.is_file():
        return [f"{nome}: falta {arquivo.name}"]
    reqs = ler_requirements(arquivo)
    declarados = {canonicalize_name(r.name) for r in reqs}
    erros = []

    for r in reqs:  # 1. o venv comum (uv.lock) satisfaz cada requisito
        chave = canonicalize_name(r.name)
        if chave not in lock:
            erros.append(f"{nome}: '{r.name}' não está no ml/uv.lock (o venv da imagem não o instala)")
        elif not r.specifier.contains(lock[chave], prereleases=True):
            erros.append(f"{nome}: '{r}' não é satisfeito pela versão do ml/uv.lock ({lock[chave]})")

    nb = nbformat.read(pasta / f"{nome}.ipynb", as_version=4)
    for _, modulo in vc.imports_de(nb):  # 2. todo import está declarado
        topo = modulo.split(".")[0]
        if topo in sys.stdlib_module_names or topo == "atlas_ml":
            continue
        candidatos = {canonicalize_name(d) for d in donos.get(topo, [])}
        if not candidatos:
            erros.append(f"{nome}: o import '{modulo}' não pertence a nenhum pacote instalado neste ambiente")
        elif not candidatos & declarados:
            erros.append(
                f"{nome}: o import '{modulo}' (pacote {', '.join(sorted(candidatos))}) não está no requirements.txt"
            )

    pacotes = pacotes_da_celula(nb)  # 3. a célula de requisitos bate com o arquivo
    if pacotes is None:
        erros.append(f"{nome}: o notebook não tem a célula de requisitos (tag 'pacotes' com PACOTES = [...])")
    elif {canonicalize_name(p) for p in pacotes} != declarados:
        so_no_notebook = sorted({canonicalize_name(p) for p in pacotes} - declarados)
        so_no_arquivo = sorted(declarados - {canonicalize_name(p) for p in pacotes})
        erros.append(
            f"{nome}: PACOTES difere do requirements.txt (só no notebook: {so_no_notebook}; só no arquivo: {so_no_arquivo})"
        )
    return erros


def verificar() -> tuple[list[str], int]:
    lock = versoes_do_lock()
    donos = md.packages_distributions()
    notebooks = sinc.notebooks_dos_modelos()
    erros = []
    for caminho in notebooks:
        erros += verificar_modelo(caminho.parent, lock, donos)
    return erros, len(notebooks)


def main() -> int:
    erros, n = verificar()
    for e in erros:
        print(f"::error::{e}")
    if erros:
        print(f"verificar_requirements: {len(erros)} problema(s) em {n} notebook(s)", file=sys.stderr)
        return 1
    print(
        f"verificar_requirements: {n} notebook(s) com requirements coerentes com o ml/uv.lock e com os imports"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
