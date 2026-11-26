#!/bin/sh
# Migraciones y catálogos de IntegraT. Corre dentro de la imagen de la API, ANTES de publicar
# una versión (Compose: servicio "migrar"; Azure: Container Apps Job "integrat-migrar").
#
# Usa el usuario dueño del esquema (DB_MIGRATIONS_USER/PASSWORD) si está definido; si no, el
# DB_USER normal (en local con Docker es el mismo usuario). Ambos pasos son idempotentes.
set -eu
cd /app/api

if [ -n "${DB_MIGRATIONS_USER:-}" ]; then
  export DB_USER="$DB_MIGRATIONS_USER"
  export DB_PASSWORD="${DB_MIGRATIONS_PASSWORD:?Falta DB_MIGRATIONS_PASSWORD}"
fi

echo "Migraciones: alembic upgrade head"
alembic upgrade head
echo "Catálogos: semillas"
python -m integrat.db.semillas
echo "Listo."
