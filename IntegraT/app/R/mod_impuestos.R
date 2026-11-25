# Tus impuestos (dentro de Más): cómo paga impuestos el negocio. De esto depende si la API separa
# el IVA de lo que vendes, compras y gastas (docs/PLAN_CONTABILIDAD.md). La app solo elige; las
# cuentas las hace la API. Tasas y reglas pendientes de validar con un contador.

REGIMENES_UI <- list(
  general = list(icono = "receipt", titulo = "Régimen general",
                 detalle = "Cobras 12 % de IVA incluido en tus precios y recuperas el de tus compras con factura."),
  pequeno = list(icono = "shop", titulo = "Pequeño contribuyente",
                 detalle = "Pagas un porcentaje de lo que vendes cada mes. No separas IVA."),
  no_se = list(icono = "question-circle", titulo = "Todavía no sé",
               detalle = "Llevamos tus cuentas sin separar IVA. Puedes cambiarlo cuando lo sepas.")
)

mod_impuestos_ui <- function(id) {
  ns <- shiny::NS(id)
  htmltools::tags$div(class = "impuestos", shiny::uiOutput(ns("contenido")))
}

mod_impuestos_server <- function(id, s, ir_a) {
  shiny::moduleServer(id, function(input, output, session) {
    ns <- session$ns
    elegido <- shiny::reactiveVal(NULL)
    error <- shiny::reactiveVal(NULL)

    actual <- shiny::reactive(regimen_iva_actual(s))
    shiny::observeEvent(actual(), elegido(actual()))

    output$contenido <- shiny::renderUI({
      shiny::req(s$negocio)
      guardado <- actual()
      marcado <- elegido() %||% guardado
      htmltools::tagList(
        enlace_atras(ns("atras")),
        htmltools::tags$h1(class = "pantalla__titulo", "¿Cómo pagas impuestos?"),
        htmltools::tags$p(class = "entrada__texto",
                          "Así sabemos si separar el IVA de lo que vendes y compras. ",
                          "Si tienes dudas, pregúntale a tu contador."),
        htmltools::tags$div(
          class = "pila", role = "group", `aria-label` = "Régimen de impuestos",
          `data-elige-grupo` = "",  # la opción tocada queda marcada de inmediato
          lapply(names(REGIMENES_UI), function(codigo) {
            r <- REGIMENES_UI[[codigo]]
            opcion_grande(ns("regimen"), codigo, r$icono, r$titulo, r$detalle,
                          activa = identical(marcado, codigo))
          })
        ),
        htmltools::tags$p(class = "entrada__texto separado",
                          "El cambio aplica a lo que registres desde ahora; lo anterior no cambia."),
        shiny::uiOutput(ns("error")),
        boton_primario(ns("guardar"), "Guardar", "check-lg")
      )
    })
    output$error <- shiny::renderUI(mensaje_error(error()))

    shiny::observeEvent(input$regimen, {
      if (input$regimen %in% names(REGIMENES_UI)) elegido(input$regimen)
    })
    shiny::observeEvent(input$atras, {
      error(NULL)
      elegido(actual())
      ir_a("mas")
    })

    shiny::observeEvent(input$guardar, {
      valor <- elegido() %||% actual()
      negocio_id <- shiny::isolate(s$negocio_id)
      r <- sesion_llamar(s, "PUT", paste0("v1/negocios/", negocio_id, "/impuestos"),
                         list(regimen_iva = valor))
      if (!r$ok) return(error(r$mensaje))
      error(NULL)
      s$regimen_iva <- valor  # sin recargar el negocio: eso redibujaría toda la app
      s$cuentas_v <- shiny::isolate(s$cuentas_v) + 1L  # el resumen del Inicio se recalcula
      shiny::showNotification(paste0("Listo: ", REGIMENES_UI[[valor]]$titulo, "."),
                              duration = 4, closeButton = FALSE, id = "impuestos-aviso")
      ir_a("mas")
    })
  })
}
