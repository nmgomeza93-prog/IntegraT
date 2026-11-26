# Mi negocio (dentro de Más): nombre, contacto y datos para facturar. La API valida el teléfono, el
# correo y el NIT, y solo deja al dueño cambiar el NIT y el nombre fiscal.

# Lo que se manda a la API: los vacíos van como null (borran el dato).
cuerpo_negocio <- function(valores, incluir_fiscal) {
  vacio_a_null <- function(x) {
    x <- trimws(x %||% "")
    if (nzchar(x)) x else NULL
  }
  cuerpo <- list(nombre = trimws(valores$nombre %||% ""),
                 telefono = vacio_a_null(valores$telefono),
                 correo = vacio_a_null(valores$correo),
                 direccion = vacio_a_null(valores$direccion))
  if (incluir_fiscal) {
    # `[<- list()`: asignar NULL con `$<-` quitaría el campo y no se borraría el dato.
    cuerpo["nit"] <- list(vacio_a_null(valores$nit))
    cuerpo["nombre_fiscal"] <- list(vacio_a_null(valores$nombre_fiscal))
  }
  cuerpo
}

mod_negocio_ui <- function(id) {
  ns <- shiny::NS(id)
  htmltools::tags$div(class = "mi-negocio", shiny::uiOutput(ns("contenido")))
}

mod_negocio_server <- function(id, s, ir_a) {
  shiny::moduleServer(id, function(input, output, session) {
    ns <- session$ns
    error <- shiny::reactiveVal(NULL)

    # El negocio al día (no s$negocio: cambiarlo redibujaría toda la app).
    datos <- shiny::reactive({
      s$al_dia  # al entrar, al día con lo que se guardó en otra pantalla
      shiny::req(s$negocio_id, shiny::isolate(s$acceso))
      sesion_llamar(s, "GET", paste0("v1/negocios/", s$negocio_id))
    })

    output$contenido <- shiny::renderUI({
      r <- datos()
      if (!r$ok) return(mensaje_error(r$mensaje))
      n <- r$cuerpo
      nit_visible <- if (is.character(n$nit)) texto_fiscal("NIT", n$nit) else ""
      htmltools::tagList(
        enlace_atras(ns("atras"), "Más"),
        htmltools::tags$h1(class = "pantalla__titulo", "Mi negocio"),
        campo_texto(ns("nombre"), "Nombre del negocio", valor = n$nombre, autocompletar = "off"),
        campo_texto(ns("telefono"), "Teléfono (opcional)",
                    valor = telefono_visible(n$telefono) %||% "", autocompletar = "off", modo = "tel"),
        campo_texto(ns("correo"), "Correo (opcional)", valor = n$correo %||% "",
                    autocompletar = "off", modo = "email"),
        campo_texto(ns("direccion"), "Dirección (opcional)", valor = n$direccion %||% ""),
        htmltools::tags$h2(class = "hoja__titulo separado", "Para tus facturas"),
        htmltools::tags$p(class = "entrada__texto",
                          "Los usaremos cuando emitas facturas electrónicas (FEL). Solo el dueño los cambia."),
        campo_texto(ns("nit"), "Tu NIT (opcional)", valor = sub("^NIT ", "", nit_visible),
                    autocompletar = "off"),
        campo_texto(ns("nombre_fiscal"), "Nombre como aparece en la SAT (opcional)",
                    valor = n$nombre_fiscal %||% ""),
        shiny::uiOutput(ns("error")),  # aparte: así no se borra lo escrito
        boton_primario(ns("guardar"), "Guardar", "check-lg")
      )
    })
    output$error <- shiny::renderUI(mensaje_error(error()))

    shiny::observeEvent(input$atras, {
      error(NULL)
      ir_a("mas")
    })

    shiny::observeEvent(input$guardar, {
      actual <- shiny::isolate(datos())$cuerpo
      valores <- list(nombre = input$nombre, telefono = input$telefono, correo = input$correo,
                      direccion = input$direccion, nit = input$nit,
                      nombre_fiscal = input$nombre_fiscal)
      # El NIT solo se manda si cambió (así un administrador puede guardar su contacto).
      nit_antes <- if (is.character(actual$nit)) sub("^NIT ", "", texto_fiscal("NIT", actual$nit)) else ""
      cambio_fiscal <- !identical(trimws(input$nit %||% ""), nit_antes) ||
        !identical(trimws(input$nombre_fiscal %||% ""), actual$nombre_fiscal %||% "")
      cuerpo <- cuerpo_negocio(valores, incluir_fiscal = cambio_fiscal)
      if (nchar(cuerpo$nombre) < 2) return(error("Escribe el nombre de tu negocio."))
      r <- sesion_llamar(s, "PUT", paste0("v1/negocios/", s$negocio_id, "/datos"), cuerpo)
      if (!r$ok) return(error(r$mensaje))
      error(NULL)
      session$sendCustomMessage("nombre_negocio", cuerpo$nombre)  # el encabezado, sin recargar
      shiny::showNotification("Listo: guardamos los datos de tu negocio.", duration = 4,
                              closeButton = FALSE, id = "negocio-aviso")
      ir_a("mas")
    })
  })
}
