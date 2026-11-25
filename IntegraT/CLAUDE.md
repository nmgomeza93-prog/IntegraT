# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Qué es IntegraT

App para que emprendedores y pequeños negocios **sin conocimientos de tecnología, contabilidad ni finanzas** administren su negocio desde el celular.
La app hace el trabajo administrativo: contabilidad automática en partida doble, costos, precios sugeridos, caja y asesor financiero. Así el usuario se enfoca en vender.
Contexto inicial: Guatemala (IVA, SAT, FEL), con lo fiscal configurable por país.
Tipos de negocio del MVP: **ventas en línea** y **restaurantes**. Se agregan otros tipos por configuración, no duplicando código.

**Estado actual: Fase 1 (fundaciones) en curso. Hecho: repo, base `integrat`, API mínima, app Shiny con diseño y navegación, la API de cuentas y negocios (registro, login, onboarding) el catálogo de productos y platillos con categorías (`docs/PLAN_CATALOGO.md`), las ventas rápidas con anulación (`docs/PLAN_VENTAS.md`), los gastos (`docs/PLAN_GASTOS.md`), el inventario con recetas (`docs/PLAN_INVENTARIO.md`), las compras a mano (`docs/PLAN_COMPRAS.md`) el motor contable con el resumen del mes (`docs/PLAN_CONTABILIDAD.md`) y la caja del día con el dinero del dueño (`docs/PLAN_CAJA.md`). Plan en `docs/PLAN_FASE1.md`.**
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
3. **Base de datos: solo `integrat`** (MySQL 9.x, decisión D-19; hoy en Railway, el piloto irá a Azure por D-23).
   El usuario de `.env` tiene privilegios globales en ese servidor (D-20, riesgo aceptado). Por eso:
   - Toda conexión debe abrir **solo** la base `integrat`.
   - Nunca se ejecutan sentencias contra otras bases (por ejemplo `cam_talent_hub_gestion_cl0` o `erp_pyme_gt`).
   - Nunca se crean ni modifican usuarios ni privilegios del servidor sin una orden explícita.
4. **Aislamiento por negocio.** Toda tabla de datos de un negocio lleva `negocio_id`.
   MySQL no tiene RLS, así que la API filtra **siempre** por el `negocio_id` del token, mediante una capa de repositorio común y no con SQL suelto.
   Pruebas automáticas verifican que un negocio no ve los datos de otro.
   El `negocio_id` sale **del token** del usuario, nunca de la configuración ni de parámetros del cliente (fue un bug grave de la v1).
5. **Fotos de facturas solo en el bucket R2 privado**, con acceso mediante URLs prefirmadas de corta duración. El bucket público es solo para el catálogo.
6. **La app Shiny no lleva secretos.** Solo necesita `API_BASE_URL`. No la conectes directamente a la base de datos.
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

- **MySQL 9.x, base `integrat`** (D-19). `MODELO_DATOS.md` se escribió pensando en PostgreSQL: donde difiera, manda `CONVENCIONES_BD.md`.
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

- Piloto (**D-23**, reemplaza a D-21): la API en **Azure Container Apps** y MySQL en **Azure Database for MySQL Flexible Server**, con secretos en **Key Vault**; Shiny sigue en **shinyapps.io**. Railway deja de usarse (`infra/railway.md` queda como histórico; falta la receta de Azure).
  La API en ejecución usa el usuario `integrat_api` (solo DML sobre `integrat`); las migraciones, `integrat_owner`. La API se endurece antes de abrirla (límite de intentos, `Idempotency-Key`, sin `/docs` fuera de `dev`).
