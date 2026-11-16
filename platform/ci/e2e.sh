#!/usr/bin/env bash
# Teste de ponta a ponta da plataforma de ML (spec ci-test-pipeline):
#   sobe Postgres + MLflow + Airflow a partir do código do commit, dispara a DAG
#   atlas_ml_example_training e confere o resultado no MLflow.
#
# Uso (raiz do repositório; Linux, WSL ou Git Bash):
#   bash platform/ci/e2e.sh
# Variáveis opcionais:
#   E2E_PROJECT        nome do projeto compose (padrão atlas-ci; isolado do dev)
#   E2E_MLFLOW_PORT    porta local do MLflow (padrão 15000)
#   E2E_AIRFLOW_PORT   porta local do Airflow (padrão 18080)
#   E2E_NO_BUILD=1     usa imagens já construídas (atlas-epidemiologia-*:local), sem build
#   E2E_KEEP=1         não derruba a stack ao final (depuração)
#   ATLAS_GIT_SHA      commit em teste (padrão: git rev-parse HEAD)
# Em falha, os logs dos serviços vão para e2e-logs/.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

PROJECT="${E2E_PROJECT:-atlas-ci}"
export MLFLOW_PORT="${E2E_MLFLOW_PORT:-15000}"
export AIRFLOW_PORT="${E2E_AIRFLOW_PORT:-18080}"
export ATLAS_GIT_SHA="${ATLAS_GIT_SHA:-$(git rev-parse HEAD)}"
MLFLOW="http://127.0.0.1:${MLFLOW_PORT}"
AIRFLOW="http://127.0.0.1:${AIRFLOW_PORT}"
DAG="atlas_ml_example_training"
# Primeiro interpretador que realmente executa (no Windows, "python3" pode ser o atalho da Store)
PY=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null && "$candidate" -c "import json, secrets" >/dev/null 2>&1; then
    PY="$candidate"
    break
  fi
done
[ -n "$PY" ] || { echo "e2e: Python 3 não encontrado" >&2; exit 1; }

log() { printf '[e2e %(%H:%M:%S)T] %s\n' -1 "$*"; }
fail() { log "FALHOU: $*"; exit 1; }
json() { "$PY" -c "import json,sys; d=json.load(sys.stdin); print($1)"; }

ENV_FILE="$(mktemp)"
rand() { "$PY" -c "import secrets; print(secrets.token_urlsafe(18))"; }
ADMIN_PASSWORD="$(rand)"
cat >"$ENV_FILE" <<EOF
GCP_PROJECT=
MLFLOW_ARTIFACTS_BUCKET=
POSTGRES_PASSWORD=$(rand)
AIRFLOW_ADMIN_PASSWORD=${ADMIN_PASSWORD}
JUPYTER_TOKEN=e2e
EXTRA_CA_PATH=
EOF
mkdir -p platform/secrets

compose() { docker compose -p "$PROJECT" -f platform/compose.dev.yml --env-file "$ENV_FILE" "$@"; }

cleanup() {
  local status=$?
  if [ "$status" -ne 0 ]; then
    mkdir -p e2e-logs
    compose ps -a >e2e-logs/ps.txt 2>&1 || true
    for svc in $(compose config --services 2>/dev/null); do
      compose logs --no-color "$svc" >"e2e-logs/${svc}.log" 2>&1 || true
    done
    log "logs dos serviços em e2e-logs/"
  fi
  if [ "${E2E_KEEP:-0}" != "1" ]; then
    compose down -v --remove-orphans >/dev/null 2>&1 || true
  fi
  rm -f "$ENV_FILE"
  exit "$status"
}
trap cleanup EXIT

log "commit ${ATLAS_GIT_SHA} · projeto ${PROJECT} · MLflow :${MLFLOW_PORT} · Airflow :${AIRFLOW_PORT}"
if [ "${E2E_NO_BUILD:-0}" = "1" ]; then
  compose up -d --no-build
else
  compose up -d --build
fi

