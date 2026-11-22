#!/usr/bin/env bash
# Espera o primeiro clone do git-sync (o link `current`) antes de iniciar um componente do Airflow.
# O Swarm ignora depends_on, e subir o Airflow sem o clone deixaria o dag-processor sem DAGs.
#
# Variáveis:
#   ATLAS_DAGS_LINK             link do git-sync (padrão /opt/airflow/git/current)
#   ATLAS_CLONE_WAIT_SECONDS    tempo máximo de espera (padrão 900)
set -euo pipefail

DIR="${ATLAS_DAGS_LINK:-/opt/airflow/git/current}/airflow/dags"
LIMITE="${ATLAS_CLONE_WAIT_SECONDS:-900}"
ESPERADO=0

while [ ! -d "$DIR" ]; do
  if [ "$ESPERADO" -ge "$LIMITE" ]; then
    echo "aguardar-clone: o git-sync não entregou $DIR em ${LIMITE}s (confira o serviço git-sync, a branch e o acesso ao GitHub)" >&2
    exit 1
  fi
  echo "aguardar-clone: esperando o primeiro clone do git-sync em $DIR (${ESPERADO}s)"
  sleep 5
  ESPERADO=$((ESPERADO + 5))
done
echo "aguardar-clone: clone encontrado em $DIR"
