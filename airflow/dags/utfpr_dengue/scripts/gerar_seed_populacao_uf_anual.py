"""Gera seeds/seed_populacao_uf_anual.csv: população residente por UF e ano, de 2000 ao ano corrente.

Fontes (API SIDRA do IBGE, https://apisidra.ibge.gov.br):
- Censo 2000 e 2010: tabela 202, variável 93 (população residente, total);
- Censo 2022: tabela 9514, variável 93 (total, todas as idades);
- Estimativas anuais: tabela 6579, variável 9324 (população residente estimada).

Prioridade por ano: censo > estimativa. Anos sem valor entre dois conhecidos são
interpolados linearmente; anos depois do último valor repetem o último (extrapolado).

Uso (só para atualizar o CSV versionado, que é a fonte da verdade do dbt):
    python airflow/dags/utfpr_dengue/scripts/gerar_seed_populacao_uf_anual.py
Se o SIDRA falhar, o script termina com erro sem tocar no CSV.
"""

from __future__ import annotations

import csv
import json
import sys
import urllib.request
from datetime import date
from pathlib import Path

SIDRA = "https://apisidra.ibge.gov.br/values"
QUERIES = {
    "censo": [
        "t/202/n3/all/v/93/p/2000,2010/c1/0/c2/0",
        "t/9514/n3/all/v/93/p/2022/c2/6794/c287/100362/c286/113635",
    ],
    "estimativa": ["t/6579/n3/all/v/9324/p/all"],
}
SOURCE = {
    "censo": "IBGE/SIDRA Censo Demográfico (tabelas 202 e 9514)",
    "estimativa": "IBGE/SIDRA Estimativas de população (tabela 6579)",
    "interpolado": "Interpolação linear entre anos com valor do IBGE",
    "extrapolado": "Repetição do último valor do IBGE",
}
# Código IBGE da UF → sigla
UF = {
    "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP", "17": "TO",
    "21": "MA", "22": "PI", "23": "CE", "24": "RN", "25": "PB", "26": "PE", "27": "AL",
    "28": "SE", "29": "BA", "31": "MG", "32": "ES", "33": "RJ", "35": "SP", "41": "PR",
    "42": "SC", "43": "RS", "50": "MS", "51": "MT", "52": "GO", "53": "DF",
}  # fmt: skip
FIRST_YEAR = 2000
OUT = Path(__file__).resolve().parents[1] / "seeds" / "seed_populacao_uf_anual.csv"


def fetch(path: str) -> list[dict]:
    req = urllib.request.Request(f"{SIDRA}/{path}?formato=json", headers={"User-Agent": "atlas-dbt"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        rows = json.load(resp)
    return rows[1:]  # a primeira linha é o cabeçalho


def collect() -> dict[str, dict[int, tuple[int, str]]]:
    known: dict[str, dict[int, tuple[int, str]]] = {uf: {} for uf in UF.values()}
    # estimativas primeiro; censos sobrescrevem no mesmo ano
    for origin in ("estimativa", "censo"):
        for path in QUERIES[origin]:
            for row in fetch(path):
                uf, year, value = UF.get(row["D1C"]), int(row["D3C"]), row["V"]
                if uf and value.isdigit():
                    known[uf][year] = (int(value), origin)
    return known


def fill(known: dict[int, tuple[int, str]], last_year: int) -> list[tuple[int, int, str]]:
    years = sorted(known)
    if not years or years[0] > FIRST_YEAR:
        raise SystemExit(f"sem valor do IBGE em {FIRST_YEAR}: {years[:3]}")
    out = []
    for year in range(FIRST_YEAR, last_year + 1):
        if year in known:
            out.append((year, *known[year]))
            continue
        before = max(y for y in years if y < year)
        after = [y for y in years if y > year]
        if after:
            nxt = min(after)
            p0, p1 = known[before][0], known[nxt][0]
            value = round(p0 + (p1 - p0) * (year - before) / (nxt - before))
            out.append((year, value, "interpolado"))
        else:
            out.append((year, known[before][0], "extrapolado"))
    return out


def main() -> int:
    last_year = date.today().year
    known = collect()
    rows = []
    for uf in sorted(known):
        for year, population, origin in fill(known[uf], last_year):
            rows.append([uf, year, population, origin, SOURCE[origin]])
    expected = len(UF) * (last_year - FIRST_YEAR + 1)
    if len(rows) != expected:
        raise SystemExit(f"esperava {expected} linhas, gerei {len(rows)}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(["uf", "year", "population", "origin", "source"])
        writer.writerows(rows)
    counts: dict[str, int] = {}
    for row in rows:
        counts[row[3]] = counts.get(row[3], 0) + 1
    print(f"{OUT.name}: {len(rows)} linhas ({len(UF)} UFs x {FIRST_YEAR}-{last_year}) {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
