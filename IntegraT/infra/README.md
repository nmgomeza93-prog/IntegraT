# infra

Aquí vivirán, según los pasos de `docs/PLAN_FASE1.md`:

- `docker-compose.yml`: MySQL local para pruebas (paso 2) y la API (paso 3).
- `Dockerfile` de la app Shiny (portabilidad hacia Azure, `docs/CONFIGURACION_SERVIDOR.md` §7).
- `cors-r2.json`: política CORS de los buckets R2.

Nunca se guardan secretos aquí: todo sale de `../.env`.
