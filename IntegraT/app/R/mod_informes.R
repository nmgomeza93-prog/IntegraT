# Informes (dentro de Más): el informe del mes. Los datos vienen de la API (`/v1/informes/mes` y
# `/v1/resultados`); las fórmulas (ticket promedio, proporciones) son de integrat.analitica.

# "Q 90.00 · 2" para un renglón de producto; "40 %" para una proporción.
porcentaje <- function(p) if (is.na(p)) "" else paste0(round(p * 100), " %")

mod_informes_ui <- function(id) {
  ns <- shiny::NS(id)
  htmltools::tags$div(class = "informes", shiny::uiOutput(ns("contenido")))
}

mod_informes_server <- function(id, s, ir_a) {
  shiny::moduleServer(id, function(input, output, session) {
    ns <- session$ns
    mes_pedido <- shiny::reactiveVal(NULL)  # NULL = este mes

    shiny::observeEvent(s$negocio_id, mes_pedido(NULL), ignoreNULL = FALSE)

    datos <- shiny::reactive({
      s$al_dia  # al entrar, al día con lo que se guardó en otra pantalla
      s$negocio_id
      shiny::req(shiny::isolate(s$acceso))
      consulta <- if (!is.null(mes_pedido())) list(mes = mes_pedido())
      list(informe = sesion_llamar(s, "GET", "v1/informes/mes", consulta = consulta),
           resultados = sesion_llamar(s, "GET", "v1/resultados", consulta = consulta))
    })

    output$contenido <- shiny::renderUI({
      d <- datos()
      atras <- enlace_atras(ns("atras"), "Más")
      if (!d$informe$ok) {
        return(htmltools::tagList(atras, htmltools::tags$h1(class = "pantalla__titulo", "Informes"),
                                  estado_vacio("lock", "No pudimos mostrar el informe",
                                               d$informe$mensaje)))
      }
      inf <- d$informe$cuerpo
      res <- if (d$resultados$ok) d$resultados$cuerpo else NULL
      es_actual <- inf$mes >= mes_actual()
      total <- as.numeric(inf$total)
      ticket <- ticket_promedio(inf$total, inf$ventas)

      htmltools::tagList(
        atras,
        htmltools::tags$h1(class = "pantalla__titulo", "Informe del mes"),
        htmltools::tags$div(
          class = "selector-mes",
          htmltools::tags$button(id = ns("mes_anterior"), type = "button",
                                 class = "boton-cantidad action-button",
                                 `aria-label` = "Mes anterior", icono("chevron-left")),
          htmltools::tags$span(class = "selector-mes__nombre", nombre_mes(inf$mes)),
          htmltools::tags$button(id = ns("mes_siguiente"), type = "button",
                                 class = "boton-cantidad action-button",
                                 `aria-label` = "Mes siguiente", disabled = if (es_actual) NA,
                                 icono("chevron-right"))
        ),
        if (inf$ventas == 0) {
          estado_vacio("bar-chart-line", paste("Sin ventas en", tolower(nombre_mes(inf$mes))),
                       "Cuando vendas, aquí verás lo que más se vende y quién te compra.")
        } else htmltools::tagList(
          tarjeta_numero(
            "Vendiste", formato_dinero(total),
            paste0(inf$ventas, if (inf$ventas == 1) " venta" else " ventas",
                   if (!is.na(ticket)) paste0(" · cada una deja ", formato_dinero(ticket),
                                              " en promedio"))
          ),
          if (!is.null(res)) htmltools::tags$ul(
            class = "lista-opciones separado",
            fila_lista("cart", "Gastaste", formato_dinero(as.numeric(res$gastaste))),
            fila_lista("piggy-bank", "Te queda", formato_dinero(as.numeric(res$te_queda)))
          ),
          htmltools::tags$h2(class = "hoja__titulo separado", "Lo que más vendiste"),
          htmltools::tags$ul(
            class = "lista-opciones",
            lapply(utils::head(inf$productos, 5), function(p) {
              fila_lista("bag-check", paste0(p$nombre, " ×", p$cantidad),
                         paste0(formato_dinero(as.numeric(p$total)), " · ",
                                porcentaje(proporcion_de(p$total, inf$total))))
            })
          ),
          htmltools::tags$h2(class = "hoja__titulo separado", "Quién te compró"),
          htmltools::tags$ul(
            class = "lista-opciones",
            lapply(utils::head(inf$clientes, 5), function(c) {
              fila_lista("person-check", c$nombre,
                         paste0(formato_dinero(as.numeric(c$total)), " · ", c$compras,
                                if (c$compras == 1) " compra" else " compras"))
            }),
            if (inf$consumidor_final$compras > 0) {
              fila_lista("person", "Consumidor final",
                         paste0(formato_dinero(as.numeric(inf$consumidor_final$total)), " · ",
                                inf$consumidor_final$compras,
                                if (inf$consumidor_final$compras == 1) " venta" else " ventas"))
            }
          ),
          htmltools::tags$h2(class = "hoja__titulo separado", "Cómo te pagaron"),
          htmltools::tags$ul(
            class = "lista-opciones",
            lapply(inf$medios, function(m) {
              info <- MEDIOS_PAGO_UI[[m$medio_pago]] %||% list(titulo = m$medio_pago, icono = "cash")
              fila_lista(info$icono, info$titulo,
                         paste0(formato_dinero(as.numeric(m$total)), " · ",
                                porcentaje(proporcion_de(m$total, inf$total))))
            })
          ),
          if (inf$anuladas > 0) {
            htmltools::tags$p(class = "entrada__texto separado", paste0(
              "No cuentan ", inf$anuladas, if (inf$anuladas == 1) " venta anulada." else " ventas anuladas."))
          }
        )
      )
    })

    shiny::observeEvent(input$atras, {
      mes_pedido(NULL)
      ir_a("mas")
    })
    shiny::observeEvent(input$mes_anterior, {
      mes <- mes_pedido() %||% mes_actual()
      mes_pedido(mes_desplazado(mes, -1L))
    })
    shiny::observeEvent(input$mes_siguiente, {
      siguiente <- mes_desplazado(mes_pedido() %||% mes_actual(), 1L)
      mes_pedido(if (siguiente >= mes_actual()) NULL else siguiente)
    })
  })
}