- Fotos públicas por `r2.dev` en el piloto (dominio propio en producción). La BD guarda llaves, no URLs.
- Todo en contenedores y configurado por variables de entorno, listo para migrar a Azure (Container Apps + Azure Database for MySQL Flexible Server + Key Vault).

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
Rscript -e "shiny::runApp('app', host = '0.0.0.0', port = 3838)"   # para abrirla desde el celular (misma Wi-Fi)
Rscript -e "testthat::test_dir('app/tests/testthat')"
Rscript -e "testthat::test_local('analitica')"
```

API en contenedor (desde la raíz `IntegraT/`): `docker compose -f infra/docker-compose.yml --env-file .env --profile api up -d --build api`.
La imagen nunca incluye `.env` (está en `.dockerignore`); recibe la configuración por variables de entorno.

Logs: `integrat/logs.py` enmascara secretos. Los errores de la BD se registran solo por su tipo, nunca con el mensaje del driver (incluye usuario y host).

App Shiny (`app/`):
- `R/` se carga automáticamente. Archivos: `tema.R` (bslib + recursos), `componentes.R` (botón primario, tarjetas, estados, hoja inferior), `navegacion.R` (barra inferior de 5 secciones) y `mod_<seccion>.R`.
- Los estilos viven **solo** en `www/css/` (tokens, base, componentes, navegación), sin `style=` en el código R. El JS está en `www/js/app.js`. La fuente Inter se sirve localmente.
- Pantallas (`navset_hidden("pantalla")` en `app.R`): bienvenida → registro / login → onboarding (4 pasos) → app. El encabezado, las secciones y la barra inferior se dibujan con `shell_ui()` (`shell.R`) con el nombre y el vocabulario del negocio que devuelve la API.
- Catálogo: `mod_productos.R` (lista por categoría, agregar, editar, archivar y crear categorías) usa `/v1/items` y `/v1/categorias`. El checklist del Inicio (`mod_inicio.R`) se marca solo: sus reglas viven en la plantilla `onboarding` del tipo de negocio (`regla: {items_minimo: n}`) y la API las evalúa en `GET /v1/negocios/{id}`.
- Ventas: `mod_vender.R` (carrito, cobro, "lo vendido hoy", detalle, anular y deshacer) usa `/v1/ventas`. La app solo muestra totales: la API calcula el total con el precio vigente, lo congela y numera por negocio; las ventas no se editan ni borran, se anulan con motivo.
- Gastos: `mod_gastos.R` ("Lo que gastaste", dentro de Más y desde la acción rápida "Registrar gasto") muestra el mes con el resumen que calcula la API, y permite anotar, editar, archivar y crear categorías. Los campos de fecha usan `input type="date"` con un binding propio en `app.js`.
- Inventario: `mod_inventario.R` ("Tu inventario", dentro de Más) lista los insumos con existencia y aviso "te queda poco", y permite agregar (con sugerencias por tipo de negocio), anotar compras, pérdidas y correcciones, cambiar nombre o mínimo y archivar. Usa `/v1/insumos` y `/v1/unidades` (`docs/PLAN_INVENTARIO.md`): la API convierte unidades y calcula el costo promedio; la app solo muestra.
- Recetas: en la ficha de un platillo o producto, "Receta y costo" (`mod_productos.R`) arma la receta con `PUT /v1/items/{id}/receta` y muestra el costo y el margen que calcula la API. Al cobrar, `mod_vender.R` avisa con `insumos_en_falta` si se acabó algún insumo (la venta ya está cobrada).
- Compras: `mod_compras.R` ("Lo que compraste", dentro de Más y desde la acción rápida "Registrar compra") registra una compra con varias líneas, proveedor opcional que se crea al vuelo, medio de pago, fecha y factura opcional, con una pantalla de revisión antes de guardar; muestra el mes, el detalle y la anulación con motivo, y lista y agrega proveedores. Usa `/v1/compras` y `/v1/proveedores` (`docs/PLAN_COMPRAS.md`): la API suma el total, sube el inventario, recalcula el costo promedio y revierte al anular. En la ficha de un producto, "Lo compro ya hecho para revenderlo" (`/v1/items/{id}/mercaderia`) lo liga a un insumo con receta de 1 unidad.
- Contabilidad (`docs/PLAN_CONTABILIDAD.md`): la API genera los asientos en la misma transacción de cada venta, anulación, gasto, compra y movimiento de inventario a mano (`integrat/contabilidad/`: `motor.py` con plan por negocio, reglas por rol, cuadre y reversos; `eventos.py` con los importes de cada operación). La app solo muestra: "Tu mes" en el Inicio (`GET /v1/resultados`, se pide cada vez que se vuelve al Inicio), "Tus impuestos" en Más (`mod_impuestos.R`, `PUT /v1/negocios/{id}/impuestos`; el régimen elegido queda en `s$regimen_iva` para no redibujar la app) y "Me dieron factura con mi NIT" en los gastos, solo en el régimen general. Libro diario y saldos (`/v1/asientos`, `/v1/cuentas`) solo por API, para el contador.
- Caja y dueño (`docs/PLAN_CAJA.md`): `mod_caja.R` ("Caja del día", en Más y desde ➕ "Cerrar el día") abre con un monto, muestra el efectivo esperado y cierra contando, con revisión de la diferencia; `mod_dueno.R` ("Tu dinero y el negocio") anota aportes y retiros. Usan `/v1/caja` y `/v1/dueno`: el esperado sale de los asientos de la cuenta de Caja desde la apertura (con el reloj de la base), y la diferencia genera un asiento de faltante o sobrante. Los comandos nuevos usan `integrat/idempotencia.py` para la `Idempotency-Key`.
- Inicio (`docs/PLAN_INICIO.md`): "Vendiste hoy" (`/v1/ventas` y `/v1/caja`), "Tu meta del mes" y "Tu mes". La meta es un punto de equilibrio simple cuya fórmula es de `integrat.analitica` (`analitica/R/meta.R`); la app la carga al arrancar con `R/analitica.R` (sin instalar el paquete) y `infra/desplegar_app.R` copia `analitica/R` al paquete que se sube. Fórmulas financieras nuevas van en `analitica/R`, nunca en `app/R`.
- Precio sugerido (`docs/PLAN_PRECIO_SUGERIDO.md`): lo calcula la API (`integrat/precios.py`) y viaja en los ítems y en la receta (`precio_sugerido`, `aviso_precio`); la app marca "Pierdes"/"Margen bajo" en el catálogo, ofrece "Usar Q…" y el margen propio en la ficha, y "Tu margen de ganancia" en Más (`mod_margen.R`, `PUT /v1/negocios/{id}/precios`; el elegido queda en `s$margen_objetivo`).
- Variantes (`docs/PLAN_VARIANTES.md`): atributos del negocio (talla, color…) y por categoría; cada variante tiene precio, inventario (mercadería por variante: `ops_insumo.item_variante_id`), receta propia opcional y precio sugerido. "Tallas y colores" en la ficha (`mod_productos.R`) y selector al vender (`mod_vender.R`, carrito con clave `ítem|variante`). Un producto sin variantes conserva su variante implícita ("Única", `atributos` nulo).
- Importaciones (`docs/PLAN_IMPORTACION.md`): `mod_importaciones.R` sube la plantilla de factura (la de la v1: hoja `Factura_camino`, filas ENCABEZADO + PRODUCTO) con `sesion_subir()` (multipart) a `/v1/importaciones/vista-previa`; la API (`integrat/importaciones/`) la lee, sugiere nombre, categoría y variantes, convierte con el cobro de la tarjeta en Q, reparte cargos y courier por valor, crea productos y variantes como mercadería al recibir y les pone su precio sugerido.
- Existencia al vender (`docs/ANALISIS_INVENTARIO_Y_CLIENTES.md`): la regla del negocio (`vender_sin_existencia`: tiendas `bloquear`, restaurantes `avisar`; Más → "Si no hay inventario", `mod_reglas_venta.R`) la aplica la API al cobrar (`integrat/existencias.py`, 409 si no alcanza). En tiendas todo producto nace como mercadería en 0. Vender muestra "Quedan N"/"Agotado"/"Sin inventario" y topa el carrito con `disponible` de cada ítem y variante.
- `sesion.R`: el token vive solo en la memoria del servidor de Shiny (nunca en el navegador). `sesion_llamar()` renueva el token vencido una vez. `api_cliente.R` (`api_llamar()`) nunca lanza error y traduce los fallos a mensajes amables.
- Las pruebas con navegador (shinytest2, 390×844) usan una **API falsa** en otro proceso (`app/tests/testthat/helper-api-falsa.R`, imita las formas de `/v1`; el contrato real lo cubren las pruebas de `api/`). Si cambias un endpoint que usa la app, actualiza también esa API falsa. Si chromote falla al arrancar Chrome, basta con repetir la prueba.
- Para ver la app con la API real sin tocar la base remota: levanta la API con `DB_*` apuntando a la base local `integrat_test` y define `API_JWT_SECRET`; la app usa `API_BASE_URL`.

Convenciones de BD en MySQL: `docs/CONVENCIONES_BD.md`.
Cambio de esquema = nueva migración en `api/migrations/versions/` + actualizar `api/src/integrat/db/tablas.py`. La prueba de comparación detecta cualquier diferencia entre ambos.

## Documentos de referencia

`docs/DECISIONES.md` · `docs/VISION_PRODUCTO.md` · `docs/PROPUESTA_ARQUITECTURA.md` · `docs/MODELO_DATOS.md` · `docs/DISENO_UX.md` ·
`docs/CONFIGURACION_SERVIDOR.md` · `docs/PRUEBA_MODELOS_IA.md` · `docs/REVISION_CONTADOR.md` · `docs/PLAN_FEL.md` · `docs/ANALISIS_V1.md`
