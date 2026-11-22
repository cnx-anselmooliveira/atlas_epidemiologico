"""Semeia o volume de trabalho do Jupyter com os notebooks do repositório (roda antes do servidor).

O usuário trabalha numa cópia, no volume `/home/atlas/work`. Só semeia quando o volume está vazio, para não
sobrescrever trabalho do usuário. A origem é a cópia que a imagem carrega (`/opt/atlas/notebooks`): o Jupyter
não tem integração com nada do projeto, nem com o clone do git-sync.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

IMAGEM = "/opt/atlas/notebooks"
ENTRADAS_IGNORADAS = {"lost+found"}  # criada pelo sistema de arquivos de um volume novo


def volume_vazio(destino: Path) -> bool:
    return not destino.exists() or not [p for p in destino.iterdir() if p.name not in ENTRADAS_IGNORADAS]


def semear(destino: str | os.PathLike[str], imagem: str = IMAGEM) -> str:
    """Copia os notebooks da imagem para `destino/notebooks`. Devolve `imagem` ou `nada`."""
    destino, origem = Path(destino), Path(imagem)
    if not volume_vazio(destino) or not (origem.is_dir() and any(origem.iterdir())):
        return "nada"
    destino.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        origem, destino / "notebooks", ignore=shutil.ignore_patterns("__pycache__", ".ipynb_checkpoints")
    )
    return "imagem"


def main() -> int:
    destino = os.environ.get("JUPYTER_ROOT_DIR", "/home/atlas/work")
    origem = semear(destino, os.environ.get("ATLAS_NOTEBOOKS_IMAGE", IMAGEM))
    print(f"semear_notebooks: {destino} <- {origem}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
