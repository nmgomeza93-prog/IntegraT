# Bienvenida: primera pantalla para quien no ha entrado (docs/DISENO_UX.md §4.0).

mod_bienvenida_ui <- function(id) {
  ns <- shiny::NS(id)
  htmltools::tags$div(
    class = "entrada",
    htmltools::tags$div(class = "entrada__marca", icono("graph-up-arrow"),
                        htmltools::tags$span("IntegraT")),
    htmltools::tags$h1(class = "entrada__titulo", "Tu negocio, sin complicarte"),
    htmltools::tags$p(
      class = "entrada__texto",
      "IntegraT lleva tus cuentas por ti. Tú solo enfócate en vender."
    ),
    boton_primario(ns("crear"), "Crear mi cuenta", "person-plus"),
    htmltools::tags$div(
      class = "entrada__aparte",
      boton_secundario(ns("entrar"), "Ya tengo cuenta", "box-arrow-in-right")
    )
  )
}

mod_bienvenida_server <- function(id, ir_pantalla) {
  shiny::moduleServer(id, function(input, output, session) {
    shiny::observeEvent(input$crear, ir_pantalla("registro"))
    shiny::observeEvent(input$entrar, ir_pantalla("login"))
  })
}
