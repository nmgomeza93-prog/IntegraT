#!/usr/bin/env bash
# Publica una versión de IntegraT en Azure: construye las imágenes EN AZURE (no en tu PC),
# corre las migraciones y actualiza la API y la app.
#   Uso (desde la raíz IntegraT/, con `az login` hecho y crear.sh ya ejecutado):
#     export SUFIJO=gt01
#     bash infra/azure/publicar.sh
#
# Orden: imágenes -> migraciones (Job) -> API -> app. Si las migraciones fallan, no se publica
# nada más (la versión anterior sigue funcionando). Por eso cada migración debe ser compatible con
# el código anterior (agregar columnas/tablas; borrar solo en una versión posterior).
set -euo pipefail
source "$(dirname "$0")/config.sh"

existe() { "$@" >/dev/null 2>&1; }

# Etiqueta = commit actual; si hay cambios sin guardar en Git, se marca para que se note.
ETIQUETA=$(git rev-parse --short HEAD)
if [ -n "$(git status --porcelain -- . 2>/dev/null)" ]; then
  ETIQUETA="${ETIQUETA}-local-$(date +%Y%m%d%H%M)"
  echo "AVISO: hay cambios sin subir a Git; la versión se etiqueta $ETIQUETA."
fi
REGISTRO="${ACR}.azurecr.io"
IMG_API="$REGISTRO/integrat-api:$ETIQUETA"
IMG_APP="$REGISTRO/integrat-app:$ETIQUETA"

ID_RECURSO=$(az identity show -n "$IDENTIDAD" -g "$GRUPO" --query id -o tsv)
KV_URI=$(az keyvault show -n "$KV" -g "$GRUPO" --query properties.vaultUri -o tsv)
KV_URI="${KV_URI%/}"
DB_HOST=$(az mysql flexible-server show -n "$MYSQL" -g "$GRUPO" --query fullyQualifiedDomainName -o tsv)

# Los secretos se leen de Key Vault con la identidad administrada (nunca pasan por aquí).
ref() { echo "$1=keyvaultref:$KV_URI/secrets/$2,identityref:$ID_RECURSO"; }
SECRETOS_API=("$(ref jwt "$SECRETO_JWT")" "$(ref db-api "$SECRETO_DB_API")")
SECRETOS_JOB=("$(ref db-owner "$SECRETO_DB_OWNER")")

BD_COMUN=(DB_HOST="$DB_HOST" DB_PORT=3306 DB_NAME="$DB_NAME" DB_SSLMODE=verify_identity
          DB_SSL_CA="$DB_SSL_CA" APP_ENV=piloto)
ENV_API=("${BD_COMUN[@]}" DB_USER="$DB_API_USER" DB_PASSWORD=secretref:db-api
         API_JWT_SECRET=secretref:jwt
         FORWARDED_ALLOW_IPS='*')   # la API solo es alcanzable por la red interna del entorno
ENV_JOB=("${BD_COMUN[@]}" DB_USER="$DB_OWNER_USER" DB_PASSWORD=secretref:db-owner
         DB_MIGRATIONS_USER="$DB_OWNER_USER" DB_MIGRATIONS_PASSWORD=secretref:db-owner)

echo "== 1/4 Imágenes $ETIQUETA (se construyen en Azure Container Registry)"
az acr build -r "$ACR" -t "integrat-api:$ETIQUETA" -f api/Dockerfile --target prod . -o none
az acr build -r "$ACR" -t "integrat-app:$ETIQUETA" -f app/Dockerfile --target prod . -o none

echo "== 2/4 Migraciones y catálogos (Job $JOB_MIGRAR)"
if existe az containerapp job show -n "$JOB_MIGRAR" -g "$GRUPO"; then
  az containerapp job secret set -n "$JOB_MIGRAR" -g "$GRUPO" --secrets "${SECRETOS_JOB[@]}" -o none
  az containerapp job update -n "$JOB_MIGRAR" -g "$GRUPO" --image "$IMG_API" \
    --set-env-vars "${ENV_JOB[@]}" -o none
