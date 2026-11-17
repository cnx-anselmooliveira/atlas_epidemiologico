# Airflow do Atlas (atlas-epidemiologia-airflow). Tags: dev, hml, X.Y.
# Contexto de build = raiz do repositório (precisa de ml/ e airflow/):
#   docker build -f airflow/Dockerfile -t atlas-epidemiologia-airflow:local \
#     --build-arg ATLAS_GIT_SHA=$(git rev-parse HEAD) .
# Rede com inspeção TLS: --secret id=extra_ca,src=<CA>

FROM apache/airflow:3.3.2-python3.12

USER root
COPY --from=ghcr.io/astral-sh/uv:0.10.12 /uv /usr/local/bin/uv

# atlas_ml num venv separado: as restrições de versão do Airflow não colidem com
# as do MLflow/scikit-learn. Só o CLI `atlas-ml` vai para o PATH. Inclui o grupo
# `models` (CatBoost, PyTorch CPU, PyMC/nutpie, Chronos) para a DAG de previsão.
ENV UV_PROJECT_ENVIRONMENT=/opt/atlas-ml \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1
COPY ml/pyproject.toml ml/uv.lock ml/README.md /opt/atlas-ml-src/
# cache do uv montado no build (fora das camadas: sem ele, os wheels baixados dobram o tamanho)
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=secret,id=extra_ca,required=false \
    if [ -s /run/secrets/extra_ca ]; then export SSL_CERT_FILE=/run/secrets/extra_ca; fi; \
    cd /opt/atlas-ml-src && uv sync --frozen --no-dev --extra models --no-install-project --python /usr/python/bin/python3.12
COPY ml/src /opt/atlas-ml-src/src
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=secret,id=extra_ca,required=false \
    if [ -s /run/secrets/extra_ca ]; then export SSL_CERT_FILE=/run/secrets/extra_ca; fi; \
    cd /opt/atlas-ml-src && uv sync --frozen --no-dev --extra models --python /usr/python/bin/python3.12 \
    && ln -s /opt/atlas-ml/bin/atlas-ml /usr/local/bin/atlas-ml \
    && chown -R airflow:0 /opt/atlas-ml-src
# O venv fica de root (leitura basta; bytecode já compilado). Um `chown -R` aqui, numa
# camada separada da instalação, duplicaria os ~2,5 GB do venv na imagem.

# dbt (projeto airflow/dags/utfpr_dengue) também num venv próprio, travado pelo uv.lock
# do projeto. O CLI `dbt` vai para o PATH; o projeto em si chega com as DAGs.
COPY airflow/dags/utfpr_dengue/pyproject.toml airflow/dags/utfpr_dengue/uv.lock /opt/dbt-src/
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=secret,id=extra_ca,required=false \
    if [ -s /run/secrets/extra_ca ]; then export SSL_CERT_FILE=/run/secrets/extra_ca; fi; \
    cd /opt/dbt-src && UV_PROJECT_ENVIRONMENT=/opt/dbt uv sync --frozen --no-dev --python /usr/python/bin/python3.12 \
    && ln -s /opt/dbt/bin/dbt /usr/local/bin/dbt \
    && chown -R airflow:0 /opt/dbt

# Configuração comum a todos os ambientes (o específico de cada um vem do compose/stack).
# DAGBAG_IMPORT_TIMEOUT=120 e DAG_FILE_PROCESSOR_TIMEOUT=180 (este precisa ser maior): as DAGs
# do Cosmos rodam `dbt ls` na leitura (sem cache, ~60 s); depois o cache do Cosmos evita repetir
ENV AIRFLOW__CORE__EXECUTOR=LocalExecutor \
    AIRFLOW__CORE__PARALLELISM=4 \
    AIRFLOW__CORE__MAX_ACTIVE_TASKS_PER_DAG=4 \
    AIRFLOW__CORE__LOAD_EXAMPLES=False \
    AIRFLOW__CORE__DAGS_ARE_PAUSED_AT_CREATION=True \
    AIRFLOW__SCHEDULER__ENABLE_HEALTH_CHECK=True \
    AIRFLOW__CORE__DAGBAG_IMPORT_TIMEOUT=120 \
    AIRFLOW__DAG_PROCESSOR__DAG_FILE_PROCESSOR_TIMEOUT=180 \
    MLFLOW_DISABLE_AGENT_HINT=1 \
    DBT_PARTIAL_PARSE=false \
    DBT_SEND_ANONYMOUS_USAGE_STATS=false \
    HF_HOME=/opt/airflow/hf-cache \
    NUMBA_CACHE_DIR=/tmp/numba-cache

# Diretório compartilhado entre componentes (ex.: senha do Simple Auth Manager em dev) e
# cache do Hugging Face (checkpoint do Chronos)
RUN mkdir -p /opt/airflow/shared /opt/airflow/hf-cache \
    && chown airflow:0 /opt/airflow/shared /opt/airflow/hf-cache \
    && chmod 2770 /opt/airflow/shared /opt/airflow/hf-cache

# Cosmos (DAGs do dbt e plugin de dbt docs) precisa estar no Python do próprio Airflow;
# fixar apache-airflow impede o pip de trocar a versão do Airflow. O dbt segue em /opt/dbt.
USER airflow
RUN --mount=type=secret,id=extra_ca,required=false,uid=50000 \
    if [ -s /run/secrets/extra_ca ]; then export PIP_CERT=/run/secrets/extra_ca; fi; \
    pip install --no-cache-dir "apache-airflow==${AIRFLOW_VERSION}" "astronomer-cosmos==1.16.0"
USER root
COPY --chown=airflow:0 airflow/dags /opt/airflow/dags
COPY --chown=airflow:0 --chmod=0755 airflow/config/init.sh /opt/atlas/init.sh
COPY --chown=airflow:0 airflow/tests /opt/atlas/tests

ARG ATLAS_GIT_SHA
ARG ATLAS_IMAGE_TAG=local
ENV ATLAS_GIT_SHA=${ATLAS_GIT_SHA} \
    ATLAS_IMAGE_TAG=${ATLAS_IMAGE_TAG}

USER airflow
