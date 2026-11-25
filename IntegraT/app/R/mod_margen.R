# Tu margen de ganancia (dentro de Más): el margen objetivo del negocio. Lo usan el precio sugerido
# de cada platillo o producto (que puede tener uno propio) y la meta del mes. El cálculo es de la
# API (precio sugerido) y de integrat.analitica (meta); aquí solo se elige el porcentaje.

margen_actual_pct <- function(s) {
  valor <- s$margen_objetivo %||% s$negocio$margen_objetivo %||% "0.35"
  round(100 * as.numeric(valor))
}

mod_margen_ui <- function(id) {
  ns <- shiny::NS(id)
  htmltools::tags$div(class = "margen", shiny::uiOutput(ns("contenido")))
}

mod_margen_server <- function(id, s, ir_a) {
  shiny::moduleServer(id, function(input, output, session) {
    ns <- session$ns
    error <- shiny::reactiveVal(NULL)

    output$contenido <- shiny::renderUI({
      shiny::req(s$negocio)
      htmltools::tagList(
        enlace_atras(ns("atras")),
        htmltools::tags$h1(class = "pantalla__titulo", "Tu margen de ganancia"),
        htmltools::tags$p(class = "entrada__texto",
                          "De cada Q 100 que vendes, ¿cuánto quieres que te quede después de pagar ",
                          "lo que cuesta hacerlo? Con esto te sugerimos precios y calculamos tu meta."),
        campo_texto(ns("pct"), "Margen (%)", valor = margen_actual_pct(s),
                    placeholder = "Ejemplo: 35", autocompletar = "off", modo = "numeric"),
        htmltools::tags$p(class = "entrada__texto",
                          "Muchos comedores trabajan entre 30 % y 60 %. Cada platillo o producto ",
                          "puede tener el suyo en su ficha."),
        mensaje_error(error()),
        boton_primario(ns("guardar"), "Guardar", "check-lg")
      )
    })

    shiny::observeEvent(input$atras, {
      error(NULL)
      ir_a("mas")
    })

    shiny::observeEvent(input$guardar, {
      pct <- suppressWarnings(as.numeric(gsub("[%[:space:]]", "", input$pct %||% "")))
      if (is.na(pct) || pct < 0 || pct > 90) {
        return(error("Escribe un margen entre 0 y 90, por ejemplo 35."))
      }
      valor <- sprintf("%.4f", pct / 100)
      r <- sesion_llamar(s, "PUT", paste0("v1/negocios/", shiny::isolate(s$negocio_id), "/precios"),
                         list(margen_objetivo = valor))
      if (!r$ok) return(error(r$mensaje))
      error(NULL)
      s$margen_objetivo <- valor  # sin recargar el negocio: eso redibujaría toda la app
      s$cuentas_v <- shiny::isolate(s$cuentas_v) + 1L  # la meta del mes se recalcula
      s$catalogo_v <- shiny::isolate(s$catalogo_v) + 1L
      shiny::showNotification(paste0("Tu margen ahora es ", pct, " %."), duration = 4,
                              closeButton = FALSE, id = "margen-aviso")
      ir_a("mas")
    })
  })
}
