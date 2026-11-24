# Navegación inferior fija de 5 secciones (docs/DISENO_UX.md §2).

SECCIONES <- c("inicio", "vender", "productos", "mas")

boton_nav <- function(destino, icono_nombre, texto, activo = FALSE) {
  htmltools::tags$li(
    htmltools::tags$button(
      type = "button", class = "nav-inferior__boton", `data-destino` = destino,
      `aria-current` = if (activo) "page" else NULL,
      icono(icono_nombre), htmltools::tags$span(texto)
    )
  )
}

# vocab: lista con al menos `catalogo` y `catalogo_icono` (según el tipo de negocio)
nav_inferior <- function(vocab) {
  htmltools::tags$nav(
    class = "nav-inferior", `aria-label` = "Secciones",
    htmltools::tags$ul(
      class = "nav-inferior__lista",
      boton_nav("inicio", "house-door", "Inicio", activo = TRUE),
      boton_nav("vender", "cart3", "Vender"),
      htmltools::tags$li(
        htmltools::tags$button(
          type = "button", class = "nav-inferior__boton nav-inferior__boton--accion",
          `data-abre-hoja` = "hoja-acciones", `aria-label` = "Acciones rápidas",
          htmltools::tags$span(class = "nav-inferior__circulo", icono("plus-lg"))
        )
      ),
      boton_nav("productos", vocab$catalogo_icono, vocab$catalogo),
      boton_nav("mas", "list", "Más")
    )
  )
}

hoja_acciones <- function(vocab) {
  hoja_inferior(
    "hoja-acciones", "¿Qué quieres hacer?",
    accion_rapida("registrar_compra", "receipt", "Registrar compra",
                  "A mano, con plantilla o con foto"),
    accion_rapida("registrar_gasto", "cash-coin", "Registrar gasto"),
    accion_rapida("agregar_item", "plus-square", paste("Agregar", vocab$item_singular)),
    accion_rapida("cerrar_dia", "safe", "Cerrar el día")
  )
}
