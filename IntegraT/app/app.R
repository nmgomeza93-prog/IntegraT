# IntegraT — app Shiny (interfaz mobile-first).
# Paso 1 de la Fase 1: pantalla mínima para verificar que el entorno funciona.
# El sistema de diseño y la navegación llegan en el paso 4 (docs/PLAN_FASE1.md).

library(shiny)
library(bslib)

ui <- page_fillable(
  theme = bs_theme(version = 5, primary = "#3346D3"),
  lang = "es",
  title = "IntegraT",
  div(
    class = "d-flex flex-column justify-content-center align-items-center h-100 text-center p-4",
    h1("Hola IntegraT"),
    p(class = "text-muted", "Tú vendes; nosotros hacemos las cuentas.")
  )
)

server <- function(input, output, session) {}

shinyApp(ui, server)
