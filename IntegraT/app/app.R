# IntegraT — app Shiny mobile-first.
# Los archivos de R/ se cargan automáticamente. La app no se conecta a la base de datos:
# todo dato pasa por la API (API_BASE_URL). Única configuración de la app.
#
# Pantallas ("pantalla"): bienvenida → registro / login → onboarding → app (con navegación
# inferior). La sesión (token) vive solo en el servidor de Shiny: ver R/sesion.R.

library(shiny)

ui <- bslib::page(
  title = "IntegraT",
  lang = "es",
  theme = tema_integrat(),
  recursos_integrat(),
  htmltools::tags$div(id = "aviso-conexion", class = "aviso-conexion", role = "status",
                      "Se perdió la conexión. Reconectando…"),
  bslib::navset_hidden(
    id = "pantalla",
    bslib::nav_panel_hidden("bienvenida", mod_bienvenida_ui("bienvenida")),
    bslib::nav_panel_hidden("registro", mod_registro_ui("registro")),
    bslib::nav_panel_hidden("login", mod_login_ui("login")),
    bslib::nav_panel_hidden("onboarding", mod_onboarding_ui("onboarding")),
    bslib::nav_panel_hidden("app", uiOutput("shell"))
  )
)

server <- function(input, output, session) {
  session$allowReconnect(TRUE)
  s <- sesion_nueva()

  ir_pantalla <- function(destino) {
    bslib::nav_select("pantalla", destino, session = session)
    session$sendCustomMessage("subir", TRUE)
  }
  ir_a <- function(destino) {
    bslib::nav_select("seccion", destino, session = session)
    session$sendCustomMessage("ir_a_seccion", destino)
  }

  marca <- new.env()  # marca$saliendo = TRUE cuando la persona sale a propósito
  salir <- function() {
    marca$saliendo <- TRUE
    sesion_salir(s)
    ir_pantalla("bienvenida")
  }

  # Si la sesión venció y no se pudo renovar, se vuelve a la bienvenida con un aviso amable.
  observeEvent(s$acceso, {
    if (!is.null(s$acceso)) return()
    if (isTRUE(marca$saliendo)) {
      marca$saliendo <- FALSE
      return()
    }
    showNotification("Tu sesión venció. Entra otra vez.", duration = 5, closeButton = FALSE)
    ir_pantalla("bienvenida")
  }, ignoreInit = TRUE, ignoreNULL = FALSE)

  output$shell <- renderUI({
    req(s$negocio)
    shell_ui(s$negocio)
  })

  observeEvent(input$nav_destino, {
    if (input$nav_destino %in% SECCIONES) bslib::nav_select("seccion", input$nav_destino)
  })
  observeEvent(input$accion_rapida, {
    if (identical(input$accion_rapida, "registrar_gasto")) {
      s$abrir_gasto <- isolate(s$abrir_gasto) + 1L  # abre el formulario de gastos
      ir_a("gastos")
    } else if (identical(input$accion_rapida, "cerrar_dia")) {
      s$abrir_cierre <- isolate(s$abrir_cierre) + 1L  # va a contar el efectivo (o a abrir)
      ir_a("caja")
    } else if (identical(input$accion_rapida, "registrar_compra")) {
      s$abrir_compra <- isolate(s$abrir_compra) + 1L  # abre el formulario de compras
      ir_a("compras")
    } else {
      aviso_pronto()
    }
  })

  output$fecha <- renderText({
    invalidateLater(60 * 60 * 1000)
    fecha_larga_es()
  })

  salud <- reactive({
    invalidateLater(60 * 1000)
    api_salud()
  })
  output$estado_conexion <- renderUI(estado_conexion_ui(salud()))

  mod_bienvenida_server("bienvenida", ir_pantalla)
  mod_registro_server("registro", s, ir_pantalla)
  mod_login_server("login", s, ir_pantalla)
  mod_onboarding_server("onboarding", s, ir_pantalla)
  mod_inicio_server("inicio", s, ir_a, seccion = reactive(input$seccion))
  mod_vender_server("vender", s, ir_a)
  mod_productos_server("productos", s, ir_a)
  mod_gastos_server("gastos", s, ir_a)
  mod_inventario_server("inventario", s, ir_a)
  mod_compras_server("compras", s, ir_a)
  mod_impuestos_server("impuestos", s, ir_a)
  mod_caja_server("caja", s, ir_a, seccion = reactive(input$seccion))
  mod_dueno_server("dueno", s, ir_a)
  mod_margen_server("margen", s, ir_a)
  mod_mas_server("mas", salir, ir_a)
}

shinyApp(ui, server)
