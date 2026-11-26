# Imagen de la API de IntegraT (local con Docker Compose y Azure Container Apps).
# Construir (desde la raíz IntegraT/):
#   producción:  docker build -t integrat-api -f api/Dockerfile .
#   desarrollo:  docker build -t integrat-api:dev --target dev -f api/Dockerfile .
# La configuración entra SOLO por variables de entorno (nunca se copia .env a la imagen).

# ---------- base: Python y variables comunes ----------
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/api/.venv/bin:$PATH"
WORKDIR /app/api

# ---------- builder: instala dependencias con uv en /app/api/.venv ----------
FROM base AS builder
COPY --from=ghcr.io/astral-sh/uv:0.13.9 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
# Dependencias primero (mejor caché de capas)
COPY api/pyproject.toml api/uv.lock api/README.md ./
RUN uv sync --frozen --no-dev --no-install-project
# El proyecto queda instalado en modo editable apuntando a /app/api/src: por eso src vive en la
# misma ruta en todas las etapas (config.py ubica db/semillas a partir de esa ruta).
COPY api/src ./src
RUN uv sync --frozen --no-dev

# ---------- dev: con pytest/ruff y recarga automática (el código se monta desde tu PC) ----------
FROM builder AS dev
RUN uv sync --frozen
COPY api/alembic.ini ./
COPY api/migrations ./migrations
COPY api/migrar.sh ./
COPY db /app/db
EXPOSE 8000
# WATCHFILES_FORCE_POLLING: en Windows/Mac los cambios en carpetas montadas no siempre avisan.
ENV WATCHFILES_FORCE_POLLING=true
CMD ["uvicorn", "integrat.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--reload-dir", "/app/api/src"]

# ---------- prod: solo Python y el entorno ya instalado (sin uv ni herramientas de desarrollo) ----------
FROM base AS prod
RUN useradd --create-home --uid 10001 integrat
COPY --from=builder --chown=integrat /app/api/.venv ./.venv
COPY --chown=integrat api/src ./src
COPY --chown=integrat api/alembic.ini api/migrar.sh ./
COPY --chown=integrat api/migrations ./migrations
COPY --chown=integrat db /app/db
USER integrat

# Azure (y Railway) inyectan el puerto en $PORT; sin esa variable escucha en 8000.
# --proxy-headers: la IP real del cliente viene en X-Forwarded-For; uvicorn solo la acepta de las
# IP listadas en FORWARDED_ALLOW_IPS (ver infra/azure/README.md).
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\", \"8000\")}/v1/salud', timeout=4)"
CMD ["sh", "-c", "exec uvicorn integrat.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers"]
