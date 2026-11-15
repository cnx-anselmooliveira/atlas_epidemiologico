#!/bin/sh
# Monta o comando do servidor MLflow a partir de variáveis de ambiente.
#
# Obrigatórias:
#   MLFLOW_BACKEND_STORE_URI   postgresql://usuario:senha@postgres:5432/mlflow
#   Destino dos artefatos, em ordem de precedência:
#     MLFLOW_ARTIFACTS_BUCKET + MLFLOW_INSTALLATION (dev|vps) → gs://<bucket>/mlflow/<instalação>
#     MLFLOW_ARTIFACTS_DESTINATION                            → outro destino (ex.: volume local no dev)
# Opcionais:
#   MLFLOW_AUTH=true           liga a autenticação (basic-auth) — exigido na VPS
#   MLFLOW_AUTH_DATABASE_URI   banco de usuários/permissões (ex.: …/mlflow_auth)
#   MLFLOW_ADMIN_USERNAME / MLFLOW_ADMIN_PASSWORD   admin criado no primeiro boot
#   MLFLOW_FLASK_SERVER_SECRET_KEY                  chave fixa do CSRF (obrigatória com auth)
#   MLFLOW_ALLOWED_HOSTS       hosts aceitos (proteção contra DNS rebinding), separados por vírgula
#   MLFLOW_WORKERS             processos do servidor (padrão 2)
set -eu

fail() { echo "mlflow-entrypoint: $*" >&2; exit 1; }

[ -n "${MLFLOW_BACKEND_STORE_URI:-}" ] || fail "MLFLOW_BACKEND_STORE_URI não definida"

if [ -n "${MLFLOW_ARTIFACTS_BUCKET:-}" ]; then
  case "${MLFLOW_INSTALLATION:-}" in
    dev|vps) ;;
    *) fail "MLFLOW_INSTALLATION deve ser dev ou vps (recebido: '${MLFLOW_INSTALLATION:-}')" ;;
  esac
  DEST="gs://${MLFLOW_ARTIFACTS_BUCKET}/mlflow/${MLFLOW_INSTALLATION}"
elif [ -n "${MLFLOW_ARTIFACTS_DESTINATION:-}" ]; then
  DEST="$MLFLOW_ARTIFACTS_DESTINATION"
else
  fail "defina MLFLOW_ARTIFACTS_BUCKET (GCS) ou MLFLOW_ARTIFACTS_DESTINATION"
fi

set -- mlflow server \
  --backend-store-uri "$MLFLOW_BACKEND_STORE_URI" \
  --artifacts-destination "$DEST" \
  --serve-artifacts \
  --host 0.0.0.0 \
  --port 5000 \
  --workers "${MLFLOW_WORKERS:-2}"

if [ -n "${MLFLOW_ALLOWED_HOSTS:-}" ]; then
  set -- "$@" --allowed-hosts "$MLFLOW_ALLOWED_HOSTS"
fi

if [ "${MLFLOW_AUTH:-false}" = "true" ]; then
  [ -n "${MLFLOW_AUTH_DATABASE_URI:-}" ] || fail "MLFLOW_AUTH=true exige MLFLOW_AUTH_DATABASE_URI"
  [ -n "${MLFLOW_ADMIN_USERNAME:-}" ] || fail "MLFLOW_AUTH=true exige MLFLOW_ADMIN_USERNAME"
  [ -n "${MLFLOW_ADMIN_PASSWORD:-}" ] || fail "MLFLOW_AUTH=true exige MLFLOW_ADMIN_PASSWORD"
  # Chave fixa da proteção CSRF; precisa ser a mesma entre reinícios e réplicas
  [ -n "${MLFLOW_FLASK_SERVER_SECRET_KEY:-}" ] || fail "MLFLOW_AUTH=true exige MLFLOW_FLASK_SERVER_SECRET_KEY"
  # Renderiza o ini com Python (sem envsubst na imagem slim); senha não aparece no comando
  python - <<'PY'
import os
tmpl = open("/etc/mlflow/basic_auth.ini.tmpl", encoding="utf-8").read()
out = tmpl
for key in ("MLFLOW_AUTH_DATABASE_URI", "MLFLOW_ADMIN_USERNAME", "MLFLOW_ADMIN_PASSWORD"):
    out = out.replace("${" + key + "}", os.environ[key])
path = os.path.expanduser("~/basic_auth.ini")
with open(path, "w", encoding="utf-8") as f:
    f.write(out)
os.chmod(path, 0o600)
PY
  export MLFLOW_AUTH_CONFIG_PATH="$HOME/basic_auth.ini"
  set -- "$@" --app-name basic-auth
fi

echo "mlflow-entrypoint: artefatos em $DEST · auth=${MLFLOW_AUTH:-false}"
exec "$@"
