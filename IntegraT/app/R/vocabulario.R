# Vocabulario de la interfaz según el tipo de negocio.
# En el paso 5 vendrá de la API (core_cfg_tipo_negocio_vocabulario); mientras tanto,
# este valor por defecto permite ver la app sin sesión.

vocabulario_defecto <- function() {
  list(
    item_singular = "producto",
    item_plural = "productos",
    catalogo = "Productos",
    catalogo_icono = "box-seam",
    vender_contexto = "Canal"
  )
}
