#!/bin/sh
# Executado uma única vez pelo entrypoint do Postgres (docker-entrypoint-initdb.d),
# quando o volume está vazio. Cria um banco e um usuário por serviço; cada usuário
# só conecta no(s) próprio(s) banco(s).
#
# Variáveis (do compose):
#   POSTGRES_PASSWORD     superusuário
#   MLFLOW_DB_PASSWORD    usuário mlflow  (bancos mlflow e mlflow_auth)
#   AIRFLOW_DB_PASSWORD   usuário airflow (banco airflow)
#   AIRFLOW_DATABASES     bancos do Airflow (dev: "airflow"; VPS: "airflow_hml airflow_prod")
set -eu

AIRFLOW_DATABASES="${AIRFLOW_DATABASES:-airflow}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<SQL
CREATE ROLE mlflow LOGIN PASSWORD '${MLFLOW_DB_PASSWORD}';
CREATE ROLE airflow LOGIN PASSWORD '${AIRFLOW_DB_PASSWORD}';
CREATE DATABASE mlflow OWNER mlflow;
CREATE DATABASE mlflow_auth OWNER mlflow;
REVOKE CONNECT ON DATABASE mlflow, mlflow_auth FROM PUBLIC;
GRANT CONNECT ON DATABASE mlflow, mlflow_auth TO mlflow;
SQL

for db in $AIRFLOW_DATABASES; do
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<SQL
CREATE DATABASE ${db} OWNER airflow;
REVOKE CONNECT ON DATABASE ${db} FROM PUBLIC;
GRANT CONNECT ON DATABASE ${db} TO airflow;
SQL
done

echo "init-databases: mlflow, mlflow_auth, ${AIRFLOW_DATABASES}"
