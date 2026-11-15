# Imagem de treino do Atlas (atlas-epidemiologia-ml). Tags: dev, hml, X.Y.
# Build:  docker build -t atlas-epidemiologia-ml:local --build-arg ATLAS_GIT_SHA=$(git rev-parse HEAD) ml/
# Rede com inspeção TLS:  adicione --secret id=extra_ca,src=<caminho da CA>

FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.10.12 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=secret,id=extra_ca,required=false \
    if [ -s /run/secrets/extra_ca ]; then export SSL_CERT_FILE=/run/secrets/extra_ca; fi; \
    uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=secret,id=extra_ca,required=false \
    if [ -s /run/secrets/extra_ca ]; then export SSL_CERT_FILE=/run/secrets/extra_ca; fi; \
    uv sync --frozen --no-dev

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

# JupyterLab para exploração no compose de dev (profile "notebook"); não é publicada.
FROM base AS notebook
COPY --from=ghcr.io/astral-sh/uv:0.10.12 /uv /usr/local/bin/uv
RUN --mount=type=secret,id=extra_ca,required=false \
    if [ -s /run/secrets/extra_ca ]; then export SSL_CERT_FILE=/run/secrets/extra_ca; fi; \
    uv pip install --python /app/.venv/bin/python --no-cache "jupyterlab>=4.4,<5" matplotlib
USER atlas
WORKDIR /home/atlas/work
EXPOSE 8888
ENTRYPOINT []
CMD ["jupyter", "lab", "--ip=0.0.0.0", "--port=8888", "--no-browser", "--ServerApp.root_dir=/home/atlas/work"]

# Imagem publicada (último estágio = alvo padrão do build)
FROM base AS runtime
USER atlas
WORKDIR /home/atlas
ENTRYPOINT ["atlas-ml"]
CMD ["--help"]
