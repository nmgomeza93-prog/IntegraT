# Plan de cierre de la Fase 1: CI, endurecimiento y despliegue del piloto

> **Objetivo:** que la API corra en Railway con HTTPS, que la app corra en shinyapps.io hablando con ella, y que se pueda usar en un celular real.
> **Criterio de salida de la fase** (`PROPUESTA_ARQUITECTURA.md` §11): prueba de aislamiento entre 2 negocios en verde **y** app desplegada usable en un celular real.
> Se avanza **paso por paso**, igual que en `PLAN_FASE1.md`: al terminar cada paso se detiene el trabajo hasta que confirmes que lo probaste. Los commits se hacen solo con esa confirmación.

## Decisiones tomadas para este plan (2026-11-24)

| # | Decisión | Efecto |
|---|---|---|
| D-21 | **La API del piloto corre en Railway**, junto a la base (no en servidor propio) | Railway da una dirección HTTPS con certificado válido: **resuelve R-03 sin comprar dominio**. No hay Caddy, firewall ni servidor que mantener. `CONFIGURACION_SERVIDOR.md` §1, §3 y §4 quedan para el plan de Azure o de servidor propio |
| — | La cuenta de shinyapps.io ya existe | El token de la cuenta lo configuras tú en tu PC (`rsconnect::setAccountInfo`); nunca va al repo |

**Consecuencia que hay que aceptar:** en Railway la API queda abierta a internet y **no se puede limitar por IP a shinyapps.io**. Por eso el paso 2 (endurecer) va **antes** de desplegar.

## Estado de partida

- ✅ API con cuentas, onboarding, catálogos y `/v1/salud`; 51 pruebas; migraciones `0001` a `0003` (la `0003` aún no aplicada a la base real).
- ✅ App con registro, login, onboarding, navegación y sesión en el servidor; pruebas con navegador.
- ✅ `api/Dockerfile` y servicio `api` en `infra/docker-compose.yml`.
- ❌ No hay CI. ❌ No hay límite de intentos de login, ni `Idempotency-Key`. ❌ La API usa el usuario con privilegios globales (D-20). ❌ La app no sabe leer su URL de la API desde `config.yml` y faltan `rsconnect` y `config` en `renv.lock`.

---

## Paso 1: CI en GitHub Actions

**Objetivo:** que cada push corra las pruebas solo, antes de desplegar nada.

**Archivos** (el repo de Git está en `C:\APP-IntegraT`, así que el flujo vive en la raíz del repo y trabaja dentro de `IntegraT/`):
```
.github/workflows/ci.yml
```
- **Trabajo `api`:** MySQL 9 como servicio, `uv sync`, `ruff check` y `pytest`. Usa las variables `TEST_DB_*` de pruebas (valores ficticios del propio flujo, no son secretos).
- **Trabajo `app`:** R 4.3 con `renv::restore()`, `testthat` de `app/tests` (incluye las de navegador con Chrome del runner) y `testthat` de `analitica`.
- Ningún secreto real en el flujo. El flujo no despliega: solo prueba.

**Cómo lo pruebas:** subir la rama y ver ambos trabajos en verde en la pestaña *Actions*. Romper una prueba a propósito en una rama de prueba y ver que el CI la detecta.

**Tú haces:** `git push` (hoy no he hecho ningún push).
**Commit:** `ci: pruebas automáticas de la API y de la app en GitHub Actions`

---

## Paso 2: Endurecer la API antes de abrirla a internet

**Objetivo:** cerrar los pendientes de seguridad que antes eran aceptables porque la API solo corría en tu PC.

