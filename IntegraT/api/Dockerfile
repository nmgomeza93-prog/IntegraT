# Imagen de la API de IntegraT (portable: servidor propio hoy, Azure Container Apps después).
# Construir (desde la raíz IntegraT/):  docker build -t integrat-api -f api/Dockerfile .
# La configuración entra SOLO por variables de entorno (nunca se copia .env a la imagen).
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.9 /uv /usr/local/bin/uv

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app/api

# Dependencias primero (mejor caché de capas)
COPY api/pyproject.toml api/uv.lock api/README.md ./
RUN uv sync --frozen --no-dev --no-install-project

# Código, migraciones y semillas
COPY api/src ./src
COPY api/alembic.ini ./
COPY api/migrations ./migrations
COPY db /app/db
RUN uv sync --frozen --no-dev

RUN useradd --create-home --uid 10001 integrat && chown -R integrat /app
USER integrat

EXPOSE 8000
CMD ["uv", "run", "--no-sync", "uvicorn", "integrat.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
