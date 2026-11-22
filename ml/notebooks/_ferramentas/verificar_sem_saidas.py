"""Barra notebooks versionados com saídas de células (só biblioteca padrão, roda no CI e no hook).

    python ml/notebooks/_ferramentas/verificar_sem_saidas.py            # todos os notebooks de ml/notebooks
    python ml/notebooks/_ferramentas/verificar_sem_saidas.py a.ipynb    # só os informados (o hook passa os staged)
    python ml/notebooks/_ferramentas/verificar_sem_saidas.py --limpar a.ipynb   # tira as saídas do arquivo

O repositório é público e a saída de uma célula pode trazer dados (tabelas da gold, previsões). Os notebooks
ficam no Git sem saídas; elas aparecem quando o notebook roda. Sai com 1 e aponta cada arquivo e célula.
Para limpar: `--limpar <arquivo>` ou "Clear All Outputs" no Jupyter.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PASTA = Path(__file__).resolve().parents[1]


def celulas_com_saida(caminho: Path) -> list[int]:
    """Índices das células de código com saída ou contador de execução."""
    nb = json.loads(caminho.read_text(encoding="utf-8"))
    return [
        i
        for i, c in enumerate(nb.get("cells", []))
        if c.get("cell_type") == "code" and (c.get("outputs") or c.get("execution_count") is not None)
    ]


def limpar(arquivo: Path) -> bool:
    """Tira as saídas e o contador de execução de um notebook, no próprio arquivo. True se mudou algo."""
    nb = json.loads(arquivo.read_text(encoding="utf-8"))
    mudou = False
    for c in nb.get("cells", []):
        if c.get("cell_type") == "code" and (c.get("outputs") or c.get("execution_count") is not None):
            c["outputs"], c["execution_count"], mudou = [], None, True
    if mudou:
        arquivo.write_text(json.dumps(nb, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return mudou


def verificar(arquivos: list[Path]) -> list[str]:
    erros = []
    for arquivo in arquivos:
        if arquivo.suffix != ".ipynb":
            continue
        try:
            celulas = celulas_com_saida(arquivo)
        except (OSError, ValueError) as erro:
            erros.append(f"{arquivo}: não foi possível ler o notebook ({erro})")
            continue
        if celulas:
            erros.append(f"{arquivo}: células com saída ou contador de execução: {celulas}")
    return erros


def main(argv: list[str]) -> int:
    if argv and argv[0] == "--limpar":
        alvos = [Path(a) for a in argv[1:]]
        for alvo in alvos:
            print(f"{alvo}: {'saídas removidas' if limpar(alvo) else 'já estava limpo'}")
        return 0
    arquivos = [Path(a) for a in argv] or sorted(PASTA.rglob("*.ipynb"))
    arquivos = [a for a in arquivos if ".ipynb_checkpoints" not in a.parts]
    erros = verificar(arquivos)
    for e in erros:
        print(f"::error::{e}")
    if erros:
        print(
            f"verificar_sem_saidas: {len(erros)} notebook(s) com saídas. Limpe com `verificar_sem_saidas.py --limpar <arquivo>` "
            "ou 'Clear All Outputs' no Jupyter antes de commitar.",
            file=sys.stderr,
        )
        return 1
    print(f"verificar_sem_saidas: {len(arquivos)} notebook(s) sem saídas")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
