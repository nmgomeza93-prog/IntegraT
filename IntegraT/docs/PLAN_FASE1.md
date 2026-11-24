# Plan de la Fase 1: Fundaciones del MVP

> Objetivo de la fase (roadmap, `PROPUESTA_ARQUITECTURA.md` §11): **repo, base de datos `integrat` con esquemas y migraciones, API mínima, app Shiny mobile-first con navegación, registro y onboarding**.
> Se avanza **paso por paso**. Al terminar cada paso, el trabajo se detiene hasta que el dueño del producto confirme que probó el paso y está conforme.
> Los commits se hacen solo con esa confirmación.

## Requisitos previos (una sola vez)

| Herramienta | Para qué | Estado en esta PC |
|---|---|---|
| Git | Versionado | Por verificar en el paso 1 |
| Python 3.12 | API | ✅ 3.12.6 instalado |
| `uv` | Entorno y dependencias de Python (`api/.venv`) | ❌ No instalado. Se instala en el paso 1 (`pip install uv` o el instalador oficial) |
| R ≥ 4.3 + RStudio | App Shiny y analítica | R no está en el PATH de la terminal; hay que confirmar la ruta de instalación |
| Docker Desktop (opcional, recomendado) | PostgreSQL local para pruebas aisladas | Por verificar |
| Base `integrat` | Desarrollo | ⚠️ **Ver "Bloqueo" abajo** |

> **Decidido (D-19): MySQL 9.7 en Railway.** En el paso 2 se adapta `MODELO_DATOS.md`:
> - Esquemas → prefijos de tabla.
> - RLS → filtro obligatorio por `negocio_id` en la capa de repositorio de la API, con pruebas.
> - Asiento cuadrado → validación en la transacción de la API.
> - UUIDv7 → generado por la API y guardado como `BINARY(16)`.
> - Para las pruebas automáticas se usará un MySQL local en Docker (ya instalado), para no tocar la base de Railway.

---

## Paso 1: Estructura del proyecto y entornos

**Objetivo:** esqueleto del monorepo, entornos reproducibles de R y Python y Git configurado sin secretos.

**Archivos que se crean:**
```
IntegraT/
├─ README.md                    # qué es, cómo arrancar
├─ .gitignore  .env.example     # ya existen (se revisan)
├─ .editorconfig  .gitattributes
├─ app/        (app.R mínimo "Hola IntegraT", R/, www/, tests/testthat/)
├─ analitica/  (DESCRIPTION, R/, tests/testthat/)   # paquete integrat.analitica vacío
├─ api/        (pyproject.toml, src/integrat/__init__.py, tests/)  # uv, Python 3.12
├─ db/         (semillas/, plantillas/)
└─ infra/      (README con lo que irá aquí)
renv.lock actualizado (shiny, bslib, bsicons, httr2, jsonlite, testthat, shinytest2)
```

**Cómo lo pruebas:**
1. `git status`: **no** debe aparecer `.env`.
2. `cd api && uv sync && uv run python -c "import integrat; print('ok')"`
3. En RStudio: `renv::status()` (sin diferencias) y `shiny::runApp("app")`, que muestra "Hola IntegraT".

**Commit:** `chore: estructura inicial del monorepo (app R, analitica, api Python) y entornos renv/uv`

---

## Paso 2: Base de datos `integrat`, esquemas y migraciones iniciales

**Objetivo:** migraciones versionadas que crean los esquemas y las primeras tablas, con convención de nombres, columnas estándar y aislamiento por negocio.

**Archivos que se crean:**
```
api/alembic.ini
api/migrations/env.py                     # lee DB_* de .env; usa DB_MIGRATIONS_USER si existe
api/migrations/versions/0001_esquemas.py  # core, cat, ops, cont, fiscal, ia, integ, dw, rpt, audit
api/migrations/versions/0002_catalogos.py # cat_pais, cat_moneda, cat_unidad_medida,
                                          # cat_tipo_negocio, cat_division_territorial, cat_canal_venta_base
api/migrations/versions/0003_nucleo.py    # usuario, titular, negocio, membresia, membresia_titular,
                                          # cfg_tipo_negocio_capacidad/_vocabulario/_plantilla, negocio_capacidad
                                          # + políticas de aislamiento por negocio_id
db/semillas/gt.yaml                       # GT, GTQ, unidades, 22 departamentos y municipios
db/semillas/tipos_negocio.yaml            # ventas_en_linea, restaurante (capacidades y vocabulario)
api/src/integrat/db/semillas.py           # carga idempotente
api/tests/test_migraciones.py             # upgrade → downgrade → upgrade
api/tests/test_aislamiento.py             # 2 negocios: ninguno ve los datos del otro
docs/CONVENCIONES_BD.md                   # resumen operativo de la convención (de MODELO_DATOS §2)
```

**Cómo lo pruebas:**
1. `cd api && uv run alembic upgrade head` → sin errores.
2. Conectarte con tu cliente (DBeaver, Workbench o psql): ver los esquemas o tablas y los catálogos cargados (GT, GTQ, tipos de negocio).
3. `uv run pytest tests/test_migraciones.py tests/test_aislamiento.py` → en verde.

**Commit:** `feat(db): esquemas, catálogos base y núcleo titular/negocio/usuario con aislamiento por negocio`

---

## Paso 3: API mínima con endpoint de salud

**Objetivo:** FastAPI conectada a `integrat` mediante `.env`, sin exponer secretos, con un endpoint de salud.

