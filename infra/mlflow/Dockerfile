# Servidor MLflow do Atlas (atlas-epidemiologia-mlflow). Tags: dev, hml, X.Y.
# Metadados no Postgres; artefatos no GCS servidos pelo próprio servidor (--serve-artifacts).
# Rede com inspeção TLS:  docker build --secret id=extra_ca,src=<CA> …

FROM python:3.12-slim
ARG ATLAS_GIT_SHA
ARG ATLAS_IMAGE_TAG=local
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MLFLOW_DISABLE_AGENT_HINT=1 \
    ATLAS_GIT_SHA=${ATLAS_GIT_SHA} \
    ATLAS_IMAGE_TAG=${ATLAS_IMAGE_TAG}

COPY requirements.txt /tmp/requirements.txt
RUN --mount=type=secret,id=extra_ca,required=false \
    if [ -s /run/secrets/extra_ca ]; then export PIP_CERT=/run/secrets/extra_ca; fi; \
    pip install -r /tmp/requirements.txt && rm /tmp/requirements.txt

RUN useradd --create-home --uid 1000 mlflow
COPY --chmod=0755 entrypoint.sh /usr/local/bin/mlflow-entrypoint
COPY basic_auth.ini.tmpl /etc/mlflow/basic_auth.ini.tmpl
USER mlflow
WORKDIR /home/mlflow
# Destino local de artefatos (dev sem bucket); existe na imagem para o volume herdar o dono
RUN mkdir -p /home/mlflow/mlartifacts
EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:5000/health', timeout=4).status == 200 else 1)"

ENTRYPOINT ["mlflow-entrypoint"]
