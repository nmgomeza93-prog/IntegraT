# Onboarding en 4 pasos (docs/DISENO_UX.md §4.0):
#   1) tipo de negocio  2) nombre  3) ¿das factura? (aquí se crea el negocio)  4) listo.
# Cada paso es una sola tarea; elegir una opción avanza solo (1 toque).

PASOS_ONBOARDING <- 3L

mod_onboarding_ui <- function(id) {
  ns <- shiny::NS(id)
  htmltools::tags$div(class = "entrada", shiny::uiOutput(ns("contenido")))
}

mod_onboarding_server <- function(id, s, ir_pantalla) {
  shiny::moduleServer(id, function(input, output, session) {
    ns <- session$ns
    paso <- shiny::reactiveVal(1L)
    eleccion <- shiny::reactiveValues(tipo = NULL, nombre = "")
    creado <- shiny::reactiveVal(NULL)
    error <- shiny::reactiveVal(NULL)
    intento <- shiny::reactiveVal(0L)

    # Cada vez que cambia la persona (entra otra o sale), el asistente empieza de cero.
    shiny::observeEvent(s$usuario, {
      paso(1L)
      eleccion$tipo <- NULL
      eleccion$nombre <- ""
      creado(NULL)
      error(NULL)
    }, ignoreNULL = FALSE)

    tipos <- shiny::reactive({
      intento()
      shiny::req(s$acceso)
      api_llamar("GET", "v1/tipos-negocio")
    })

    output$error <- shiny::renderUI(mensaje_error(error()))

    # --- Pantallas ---------------------------------------------------------------------
    ui_tipo <- function() {
      r <- tipos()
      if (!r$ok) {
        return(estado_vacio("wifi-off", "No pudimos cargar las opciones", r$mensaje,
                            boton_secundario(ns("reintentar"), "Intentar de nuevo", "arrow-repeat")))
      }
      htmltools::tagList(
        progreso_pasos(1, PASOS_ONBOARDING),
        htmltools::tags$h1(class = "entrada__titulo", "¿Qué tipo de negocio tienes?"),
        htmltools::tags$div(
          class = "pila",
          lapply(r$cuerpo, function(t) {
            opcion_grande(ns("tipo"), t$codigo, t$icono, t$nombre, t$descripcion,
                          activa = identical(eleccion$tipo, t$codigo))
          })
        )
      )
    }

    ui_nombre <- function() {
      htmltools::tagList(
        enlace_atras(ns("atras")),
        progreso_pasos(2, PASOS_ONBOARDING),
        htmltools::tags$h1(class = "entrada__titulo", "¿Cómo se llama tu negocio?"),
        campo_texto(ns("nombre"), "Nombre de tu negocio", valor = eleccion$nombre,
                    placeholder = "El nombre que ven tus clientes", autocompletar = "organization"),
        shiny::uiOutput(ns("error")),
        boton_primario(ns("seguir_nombre"), "Seguir", "arrow-right")
      )
    }

    ui_factura <- function() {
      htmltools::tagList(
        enlace_atras(ns("atras")),
        progreso_pasos(3, PASOS_ONBOARDING),
        htmltools::tags$h1(class = "entrada__titulo", "¿Das factura a tus clientes?"),
        htmltools::tags$p(class = "entrada__texto",
                          "Es para preparar tu negocio. Puedes cambiarlo después."),
        htmltools::tags$div(
          class = "pila",
          opcion_grande(ns("factura"), "si", "receipt", "Sí, doy factura"),
          opcion_grande(ns("factura"), "no", "x-circle", "No, todavía no"),
          opcion_grande(ns("factura"), "no_se", "question-circle", "No sé",
                        "No te preocupes, lo vemos después")
        ),
        shiny::uiOutput(ns("error"))
      )
    }

    ui_listo <- function() {
      negocio <- creado()
      htmltools::tagList(
        estado_vacio("check-circle", paste0("¡Listo, ", negocio$nombre, "!"),
                     "Tu negocio ya está creado. Empieza por aquí:"),
        htmltools::tags$section(
          class = "tarjeta",
          htmltools::tags$h2(class = "hoja__titulo", "Tus primeros pasos"),
          lista_pasos(negocio$primeros_pasos)
        ),
        htmltools::tags$div(class = "separado",
                            boton_primario(ns("ir_app"), "Ir a mi negocio", "arrow-right"))
      )
    }

    output$contenido <- shiny::renderUI({
      switch(as.character(paso()),
        "1" = ui_tipo(), "2" = ui_nombre(), "3" = ui_factura(), "4" = ui_listo()
      )
    })

    # --- Acciones ----------------------------------------------------------------------
    shiny::observeEvent(input$reintentar, intento(intento() + 1L))

    shiny::observeEvent(input$atras, {
      error(NULL)
      if (paso() %in% c(2L, 3L)) paso(paso() - 1L)
    })

    shiny::observeEvent(input$tipo, {
      if (paso() != 1L) return()
      eleccion$tipo <- input$tipo
      error(NULL)
      paso(2L)
    })

    shiny::observeEvent(input$seguir_nombre, {
      if (paso() != 2L) return()
      nombre <- trimws(input$nombre %||% "")
      if (nchar(nombre) < 2) return(error("Escribe el nombre de tu negocio."))
      eleccion$nombre <- nombre
      error(NULL)
      paso(3L)
    })

    # Aquí se crea el negocio. La guarda por paso evita crearlo dos veces si se toca dos veces.
    shiny::observeEvent(input$factura, {
      if (paso() != 3L) return()
      r <- sesion_llamar(s, "POST", "v1/negocios", list(
        nombre = eleccion$nombre,
        tipo_negocio_codigo = eleccion$tipo,
        da_factura = input$factura
      ))
      if (!r$ok) return(error(r$mensaje))
      error(NULL)
      s$acceso <- r$cuerpo$acceso$access_token  # token ya atado al negocio nuevo
      s$negocio_id <- r$cuerpo$id
      creado(r$cuerpo)
      paso(4L)
    })

    shiny::observeEvent(input$ir_app, {
      shiny::req(creado())
      s$negocio <- creado()
      ir_pantalla("app")
    })
  })
}
