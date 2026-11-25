# Estructura de la app ya con sesión: encabezado, secciones y navegación inferior.
# Se dibuja con los datos del negocio (nombre y vocabulario según su tipo).

shell_ui <- function(negocio) {
  vocab <- vocab_negocio(negocio)
  htmltools::tagList(
    htmltools::tags$header(
      class = "app-encabezado",
      htmltools::tags$div(
        htmltools::tags$p(class = "app-encabezado__negocio", negocio$nombre),
        htmltools::tags$p(class = "app-encabezado__fecha", shiny::textOutput("fecha", inline = TRUE))
      ),
      shiny::uiOutput("estado_conexion", inline = TRUE)
    ),
    htmltools::tags$main(
      class = "app-contenido",
      bslib::navset_hidden(
        id = "seccion",
        bslib::nav_panel_hidden("inicio", mod_inicio_ui("inicio", vocab, negocio$primeros_pasos)),
        bslib::nav_panel_hidden("vender", mod_vender_ui("vender", vocab)),
        bslib::nav_panel_hidden("productos", mod_productos_ui("productos", vocab)),
        bslib::nav_panel_hidden("gastos", mod_gastos_ui("gastos")),
        bslib::nav_panel_hidden("inventario", mod_inventario_ui("inventario")),
        bslib::nav_panel_hidden("compras", mod_compras_ui("compras")),
        bslib::nav_panel_hidden("impuestos", mod_impuestos_ui("impuestos")),
        bslib::nav_panel_hidden("caja", mod_caja_ui("caja")),
        bslib::nav_panel_hidden("dueno", mod_dueno_ui("dueno")),
        bslib::nav_panel_hidden("mas", mod_mas_ui("mas"))
      )
    ),
    nav_inferior(vocab),
    hoja_acciones(vocab)
  )
}
