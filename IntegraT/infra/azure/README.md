# IntegraT en Azure (piloto)

Receta para desplegar IntegraT en Azure (decisiones D-23 y D-24). **Ningún secreto va en este
archivo ni en Git:** las contraseñas se generan en `crear.sh` y viven solo en Key Vault.
Los puntos marcados **[verificar]** dependen de la versión de la CLI o del portal de Azure.

## Qué se crea

```
                 Internet (HTTPS)
                        │
        ┌───────────────▼────────────────┐   Entorno de Container Apps (cae-integrat)
        │  integrat-app  (Shiny, 3838)   │   - ingreso público, afinidad de sesión
        └───────────────┬────────────────┘
                        │ HTTPS interno (API_BASE_URL)
        ┌───────────────▼────────────────┐
        │  integrat-api  (FastAPI, 8000) │   - ingreso SOLO interno (no se ve desde Internet)
        └───────────────┬────────────────┘
                        │ TLS verificado
        ┌───────────────▼────────────────┐
        │ MySQL Flexible Server (8.4)    │   - base `integrat`, B1ms, copias 7 días
        └────────────────────────────────┘
  integrat-migrar (Job manual): alembic + semillas antes de cada versión
  Key Vault: secretos  ·  Container Registry: imágenes  ·  Log Analytics: registros
  Identidad administrada id-integrat: lee imágenes (AcrPull) y secretos (Secrets User)
```

| Pieza | Servicio | Por qué |
|---|---|---|
| App Shiny | Container Apps, 1 réplica fija, *sticky sessions* | Shiny guarda la sesión en memoria y usa websockets |
| API | Container Apps, 1–3 réplicas, ingreso interno | Escala por peticiones; solo la llama la app (menos superficie de ataque) |
| Migraciones | Container Apps Job (manual) | Corren con el usuario dueño del esquema, separadas de la API |
| MySQL | Azure Database for MySQL Flexible Server | Copias, parches y TLS administrados |
| Secretos | Key Vault + identidad administrada | Sin contraseñas en imágenes, Git ni variables escritas a mano |
| Imágenes | Azure Container Registry (Basic) | Se construyen en Azure: no cargan tu PC |
| Fotos | Cloudflare R2 (sin cambios) | Egreso gratis (D-09) |

Costo aproximado del piloto (con 1 réplica siempre encendida de cada app): en el orden de
USD 40–70 al mes **[verificar en la calculadora de Azure]**. La API podría bajar a 0 réplicas
(`--min-replicas 0`) a cambio de unos segundos de espera en el primer uso.

## 1. Requisitos (una vez)
1. [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) instalada.
2. Git Bash (viene con Git para Windows) y Python (para generar contraseñas).
3. `az login` y elegir la suscripción: `az account set --subscription "<nombre o id>"`.
4. Tu usuario necesita rol **Owner** (o Contributor + User Access Administrator) en la suscripción
   o el grupo: el script asigna permisos a la identidad administrada.

## 2. Crear la infraestructura (una vez)
Desde la raíz `IntegraT/`, en Git Bash:

```bash
export SUFIJO=gt01            # minúsculas y números; no lo cambies después
bash infra/azure/crear.sh     # 10–20 minutos (MySQL es lo más lento)
```

Crea el grupo `rg-integrat-piloto` en `eastus2`, el registro, la identidad, Key Vault con los
secretos (JWT y contraseñas generadas al azar), MySQL con la base `integrat` y el entorno de
Container Apps. Puedes repetirlo: lo que ya existe no se toca.

Si `--version 8.4` no está disponible en tu región: `MYSQL_VERSION=8.0.21 bash infra/azure/crear.sh`.

## 3. Crear los usuarios de MySQL (una vez, a mano)
La API **no** usa el administrador. Crea dos usuarios con permisos mínimos:

1. Permite tu IP de forma temporal:
   ```bash
   source infra/azure/config.sh
   az mysql flexible-server firewall-rule create -g "$GRUPO" -n "$MYSQL" \
     --rule-name mi-pc --start-ip-address <tu IP> --end-ip-address <tu IP>
   ```
