# API de IntegraT en Railway (piloto)

Receta para desplegar la API (D-21). **Ningún valor secreto va en este archivo ni en Git:** las
variables se cargan solo en el panel de Railway. Los textos marcados **[verificar]** dependen de
cómo se llame la opción en la interfaz de Railway en el momento del despliegue.

## 1. Antes de empezar
- La base `integrat` ya está migrada (`0005`) y existen los usuarios `integrat_api` (la API en
  ejecución: solo `SELECT/INSERT/UPDATE/DELETE` sobre `integrat`) e `integrat_owner` (migraciones).
- El proyecto de Railway: la red interna (`*.railway.internal`) solo conecta servicios **del mismo
  proyecto**. Si el MySQL de `integrat` está en otro proyecto, se usa su dirección pública (proxy
  TCP) con TLS obligatorio. Si ese proyecto comparte otras aplicaciones, es preferible poner la API
  de IntegraT en un proyecto o servicio separado.

## 2. Crear el servicio
1. *New → GitHub Repo* y elegir el repositorio. **[verificar]**
2. En *Settings*:
   - **Root Directory:** `IntegraT` (el repositorio tiene el proyecto en esa subcarpeta).
   - **Builder:** Dockerfile, ruta `api/Dockerfile`. **[verificar]**
   - **Healthcheck Path:** `/v1/salud`.
   - **Pre-deploy Command:** el comando de la sección 4. **[verificar]**
3. *Networking → Generate Domain* para obtener la dirección HTTPS.

Railway inyecta `PORT`; la imagen escucha en ese puerto (si no existe, en 8000).

## 3. Variables (solo en el panel de Railway)

| Variable | Valor |
|---|---|
| `APP_ENV` | `piloto` |
| `DB_HOST`, `DB_PORT` | host y puerto de MySQL (interno si es el mismo proyecto) |
| `DB_NAME` | `integrat` |
| `DB_USER`, `DB_PASSWORD` | `integrat_api` y su contraseña (en tu `.env`: `DB_API_USER`, `DB_API_PASSWORD`) |
| `DB_SSLMODE` | `required` como mínimo |
| `DB_MIGRATIONS_USER`, `DB_MIGRATIONS_PASSWORD` | `integrat_owner` y su contraseña (solo para el comando previo al despliegue) |
| `API_JWT_SECRET` | **un secreto nuevo**, distinto del de desarrollo: `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `API_JWT_ACCESO_MINUTOS`, `API_JWT_REFRESCO_DIAS` | `15` y `30` |
| `API_ALLOWED_ORIGINS` | vacío (quien llama es el servidor de Shiny, no el navegador) |
| `FORWARDED_ALLOW_IPS` | ver sección 5 |

No cargues `TEST_DB_*`, `.env` ni claves de R2 o Anthropic todavía: la API no las usa en esta fase.

## 4. Migraciones en cada despliegue
Comando previo al despliegue (usa el usuario con permiso de alterar tablas, no el de ejecución):

```sh
sh -c 'DB_USER="$DB_MIGRATIONS_USER" DB_PASSWORD="$DB_MIGRATIONS_PASSWORD" uv run --no-sync alembic upgrade head'
```

Si Railway no permite ese comando, se corre `alembic upgrade head` desde tu PC (con `DB_*` del
usuario de migraciones) **antes** de publicar una versión que cambie el esquema.

## 5. La IP real del cliente (límite de intentos)
El límite de intentos por IP lee `X-Forwarded-For`, que uvicorn solo acepta de las IP incluidas en
`FORWARDED_ALLOW_IPS` (por defecto, solo `127.0.0.1`). Detrás del proxy de Railway:

- Si queda vacío, todos los intentos parecerían venir de la IP del proxy y el límite por IP
  bloquearía a todos a la vez.
- Con `*` se acepta el encabezado de cualquiera. Es aceptable **solo** si el servicio no es
  alcanzable salvo a través del proxy de Railway y este reescribe el encabezado **[verificar]**.
- El límite **por correo** protege las cuentas aunque la IP sea falsa.

Verificación después del despliegue (sección 6, punto 4).

## 6. Cómo comprobar el despliegue
1. `https://<tu-dirección>/v1/salud` → `"estado":"ok"`, con el candado válido. En `piloto` no
   muestra entorno ni migración.
2. `https://<tu-dirección>/docs` → 404.
3. Seis intentos de login fallidos con el mismo correo → el sexto da 429.
4. IP real: tras unos intentos fallidos, comprobar en los registros de Railway que `ip=` muestra
   la IP del cliente y no la del proxy (`Acceso: login fallido ip=… correo#…`). Si todas las
   líneas muestran la misma IP interna, ajustar `FORWARDED_ALLOW_IPS`.
5. Los registros no muestran contraseñas, tokens ni el host de la base.

## 7. Probar la imagen antes de subir
```bash
docker build -t integrat-api -f api/Dockerfile .
# con las variables de la sección 3 (o las de la base local de pruebas):
docker run --rm -p 8000:8000 -e PORT=8000 -e APP_ENV=piloto -e DB_HOST=... integrat-api
```