else
  az containerapp job create -n "$JOB_MIGRAR" -g "$GRUPO" --environment "$ENTORNO" \
    --trigger-type Manual --replica-timeout 900 --replica-retry-limit 0 \
    --replica-completion-count 1 --parallelism 1 \
    --image "$IMG_API" --registry-server "$REGISTRO" --registry-identity "$ID_RECURSO" \
    --mi-user-assigned "$ID_RECURSO" --secrets "${SECRETOS_JOB[@]}" --env-vars "${ENV_JOB[@]}" \
    --command "sh" --args "/app/api/migrar.sh" --cpu 0.25 --memory 0.5Gi -o none
fi
EJECUCION=$(az containerapp job start -n "$JOB_MIGRAR" -g "$GRUPO" --query name -o tsv)
echo "   ejecución $EJECUCION"
while :; do
  ESTADO=$(az containerapp job execution show -n "$JOB_MIGRAR" -g "$GRUPO" \
             --job-execution-name "$EJECUCION" --query properties.status -o tsv)
  case "$ESTADO" in
    Succeeded) echo "   migraciones listas"; break ;;
    Failed|Stopped|Degraded)
      echo "ERROR: las migraciones terminaron en '$ESTADO'. No se publicó nada más."
      echo "Registros: Log Analytics -> ContainerAppConsoleLogs_CL | where ContainerJobName_s == '$JOB_MIGRAR'"
      exit 1 ;;
    *) sleep 10 ;;
  esac
done

echo "== 3/4 API ($APP_API, solo red interna)"
if existe az containerapp show -n "$APP_API" -g "$GRUPO"; then
  az containerapp secret set -n "$APP_API" -g "$GRUPO" --secrets "${SECRETOS_API[@]}" -o none
  az containerapp update -n "$APP_API" -g "$GRUPO" --image "$IMG_API" \
    --set-env-vars "${ENV_API[@]}" -o none
else
  az containerapp create -n "$APP_API" -g "$GRUPO" --environment "$ENTORNO" \
    --image "$IMG_API" --registry-server "$REGISTRO" --registry-identity "$ID_RECURSO" \
    --user-assigned "$ID_RECURSO" --secrets "${SECRETOS_API[@]}" --env-vars "${ENV_API[@]}" \
    --ingress internal --target-port 8000 --min-replicas 1 --max-replicas 3 \
    --cpu 0.5 --memory 1.0Gi -o none
fi
API_FQDN=$(az containerapp show -n "$APP_API" -g "$GRUPO" --query properties.configuration.ingress.fqdn -o tsv)

echo "== 4/4 App Shiny ($APP_SHINY, pública, sesiones con afinidad)"
ENV_APP=(API_BASE_URL="https://$API_FQDN")
if existe az containerapp show -n "$APP_SHINY" -g "$GRUPO"; then
  az containerapp update -n "$APP_SHINY" -g "$GRUPO" --image "$IMG_APP" \
    --set-env-vars "${ENV_APP[@]}" -o none
else
  # Una réplica: la sesión de Shiny vive en memoria. Para crecer, subir max-replicas: la afinidad
  # (sticky sessions) ya está activa y mantiene a cada usuario en su réplica.
  az containerapp create -n "$APP_SHINY" -g "$GRUPO" --environment "$ENTORNO" \
    --image "$IMG_APP" --registry-server "$REGISTRO" --registry-identity "$ID_RECURSO" \
    --user-assigned "$ID_RECURSO" --env-vars "${ENV_APP[@]}" \
    --ingress external --target-port 3838 --min-replicas 1 --max-replicas 1 \
    --cpu 0.5 --memory 1.0Gi -o none
  az containerapp ingress sticky-sessions set -n "$APP_SHINY" -g "$GRUPO" --affinity sticky -o none
fi
APP_FQDN=$(az containerapp show -n "$APP_SHINY" -g "$GRUPO" --query properties.configuration.ingress.fqdn -o tsv)

echo
echo "Publicado $ETIQUETA"
echo "  App: https://$APP_FQDN"
echo "  API (interna): https://$API_FQDN"