**Archivos que se crean:**
```
api/src/integrat/main.py            # FastAPI, prefijo /v1, OpenAPI
api/src/integrat/config.py          # pydantic-settings: lee .env; repr enmascarado
api/src/integrat/db/conexion.py     # pool de conexiones, TLS según DB_SSLMODE
api/src/integrat/salud/router.py    # GET /v1/salud
api/src/integrat/logs.py            # logging estructurado; filtro que enmascara secretos
api/tests/test_salud.py
api/tests/test_config_no_filtra_secretos.py
api/Dockerfile
infra/docker-compose.yml            # api (+ postgres local opcional para pruebas)
```

`GET /v1/salud` devuelve, por ejemplo: `{"estado":"ok","version":"0.1.0","bd":{"conectada":true,"latencia_ms":42,"migracion":"0003"}}`, sin host, usuario ni contraseña.

**Cómo lo pruebas:**
1. `cd api && uv run uvicorn integrat.main:app --reload`
2. Abrir `http://localhost:8000/v1/salud` → `"estado":"ok"`. Abrir `http://localhost:8000/docs` → documentación OpenAPI.
3. Cambiar temporalmente `DB_PASSWORD` en `.env` por un valor incorrecto → `/v1/salud` responde `"bd":{"conectada":false}` y el log **no** muestra la contraseña.
4. `uv run pytest` → en verde.

**Commit:** `feat(api): API mínima FastAPI con configuración por .env y endpoint /v1/salud`

---

## Paso 4: App Shiny con el sistema de diseño y la navegación

**Objetivo:** el "esqueleto visual" mobile-first: tema índigo, componentes base, navegación inferior de 5 secciones y conexión a la API.

**Archivos que se crean:**
```
app/app.R
app/R/tema.R                 # bs_theme(version = 5) con los tokens de DISENO_UX §5
app/R/componentes.R          # boton_primario(), tarjeta_numero(), tarjeta_consejo(), estado_vacio(), hoja_inferior()
app/R/navegacion.R           # barra inferior: Inicio · Vender · ➕ · Productos/Menú · Más (navset_hidden)
app/R/mod_inicio.R  mod_vender.R  mod_productos.R  mod_mas.R   # pantallas de muestra con estados vacíos
app/R/api_cliente.R          # httr2; API_BASE_URL desde config; llama a /v1/salud
app/www/css/tokens.css  base.css  componentes.css  navegacion.css
app/www/fonts/inter/*        # fuente local (no Google Fonts)
app/www/js/reconexion.js     # mensaje "Reconectando…"
app/tests/testthat/test-componentes.R
app/tests/testthat/test-app-navegacion.R   # shinytest2, viewport 390×844
```

**Cómo lo pruebas:**
1. `shiny::runApp("app", host = "0.0.0.0", port = 3838)` y abrirlo **en tu celular** (misma red Wi-Fi: `http://<IP-de-tu-PC>:3838`).
2. Revisar: barra inferior fija, botones de 48 px o más, contraste, el ➕ abre una hoja inferior, y el indicador "API conectada ✅" (con el paso 3 corriendo).
3. Apagar la API → la app muestra un mensaje amable, no un error técnico.
4. `testthat::test_dir("app/tests/testthat")` → en verde.

**Commit:** `feat(app): sistema de diseño índigo mobile-first y navegación inferior`

---

## Paso 5: Registro del usuario y onboarding con tipo de negocio

**Objetivo:** que una persona cree su cuenta, elija su tipo de negocio y llegue al Inicio con su checklist de primeros pasos.

**API (archivos que se crean):**
```
api/src/integrat/auth/          # registro, login (argon2id), tokens JWT de corta duración + refresh
api/src/integrat/negocios/      # crear negocio (+ membresía dueño + capacidades del tipo), titular opcional
api/src/integrat/catalogos/     # GET /v1/tipos-negocio, /v1/regimenes
api/tests/test_auth.py  test_negocios.py  test_aislamiento_api.py
```
Endpoints:
- `POST /v1/auth/registro`, `POST /v1/auth/login`, `POST /v1/auth/refrescar`, `GET /v1/yo`
- `GET /v1/tipos-negocio`
- `POST /v1/negocios`, `GET /v1/negocios/{id}`

La verificación del correo o SMS queda simulada en desarrollo (el código se ve en el log de dev), y la real queda para después.

**App (archivos que se crean):**
```
app/R/mod_bienvenida.R  mod_registro.R  mod_login.R
app/R/mod_onboarding.R   # 1) tipo de negocio (tarjetas) 2) nombre + logo opcional 3) ¿Das factura? 4) listo
app/R/sesion.R           # token en la sesión del servidor; nunca en el navegador
app/tests/testthat/test-onboarding.R   # shinytest2: flujo completo
```

**Cómo lo pruebas:**
1. Con la API y la app corriendo, desde el celular: **Crear cuenta → elegir "Tengo un restaurante" → "Comedor Doña Mari" → "No sé / todavía no" → Inicio** con el checklist del restaurante ("Agrega tus 5 platillos…").
2. Repetir con otro correo eligiendo "Vendo en línea" → el vocabulario cambia ("Productos" en lugar de "Menú").
3. Iniciar sesión con la primera cuenta → no se ve nada del negocio de la segunda.
4. `uv run pytest` y `testthat::test_dir("app/tests/testthat")` → en verde.

**Commits:**
- `feat(api): registro, login y creación de negocio con tipo y capacidades`
- `feat(app): pantallas de registro y onboarding por tipo de negocio`

---

## Después del paso 5 (cierre de la Fase 1, se planifica aparte)

- Desplegar la API en el servidor (HTTPS) y la app en shinyapps.io (`CONFIGURACION_SERVIDOR.md`).
- Criterio de salida de la fase: prueba de aislamiento en verde + app desplegada usable en un celular real.