| Qué | Cómo | Por qué |
|---|---|---|
| **Límite de intentos** en `/auth/login`, `/auth/registro` y `/auth/refrescar` | Tabla `core_intento_acceso` (migración `0004`), conteo por IP y por correo en los últimos 15 min, respuesta `429` con mensaje amable | Sin esto, cualquiera puede probar contraseñas sin freno. Va en base de datos (no en memoria) para que funcione con varias réplicas y reinicios |
| **IP real del cliente** detrás del proxy de Railway | `uvicorn --proxy-headers` con `--forwarded-allow-ips` limitado [verificar el valor en Railway] | Si no, todos los intentos parecen venir de la misma IP del proxy |
| **`Idempotency-Key`** en `POST /v1/negocios` | Cabecera opcional; tabla `core_idempotencia` (migración `0004`, 24 h): misma clave y mismo usuario devuelve el mismo negocio. La app manda un UUID por onboarding | Regla de `CLAUDE.md`. Hoy un doble toque en la API crearía dos negocios |
| **Menos información pública** | `/docs` y `/v1/openapi.json` desactivados cuando `APP_ENV` sea `piloto` o `prod`; `/v1/salud` sin `migracion` ni `entorno` para quien no esté en `dev` | No regalar el mapa de la API ni la versión de la base |
| **Tamaño máximo de petición** y `API_ALLOWED_ORIGINS` vacío | Límite de cuerpo en el middleware. No hace falta CORS: quien llama a la API es el **servidor** de Shiny, no el navegador | Reduce superficie |
| **Registros de seguridad** | Log de intentos fallidos y de bloqueos, sin correos completos ni contraseñas (el filtro de `logs.py` ya enmascara secretos) | Poder investigar un ataque |

**Queda fuera** (se decide en la Fase 2): **verificación de correo o SMS**. Hoy nadie recibe mensajes de IntegraT, así que registrarse con un correo ajeno no daña a nadie; cuando haya correos de resumen o avisos, será obligatoria.

**Cómo lo pruebas:**
1. `python -m uv run pytest`: pruebas nuevas de límite (6.º intento fallido → 429, otro correo no se ve afectado, el contador se vacía con el tiempo), de idempotencia (mismo `Idempotency-Key` → un solo negocio) y de que `/docs` no existe con `APP_ENV=piloto`.
2. En la app: tocar "¿Das factura?" dos veces rápido sigue creando un solo negocio (ya cubierto) y ahora también si falla la red a mitad.

**Commits:**
- `feat(api): límite de intentos de acceso y respuesta 429`
- `feat(api): Idempotency-Key en la creación de negocios`
- `chore(api): documentación y salud mínimas en producción`

---

## Paso 3: Base de datos del piloto (D-19 y D-20)

**Objetivo:** que la API no use credenciales con poder sobre otras bases, y que la base real quede migrada y respaldada.

> ⚠️ **Regla de `CLAUDE.md`:** nunca se crean ni modifican usuarios o privilegios del servidor sin una orden explícita tuya. Este paso **no lo hago por mi cuenta**: te dejo el SQL y, si me das la orden, lo ejecuto.

1. **Confirmar el proyecto de Railway:** la red interna (`*.railway.internal`) solo conecta servicios **del mismo proyecto**. Hay que ver si el MySQL de `integrat` está en el mismo proyecto donde va a vivir la API. Si comparte proyecto con otras apps (por ejemplo la base `cam_talent_hub_gestion_cl0`), recomiendo un **proyecto o servicio separado** para IntegraT.
2. **Usuario de ejecución con mínimo privilegio** (lo reemplaza D-20 para el despliegue):
   ```sql
   -- lo corre un administrador; la contraseña se escribe por consola, nunca en un archivo
   CREATE USER 'integrat_api'@'%' IDENTIFIED BY '<CONTRASEÑA_FUERTE>';
   GRANT SELECT, INSERT, UPDATE, DELETE ON integrat.* TO 'integrat_api'@'%';
   ```
   Y otro para migraciones (`integrat_owner`, con `CREATE/ALTER/DROP/INDEX/REFERENCES` solo sobre `integrat.*`). La API en ejecución **no** puede alterar tablas ni ver otras bases. Se confirma con una prueba: conectar con `integrat_api` e intentar `SHOW DATABASES` o leer otra base → debe fallar.
