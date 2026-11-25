# Más: opciones secundarias (revelación progresiva) y accesibilidad.

mod_mas_ui <- function(id) {
  ns <- shiny::NS(id)
  htmltools::tagList(
    htmltools::tags$h1(class = "pantalla__titulo", "Más"),
    htmltools::tags$ul(
      class = "lista-opciones",
      item_lista("cash-coin", "Gastos", id = ns("gastos"), class = "action-button"),
      item_lista("basket", "Inventario", id = ns("inventario"), class = "action-button"),
      item_lista("receipt", "Compras y proveedores", id = ns("compras"), class = "action-button"),
      item_lista("safe", "Caja del día", id = ns("caja"), class = "action-button"),
      item_lista("wallet2", "Tu dinero y el negocio", id = ns("dueno"), class = "action-button"),
      item_lista("percent", "Tu margen de ganancia", id = ns("margen"), class = "action-button"),
      item_lista("bank", "Tus impuestos", id = ns("impuestos"), class = "action-button"),
      item_lista("bar-chart-line", "Informes", "Pronto", id = ns("informes"),
                 class = "action-button"),
      item_lista("shop", "Mi negocio", "Pronto", id = ns("negocio"), class = "action-button"),
      item_lista("question-circle", "Ayuda", "Pronto", id = ns("ayuda"), class = "action-button"),
      item_lista("box-arrow-right", "Salir de mi cuenta", id = ns("salir"), class = "action-button")
    ),
    htmltools::tags$section(
      class = "tarjeta separado",
      htmltools::tags$h2(class = "hoja__titulo", "Tamaño de la letra"),
      htmltools::tags$div(
        class = "segmentado", role = "group", `aria-label` = "Tamaño de la letra",
        htmltools::tags$button(type = "button", class = "segmentado__opcion",
                               `data-tamano-texto` = "normal", `aria-pressed` = "true", "Normal"),
        htmltools::tags$button(type = "button", class = "segmentado__opcion",
                               `data-tamano-texto` = "grande", `aria-pressed` = "false", "Grande"),
        htmltools::tags$button(type = "button", class = "segmentado__opcion",
                               `data-tamano-texto` = "muy_grande", `aria-pressed` = "false",
                               "Muy grande")
      )
    )
  )
}

mod_mas_server <- function(id, al_salir, ir_a) {
  shiny::moduleServer(id, function(input, output, session) {
    shiny::observeEvent(input$salir, al_salir())
    shiny::observeEvent(input$gastos, ir_a("gastos"))
    shiny::observeEvent(input$inventario, ir_a("inventario"))
    shiny::observeEvent(input$compras, ir_a("compras"))
    shiny::observeEvent(input$impuestos, ir_a("impuestos"))
    shiny::observeEvent(input$caja, ir_a("caja"))
    shiny::observeEvent(input$dueno, ir_a("dueno"))
    shiny::observeEvent(input$margen, ir_a("margen"))
    for (opcion in c("informes", "negocio", "ayuda")) {
      local({
        o <- opcion
        shiny::observeEvent(input[[o]], aviso_pronto())
      })
    }
  })
}
