# IntegraT — app Shiny mobile-first (paso 4 de la Fase 1: sistema de diseño y navegación).
# Los archivos de R/ se cargan automáticamente. La app no se conecta a la base de datos:
# todo dato pasa por la API (API_BASE_URL).

library(shiny)

vocab <- vocabulario_defecto()

ui <- bslib::page(
  title = "IntegraT",
  lang = "es",
  theme = tema_integrat(),
  recursos_integrat(),
  htmltools::tags$div(id = "aviso-conexion", class = "aviso-conexion", role = "status",
                      "Se perdió la conexión. Reconectando…"),
  htmltools::tags$header(
    class = "app-encabezado",
    htmltools::tags$div(
      htmltools::tags$p(class = "app-encabezado__negocio", "Mi negocio"),
      htmltools::tags$p(class = "app-encabezado__fecha", textOutput("fecha", inline = TRUE))
    ),
    uiOutput("estado_conexion", inline = TRUE)
  ),
  htmltools::tags$main(
    class = "app-contenido",
    bslib::navset_hidden(
      id = "seccion",
      bslib::nav_panel_hidden("inicio", mod_inicio_ui("inicio", vocab)),
      bslib::nav_panel_hidden("vender", mod_vender_ui("vender", vocab)),
      bslib::nav_panel_hidden("productos", mod_productos_ui("productos", vocab)),
      bslib::nav_panel_hidden("mas", mod_mas_ui("mas"))
    )
  ),
  nav_inferior(vocab),
  hoja_acciones(vocab)
)

server <- function(input, output, session) {
  session$allowReconnect(TRUE)

  ir_a <- function(destino) {
    bslib::nav_select("seccion", destino, session = session)
    session$sendCustomMessage("ir_a_seccion", destino)
  }

  observeEvent(input$nav_destino, {
    if (input$nav_destino %in% SECCIONES) bslib::nav_select("seccion", input$nav_destino)
  })
  observeEvent(input$accion_rapida, aviso_pronto())

  output$fecha <- renderText({
    invalidateLater(60 * 60 * 1000)
    fecha_larga_es()
  })

  salud <- reactive({
    invalidateLater(60 * 1000)
    api_salud()
  })
  output$estado_conexion <- renderUI(estado_conexion_ui(salud()))

  mod_inicio_server("inicio", ir_a)
  mod_vender_server("vender", ir_a)
  mod_productos_server("productos")
  mod_mas_server("mas")
}

shinyApp(ui, server)
