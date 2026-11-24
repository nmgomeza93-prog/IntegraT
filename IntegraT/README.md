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
