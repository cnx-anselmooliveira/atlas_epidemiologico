"""Limite de threads por tarefa de treino.

Várias tarefas pesadas rodam juntas na mesma máquina (DAG atlas_dengue_forecast_br). Sem limite, cada
uma abre uma thread por núcleo (PyTorch, CatBoost, BLAS) e todas disputam a CPU: um treino que leva
minutos passa de 30. O padrão divide os núcleos por 3 (as 3 tarefas simultâneas da DAG).
ATLAS_THREADS muda o valor.
"""

from __future__ import annotations

import os

VARIAVEIS = ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS")


def threads() -> int:
    """Threads por tarefa: ATLAS_THREADS, ou um terço dos núcleos (no mínimo 1)."""
    pedido = os.environ.get("ATLAS_THREADS", "").strip()
    if pedido.isdigit() and int(pedido) > 0:
        return int(pedido)
    return max(1, (os.cpu_count() or 3) // 3)


def limitar() -> int:
    """Define as variáveis das bibliotecas numéricas (vale para quem ainda não foi importada)."""
    n = threads()
    for nome in VARIAVEIS:
        os.environ.setdefault(nome, str(n))
    return n
