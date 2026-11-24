# Tema bslib de IntegraT (tokens en www/css/tokens.css; docs/DISENO_UX.md §5).

tema_integrat <- function() {
  bslib::bs_theme(
    version = 5,
    primary = "#3346D3",
    success = "#15803D",
    warning = "#B45309",
    danger = "#B91C1C",
    bg = "#F6F7F9",
    fg = "#111827",
    base_font = c("Inter", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"),
    "font-size-base" = "1.0625rem",
    "border-radius" = "12px",
    "border-radius-lg" = "16px",
    "btn-padding-y" = "0.75rem",
    "link-decoration" = "none"
  )
}

# Hojas de estilo y scripts propios (servidos desde www/, sin CDN).
recursos_integrat <- function() {
  htmltools::tagList(
    htmltools::tags$meta(name = "viewport",
                         content = "width=device-width, initial-scale=1, viewport-fit=cover"),
    htmltools::tags$meta(name = "theme-color", content = "#3346D3"),
    htmltools::tags$link(rel = "stylesheet", href = "css/tokens.css"),
    htmltools::tags$link(rel = "stylesheet", href = "css/base.css"),
    htmltools::tags$link(rel = "stylesheet", href = "css/componentes.css"),
    htmltools::tags$link(rel = "stylesheet", href = "css/navegacion.css"),
    htmltools::tags$script(src = "js/app.js", defer = NA)
  )
}
