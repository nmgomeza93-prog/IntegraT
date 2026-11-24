# Convenciones de la base de datos `integrat` (MySQL 9)

> Resumen operativo de la convención (decisión D-19: MySQL en lugar de PostgreSQL).
> Complementa `MODELO_DATOS.md`: donde ese documento dice PostgreSQL, **manda este**.

## 1. Cómo se adaptó el diseño a MySQL

| Diseño original (PostgreSQL) | En MySQL | Dónde se implementa |
|---|---|---|
| Esquemas `core`, `cat`, `ops`, … | **Prefijo de tabla**: `core_`, `cat_`, `ops_`, `cont_`, `fiscal_`, `ia_`, `integ_`, `dw_`, `rpt_`, `audit_` dentro de la única base `integrat` | `integrat/db/tablas.py` (`PREFIJOS_PERMITIDOS`) |
| RLS por `negocio_id` | **Filtro obligatorio en la API**: toda consulta a una tabla con `negocio_id` se arma con `integrat.db.aislamiento` (`seleccionar`, `insertar`, `actualizar`) usando el `negocio_id` del token | `integrat/db/aislamiento.py` + `tests/test_aislamiento.py` |
| `uuidv7()` nativo | UUIDv7 **generado por la API** y guardado como `BINARY(16)` | `integrat/db/tipos.py` (`uuid7`, `UUIDBinario`) |
| `timestamptz` | `DATETIME(6)` **en UTC**: cada conexión ejecuta `SET time_zone = '+00:00'`. La zona del negocio se aplica en la API | `integrat/db/conexion.py` |
| Trigger diferido "asiento cuadrado" | Validación en la transacción de la API antes del COMMIT (llega con el motor contable) | Fase 2 |
| `FORCE ROW LEVEL SECURITY` para la app | La app Shiny **no se conecta a la BD** (todo va por la API) | `PROPUESTA_ARQUITECTURA.md` §3 |
| Funciones `SECURITY DEFINER` para el consolidado | Consultas de consolidado en la API, después de verificar el rol del titular | Fase 5 |

## 2. Nombres

- Español, `snake_case`, minúsculas, sin tildes ni ñ. **Tablas en singular** con prefijo de esquema: `core_negocio`, `cat_pais`.
- Los catálogos globales ya llevan el prefijo `cat_` (no se escribe `cat_cat_`). Las tablas de configuración llevan `cfg_` después del esquema: `core_cfg_tipo_negocio_capacidad`, `fiscal_cfg_regimen`.
- Analítica: `dw_dim_*`, `dw_fact_*`. Vistas: `rpt_vw_*`. Rutinas: `fn_*` y `sp_*`, solo para integridad, ETL y reportes (**la lógica de negocio vive en la API**).
- **PK** `id BINARY(16)` (UUIDv7). Los catálogos usan su `codigo` como PK (`GT`, `GTQ`, `restaurante`).
- **FK** `<tabla_sin_prefijo>_id` (`negocio_id`, `titular_id`) o `<catalogo>_codigo` (`pais_codigo`).
- Restricciones con nombre explícito:
  - `fk_<tabla>_<columna>`
  - `uq_<tabla>_<cols>`
  - `ck_<tabla>_<nombre>` (en MySQL, el nombre de un CHECK debe ser único en toda la base)
  - `ix_<tabla>_<cols>`
- Toda FK tiene su índice explícito, o es la primera columna de una PK o UNIQUE.

## 3. Tipos

| Uso | Tipo |
|---|---|
| Identificadores | `BINARY(16)` (UUIDv7) |
| Dinero | `DECIMAL(14,2)` |
| Cantidades | `DECIMAL(14,4)` |
| Costos unitarios | `DECIMAL(14,6)` |
| Factores de conversión | `DECIMAL(20,10)` |
| Fechas y horas | `DATETIME(6)` en UTC (`*_en`) |
| Fechas de negocio | `DATE` |
| Booleanos | `TINYINT(1)`, con prefijo `es_` o `tiene_` cuando no es obvio |
| Estados | `VARCHAR` + `CHECK` (**nunca ENUM**) |
| Datos flexibles | `JSON` (configuración, plantillas, respuestas de IA) |
| Tablas | Motor InnoDB · `utf8mb4` · `utf8mb4_0900_ai_ci` |

## 4. Columnas estándar

- **Tablas de negocio** (con `id`): `creado_en`, `creado_por`, `actualizado_en` (con ON UPDATE), `actualizado_por`, `eliminado_en` (borrado lógico), `eliminado_por` y `version`.
  La prueba `test_convencion_de_nombres` lo exige.
- **Catálogos y configuración global**: `creado_en` y `actualizado_en`.
- Toda tabla con datos de un negocio lleva `negocio_id` y **solo** se consulta mediante `integrat.db.aislamiento`.

## 5. Migraciones y semillas

- **Alembic** en `api/migrations/versions/` (`0001_catalogos`, `0002_nucleo`, …). Cada migración se escribe a mano con nombres explícitos.
  **Una migración aplicada nunca se edita**: para corregir, se crea otra.
- MySQL **no tiene DDL transaccional**: si una migración falla a la mitad, hay que revisar y limpiar antes de reintentar.
- `integrat/db/tablas.py` debe coincidir con las migraciones. La prueba `test_la_metadata_coincide_con_la_base_migrada` lo verifica.
- Las semillas (`db/semillas/NN_*.yaml`) son idempotentes (`INSERT … ON DUPLICATE KEY UPDATE`).

## 6. Seguridad

- Solo se admiten las bases `integrat` (real) e `integrat_test` (local). `config.py` rechaza cualquier otra, y cada conexión verifica `DATABASE()`.
- Las pruebas usan **solo** el MySQL local de Docker (`TEST_DB_*`). `ConfigBDPruebas` exige `127.0.0.1` y `integrat_test`.
- Las contraseñas son `SecretStr`: no aparecen en `repr`, en logs ni en mensajes de error.

## 7. Comandos

```bash
# Base local de pruebas (Docker)
docker compose -f infra/docker-compose.yml --env-file .env up -d --wait mysql-test

cd api
python -m uv run pytest                           # pruebas (usa integrat_test)
python -m uv run alembic upgrade head             # migra la base real (DB_* de .env)
python -m uv run python -m integrat.db.semillas   # carga o actualiza catálogos en la base real
python -m uv run alembic current                  # versión aplicada
python -m uv run alembic -x pruebas=si upgrade head   # migra la base local de pruebas
```
