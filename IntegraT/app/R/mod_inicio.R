# Inicio: "¿cómo va mi negocio hoy?" (docs/DISENO_UX.md §4.1). Por ahora con datos vacíos.

mod_inicio_ui <- function(id, vocab) {
  ns <- shiny::NS(id)
  htmltools::tags$div(
    class = "pila",
    tarjeta_numero(
      "Hoy", formato_dinero(0),
      contexto = "Aún no registras ventas hoy.",
      estado = etiqueta_estado("Empieza hoy", "neutro")
    ),
    tarjeta_numero(
      "Tu meta del mes", "—",
      contexto = "La calculamos cuando anotes tus gastos fijos: así sabrás cuánto vender para no perder."
    ),
    tarjeta_consejo(
      paste0("Agrega tu primer ", vocab$item_singular,
             " tomándole una foto. Después podrás vender en 3 toques."),
      accion = boton_secundario(ns("ir_productos"), paste("Agregar mi primer", vocab$item_singular),
                                "camera")
    )
  )
}

mod_inicio_server <- function(id, ir_a) {
  shiny::moduleServer(id, function(input, output, session) {
    shiny::observeEvent(input$ir_productos, ir_a("productos"))
  })
}