3. **TLS hacia la base:** `DB_SSLMODE=required` como mínimo; `verify_identity` con el certificado de Railway si se puede [verificar].
4. **Migrar la base real:** `alembic upgrade head` (aplica `0003` y `0004`) y `python -m integrat.db.semillas`.
5. **Respaldos:** confirmar si el plan de Railway incluye copias automáticas [verificar]. Si no, un `mysqldump` cifrado a un bucket R2 de respaldos, y **una restauración probada** en la base local antes de empezar el piloto.

**Cómo lo pruebas:** `/v1/salud` desde tu PC con `DB_USER=integrat_api` muestra la migración `0004`; la prueba de "ver otras bases" falla como se espera; la restauración del respaldo funciona.

**Commit:** `docs: usuarios de base de datos y respaldos del piloto` (solo documentación y el script de respaldo; ninguna credencial).

---

## Paso 4: Desplegar la API en Railway

**Objetivo:** API accesible por HTTPS con una dirección propia de Railway.

**Archivos que cambio:**
```
api/Dockerfile         # escuchar en el puerto $PORT que inyecta Railway (hoy está fijo en 8000)
infra/railway.md       # receta paso a paso con los nombres de las variables (sin valores)
docs/CONFIGURACION_SERVIDOR.md   # sección nueva: piloto en Railway + MySQL (hoy dice PostgreSQL)
docs/DECISIONES.md     # D-21; R-03 resuelta
CLAUDE.md              # sección "Hospedaje" al día
```

**Tú haces en Railway** (yo te guío con la receta):
1. Servicio nuevo desde el repo de GitHub, *Root Directory* `IntegraT`, Dockerfile `api/Dockerfile` [verificar los nombres exactos en la interfaz].
2. Variables, **solo en el panel de Railway** (nunca en Git): `APP_ENV=piloto`, `DB_HOST` (el host interno), `DB_PORT`, `DB_NAME=integrat`, `DB_USER=integrat_api`, `DB_PASSWORD`, `DB_SSLMODE`, `API_JWT_SECRET` (**un secreto nuevo**, distinto del de desarrollo; 48 bytes aleatorios), `API_JWT_ACCESO_MINUTOS`, `API_JWT_REFRESCO_DIAS`.
3. *Healthcheck* en `/v1/salud`, comando previo al despliegue `alembic upgrade head` (con el usuario de migraciones) [verificar que Railway lo permita así].
4. *Generate Domain* para obtener la dirección HTTPS.

**Cómo lo pruebas:**
1. Antes de subir: `docker compose -f infra/docker-compose.yml --env-file .env --profile api up -d --build api` y abrir `http://localhost:8000/v1/salud` (la imagen real, ya con `$PORT`).
2. Ya en Railway: `https://<tu-dirección>/v1/salud` → `"estado":"ok"` con candado válido; `/docs` → 404; seis intentos de login fallidos → 429.
3. Los registros de Railway no muestran contraseñas, tokens ni el host de la base.

**Commit:** `feat(infra): API lista para Railway (puerto dinámico) y documentación del despliegue`

---

## Paso 5: Desplegar la app en shinyapps.io

**Objetivo:** app pública en shinyapps.io que habla con la API de Railway, sin secretos en el paquete.

**Archivos:**
```
app/config.yml                 # default: http://127.0.0.1:8000 · shinyapps: https://<tu-dirección>  (no es secreto)
app/R/api_cliente.R            # api_base_url(): variable de entorno → config.yml → localhost
infra/desplegar_app.R          # arma el paquete con lista explícita de archivos y despliega
app/tests/testthat/test-paquete.R   # el paquete NO contiene .env, ni tests, ni nada fuera de la lista
renv.lock                      # + rsconnect y config
```
- `desplegar_app.R` incluye **solo** `app.R`, `R/`, `www/` y `config.yml`; **falla** si encuentra `.env`, claves o tokens en el paquete (se revisa por nombre y por contenido).
- `rsconnect::deployApp` toma las credenciales de la cuenta que **tú** guardaste en tu PC; no se escriben en el script.
- shinyapps.io define `R_CONFIG_ACTIVE=shinyapps`, que activa la URL de producción.

