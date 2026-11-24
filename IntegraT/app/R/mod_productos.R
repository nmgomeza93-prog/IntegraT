# Productos / Menú (según el tipo de negocio). Por ahora, estado vacío que enseña.

mod_productos_ui <- function(id, vocab) {
  ns <- shiny::NS(id)
  htmltools::tagList(
    htmltools::tags$h1(class = "pantalla__titulo", vocab$catalogo),
    estado_vacio(
      vocab$catalogo_icono,
      paste("Aún no tienes", vocab$item_plural),
      "Empieza por el que más vendes: tómale una foto y ponle precio.",
      boton_primario(ns("agregar"), paste("Agregar mi primer", vocab$item_singular), "camera")
    )
  )
}

mod_productos_server <- function(id) {
  shiny::moduleServer(id, function(input, output, session) {
    shiny::observeEvent(input$agregar, aviso_pronto())
  })
}
