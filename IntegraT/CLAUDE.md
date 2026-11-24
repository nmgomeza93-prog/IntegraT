# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Qué es IntegraT

App para que emprendedores y pequeños negocios **sin conocimientos de tecnología, contabilidad ni finanzas** administren su negocio desde el celular.
La app hace el trabajo administrativo: contabilidad automática en partida doble, costos, precios sugeridos, caja y asesor financiero. Así el usuario se enfoca en vender.
Contexto inicial: Guatemala (IVA, SAT, FEL), con lo fiscal configurable por país.
Tipos de negocio del MVP: **ventas en línea** y **restaurantes**. Se agregan otros tipos por configuración, no duplicando código.

**Estado actual: Fase 0 cerrada (análisis y propuesta aprobados). Todavía no hay código de la aplicación.**
Antes de trabajar, lee `docs/DECISIONES.md` y el documento de `docs/` que corresponda a la tarea.

## Reglas de seguridad (obligatorias)

1. **La v1 es solo de referencia.** `C:\APP-Emprende\Emprende` (R/Shiny + MySQL `erp_pyme_gt`):
   - No la modifiques, no la muevas, no borres nada ahí y no ejecutes sus scripts.
   - No te conectes a su base de datos ni reutilices sus credenciales, `.Renviron`, `config.yml` o archivos de datos.
   - IntegraT es un producto nuevo inspirado en ella, no una migración ni una copia de código.
