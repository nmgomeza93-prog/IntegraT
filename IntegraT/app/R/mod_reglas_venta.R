# Si no hay inventario (dentro de Más): la regla del negocio para vender lo que no hay. La aplica
# la API al cobrar (docs/ANALISIS_INVENTARIO_Y_CLIENTES.md); aquí solo se elige.

REGLAS_VENTA_UI <- list(
  bloquear = list(icono = "slash-circle", titulo = "No dejar vender",
                  detalle = "Solo se vende lo que tienes. Primero compra o importa; así tu inventario siempre cuadra."),
  avisar = list(icono = "exclamation-triangle", titulo = "Avisar y dejar vender",
                detalle = "Se cobra aunque no alcance y te avisamos. Útil si aún no anotas todos tus ingredientes.")
)

mod_reglas_venta_ui <- function(id) {
  ns <- shiny::NS(id)
  htmltools::tags$div(class = "reglas-venta", shiny::uiOutput(ns("contenido")))
}

mod_reglas_venta_server <- function(id, s, ir_a) {
  shiny::moduleServer(id, function(input, output, session) {
    ns <- session$ns
    elegida <- shiny::reactiveVal(NULL)
    error <- shiny::reactiveVal(NULL)
    actual <- shiny::reactive(regla_venta_actual(s))
    shiny::observeEvent(actual(), elegida(actual()))

    output$contenido <- shiny::renderUI({
      shiny::req(s$negocio)
      marcada <- elegida() %||% actual()
      htmltools::tagList(
        enlace_atras(ns("atras")),
        htmltools::tags$h1(class = "pantalla__titulo", "Si no hay inventario"),
        htmltools::tags$p(class = "entrada__texto",
                          "¿Qué hacemos cuando quieres vender algo que ya no tienes?"),
        htmltools::tags$div(
          class = "pila", role = "group", `aria-label` = "Regla de venta", `data-elige-grupo` = "",
          lapply(names(REGLAS_VENTA_UI), function(codigo) {
            r <- REGLAS_VENTA_UI[[codigo]]
            opcion_grande(ns("regla"), codigo, r$icono, r$titulo, r$detalle,
                          activa = identical(marcada, codigo))
          })
        ),
        campo_texto(ns("minimo"), "Avísame cuando queden (unidades)",
                    valor = round(as.numeric(s$minimo_defecto %||% s$negocio$minimo_defecto %||% "0")),
                    autocompletar = "off", modo = "numeric"),
        htmltools::tags$div(
          class = "casilla",
          shiny::checkboxInput(ns("aplicar"), "Usarlo también en los productos que ya tengo",
                               value = FALSE, width = "100%")
        ),
        mensaje_error(error()),
        boton_primario(ns("guardar"), "Guardar", "check-lg")
      )
    })

    shiny::observeEvent(input$regla, if (input$regla %in% names(REGLAS_VENTA_UI)) elegida(input$regla))
    shiny::observeEvent(input$atras, {
      error(NULL)
      elegida(actual())
      ir_a("mas")
    })
    shiny::observeEvent(input$guardar, {
      valor <- elegida() %||% actual()
      minimo <- suppressWarnings(as.integer(trimws(input$minimo %||% "")))
      if (is.na(minimo) || minimo < 0 || minimo > 9999) {
        return(error("Escribe cuántas unidades, por ejemplo 2 (o 0 para no avisar)."))
      }
      r <- sesion_llamar(s, "PUT", paste0("v1/negocios/", shiny::isolate(s$negocio_id), "/ventas"),
                         list(vender_sin_existencia = valor, minimo_defecto = minimo,
                              aplicar_a_todos = isTRUE(input$aplicar)))
      if (!r$ok) return(error(r$mensaje))
      error(NULL)
      s$vender_sin_existencia <- valor  # sin recargar el negocio: eso redibujaría toda la app
      s$minimo_defecto <- as.character(minimo)
      s$catalogo_v <- shiny::isolate(s$catalogo_v) + 1L  # Vender se pone al día
      shiny::showNotification(paste0("Listo: ", REGLAS_VENTA_UI[[valor]]$titulo, "."),
                              duration = 4, closeButton = FALSE, id = "reglas-aviso")
      ir_a("mas")
    })
  })
}
