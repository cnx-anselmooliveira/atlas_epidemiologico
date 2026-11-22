"""Verificações estáticas dos notebooks de modelo (rodam no CI, sem executar nada).

    uv run python ml/notebooks/_ferramentas/verificar_comum.py

1. As células `comum` são idênticas à fonte (`comum.py`) e, portanto, entre os seis notebooks.
2. Nenhum notebook importa a implementação de modelo, janelas ou avaliação do pacote: de `atlas_ml`
   só os ajudantes de plataforma (`config`, `tracking`, `registry` e `data.bigquery`).

Sai com 1 e lista cada problema (notebook, célula e motivo) se algo falhar.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import nbformat

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

import sincronizar_comum as sinc  # noqa: E402

PLATAFORMA_PERMITIDA = ("atlas_ml.config", "atlas_ml.tracking", "atlas_ml.registry", "atlas_ml.data.bigquery")


def codigo(cell) -> str:
    """Código da célula sem linhas de magia (%, !), que o `ast` não entende."""
    return "\n".join(linha for linha in cell.source.splitlines() if not linha.lstrip().startswith(("%", "!")))


def imports_de(nb) -> list[tuple[int, str]]:
    """(índice da célula, módulo importado) de todos os imports do notebook, inclusive dentro de funções."""
    achados = []
    for i, cell in enumerate(nb.cells):
        if cell.cell_type != "code":
            continue
        try:
            arvore = ast.parse(codigo(cell))
        except SyntaxError:
            continue
        for no in ast.walk(arvore):
            if isinstance(no, ast.Import):
                achados += [(i, a.name) for a in no.names]
            elif isinstance(no, ast.ImportFrom) and no.module and no.level == 0:
                achados.append((i, no.module))
    return achados


def imports_proibidos(caminho: Path) -> list[str]:
    nb = nbformat.read(caminho, as_version=4)
    problemas = []
    for i, modulo in imports_de(nb):
        if not (modulo == "atlas_ml" or modulo.startswith("atlas_ml.")):
            continue
        if not any(modulo == p or modulo.startswith(p + ".") for p in PLATAFORMA_PERMITIDA):
            problemas.append(
                f"célula {i}: import de '{modulo}' (de atlas_ml só são permitidos: {', '.join(PLATAFORMA_PERMITIDA)})"
            )
    return problemas


def verificar(notebooks: list[Path] | None = None) -> list[str]:
    erros = []
    for caminho in notebooks or sinc.notebooks_dos_modelos():
        nome = caminho.parent.name
        erros += [f"{nome}: {p}" for p in sinc.diferencas(caminho)]
        erros += [f"{nome}: {p}" for p in imports_proibidos(caminho)]
    return erros


def main() -> int:
    notebooks = sinc.notebooks_dos_modelos()
    erros = verificar(notebooks)
    for e in erros:
        print(f"::error::{e}")
    if erros:
        print(f"verificar_comum: {len(erros)} problema(s) em {len(notebooks)} notebook(s)", file=sys.stderr)
        return 1
    print(f"verificar_comum: {len(notebooks)} notebook(s) com células comuns idênticas e sem import proibido")
    return 0


if __name__ == "__main__":
    sys.exit(main())
