#!/usr/bin/env bash
# Casos da via rápida do CI (platform/ci/escopo.sh), sem rede. Roda no job lint do ci.yml:
#   bash platform/ci/test-escopo.sh
set -euo pipefail

ESCOPO="$(dirname "$0")/escopo.sh"
falhas=0

caso() {
  local nome="$1" esperado="$2" entrada="$3" obtido
  obtido="$(printf '%s' "$entrada" | bash "$ESCOPO" 2>/dev/null)"
  if [ "$obtido" = "rapido=${esperado}" ]; then
    echo "ok   ${nome}"
  else
    echo "FAIL ${nome}: esperado rapido=${esperado}, obtido ${obtido}"
    falhas=$((falhas + 1))
  fi
}

caso "só DAG" true $'airflow/dags/atlas_forecast_lstm.py\n'
caso "DAG e fábrica em atlas_ingest" true $'airflow/dags/atlas_dengue_forecast_br.py\nairflow/dags/atlas_ingest/forecast_modelo.py\n'
caso "DAG e pacote ml" false $'airflow/dags/atlas_forecast_lstm.py\nml/src/atlas_ml/forecast/notebook.py\n'
caso "uv.lock do dbt" false $'airflow/dags/utfpr_dengue/uv.lock\n'
caso "pyproject do dbt" false $'airflow/dags/utfpr_dengue/pyproject.toml\n'
caso "model do dbt (SQL)" true $'airflow/dags/utfpr_dengue/models/gold/gold_dengue_epi_curve_weekly.sql\n'
caso "só notebook" true $'ml/notebooks/lstm/lstm.ipynb\n'
caso "só Markdown" true $'README.md\nairflow/README.md\n'
caso "OpenSpec e docs" true $'openspec/changes/x/tasks.md\ndocs/referencias/a.csv\n'
caso "lista vazia" false ''
caso "workflow alterado" false $'.github/workflows/ci.yml\n'
caso "DAG com o teste dela" true $'airflow/dags/atlas_forecast_svr.py\nairflow/tests/test_dags.py\n'
caso "Dockerfile do Airflow" false $'airflow/Dockerfile\n'
caso "CRLF no fim da linha" true $'airflow/dags/etl_brasil.py\r\n'
caso "sem quebra de linha no fim" true 'ml/notebooks/svr/svr.ipynb'

if [ "$falhas" -gt 0 ]; then
  echo "${falhas} caso(s) falharam"
  exit 1
fi
