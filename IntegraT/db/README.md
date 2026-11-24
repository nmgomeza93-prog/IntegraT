# db

- `semillas/`: catálogos globales (país, moneda, unidades, divisiones territoriales, tipos de negocio). Se cargan de forma idempotente desde la API (paso 2).
- `plantillas/`: plan de cuentas, reglas contables y perfiles por tipo de negocio, en YAML.

Las migraciones del esquema viven en `api/migrations/` (Alembic).
