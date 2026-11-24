# Vocabulario de la interfaz según el tipo de negocio.
# Viene de la API (negocio$vocabulario, de core_cfg_tipo_negocio_vocabulario);
# este valor por defecto rellena lo que falte.

vocabulario_defecto <- function() {
  list(
    item_singular = "producto",
    item_plural = "productos",
    catalogo = "Productos",
    catalogo_icono = "box-seam",
    vender_contexto = "Canal"
  )
}

# Vocabulario del negocio que respondió la API, con los valores por defecto de relleno.
vocab_negocio <- function(negocio) {
  propio <- lapply(negocio$vocabulario %||% list(), as.character)
  utils::modifyList(vocabulario_defecto(), propio)
}
