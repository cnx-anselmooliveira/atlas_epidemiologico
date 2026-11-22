# Imagem de treino do Atlas (atlas-epidemiologia-ml). Tags: dev, hml, X.Y.
# Build:  docker build -t atlas-epidemiologia-ml:local --build-arg ATLAS_GIT_SHA=$(git rev-parse HEAD) ml/
# Rede com inspeção TLS:  adicione --secret id=extra_ca,src=<caminho da CA>
# Modelos de previsão (CatBoost, PyTorch CPU, PyMC, Chronos): --build-arg ATLAS_ML_EXTRAS=models

FROM python:3.12-slim AS build
# Grupo opcional do pyproject (vazio = imagem leve, só o núcleo do atlas_ml)
ARG ATLAS_ML_EXTRAS=""
COPY --from=ghcr.io/astral-sh/uv:0.10.12 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=secret,id=extra_ca,required=false \
    if [ -s /run/secrets/extra_ca ]; then export SSL_CERT_FILE=/run/secrets/extra_ca; fi; \
    uv sync --frozen --no-dev --no-install-project ${ATLAS_ML_EXTRAS:+--extra $ATLAS_ML_EXTRAS}
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=secret,id=extra_ca,required=false \
    if [ -s /run/secrets/extra_ca ]; then export SSL_CERT_FILE=/run/secrets/extra_ca; fi; \
    uv sync --frozen --no-dev ${ATLAS_ML_EXTRAS:+--extra $ATLAS_ML_EXTRAS}

FROM python:3.12-slim AS base
# Sem valor padrão de commit: sem ATLAS_GIT_SHA o treino falha (spec ml-model-lifecycle)
ARG ATLAS_GIT_SHA
ARG ATLAS_IMAGE_TAG=local
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    MLFLOW_DISABLE_AGENT_HINT=1 \
    ATLAS_GIT_SHA=${ATLAS_GIT_SHA} \
    ATLAS_IMAGE_TAG=${ATLAS_IMAGE_TAG}
RUN useradd --create-home --uid 1000 atlas
COPY --from=build /app /app

# JupyterLab de exploração: no compose de dev (profile "notebook") e no stack de hml (atlas-epidemiologia-ml-notebook).
# Mesmas versões do Airflow: o venv sai do mesmo ml/uv.lock. A senha (hash, por Docker secret) ou o token de dev
# vêm de /etc/jupyter/jupyter_server_config.py: sem uma das duas coisas o servidor não sobe.
FROM base AS notebook
COPY --from=ghcr.io/astral-sh/uv:0.10.12 /uv /usr/local/bin/uv
RUN --mount=type=secret,id=extra_ca,required=false \
    if [ -s /run/secrets/extra_ca ]; then export SSL_CERT_FILE=/run/secrets/extra_ca; fi; \
    uv pip install --python /app/.venv/bin/python --no-cache "jupyterlab>=4.4,<5" matplotlib
COPY docker/jupyter_server_config.py /etc/jupyter/jupyter_server_config.py
COPY docker/semear_notebooks.py /opt/atlas/semear_notebooks.py
# cópia dos notebooks do repositório: semente do volume de trabalho quando não há clone do git-sync
COPY notebooks /opt/atlas/notebooks
# o sistema de arquivos raiz é somente leitura no stack: o que o Jupyter e as bibliotecas gravam vai para /tmp
ENV JUPYTER_RUNTIME_DIR=/tmp/jupyter/runtime \
    JUPYTER_DATA_DIR=/tmp/jupyter/data \
    IPYTHONDIR=/tmp/ipython \
    MPLCONFIGDIR=/tmp/matplotlib \
    NUMBA_CACHE_DIR=/tmp/numba \
    JUPYTER_ROOT_DIR=/home/atlas/work
# um volume novo herda o dono desta pasta: tem de ser o usuário do processo, senão o Jupyter não grava nada
RUN mkdir -p /home/atlas/work && chown atlas:atlas /home/atlas/work
USER atlas
WORKDIR /home/atlas/work
EXPOSE 8888
ENTRYPOINT []
# semeia o volume de trabalho (só se vazio) e sobe o servidor; a configuração vem de /etc/jupyter
CMD ["bash", "-c", "python /opt/atlas/semear_notebooks.py && exec jupyter lab --ip=0.0.0.0 --port=8888 --no-browser"]

# Imagem publicada (último estágio = alvo padrão do build)
FROM base AS runtime
USER atlas
WORKDIR /home/atlas
ENTRYPOINT ["atlas-ml"]
CMD ["--help"]
