# syntax=docker/dockerfile:1

# `python:3.13-slim` y no Alpine: numpy, scipy y scikit-learn publican ruedas
# manylinux (glibc) para amd64 y arm64, y no para musl. En Alpine se compilarian
# desde el codigo fuente en cada construccion. Vease ADR-022.

# ---------------------------------------------------------------------------
# Etapa 1 — entorno virtual con las dependencias de produccion y el servicio
# ---------------------------------------------------------------------------
FROM python:3.13.15-slim AS build

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN pip install --no-cache-dir uv==0.12.21

WORKDIR /app

# Primero solo las dependencias: esta capa se reutiliza mientras no cambie el lockfile.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY README.md ./
COPY src ./src
COPY docs/diccionario/semilla-v1.json ./docs/diccionario/semilla-v1.json
# `--no-editable`: el servicio se instala dentro del entorno, sin depender de `src`.
RUN uv sync --frozen --no-dev --no-editable

# ---------------------------------------------------------------------------
# Etapa 2 — imagen final
# ---------------------------------------------------------------------------
FROM python:3.13.15-slim AS runtime

ENV APP_ENV=production \
    PORT=3011 \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Usuario sin privilegios, como `node` en las imagenes NestJS.
RUN groupadd --system --gid 1000 chatbot \
    && useradd --system --uid 1000 --gid chatbot --no-create-home chatbot

WORKDIR /app

COPY --from=build --chown=chatbot:chatbot /app/.venv /app/.venv
COPY --from=build --chown=chatbot:chatbot /app/docs /app/docs

USER chatbot

EXPOSE 3011

HEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=3 \
  CMD ["python", "-c", "import os,sys,urllib.request;sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','3011')+'/api/health/ready',timeout=2).status==200 else 1)"]

CMD ["python", "-m", "chatbot.main"]
