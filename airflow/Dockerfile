# Airflow do Atlas (atlas-epidemiologia-airflow). Tags: dev, hml, X.Y.
# Contexto de build = raiz do repositório (precisa de ml/ e airflow/):
#   docker build -f airflow/Dockerfile -t atlas-epidemiologia-airflow:local \
#     --build-arg ATLAS_GIT_SHA=$(git rev-parse HEAD) .
# Rede com inspeção TLS: --secret id=extra_ca,src=<CA>

FROM apache/airflow:3.3.2-python3.12

USER root
COPY --from=ghcr.io/astral-sh/uv:0.10.12 /uv /usr/local/bin/uv

# atlas_ml num venv separado: as restrições de versão do Airflow não colidem com
# as do MLflow/scikit-learn. Só o CLI `atlas-ml` vai para o PATH.
ENV UV_PROJECT_ENVIRONMENT=/opt/atlas-ml \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1
COPY ml/pyproject.toml ml/uv.lock ml/README.md /opt/atlas-ml-src/
RUN --mount=type=secret,id=extra_ca,required=false \
    if [ -s /run/secrets/extra_ca ]; then export SSL_CERT_FILE=/run/secrets/extra_ca; fi; \
    cd /opt/atlas-ml-src && uv sync --frozen --no-dev --no-install-project --python /usr/python/bin/python3.12
COPY ml/src /opt/atlas-ml-src/src
RUN --mount=type=secret,id=extra_ca,required=false \
    if [ -s /run/secrets/extra_ca ]; then export SSL_CERT_FILE=/run/secrets/extra_ca; fi; \
    cd /opt/atlas-ml-src && uv sync --frozen --no-dev --python /usr/python/bin/python3.12 \
    && ln -s /opt/atlas-ml/bin/atlas-ml /usr/local/bin/atlas-ml \
    && chown -R airflow:0 /opt/atlas-ml /opt/atlas-ml-src

# Configuração comum a todos os ambientes (o específico de cada um vem do compose/stack)
ENV AIRFLOW__CORE__EXECUTOR=LocalExecutor \
    AIRFLOW__CORE__PARALLELISM=4 \
    AIRFLOW__CORE__MAX_ACTIVE_TASKS_PER_DAG=4 \
    AIRFLOW__CORE__LOAD_EXAMPLES=False \
    AIRFLOW__CORE__DAGS_ARE_PAUSED_AT_CREATION=True \
    AIRFLOW__SCHEDULER__ENABLE_HEALTH_CHECK=True \
    MLFLOW_DISABLE_AGENT_HINT=1

COPY --chown=airflow:0 airflow/dags /opt/airflow/dags
COPY --chown=airflow:0 --chmod=0755 airflow/config/init.sh /opt/atlas/init.sh
COPY --chown=airflow:0 airflow/tests /opt/atlas/tests

ARG ATLAS_GIT_SHA
ARG ATLAS_IMAGE_TAG=local
ENV ATLAS_GIT_SHA=${ATLAS_GIT_SHA} \
    ATLAS_IMAGE_TAG=${ATLAS_IMAGE_TAG}

USER airflow
