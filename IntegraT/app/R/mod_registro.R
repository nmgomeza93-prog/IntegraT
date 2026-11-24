# Registro: nombre, correo y contraseña. Después sigue el onboarding.

mod_registro_ui <- function(id) {
  ns <- shiny::NS(id)
  htmltools::tags$div(
    class = "entrada",
    enlace_atras(ns("atras")),
    htmltools::tags$h1(class = "entrada__titulo", "Crea tu cuenta"),
    htmltools::tags$p(class = "entrada__texto", "Solo te tomará un minuto."),
    campo_texto(ns("nombre"), "Tu nombre", autocompletar = "name"),
    campo_texto(ns("correo"), "Tu correo", autocompletar = "email", modo = "email"),
    campo_texto(ns("clave"), "Una contraseña (mínimo 8 caracteres)",
                autocompletar = "new-password", clave = TRUE),
    shiny::uiOutput(ns("error")),
    boton_primario(ns("crear"), "Crear mi cuenta", "check-lg")
  )
}

mod_registro_server <- function(id, s, ir_pantalla) {
  shiny::moduleServer(id, function(input, output, session) {
    error <- shiny::reactiveVal(NULL)
    output$error <- shiny::renderUI(mensaje_error(error()))

    shiny::observeEvent(input$atras, {
      error(NULL)
      ir_pantalla("bienvenida")
    })

    shiny::observeEvent(input$crear, {
      nombre <- trimws(input$nombre %||% "")
      correo <- tolower(trimws(input$correo %||% ""))
      clave <- input$clave %||% ""
      if (nchar(nombre) < 2) return(error("Escribe tu nombre."))
      if (!correo_valido(correo)) return(error("Escribe un correo válido, por ejemplo nombre@correo.com."))
      if (nchar(clave) < 8) return(error("Tu contraseña necesita al menos 8 caracteres."))

      r <- api_llamar("POST", "v1/auth/registro",
                      list(nombre = nombre, correo = correo, clave = clave))
      if (!r$ok) return(error(r$mensaje))

      error(NULL)
      shiny::updateTextInput(session, "clave", value = "")
      sesion_abrir(s, r$cuerpo)
      siguiente <- sesion_continuar(s, ir_pantalla)
      if (!siguiente$ok) error(siguiente$mensaje)
    })
  })
}
