# Vender: en el paso actual solo enseña qué hacer primero (estado vacío).

mod_vender_ui <- function(id, vocab) {
  ns <- shiny::NS(id)
  htmltools::tagList(
    htmltools::tags$h1(class = "pantalla__titulo", "Vender"),
    estado_vacio(
      "cart3",
      paste("Aún no tienes", vocab$item_plural, "para vender"),
      paste0("Agrega tus ", vocab$item_plural, " y aquí podrás registrar una venta con 3 toques."),
      boton_primario(ns("agregar"), paste("Agregar mi primer", vocab$item_singular), "plus-lg")
    )
  )
}

mod_vender_server <- function(id, ir_a) {
  shiny::moduleServer(id, function(input, output, session) {
    shiny::observeEvent(input$agregar, ir_a("productos"))
  })
}
