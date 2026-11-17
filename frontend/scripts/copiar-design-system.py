"""Copia do design system original (local, fora do Git) só o que o site usa.

Uso (na raiz do repositório): python -I frontend/scripts/copiar-design-system.py frontend
"""

import re
import shutil
import sys
from pathlib import Path

front = Path(sys.argv[1])
ref = front / "design-system" / "status_invest"

ARQUIVOS = {
    "tokens/tokens.css": ("src/styles/ds/tokens.css", "tokens (cores, tipografia, espaços, sombras, tema escuro)"),
    "css/base.css": ("src/styles/ds/base.css", "base: reset e tipografia"),
    "css/layout.css": ("src/styles/ds/layout.css", "layout"),
    "css/components.css": ("src/styles/ds/components.css", "componentes (.ds-*)"),
    "css/utilities.css": ("src/styles/ds/utilities.css", "utilitários"),
    "js/ds.js": ("src/scripts/ds/ds.js", None),
    "js/echarts-theme.js": ("src/scripts/ds/echarts-theme.js", None),
}

ORIGEM = (
    "Cópia de frontend/design-system/status_invest/{orig} (cópia local de consulta, fora do Git).\n"
    "   Para mudar: altere o original e copie de novo."
)

# frases dos comentários que descrevem a página de referência, não o site
LIMPEZA = [
    (r' \(como o "paper" da referência\)', ""),
    (r' \(o "special" da referência\)', ""),
    (r" \(como a referência\)", ""),
    (r" \(top-info\)", ""),
]

PROIBIDO = re.compile(r"status ?invest|mglu3|top-info|referência", re.I)


def cabecalho_css(titulo, orig):
    return (
        "/* =============================================================================\n"
        f"   Atlas DS · Painel — {titulo}\n"
        f"   {ORIGEM.format(orig=orig)}\n"
        "   ========================================================================== */"
    )


for orig, (destino, titulo) in ARQUIVOS.items():
    texto = (ref / orig).read_text(encoding="utf-8")
    primeiro = re.match(r"/\*.*?\*/", texto, re.S)
    assert primeiro, orig
    corpo = texto[primeiro.end():]
    if titulo is None:  # JS: mantém o comentário de uso, acrescenta a origem
        bloco = primeiro.group(0)
        bloco = bloco.replace('"../../design-system/js/echarts-theme.js"', '"../scripts/ds/echarts-theme.js"')
        bloco = bloco.replace(
            "   ========================================================================== */",
            f"   {ORIGEM.format(orig=orig)}\n   ========================================================================== */",
            1,
        )
        novo = bloco + corpo
    else:
        novo = cabecalho_css(titulo, orig) + corpo
    for padrao, troca in LIMPEZA:
        novo = re.sub(padrao, troca, novo)
    linhas_ruins = [ln for ln in novo.splitlines() if PROIBIDO.search(ln) and "Cópia de" not in ln]
    assert not linhas_ruins, (destino, linhas_ruins)
    alvo = front / destino
    alvo.parent.mkdir(parents=True, exist_ok=True)
    alvo.write_bytes(novo.encode("utf-8"))
    print(f"{orig} -> {destino}")

shutil.copyfile(ref / "icons/icons.svg", front / "public/icons.svg")
assert not PROIBIDO.search((front / "public/icons.svg").read_text(encoding="utf-8"))
print("icons/icons.svg -> public/icons.svg")
