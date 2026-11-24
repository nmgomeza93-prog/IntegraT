# Inicio de sesión.

mod_login_ui <- function(id) {
  ns <- shiny::NS(id)
  htmltools::tags$div(
    class = "entrada",
    enlace_atras(ns("atras")),
    htmltools::tags$h1(class = "entrada__titulo", "Entra a tu cuenta"),
    campo_texto(ns("correo"), "Tu correo", autocompletar = "email", modo = "email"),
    campo_texto(ns("clave"), "Tu contraseña", autocompletar = "current-password", clave = TRUE),
    shiny::uiOutput(ns("error")),
    boton_primario(ns("entrar"), "Entrar", "box-arrow-in-right"),
    htmltools::tags$div(
      class = "entrada__aparte",
      htmltools::tags$p(class = "entrada__texto", "¿Aún no tienes cuenta?"),
      boton_secundario(ns("crear"), "Crear mi cuenta", "person-plus")
    )
  )
}

mod_login_server <- function(id, s, ir_pantalla) {
  shiny::moduleServer(id, function(input, output, session) {
    error <- shiny::reactiveVal(NULL)
    output$error <- shiny::renderUI(mensaje_error(error()))

    shiny::observeEvent(input$atras, {
      error(NULL)
      ir_pantalla("bienvenida")
    })
    shiny::observeEvent(input$crear, {
      error(NULL)
      ir_pantalla("registro")
    })

    shiny::observeEvent(input$entrar, {
      correo <- tolower(trimws(input$correo %||% ""))
      clave <- input$clave %||% ""
      if (!correo_valido(correo) || !nzchar(clave)) {
        return(error("Escribe tu correo y tu contraseña."))
      }

      r <- api_llamar("POST", "v1/auth/login", list(correo = correo, clave = clave))
      if (!r$ok) return(error(r$mensaje))

      error(NULL)
      shiny::updateTextInput(session, "clave", value = "")
      sesion_abrir(s, r$cuerpo)
      siguiente <- sesion_continuar(s, ir_pantalla)
      if (!siguiente$ok) error(siguiente$mensaje)
    })
  })
}