**Cómo lo pruebas:**
1. `testthat` del paquete en verde (no hay `.env`, no hay secretos).
2. Despliegue y abrir la dirección de shinyapps.io **en el celular, con datos móviles** (no la Wi-Fi de casa): crear cuenta → restaurante → "Comedor Doña Mari" → Inicio con su checklist.
3. Con la API apagada en Railway, la app muestra "No pudimos conectar…" y no un error técnico.

**Commit:** `feat(app): configuración por entorno y despliegue seguro a shinyapps.io`

---

## Paso 6: Verificación de cierre de la fase

**Objetivo:** demostrar el criterio de salida con evidencia.

1. **Prueba de aislamiento en verde:** el CI del último commit pasa `test_aislamiento` y `test_aislamiento_api`.
2. **Prueba de aislamiento en el entorno real,** a mano con dos cuentas en la app desplegada:
   - Cuenta A: restaurante. Cuenta B: tienda en línea.
   - Cada una ve solo su nombre, su vocabulario ("Menú" y "Productos") y sus pasos.
   - Con la sesión de A, abrir la dirección de la API con el id del negocio de B → 404.
3. **Celular real,** datos móviles, tamaño de letra grande: barra inferior, botones de 48 px o más, sin desbordes, "Salir de mi cuenta" funciona.
4. **Lista de salida** (se marca en este documento al terminar):
   - [ ] CI en verde · [ ] API en Railway con HTTPS válido · [ ] usuario `integrat_api` sin acceso a otras bases · [ ] base migrada y con una restauración probada · [ ] app en shinyapps.io sin secretos · [ ] aislamiento verificado en el entorno real · [ ] probado en celular real.
5. **Limpieza:** borrar las cuentas de prueba de la base real, o dejarlas marcadas.

**Cierre:** etiqueta `fase-1` en Git y actualizar `CLAUDE.md` ("Estado actual: Fase 1 cerrada; sigue la Fase 2").

---

## Quién hace qué

| Tú | Yo |
|---|---|
| `git push` y conectar el repo a Railway | CI, límites de acceso, idempotencia, Dockerfile, `config.yml`, script de despliegue |
| Dar la **orden explícita** para crear los usuarios de la base (o correr el SQL) | Preparar el SQL, las pruebas y la receta de Railway |
| Cargar las variables en el panel de Railway (secreto JWT nuevo incluido) | Verificar `/v1/salud` y los registros, sin leer ni mostrar secretos |
| Guardar el token de shinyapps.io en tu PC y probar en el celular con datos móviles | Armar y verificar el paquete de la app |

## Riesgos y cosas por verificar

| Riesgo | Mitigación |
|---|---|
| La API queda abierta a todo internet (no se limita por IP) | Paso 2: límites de intentos, tokens de corta vida con rotación, sin `/docs`, sin datos en `/v1/salud` |
| El usuario actual (D-20) tiene poder sobre otras bases del servidor | Paso 3: usuario propio de mínimo privilegio **antes** de desplegar |
| Cambios de Railway o de shinyapps.io (la lista de IPs y los planes cambian) | Todo marcado **[verificar]** se confirma al ejecutar; la app y la API están en contenedores y se configuran solo por variables, listos para Azure |
| El plan gratis de shinyapps.io limita horas activas y se duerme | Aceptable para probar; para el piloto con 10 negocios hay que elegir plan |
| Respaldos de Railway no incluidos en tu plan | Paso 3: `mysqldump` cifrado a R2 con restauración probada |
| Un push con `.env` por error | `.env` ya está en `.gitignore`; el flujo de CI y `desplegar_app.R` fallan si detectan secretos |

## Qué NO entra en el cierre de la Fase 1

- Verificación de correo o SMS, recuperación de contraseña, roles distintos de dueño (Fase 2).
- R2, fotos y catálogo (Fase 2). Worker y IA (Fase 3).
- Dominio propio y migración a Azure (Fase 6).
