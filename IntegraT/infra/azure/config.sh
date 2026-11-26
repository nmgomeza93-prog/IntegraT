# Nombres de los recursos de Azure de IntegraT (piloto). NO contiene secretos.
# Lo cargan crear.sh y publicar.sh. Puedes cambiar cualquier valor con una variable de entorno
# antes de ejecutarlos (por ejemplo: SUFIJO=abc12 sh infra/azure/crear.sh).

# Sufijo corto (minúsculas y números) para los nombres que deben ser únicos en todo Azure
# (registro de imágenes, Key Vault y servidor MySQL). Elige uno y no lo cambies después.
SUFIJO="${SUFIJO:?Define SUFIJO (minúsculas y números, 4-8 caracteres), por ejemplo: export SUFIJO=gt01}"

UBICACION="${UBICACION:-eastus2}"
GRUPO="${GRUPO:-rg-integrat-piloto}"

ACR="${ACR:-acrintegrat${SUFIJO}}"                 # registro de imágenes (solo letras y números)
KV="${KV:-kv-integrat-${SUFIJO}}"                  # Key Vault (3-24 caracteres)
MYSQL="${MYSQL:-mysql-integrat-${SUFIJO}}"         # Azure Database for MySQL Flexible Server
LOG="${LOG:-log-integrat}"                         # Log Analytics
ENTORNO="${ENTORNO:-cae-integrat}"                 # entorno de Container Apps
IDENTIDAD="${IDENTIDAD:-id-integrat}"              # identidad administrada (lee ACR y Key Vault)

APP_API="${APP_API:-integrat-api}"
APP_SHINY="${APP_SHINY:-integrat-app}"
JOB_MIGRAR="${JOB_MIGRAR:-integrat-migrar}"

# Base de datos y usuarios (los nombres no son secretos; las contraseñas viven en Key Vault).
DB_NAME=integrat
DB_ADMIN_USER="${DB_ADMIN_USER:-integratadmin}"
DB_API_USER="${DB_API_USER:-integrat_api}"
DB_OWNER_USER="${DB_OWNER_USER:-integrat_owner}"
MYSQL_VERSION="${MYSQL_VERSION:-8.4}"   # la más nueva en Flexible Server [verificar]; si no existe, 8.0.21

# Nombres de los secretos en Key Vault.
SECRETO_JWT=api-jwt-secret
SECRETO_DB_ADMIN=db-admin-password
SECRETO_DB_API=db-api-password
SECRETO_DB_OWNER=db-owner-password

# Certificados raíz del sistema (incluyen los de Azure MySQL: DigiCert Global Root G2 y
# Microsoft RSA Root CA 2017): permiten validar el TLS de MySQL sin copiar archivos.
DB_SSL_CA=/etc/ssl/certs/ca-certificates.crt

# Git Bash en Windows convierte "/subscriptions/..." en rutas de Windows: lo evitamos.
export MSYS_NO_PATHCONV=1