2. Consulta las contraseñas en Key Vault (no las copies a ningún archivo):
   ```bash
   az keyvault secret show --vault-name "$KV" -n db-admin-password --query value -o tsv
   az keyvault secret show --vault-name "$KV" -n db-owner-password --query value -o tsv
   az keyvault secret show --vault-name "$KV" -n db-api-password   --query value -o tsv
   ```
3. Conéctate con MySQL Workbench o DBeaver al host
   `<MYSQL>.mysql.database.azure.com`, usuario `integratadmin`, con SSL obligatorio, y ejecuta
   (reemplaza las contraseñas por las de Key Vault):
   ```sql
   CREATE USER 'integrat_owner'@'%' IDENTIFIED BY '<db-owner-password>' REQUIRE SSL;
   GRANT ALL PRIVILEGES ON integrat.* TO 'integrat_owner'@'%';

   CREATE USER 'integrat_api'@'%' IDENTIFIED BY '<db-api-password>' REQUIRE SSL;
   GRANT SELECT, INSERT, UPDATE, DELETE ON integrat.* TO 'integrat_api'@'%';
   ```
4. Quita la regla de tu IP:
   ```bash
   az mysql flexible-server firewall-rule delete -g "$GRUPO" -n "$MYSQL" --rule-name mi-pc --yes
   ```

## 4. Publicar una versión (cada vez)
Primero sube los cambios a GitHub (la versión se etiqueta con el commit). Luego:

```bash
export SUFIJO=gt01
bash infra/azure/publicar.sh
```

1. Construye `integrat-api` e `integrat-app` **en Azure** (`az acr build`), etiquetadas con el commit.
2. Corre el Job `integrat-migrar` (`api/migrar.sh`: `alembic upgrade head` + semillas). Si falla,
   se detiene y la versión anterior sigue funcionando.
3. Actualiza la API y después la app.
4. Muestra la dirección pública de la app (`https://integrat-app.<...>.azurecontainerapps.io`).

Las migraciones corren **antes** que el código nuevo: deben ser compatibles con la versión anterior
(agregar tablas o columnas; borrar o renombrar en una versión posterior).

### Volver a la versión anterior
```bash
az containerapp revision list -n integrat-api -g rg-integrat-piloto -o table
az containerapp update -n integrat-api -g rg-integrat-piloto \
  --image acrintegrat<SUFIJO>.azurecr.io/integrat-api:<commit anterior>
```
(lo mismo con `integrat-app`). Una migración no se deshace sola: si hace falta, se escribe una
migración nueva que revierta el cambio.

## 5. Comprobar el despliegue
1. Abre la app y entra con una cuenta: si carga el Inicio, la app llega a la API y la API a MySQL.
2. Desde la app no debe verse `/docs` de la API: la API no tiene dirección pública.
3. Seis intentos de login fallidos con el mismo correo → el sexto dice "Demasiados intentos".
4. Registros: portal de Azure → Container Apps → `integrat-api` → *Log stream*, o Log Analytics:
   `ContainerAppConsoleLogs_CL | where ContainerAppName_s == "integrat-api"`.
   No deben aparecer contraseñas, tokens ni el host de la base.
5. Key Vault → *Secrets*: solo la identidad `id-integrat` y tú tienen acceso.

## Notas
- **IP del cliente:** la API solo recibe tráfico interno, así que `FORWARDED_ALLOW_IPS=*` es seguro.
  Hoy quien llama a la API es el servidor de Shiny, así que el límite por IP ve la IP de la app.
  El límite **por correo** protege cada cuenta igual.
- **MySQL y la red:** `--public-access 0.0.0.0` permite conexiones solo desde servicios de Azure,
  con TLS obligatorio y validado (`DB_SSLMODE=verify_identity`). Para aislarlo del todo, el paso
  siguiente es una red virtual (VNet) con acceso privado (más costo y configuración).
- **Cambiar un secreto:** `az keyvault secret set --vault-name <KV> -n <nombre> --value ...` y
  luego `az containerapp revision restart` (o publicar de nuevo). Si es la contraseña de un
  usuario de MySQL, cámbiala también en MySQL (`ALTER USER`).
- **Dominio propio:** Container Apps → *Custom domains* con certificado administrado (gratis).
