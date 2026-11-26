#!/usr/bin/env bash
# Crea, UNA sola vez, la infraestructura de IntegraT en Azure (piloto).
#   Uso (desde la raíz IntegraT/, con `az login` hecho):
#     export SUFIJO=gt01
#     bash infra/azure/crear.sh
# Es seguro repetirlo: lo que ya existe se deja como está.
# Las contraseñas se generan aquí y van DIRECTO a Key Vault: nunca se imprimen ni se guardan en disco.
# Paso siguiente (manual): crear los usuarios de MySQL (infra/azure/README.md, paso 3).
set -euo pipefail
source "$(dirname "$0")/config.sh"

aleatorio() { python -c "import secrets; print(secrets.token_urlsafe(${1:-32}))"; }
existe() { "$@" >/dev/null 2>&1; }

echo "== Suscripción: $(az account show --query name -o tsv)"
az extension add --name containerapp --upgrade --only-show-errors
for p in Microsoft.App Microsoft.OperationalInsights Microsoft.ContainerRegistry \
         Microsoft.KeyVault Microsoft.DBforMySQL Microsoft.ManagedIdentity; do
  az provider register --namespace "$p" --only-show-errors >/dev/null
done

echo "== Grupo de recursos $GRUPO ($UBICACION)"
az group create -n "$GRUPO" -l "$UBICACION" -o none

echo "== Registro de imágenes $ACR"
existe az acr show -n "$ACR" -g "$GRUPO" || \
  az acr create -n "$ACR" -g "$GRUPO" --sku Basic --admin-enabled false -o none
ACR_ID=$(az acr show -n "$ACR" -g "$GRUPO" --query id -o tsv)

echo "== Identidad administrada $IDENTIDAD"
existe az identity show -n "$IDENTIDAD" -g "$GRUPO" || az identity create -n "$IDENTIDAD" -g "$GRUPO" -o none
ID_PRINCIPAL=$(az identity show -n "$IDENTIDAD" -g "$GRUPO" --query principalId -o tsv)

echo "== Key Vault $KV (permisos por RBAC)"
existe az keyvault show -n "$KV" -g "$GRUPO" || \
  az keyvault create -n "$KV" -g "$GRUPO" -l "$UBICACION" --enable-rbac-authorization true -o none
KV_ID=$(az keyvault show -n "$KV" -g "$GRUPO" --query id -o tsv)

echo "== Permisos: la identidad lee imágenes y secretos; tú administras los secretos"
asignar() {  # rol, principal, tipo, alcance (solo si aún no lo tiene)
  local ya
  ya=$(az role assignment list --assignee "$2" --role "$1" --scope "$4" --query "length(@)" -o tsv)
  [ "$ya" != "0" ] || az role assignment create --assignee-object-id "$2" \
    --assignee-principal-type "$3" --role "$1" --scope "$4" -o none
}
asignar "AcrPull" "$ID_PRINCIPAL" ServicePrincipal "$ACR_ID"
asignar "Key Vault Secrets User" "$ID_PRINCIPAL" ServicePrincipal "$KV_ID"
YO=$(az ad signed-in-user show --query id -o tsv)
asignar "Key Vault Secrets Officer" "$YO" User "$KV_ID"

echo "== Secretos (solo se crean si no existen; nunca se muestran)"
guardar_si_falta() {  # nombre, longitud
  if ! existe az keyvault secret show --vault-name "$KV" -n "$1"; then
    # El permiso recién asignado puede tardar un par de minutos en aplicarse.
    for _ in 1 2 3 4 5 6; do
      az keyvault secret set --vault-name "$KV" -n "$1" --value "$(aleatorio "$2")" -o none && return 0
      echo "   (esperando el permiso de Key Vault...)"; sleep 20
    done
    return 1
  fi
}
guardar_si_falta "$SECRETO_JWT" 48
guardar_si_falta "$SECRETO_DB_ADMIN" 24
guardar_si_falta "$SECRETO_DB_API" 24
guardar_si_falta "$SECRETO_DB_OWNER" 24

echo "== MySQL Flexible Server $MYSQL (Burstable B1ms, MySQL $MYSQL_VERSION)"
if ! existe az mysql flexible-server show -n "$MYSQL" -g "$GRUPO"; then
  # --public-access 0.0.0.0: solo servicios de Azure (Container Apps). TLS obligatorio (por defecto).
  az mysql flexible-server create -n "$MYSQL" -g "$GRUPO" -l "$UBICACION" \
    --tier Burstable --sku-name Standard_B1ms --storage-size 20 --version "$MYSQL_VERSION" \
    --admin-user "$DB_ADMIN_USER" \
    --admin-password "$(az keyvault secret show --vault-name "$KV" -n "$SECRETO_DB_ADMIN" --query value -o tsv)" \
    --public-access 0.0.0.0 --backup-retention 7 --yes -o none
fi
existe az mysql flexible-server db show -g "$GRUPO" -s "$MYSQL" -d "$DB_NAME" || \
  az mysql flexible-server db create -g "$GRUPO" -s "$MYSQL" -d "$DB_NAME" \
    --charset utf8mb4 --collation utf8mb4_0900_ai_ci -o none

echo "== Log Analytics y entorno de Container Apps $ENTORNO"
existe az monitor log-analytics workspace show -n "$LOG" -g "$GRUPO" || \
  az monitor log-analytics workspace create -n "$LOG" -g "$GRUPO" -l "$UBICACION" -o none
if ! existe az containerapp env show -n "$ENTORNO" -g "$GRUPO"; then
  az containerapp env create -n "$ENTORNO" -g "$GRUPO" -l "$UBICACION" \
    --logs-workspace-id "$(az monitor log-analytics workspace show -n "$LOG" -g "$GRUPO" --query customerId -o tsv)" \
    --logs-workspace-key "$(az monitor log-analytics workspace get-shared-keys -n "$LOG" -g "$GRUPO" --query primarySharedKey -o tsv)" \
    -o none
fi

echo
echo "Infraestructura lista."
echo "Siguiente: crear los usuarios de MySQL (infra/azure/README.md, paso 3) y luego:"
echo "  bash infra/azure/publicar.sh"