2. **Credenciales solo en `.env`** (`DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, R2, Anthropic, etc.):
   - **Nunca** escribas valores de credenciales en código, documentos, commits, tests, logs ni mensajes.
   - No leas ni muestres el contenido de `.env`.
   - `.env` está en `.gitignore`; `.env.example` lista solo los nombres, sin valores.
   - Los logs registran configuración enmascarada.
3. **Base de datos: solo `integrat`** (MySQL 9.x en Railway, decisión D-19).
   El usuario de `.env` tiene privilegios globales en ese servidor (D-20, riesgo aceptado). Por eso:
   - Toda conexión debe abrir **solo** la base `integrat`.
   - Nunca se ejecutan sentencias contra otras bases (por ejemplo `cam_talent_hub_gestion_cl0` o `erp_pyme_gt`).
   - Nunca se crean ni modifican usuarios ni privilegios del servidor sin una orden explícita.
4. **Aislamiento por negocio.** Toda tabla de datos de un negocio lleva `negocio_id`.
   MySQL no tiene RLS, así que la API filtra **siempre** por el `negocio_id` del token, mediante una capa de repositorio común y no con SQL suelto.
   Pruebas automáticas verifican que un negocio no ve los datos de otro.
   El `negocio_id` sale **del token** del usuario, nunca de la configuración ni de parámetros del cliente (fue un bug grave de la v1).
5. **Fotos de facturas solo en el bucket R2 privado**, con acceso mediante URLs prefirmadas de corta duración. El bucket público es solo para el catálogo.
6. **La app Shiny no lleva secretos.** Solo necesita `API_BASE_URL`. No la conectes directamente a PostgreSQL.
7. **IA para facturas: siempre opcional y bajo control del usuario.** Nunca llames al modelo sin que se cumplan estas condiciones:
   - La IA está activada para el negocio.
   - El usuario confirmó el precio mostrado.
   - Hay saldo y no se supera el límite mensual.

## Arquitectura (decisión D-01/D-02)

- `app/`: **Shiny para R** (bslib, mobile-first). Interfaz + analítica en R (paquete `analitica/` = `integrat.analitica`): punto de equilibrio, proyecciones, informe del mes y consejos.
- `api/`: **FastAPI (Python)** + worker. Único dueño de la BD y de R2. Contiene:
  - Comandos de negocio.
  - Inventario y costo promedio ponderado.
  - **Precio sugerido**.
  - **Motor contable**.
  - Fiscal y FEL.
  - IA de facturas.
  - Integraciones y automatizaciones.
- **Frontera R ↔ Python** (`docs/PROPUESTA_ARQUITECTURA.md` §3):
  - R nunca escribe en la BD ni en R2; llama a la API (OpenAPI `/v1`).
  - R lee datos solo mediante los endpoints de *datasets* de la API.
  - Cada fórmula tiene un solo dueño. No la reimplementes en el otro lenguaje.
  - El dinero viaja como texto decimal, nunca como float.
- Comandos de la API: atómicos (una transacción: operación + inventario + asiento), con `Idempotency-Key` y outbox para eventos y webhooks.
- La BD no contiene lógica de negocio. Las funciones y procedimientos (`fn_`, `sp_`) son solo para integridad, RLS, ETL y lecturas de reporte (lección de la v1).

## Base de datos (`docs/MODELO_DATOS.md`)

- **MySQL 9.x, base `integrat`** (D-19). Partes de `MODELO_DATOS.md` asumían PostgreSQL y se adaptan en el paso 2 de la Fase 1.
  Los "esquemas" lógicos (`core`, `cat`, `ops`, `cont`, `fiscal`, `ia`, `integ`, `dw`, `rpt`, `audit`) se mantienen como **prefijo de tabla** dentro de la única base `integrat`.
- Convenciones:
  - Español, snake_case, tablas en singular, PK `id uuid` (UUIDv7), FK `<tabla>_id`.
  - Prefijos: `cat_` (catálogos globales), `cfg_` (configuración), `dim_`/`fact_` (estrella), `vw_`/`mv_`, `fn_`, `sp_`, `trg_`, `ix_`/`uq_`/`fk_`/`ck_`.
  - Sin ENUM nativos.
  - Columnas de auditoría, `eliminado_en` (borrado lógico) y `version` en las tablas de negocio.
- Asientos, movimientos de inventario, de saldo IA y documentos fiscales son **inmutables**: se corrigen con un reverso.
  La API valida que cada asiento cuadre dentro de la transacción (MySQL no tiene restricciones diferidas).
- Migraciones con Alembic, escritas a mano con nombres explícitos. Nunca edites una migración ya aplicada.
- La implementación física en MySQL (prefijos, UUIDv7 `BINARY(16)`, `DATETIME(6)` UTC, aislamiento en la API) está en `docs/CONVENCIONES_BD.md`, que manda sobre `MODELO_DATOS.md`.

## Contabilidad y fiscal

- El motor contable usa reglas configurables (`cont.cfg_regla_contable`): evento → conceptos → **roles de cuenta** → cuentas del plan del negocio.
  **No uses códigos de cuenta fijos en el código.**
- Libros por negocio. El régimen fiscal es del **titular (NIT)**. Los libros y declaraciones se consolidan por titular.
- Todo lo contable y fiscal de Guatemala está **pendiente de validación por un contador**: `docs/REVISION_CONTADOR.md`.
  No presentes tasas, límites ni artículos como definitivos; están marcados [verificar].
- FEL no se emite en el MVP, pero los datos requeridos se capturan desde ya (`docs/PLAN_FEL.md`).

## Producto y UX (`docs/DISENO_UX.md`)

- Trato de **tú**. Lenguaje cotidiano: "Lo que vendiste", "Lo que gastaste", "Lo que te queda". Sin jerga contable en la interfaz.
- Una pantalla, una tarea; máximo 3 toques para las acciones frecuentes; navegación inferior de 5 secciones; botón primario único.
- Mobile-first (360–390 px), objetivos táctiles de 48 px o más, sin tablas en el celular, hojas inferiores en lugar de modales.
- Siempre en línea (no hay modo offline), pero el estado importante vive en el servidor (borradores).
- Compras en 3 modos que terminan en la misma pantalla de revisión: a mano (guiado), plantilla simple (gratis) y foto + IA (opcional, con costo visible).
- Color de marca azul índigo `#3346D3`. Verde, ámbar y rojo se reservan para estados.

## Hospedaje (`docs/CONFIGURACION_SERVIDOR.md`)

- Piloto: Shiny en **shinyapps.io**; API, worker y PostgreSQL en el servidor propio. Solo el puerto 443 (API) queda expuesto; PostgreSQL no se expone.
- Fotos públicas por `r2.dev` en el piloto (dominio propio en producción). La BD guarda llaves, no URLs.
- Todo en contenedores y configurado por variables de entorno, listo para migrar a Azure (Container Apps + PostgreSQL Flexible Server + Key Vault).

## Comandos

El repo de Git está en `C:\APP-IntegraT` (remoto en GitHub). El proyecto vive en la subcarpeta `IntegraT/`.
`uv` y `Rscript` no están en el PATH: usa `python -m uv` y `"C:/Program Files/R/R-4.3.0/bin/Rscript.exe"`.

```bash
# Base MySQL local para pruebas (Docker; credenciales TEST_DB_* en .env)
docker compose -f infra/docker-compose.yml --env-file .env up -d --wait mysql-test

# API (desde api/)
python -m uv sync
python -m uv run pytest                                  # todas las pruebas (usan integrat_test)
python -m uv run pytest tests/test_aislamiento.py::test_cada_negocio_ve_solo_lo_suyo  # una sola
python -m uv run ruff check .
python -m uv run uvicorn integrat.main:app --reload      # API en http://localhost:8000 (/v1/salud, /docs)
python -m uv run alembic upgrade head                    # migra la base real (DB_*)
python -m uv run python -m integrat.db.semillas          # catálogos idempotentes

# App y analítica (R, desde la raíz IntegraT/)
Rscript -e "shiny::runApp('app')"
Rscript -e "testthat::test_dir('app/tests/testthat')"
Rscript -e "testthat::test_local('analitica')"
```

API en contenedor (desde la raíz `IntegraT/`): `docker compose -f infra/docker-compose.yml --env-file .env --profile api up -d --build api`.
La imagen nunca incluye `.env` (está en `.dockerignore`); recibe la configuración por variables de entorno.

Logs: `integrat/logs.py` enmascara secretos. Los errores de la BD se registran solo por su tipo, nunca con el mensaje del driver (incluye usuario y host).

Convenciones de BD en MySQL: `docs/CONVENCIONES_BD.md`.
Cambio de esquema = nueva migración en `api/migrations/versions/` + actualizar `api/src/integrat/db/tablas.py`. La prueba de comparación detecta cualquier diferencia entre ambos.

## Documentos de referencia

`docs/DECISIONES.md` · `docs/VISION_PRODUCTO.md` · `docs/PROPUESTA_ARQUITECTURA.md` · `docs/MODELO_DATOS.md` · `docs/DISENO_UX.md` ·
`docs/CONFIGURACION_SERVIDOR.md` · `docs/PRUEBA_MODELOS_IA.md` · `docs/REVISION_CONTADOR.md` · `docs/PLAN_FEL.md` · `docs/ANALISIS_V1.md`
