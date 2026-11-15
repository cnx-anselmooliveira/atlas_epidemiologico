#!/usr/bin/env bash
# Inicialização do Airflow (serviço airflow-init): migra o banco e cria o admin.
# Idempotente: pode rodar a cada deploy.
#
# Variáveis:
#   AIRFLOW__CORE__AUTH_MANAGER   SimpleAuthManager (dev) ou FabAuthManager (VPS)
#   AIRFLOW_ADMIN_USERNAME        padrão: admin
#   AIRFLOW_ADMIN_PASSWORD        obrigatória
set -euo pipefail

: "${AIRFLOW_ADMIN_PASSWORD:?AIRFLOW_ADMIN_PASSWORD não definida}"
ADMIN="${AIRFLOW_ADMIN_USERNAME:-admin}"

echo "airflow-init: migrando o banco de metadados"
airflow db migrate

case "${AIRFLOW__CORE__AUTH_MANAGER:-}" in
  *FabAuthManager*)
    echo "airflow-init: garantindo o usuário $ADMIN (FAB)"
    if airflow users list -o plain 2>/dev/null | awk '{print $2}' | grep -qx "$ADMIN"; then
      airflow users reset-password --username "$ADMIN" --password "$AIRFLOW_ADMIN_PASSWORD"
    else
      airflow users create --role Admin --username "$ADMIN" --password "$AIRFLOW_ADMIN_PASSWORD" \
        --firstname Atlas --lastname Admin --email "${AIRFLOW_ADMIN_EMAIL:-admin@example.com}"
    fi
    ;;
  *SimpleAuthManager*|"")
    # Simple Auth Manager (dev): usuários vêm de AIRFLOW__CORE__SIMPLE_AUTH_MANAGER_USERS e as
    # senhas do arquivo apontado por AIRFLOW__CORE__SIMPLE_AUTH_MANAGER_PASSWORDS_FILE.
    PW_FILE="${AIRFLOW__CORE__SIMPLE_AUTH_MANAGER_PASSWORDS_FILE:-/opt/airflow/simple_auth_passwords.json}"
    echo "airflow-init: gravando a senha do $ADMIN em $PW_FILE (Simple Auth Manager)"
    python - "$PW_FILE" "$ADMIN" <<'PY'
import json, os, sys
path, user = sys.argv[1], sys.argv[2]
with open(path, "w", encoding="utf-8") as f:
    json.dump({user: os.environ["AIRFLOW_ADMIN_PASSWORD"]}, f)
os.chmod(path, 0o600)
PY
    ;;
  *)
    echo "airflow-init: auth manager desconhecido: $AIRFLOW__CORE__AUTH_MANAGER" >&2
    exit 1
    ;;
esac

echo "airflow-init: pronto"
