#!/usr/bin/env bash
# Testes negativos das regras do serviço jupyter no check-stack.sh: cada violação tem de ser recusada.
# Parte do docker-compose.yml válido, estraga uma coisa por vez (STACK_FILE) e espera que o check falhe com a
# mensagem certa. Roda no CI (job "stack") e à mão: bash platform/ci/test-check-stack-jupyter.sh
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.."

PY=""
for candidato in python3 python py; do
  if command -v "$candidato" >/dev/null 2>&1 && "$candidato" -c "import yaml" >/dev/null 2>&1; then
    PY="$candidato"
    break
  fi
done
[ -n "$PY" ] || { echo "test-check-stack-jupyter: Python 3 com PyYAML não encontrado" >&2; exit 2; }

BASH_BIN="$BASH" "$PY" - <<'PY'
import os
import subprocess
import sys
import tempfile

# a saída do check no Windows não é UTF-8: compara só trechos ASCII e imprime sem quebrar
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REDES = "    networks: [network_public]\n    deploy:\n      <<: *airflow-deploy\n      replicas: ${JUPYTER_REPLICAS"
INICIO = '    user: "1000:1000"\n    read_only: true\n    cap_drop: [ALL]\n    environment:\n      ATLAS_ENV: ${ATLAS_ENV:?hml ou prod}\n      # só o HASH'
HASH = "      JUPYTER_PASSWORD_HASH: ${JUPYTER_PASSWORD_HASH:?hash argon2 da senha do Jupyter}\n"
VOLUMES = "      - jupyter_work:/home/atlas/work\n      - jupyter_hf_cache:/home/atlas/hf-cache\n"

# nome | trecho que o check deve citar | (trecho do compose, substituto)
CASOS = [
    ("porta publicada", "publica porta no host", (REDES, '    ports:\n      - "8888:8888"\n' + REDES)),
    (
        "com um secret",
        "pode ter secrets",
        ("    volumes:\n" + VOLUMES, "    secrets:\n      - training_sa\n    volumes:\n" + VOLUMES),
    ),
    (
        "na rede interna",
        "rede interna atlas_internal",
        (REDES, REDES.replace("[network_public]", "[atlas_internal, network_public]")),
    ),
    (
        "com credencial do MLflow",
        "veis de credencial",
        (HASH, HASH + "      MLFLOW_TRACKING_URI: http://mlflow:5000\n"),
    ),
    (
        "com credencial do Google",
        "veis de credencial",
        (HASH, HASH + "      GOOGLE_APPLICATION_CREDENTIALS: /run/secrets/x.json\n"),
    ),
    ("montando o volume do Airflow", "volume do Airflow", (VOLUMES, VOLUMES + "      - airflow_dags:/opt/airflow/git:ro\n")),
    ("sem o hash da senha", "sem JUPYTER_PASSWORD_HASH", (HASH, "")),
    ("sem cap_drop", "sem cap_drop", (INICIO, INICIO.replace("    cap_drop: [ALL]\n", ""))),
    ("sem read_only", "sem read_only", (INICIO, INICIO.replace("    read_only: true\n", ""))),
    ("como root", "roda como root", (INICIO, INICIO.replace('"1000:1000"', '"0:0"'))),
    (
        "sem limite de tentativas",
        "limite de tentativas (ratelimit)",
        (".middlewares=atlas-${ATLAS_ENV}-jupyter-limite", ".middlewares=atlas-${ATLAS_ENV}-outro"),
    ),
]

original = open("docker-compose.yml", encoding="utf-8").read().replace("\r\n", "\n")
falhas = 0
with tempfile.TemporaryDirectory() as tmp:
    for nome, esperado, (velho, novo) in CASOS:
        if original.count(velho) != 1:
            sys.exit(f"{nome}: o trecho esperado do compose mudou (achei {original.count(velho)} vezes)")
        destino = os.path.join(tmp, "stack.yml")
        with open(destino, "w", encoding="utf-8", newline="\n") as f:
            f.write(original.replace(velho, novo, 1))
        r = subprocess.run(
            [os.environ["BASH_BIN"], "platform/ci/check-stack.sh"],
            env={**os.environ, "STACK_FILE": destino},
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        saida = r.stdout + r.stderr
        if r.returncode == 0:
            print(f"FALHOU  {nome}: o check-stack aceitou um stack com a violação")
            falhas += 1
        elif esperado in saida:
            print(f"ok      {nome}")
        else:
            print(f"FALHOU  {nome}: recusou, mas sem a mensagem esperada ({esperado!r})")
            print("\n".join(saida.strip().splitlines()[-3:]))
            falhas += 1

if falhas:
    sys.exit(f"test-check-stack-jupyter: {falhas} caso(s) com problema")
print("test-check-stack-jupyter: todas as violações foram recusadas")
PY