log "aguardando os 6 serviços ficarem saudáveis"
deadline=$((SECONDS + 600))
while :; do
  init_state="$(compose ps -a --format '{{.Service}} {{.State}} {{.ExitCode}}' | awk '$1=="airflow-init"{print $2" "$3}')"
  case "$init_state" in exited\ 0|"") ;; exited\ *) fail "airflow-init terminou com erro (${init_state})" ;; esac
  healthy="$(compose ps --format '{{.Health}}' | grep -c '^healthy$' || true)"
  unhealthy="$(compose ps --format '{{.Service}} {{.Health}}' | awk '$2=="unhealthy"{print $1}')"
  [ -z "$unhealthy" ] || fail "serviço(s) unhealthy: ${unhealthy}"
  [ "$healthy" -ge 6 ] && break
  [ "$SECONDS" -lt "$deadline" ] || fail "tempo esgotado esperando health (${healthy}/6)"
  sleep 5
done
log "plataforma saudável"

TOKEN="$(curl -fsS -H 'Content-Type: application/json' \
  -d "{\"username\":\"admin\",\"password\":\"${ADMIN_PASSWORD}\"}" "${AIRFLOW}/auth/token" | json "d['access_token']")"
AUTH=(-H "Authorization: Bearer ${TOKEN}")

log "aguardando a DAG ${DAG} ser carregada"
deadline=$((SECONDS + 180))
until curl -fsS -o /dev/null "${AUTH[@]}" "${AIRFLOW}/api/v2/dags/${DAG}"; do
  [ "$SECONDS" -lt "$deadline" ] || fail "DAG ${DAG} não apareceu no Airflow"
  sleep 5
done

curl -fsS -o /dev/null -X PATCH "${AUTH[@]}" -H 'Content-Type: application/json' \
  -d '{"is_paused": false}' "${AIRFLOW}/api/v2/dags/${DAG}"
RUN_ID="$(curl -fsS -X POST "${AUTH[@]}" -H 'Content-Type: application/json' \
  -d '{"logical_date": null}' "${AIRFLOW}/api/v2/dags/${DAG}/dagRuns" | json "d['dag_run_id']")"
log "DAG disparada: ${RUN_ID}"

deadline=$((SECONDS + 600))
while :; do
  state="$(curl -fsS "${AUTH[@]}" "${AIRFLOW}/api/v2/dags/${DAG}/dagRuns/${RUN_ID}" | json "d['state']")"
  case "$state" in
    success) break ;;
    failed) fail "a execução da DAG terminou em failed" ;;
  esac
  [ "$SECONDS" -lt "$deadline" ] || fail "tempo esgotado esperando a DAG (estado: ${state})"
  sleep 5
done
log "DAG terminou com sucesso"

EXP_ID="$(curl -fsS "${MLFLOW}/api/2.0/mlflow/experiments/get-by-name?experiment_name=atlas%2Fexample" \
  | json "d['experiment']['experiment_id']")"
RUN_JSON="$(curl -fsS -H 'Content-Type: application/json' \
  -d "{\"experiment_ids\": [\"${EXP_ID}\"], \"max_results\": 1, \"order_by\": [\"attributes.start_time DESC\"]}" \
  "${MLFLOW}/api/2.0/mlflow/runs/search")"
check_tags="
r = d['runs'][0]
tags = {t['key']: t['value'] for t in r['data']['tags']}
problems = []
if r['info']['status'] != 'FINISHED': problems.append('status=' + r['info']['status'])
for k in ('atlas.env', 'atlas.git_sha', 'atlas.image_tag', 'atlas.data_version'):
    if not tags.get(k): problems.append('sem ' + k)
if tags.get('atlas.env') != 'dev': problems.append('atlas.env=' + str(tags.get('atlas.env')))
if tags.get('atlas.git_sha') != sys.argv[1]: problems.append('atlas.git_sha=' + str(tags.get('atlas.git_sha')))
print('; '.join(problems) or 'ok')
"
result="$(printf '%s' "$RUN_JSON" | "$PY" -c "import json,sys; d=json.load(sys.stdin); ${check_tags}" "$ATLAS_GIT_SHA")"
[ "$result" = "ok" ] || fail "run no MLflow: ${result}"
log "run no MLflow com tags atlas.* e commit corretos"

curl -fsS -o /dev/null "${MLFLOW}/api/2.0/mlflow/registered-models/alias?name=atlas-example&alias=dev" \
  || fail "modelo atlas-example sem alias @dev"
log "modelo atlas-example registrado com @dev"
log "OK — teste de ponta a ponta passou"
