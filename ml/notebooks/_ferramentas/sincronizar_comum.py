"""Sincroniza as células `comum` dos notebooks de modelo com a fonte (`comum.py`).

Ferramenta de desenvolvimento: os notebooks rodam sem ela. Use depois de alterar `comum.py` (ou de
editar uma célula comum à mão num notebook, para propagar a edição, altere antes o `comum.py`).

    uv run python ml/notebooks/_ferramentas/sincronizar_comum.py            # reescreve os seis notebooks
    uv run python ml/notebooks/_ferramentas/sincronizar_comum.py --verificar  # só confere (não escreve)
    uv run python ml/notebooks/_ferramentas/sincronizar_comum.py a.ipynb b.ipynb   # notebooks escolhidos

Só as células com a tag `comum` são tocadas; o resto do notebook (parâmetros, seção do modelo,
textos) fica como está.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import nbformat

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

import comum  # noqa: E402

PASTA_NOTEBOOKS = AQUI.parent


def notebooks_dos_modelos() -> list[Path]:
    """`ml/notebooks/<modelo>/<modelo>.ipynb` (o que fica em pastas começando por `_` é ferramenta)."""
    return sorted(
        p
        for p in PASTA_NOTEBOOKS.glob("*/*.ipynb")
        if not p.parent.name.startswith("_") and p.stem == p.parent.name
    )


def celulas_comuns(nb) -> list:
    return [c for c in nb.cells if c.cell_type == "code" and "comum" in c.metadata.get("tags", [])]


def diferencas(caminho: Path, fonte: dict[str, str] | None = None) -> list[str]:
    """Descreve como as células comuns do notebook divergem da fonte (lista vazia = idêntico)."""
    fonte = fonte or comum.CELULAS
    nb = nbformat.read(caminho, as_version=4)
    achadas = {}
    problemas = []
    for cell in celulas_comuns(nb):
        secao = cell.metadata.get("secao")
        if secao not in fonte:
            problemas.append(f"célula comum com seção desconhecida: {secao!r}")
            continue
        achadas[secao] = cell
        if cell.source != fonte[secao]:
            problemas.append(f"célula comum '{secao}' difere da fonte")
    for secao in fonte:
        if secao not in achadas:
            problemas.append(f"falta a célula comum '{secao}'")
    ordem = [c.metadata.get("secao") for c in celulas_comuns(nb)]
    esperada = [s for s in comum.ORDEM if s in achadas]
    if ordem != esperada and not problemas:
        problemas.append(f"células comuns fora da ordem: {ordem}")
    return problemas


def sincronizar(caminho: Path, fonte: dict[str, str] | None = None) -> list[str]:
    """Reescreve as células comuns divergentes. Devolve as seções alteradas."""
    fonte = fonte or comum.CELULAS
    nb = nbformat.read(caminho, as_version=4)
    alteradas = []
    for cell in celulas_comuns(nb):
        secao = cell.metadata.get("secao")
        if secao not in fonte:
            raise ValueError(f"{caminho.name}: célula comum com seção desconhecida: {secao!r}")
        if cell.source != fonte[secao]:
            cell.source = fonte[secao]
            alteradas.append(secao)
    if alteradas:
        nbformat.write(nb, caminho)
    return alteradas


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("notebooks", nargs="*", type=Path)
    parser.add_argument("--verificar", action="store_true", help="só confere; sai com 1 se algo diverge")
    args = parser.parse_args(argv)
    alvos = args.notebooks or notebooks_dos_modelos()
    if not alvos:
        print("nenhum notebook de modelo encontrado")
        return 0
    divergiu = False
    for caminho in alvos:
        if args.verificar:
            problemas = diferencas(caminho)
            divergiu |= bool(problemas)
            print(
                f"{'ok  ' if not problemas else 'DIFERE'} {caminho.parent.name}: {'; '.join(problemas) or 'idêntico à fonte'}"
            )
        else:
            alteradas = sincronizar(caminho)
            print(f"{caminho.parent.name}: {', '.join(alteradas) if alteradas else 'já estava igual'}")
    return 1 if divergiu else 0


if __name__ == "__main__":
    sys.exit(main())
