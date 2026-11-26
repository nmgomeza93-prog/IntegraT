# IntegraT

App para que emprendedores y pequeños negocios administren su negocio desde el celular:
ventas, caja, compras, inventario, costos, precios sugeridos, contabilidad automática y asesor financiero.
Tú vendes; IntegraT hace las cuentas.

> Estado: **Fase 1 — Fundaciones** (ver `docs/PLAN_FASE1.md`). Decisiones en `docs/DECISIONES.md`.

## Estructura

| Carpeta | Qué contiene | Tecnología |
|---|---|---|
| `app/` | Interfaz (mobile-first) | Shiny para R + bslib |
| `analitica/` | Paquete `integrat.analitica`: punto de equilibrio, proyecciones, informes | R |
| `api/` | API de dominio, motor contable, R2, IA de facturas, integraciones | Python 3.12 + FastAPI (uv) |
| `db/` | Semillas de catálogos y plantillas (plan de cuentas, reglas, tipos de negocio) | YAML |
| `infra/` | Docker, despliegue | — |
| `docs/` | Visión, arquitectura, modelo de datos, UX, decisiones | Markdown |

Frontera R ↔ Python: Python es dueño de los datos y las reglas de negocio; R, de la interfaz y el análisis.
R nunca escribe en la base de datos (`docs/PROPUESTA_ARQUITECTURA.md` §3).

## Requisitos

- R 4.3 + RStudio (el proyecto usa `renv`; `.Rprofile` lo activa solo).
- Python 3.12 y [`uv`](https://docs.astral.sh/uv/) (`pip install --user uv`; si `uv` no está en el PATH, usa `python -m uv`).
- Docker Desktop (para la base MySQL local de pruebas, desde el paso 2).

## Configuración

```bash
cp .env.example .env    # y completa los valores — .env NUNCA se sube a Git
```

## Arranque rápido

```bash
# API (Python)
cd api
python -m uv sync
python -m uv run pytest

# App (R) — desde la raíz del proyecto
Rscript -e "renv::restore()"
Rscript -e "shiny::runApp('app')"
Rscript -e "testthat::test_dir('app/tests/testthat')"
```

## Con Docker (todo junto, sin instalar R ni Python)

Solo necesitas Docker Desktop. Levanta MySQL local, migraciones, API y app con recarga automática:

```bash
# 1. En tu .env, agrega (valores tuyos, solo para tu PC; ver .env.example):
#    LOCAL_DB_PASSWORD=...   LOCAL_DB_ROOT_PASSWORD=...   API_JWT_SECRET=...
# 2. Desde la raíz IntegraT/:
docker compose up --build      # la primera vez tarda (descarga R y los paquetes)
```

- App: <http://localhost:3838> · API: <http://localhost:8000/docs>
- Guardas un archivo de `api/src` → la API se reinicia sola. Guardas uno de `app/` → Shiny recarga
  la página. Cambios en `analitica/R` o en dependencias: `docker compose restart app` /
  `docker compose up --build`.
- Cada arranque corre las migraciones y los catálogos (`api/migrar.sh`) antes de la API.
- `docker compose down` apaga y **conserva** los datos; `docker compose down -v` los borra.
- Los contenedores nunca reciben la base real: usan su propio MySQL 8.4 (la misma versión que Azure).
- Otro puerto o abrirla desde el celular: `API_PUERTO`, `APP_PUERTO`, `APP_IP=0.0.0.0` en `.env`.

## Despliegue en Azure

Container Apps (app pública + API interna), MySQL Flexible Server y Key Vault.
Receta completa: [`infra/azure/README.md`](infra/azure/README.md).

```bash
export SUFIJO=gt01
bash infra/azure/crear.sh      # una vez: crea la infraestructura
bash infra/azure/publicar.sh   # cada versión: imágenes, migraciones, API y app
```
