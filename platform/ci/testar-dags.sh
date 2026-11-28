#!/usr/bin/env bash
# Testes das DAGs em segundos, antes de abrir o PR (mudança add-forecast-model-dags): os mesmos do job
# `dags` do CI, na imagem do Airflow com as DAGs, os testes e os notebooks do disco montados. Não precisa
# do Airflow de pé nem de rede (exceto para baixar a imagem publicada na primeira vez).
#
#   bash platform/ci/testar-dags.sh              # imagem local (atlas-epidemiologia-airflow:local)
#   bash platform/ci/testar-dags.sh --publicada  # imagem :hml do DockerHub (a mesma da via rápida do CI)
#   bash platform/ci/testar-dags.sh test_dags.py # só um arquivo de teste (também com --publicada)
#
# A imagem só importa pelo que não muda com as DAGs (Airflow, Cosmos, dbt, venv do atlas_ml): uma imagem
# local de dias atrás serve, desde que as dependências não tenham mudado desde então.
set -euo pipefail

RAIZ="$(cd "$(dirname "$0")/../.." && pwd)"
IMAGEM="${ATLAS_AIRFLOW_IMAGE:-atlas-epidemiologia-airflow:local}"
TESTES=()
for arg in "$@"; do
  case "$arg" in
    --publicada) IMAGEM="anselmomendes/atlas-epidemiologia-airflow:hml" ;;
    -h | --help)
      sed -n '2,11p' "$0"
      exit 0
      ;;
    *) TESTES+=("$arg") ;;
  esac
done
if [ "${#TESTES[@]}" -eq 0 ]; then
  TESTES=(test_dags.py test_forecast_modelo.py test_sinan_ingest.py test_forecast_export.py test_etl_brasil.py
    test_ingestao_arquivo.py)
fi

if ! docker image inspect "$IMAGEM" >/dev/null 2>&1; then
  if [ "$IMAGEM" = "atlas-epidemiologia-airflow:local" ]; then
    echo "testar-dags: imagem $IMAGEM não existe; builde com 'docker compose -f platform/compose.dev.yml build airflow-init' ou use --publicada" >&2
    exit 1
  fi
  docker pull "$IMAGEM"
fi

# No Git Bash do Windows, caminhos do host precisam do formato C:/... e sem conversão automática
caminho() {
  if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s' "$1"; fi
}
export MSYS_NO_PATHCONV=1

falhas=0
for teste in "${TESTES[@]}"; do
  echo "=== ${teste} (${IMAGEM})"
  status=0
  saida="$(docker run --rm --entrypoint python \
    -e DBT_BQ_KEYFILE=/tmp/chave-ficticia.json \
    -e AIRFLOW__COSMOS__ENABLE_CACHE_DBT_LS=False \
    -v "$(caminho "$RAIZ/airflow/dags"):/opt/airflow/dags" \
    -v "$(caminho "$RAIZ/airflow/tests"):/opt/atlas/tests:ro" \
    -v "$(caminho "$RAIZ/ml/notebooks"):/opt/atlas/notebooks:ro" \
    "$IMAGEM" "/opt/atlas/tests/${teste}" 2>&1)" || status=$?
  # só o resultado dos testes (o Cosmos registra muito ao ler as DAGs do dbt); em erro, o fim do log
  printf '%s\n' "$saida" | grep -E '^(ok|FAIL) ' || true
  if [ "$status" -ne 0 ]; then
    printf '%s\n' "$saida" | grep -v -i 'warning' | tail -20
    falhas=$((falhas + 1))
  fi
done

if [ "$falhas" -gt 0 ]; then
  echo "testar-dags: ${falhas} arquivo(s) de teste com falha" >&2
  exit 1
fi
echo "testar-dags: todos os testes passaram"
