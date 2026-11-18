#!/usr/bin/env bash
# Roda o dbt do projeto utfpr_dengue localmente, com o mesmo profile da DAG dbt_brasil.
#   ./airflow/dags/utfpr_dengue/dbt.sh debug
#   ./airflow/dags/utfpr_dengue/dbt.sh build --select +gold_dengue_casos_provaveis_uf_semanal
# Padrões (sobrescreva exportando antes):
#   DBT_BQ_KEYFILE  <repo>/platform/secrets/training-sa.json
#   artefatos       <repo>/.dbt-local/{target,logs,dbt_packages} (ignorado pelo git)
# Rede com inspeção TLS: o uv recebe --native-tls.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="$(cd "$here/../../.." && pwd)"
export DBT_BQ_KEYFILE="${DBT_BQ_KEYFILE:-$repo/platform/secrets/training-sa.json}"
export DBT_TARGET_PATH="${DBT_TARGET_PATH:-$repo/.dbt-local/target}"
export DBT_LOG_PATH="${DBT_LOG_PATH:-$repo/.dbt-local/logs}"
export DBT_PACKAGES_INSTALL_PATH="${DBT_PACKAGES_INSTALL_PATH:-$repo/.dbt-local/dbt_packages}"
export DBT_SEND_ANONYMOUS_USAGE_STATS=false
export PYTHONIOENCODING=utf-8  # console do Windows (cp1252) não imprime todos os caracteres do log
# venv do uv fora da pasta de DAGs: o Cosmos calcula um hash da pasta do projeto a cada
# leitura da DAG, e um .venv aqui dentro deixaria isso lento demais (montagem do Windows)
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-$repo/.dbt-local/venv}"
exec uv run --native-tls --project "$here" dbt "$@" --project-dir "$here" --profiles-dir "$here"
