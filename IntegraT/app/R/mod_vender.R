# Vender: elegir productos o platillos, cobrar y ver lo vendido hoy (docs/PLAN_VENTAS.md).
# La app NO calcula el total que se cobra: solo lo muestra. La API lo calcula con el precio
# vigente y lo congela; lo que se muestra al confirmar es lo que responde la API.

MEDIOS_PAGO_UI <- list(
  efectivo = list(titulo = "Efectivo", icono = "cash-coin"),
  tarjeta = list(titulo = "Tarjeta", icono = "credit-card"),
  transferencia = list(titulo = "Transferencia", icono = "bank")
)

# "1 platillo" / "3 platillos"
texto_cantidad <- function(n, singular, plural) {
  paste(n, if (n == 1) singular else plural)
}

# Total para MOSTRAR (la API recalcula el verdadero al cobrar).
total_lineas <- function(lineas) {
  round(sum(vapply(lineas, function(l) l$precio * l$cantidad, 0)), 2)
}

# Hora local de una fecha ISO en UTC ("2026-11-24T20:01:03.75Z") -> "14:01".
hora_local <- function(iso, zona = ZONA_HORARIA_DEFECTO) {
  limpio <- sub("(Z|[+]00:00)$", "", sub("[.][0-9]+", "", iso))
  momento <- as.POSIXct(limpio, format = "%Y-%m-%dT%H:%M:%S", tz = "UTC")
  format(momento, "%H:%M", tz = zona)
}

# Aviso amable cuando el cobro dejó a algún insumo sin existencia (la venta ya se cobró).
aviso_insumos_en_falta <- function(nombres) {
  nombres <- unlist(nombres)
  if (length(nombres) == 0) return(NULL)
  lista <- if (length(nombres) == 1) nombres else {
    paste0(paste(utils::head(nombres, -1), collapse = ", "), " y ", utils::tail(nombres, 1))
  }
  htmltools::tags$section(
    class = "tarjeta aviso-insumos", role = "status",
    etiqueta_estado("Se acabó", "atencion"),
    htmltools::tags$p(class = "entrada__texto", paste0(
      "Con esta venta se acabó: ", lista, ". Anota una compra en Inventario para reponerlo."
    ))
  )
}

mod_vender_ui <- function(id, vocab) {
  ns <- shiny::NS(id)
  htmltools::tags$div(class = "vender", shiny::uiOutput(ns("contenido")))
}

mod_vender_server <- function(id, s, ir_a) {
  shiny::moduleServer(id, function(input, output, session) {
    ns <- session$ns
    vista <- shiny::reactiveVal("catalogo")  # "catalogo", "cobro", "listo" o "hoy"
    carrito <- shiny::reactiveVal(list())    # id del ítem -> cantidad
    medio <- shiny::reactiveVal("efectivo")  # el último usado queda elegido
    error <- shiny::reactiveVal(NULL)
    ultima <- shiny::reactiveVal(NULL)       # la venta recién cobrada (respuesta de la API)
    refresco <- shiny::reactiveVal(0L)
    base_clave <- shiny::reactiveVal(NULL)
    venta_abierta <- shiny::reactiveVal(NULL)  # la venta que se ve en el detalle
    por_anular <- shiny::reactiveVal(FALSE)    # pidiendo confirmación para anular
    por_deshacer <- shiny::reactiveVal(FALSE)  # ídem, para deshacer la recién cobrada

    vocab <- shiny::reactive(vocab_negocio(shiny::req(s$negocio)))

    # Cuando cambia la persona o el negocio, se empieza de cero.
    shiny::observeEvent(s$negocio_id, {
      vista("catalogo")
      carrito(list())
      medio("efectivo")
      error(NULL)
      ultima(NULL)
      venta_abierta(NULL)
      por_anular(FALSE)
      por_deshacer(FALSE)
      base_clave(paste(as.character(openssl::rand_bytes(16)), collapse = ""))
    }, ignoreNULL = FALSE)

    datos <- shiny::reactive({
      refresco()
      s$negocio_id
      s$catalogo_v
      shiny::req(shiny::isolate(s$acceso))
      list(
        items = sesion_llamar(s, "GET", "v1/items", consulta = list(limite = 200)),
        categorias = sesion_llamar(s, "GET", "v1/categorias")
      )
    })

    items_por_id <- function() {
      lista <- datos()$items$cuerpo$items
      stats::setNames(lista, vapply(lista, function(i) i$id, ""))
    }

    lineas_carrito <- function() {
      items <- items_por_id()
      lineas <- list()
      for (id in names(carrito())) {
        item <- items[[id]]
        if (is.null(item)) next
        lineas[[length(lineas) + 1L]] <- list(
          id = id, nombre = item$nombre, cantidad = carrito()[[id]],
          precio = as.numeric(item$precio_venta)
        )
      }
      lineas
    }

    # Clave de idempotencia: el mismo carrito y medio en el mismo intento = la misma venta (un
    # doble toque o un reintento tras perder la respuesta no cobra dos veces).
    clave_idempotencia <- function(lineas, medio_pago) {
      huella <- openssl::sha256(charToRaw(paste(
        base_clave(), medio_pago,
        paste(vapply(lineas, function(l) paste0(l$id, ":", l$cantidad), ""), collapse = ","),
        sep = "|"
      )))
      paste0("venta-", substr(as.character(huella), 1, 40))
    }

    ir_a_vista <- function(nueva) {
      vista(nueva)
      session$sendCustomMessage("subir", TRUE)
    }

    # --- Pantallas ---------------------------------------------------------------------
    ui_catalogo <- function() {
      v <- vocab()
      d <- datos()
      if (!d$items$ok) {
        return(htmltools::tagList(
          htmltools::tags$h1(class = "pantalla__titulo", "Vender"),
          estado_vacio("wifi-off", paste("No pudimos cargar tus", v$item_plural), d$items$mensaje,
                       boton_secundario(ns("reintentar"), "Intentar de nuevo", "arrow-repeat"))
        ))
      }
      items <- d$items$cuerpo$items
      if (length(items) == 0) {
        return(htmltools::tagList(
          htmltools::tags$h1(class = "pantalla__titulo", "Vender"),
          estado_vacio(
            "cart3", paste("Aún no tienes", v$item_plural, "para vender"),
            paste0("Agrega tus ", v$item_plural, " y aquí podrás registrar una venta con 3 toques."),
            boton_primario(ns("agregar"), paste("Agregar mi primer", v$item_singular), "plus-lg")
          ),
          enlace_accion(ns("ver_hoy"), "Lo vendido hoy", "receipt")
        ))
      }
      htmltools::tagList(
        htmltools::tags$div(
          class = "vender__encabezado",
          htmltools::tags$h1(class = "pantalla__titulo", "Vender"),
          enlace_accion(ns("ver_hoy"), "Lo vendido hoy", "receipt")
        ),
        htmltools::tags$p(class = "entrada__texto", paste0("Toca un ", v$item_singular,
                                                           " para sumarlo a la venta.")),
        if (length(items) >= 8) {
          htmltools::tags$div(
            class = "campo catalogo__buscador",
            shiny::textInput(ns("buscar"), NULL, placeholder = paste("Buscar", v$item_singular),
                             width = "100%")
          )
        },
        shiny::uiOutput(ns("grilla")),
        shiny::uiOutput(ns("barra"))
      )
    }

    output$grilla <- shiny::renderUI({
      v <- vocab()
      items <- datos()$items$cuerpo$items
      consulta <- sin_tildes(trimws(input$buscar %||% ""))
      if (nzchar(consulta)) {
        items <- Filter(function(i) grepl(consulta, sin_tildes(i$nombre), fixed = TRUE), items)
        if (length(items) == 0) {
          return(htmltools::tags$p(class = "catalogo__sin-resultados",
                                   "No encontramos nada con ese nombre."))
        }
      }
      en_carrito <- carrito()
      categorias <- if (isTRUE(datos()$categorias$ok)) datos()$categorias$cuerpo else list()
      grupos <- agrupar_items(items, categorias)
      htmltools::tagList(lapply(grupos, function(g) {
        htmltools::tagList(
          if (nzchar(g$titulo)) htmltools::tags$h2(class = "catalogo__grupo", g$titulo),
          htmltools::tags$ul(
            class = "lista-opciones",
            lapply(g$items, function(i) {
              n <- en_carrito[[i$id]]
              item_lista(
                "tag", i$nombre,
                htmltools::tagList(
                  if (!is.null(n)) htmltools::tags$span(class = "cantidad-insignia", paste0("×", n)),
                  formato_dinero(as.numeric(i$precio_venta))
                ),
                `data-elige-input` = ns("agregar_item"), `data-elige-valor` = i$id
              )
            })
          )
        )
      }))
    })

    output$barra <- shiny::renderUI({
      v <- vocab()
      lineas <- lineas_carrito()
      if (length(lineas) == 0) return(NULL)
      unidades <- sum(vapply(lineas, function(l) l$cantidad, 0L))
      htmltools::tags$div(
        class = "barra-carrito",
        htmltools::tags$span(
          class = "barra-carrito__texto",
          paste0(texto_cantidad(unidades, v$item_singular, v$item_plural), " · ",
                 formato_dinero(total_lineas(lineas)))
        ),
        boton_primario(ns("ir_cobrar"), "Cobrar", "arrow-right")
      )
    })

    ui_cobro <- function() {
      lineas <- lineas_carrito()
      total <- total_lineas(lineas)
      htmltools::tagList(
        enlace_atras(ns("volver_catalogo"), "Seguir agregando"),
        htmltools::tags$h1(class = "pantalla__titulo", "Cobrar"),
        htmltools::tags$section(
          class = "tarjeta",
          htmltools::tags$ul(
            class = "lineas-carrito",
            lapply(lineas, function(l) {
              htmltools::tags$li(
                class = "linea-carrito",
                htmltools::tags$span(class = "linea-carrito__nombre", l$nombre),
                htmltools::tags$span(
                  class = "linea-carrito__control",
                  htmltools::tags$button(
                    type = "button", class = "boton-cantidad", `aria-label` = paste("Quitar uno de", l$nombre),
                    `data-elige-input` = ns("ajustar"), `data-elige-valor` = paste0("menos:", l$id),
                    icono("dash-lg")
                  ),
                  htmltools::tags$span(class = "linea-carrito__cantidad", l$cantidad),
                  htmltools::tags$button(
                    type = "button", class = "boton-cantidad", `aria-label` = paste("Agregar uno de", l$nombre),
                    `data-elige-input` = ns("ajustar"), `data-elige-valor` = paste0("mas:", l$id),
                    icono("plus-lg")
                  )
                ),
                htmltools::tags$span(class = "linea-carrito__total",
                                     formato_dinero(l$precio * l$cantidad))
              )
            })
          ),
          htmltools::tags$div(
            class = "total-venta",
            htmltools::tags$span("Total"),
            htmltools::tags$span(class = "total-venta__monto numero", formato_dinero(total))
          )
        ),
        htmltools::tags$h2(class = "hoja__titulo separado", "¿Cómo paga?"),
        htmltools::tags$div(
          class = "pila",
          lapply(names(MEDIOS_PAGO_UI), function(m) {
            opcion_grande(ns("medio"), m, MEDIOS_PAGO_UI[[m]]$icono, MEDIOS_PAGO_UI[[m]]$titulo,
                          activa = identical(medio(), m))
          })
        ),
        shiny::uiOutput(ns("error")),
        htmltools::tags$div(
          class = "barra-carrito barra-carrito--cobro",  # siempre a la vista, sin buscarlo
          boton_primario(ns("confirmar"), paste("Cobrar", formato_dinero(total)), "check-lg")
        )
      )
    }

    ui_listo <- function() {
      venta <- ultima()
      htmltools::tagList(
        estado_vacio(
          "check-circle", paste0("¡Vendiste ", formato_dinero(as.numeric(venta$total)), "!"),
          paste0("Venta ", venta$numero, " · ", MEDIOS_PAGO_UI[[venta$medio_pago]]$titulo)
        ),
        aviso_insumos_en_falta(venta$insumos_en_falta),
        if (por_deshacer()) {
          htmltools::tags$section(
            class = "tarjeta",
            htmltools::tags$h2(class = "hoja__titulo",
                               paste0("¿Deshacer la venta ", venta$numero, "?")),
            htmltools::tags$p(class = "entrada__texto",
                              "Quedará anulada y dejará de contar en tus ventas. No se borra nada."),
            shiny::uiOutput(ns("error")),
            htmltools::tags$div(
              class = "pila",
              boton_primario(ns("confirmar_deshacer"), "Sí, deshacer", "arrow-counterclockwise"),
              boton_secundario(ns("cancelar_deshacer"), "No, dejarla", "x-lg")
            )
          )
        } else {
          htmltools::tags$div(
            class = "pila",
            boton_primario(ns("otra"), "Otra venta", "plus-lg"),
            boton_secundario(ns("ver_hoy"), "Ver lo vendido hoy", "receipt"),
            enlace_accion(ns("deshacer"), "Deshacer esta venta", "arrow-counterclockwise")
          )
        }
      )
    }

    ui_detalle <- function() {
      venta <- venta_abierta()
      anulada <- identical(venta$estado, "anulada")
      htmltools::tagList(
        enlace_atras(ns("volver_hoy"), "Lo vendido hoy"),
        htmltools::tags$h1(class = "pantalla__titulo", paste("Venta", venta$numero)),
        htmltools::tags$p(
          etiqueta_estado(if (anulada) "Anulada" else "Cobrada", if (anulada) "alerta" else "bien"),
          htmltools::tags$span(
            class = "entrada__texto",
            paste0(" ", hora_local(venta$fecha_hora), " · ", MEDIOS_PAGO_UI[[venta$medio_pago]]$titulo)
          )
        ),
        htmltools::tags$section(
          class = "tarjeta",
          htmltools::tags$ul(
            class = "lineas-carrito",
            lapply(venta$lineas, function(l) {
              htmltools::tags$li(
                class = "linea-carrito",
                htmltools::tags$span(class = "linea-carrito__nombre", l$nombre),
                htmltools::tags$span(
                  class = "entrada__texto",
                  paste0(l$cantidad, " × ", formato_dinero(as.numeric(l$precio_unitario)))
                ),
                htmltools::tags$span(class = "linea-carrito__total",
                                     formato_dinero(as.numeric(l$total)))
              )
            })
          ),
          htmltools::tags$div(
            class = "total-venta",
            htmltools::tags$span("Total"),
            htmltools::tags$span(class = "total-venta__monto numero",
                                 formato_dinero(as.numeric(venta$total)))
          )
        ),
        if (anulada) {
          htmltools::tags$p(
            class = "entrada__texto separado",
            paste0("Anulada a las ", hora_local(venta$anulada_en), ". Motivo: ",
                   venta$motivo_anulacion)
          )
        } else if (!por_anular()) {
          htmltools::tags$div(class = "separado",
                              boton_secundario(ns("anular"), "Anular esta venta", "x-circle"))
        } else {
          htmltools::tags$section(
            class = "tarjeta separado",
            htmltools::tags$h2(class = "hoja__titulo", "¿Anular esta venta?"),
            htmltools::tags$p(
              class = "entrada__texto",
              "Dejará de contar en tus ventas. No se borra: queda guardada con el motivo."
            ),
            htmltools::tags$div(
              class = "pila",
              campo_texto(ns("motivo"), "¿Por qué la anulas?",
                          placeholder = "Ejemplo: me equivoqué de platillo", autocompletar = "off"),
              shiny::uiOutput(ns("error")),
              boton_primario(ns("confirmar_anular"), "Sí, anular", "x-circle"),
              boton_secundario(ns("cancelar_anular"), "No, dejarla", "x-lg")
            )
          )
        }
      )
    }

    ui_hoy <- function() {
      refresco()
      r <- sesion_llamar(s, "GET", "v1/ventas")
      if (!r$ok) {
        return(htmltools::tagList(
          enlace_atras(ns("volver_catalogo")),
          estado_vacio("wifi-off", "No pudimos cargar tus ventas", r$mensaje,
                       boton_secundario(ns("reintentar"), "Intentar de nuevo", "arrow-repeat"))
        ))
      }
      dia <- r$cuerpo
      resumen <- dia$resumen
      htmltools::tagList(
        enlace_atras(ns("volver_catalogo")),
        htmltools::tags$h1(class = "pantalla__titulo", "Lo vendido hoy"),
        tarjeta_numero(
          "Total de hoy", formato_dinero(as.numeric(resumen$total)),
          contexto = if (resumen$cantidad == 0) "Todavía no vendes nada hoy." else
            texto_cantidad(resumen$cantidad, "venta", "ventas")
        ),
        if (resumen$cantidad > 0) {
          htmltools::tags$ul(
            class = "lista-opciones separado",
            lapply(names(MEDIOS_PAGO_UI), function(m) {
              fila_lista(MEDIOS_PAGO_UI[[m]]$icono, MEDIOS_PAGO_UI[[m]]$titulo,
                         formato_dinero(as.numeric(resumen$por_medio[[m]])))
            })
          )
        },
        if (length(dia$ventas) > 0) {
          htmltools::tagList(
            htmltools::tags$h2(class = "hoja__titulo separado", "Ventas"),
            htmltools::tags$ul(
              class = "lista-opciones",
              lapply(dia$ventas, function(v) {
                anulada <- identical(v$estado, "anulada")
                item_lista(
                  if (anulada) "x-circle" else MEDIOS_PAGO_UI[[v$medio_pago]]$icono,
                  paste0("Venta ", v$numero, " · ", hora_local(v$fecha_hora)),
                  if (anulada) "Anulada" else formato_dinero(as.numeric(v$total)),
                  `data-elige-input` = ns("abrir_venta"), `data-elige-valor` = v$id
                )
              })
            )
          )
        }
      )
    }

    output$contenido <- shiny::renderUI({
      switch(vista(), catalogo = ui_catalogo(), cobro = ui_cobro(), listo = ui_listo(),
             hoy = ui_hoy(), detalle = ui_detalle())
    })
    output$error <- shiny::renderUI(mensaje_error(error()))

    # --- Acciones ----------------------------------------------------------------------
    shiny::observeEvent(input$agregar, ir_a("productos"))
    shiny::observeEvent(input$reintentar, refresco(refresco() + 1L))

    shiny::observeEvent(input$agregar_item, {
      id <- input$agregar_item
      if (is.null(items_por_id()[[id]])) return()
      actual <- carrito()
      actual[[id]] <- min((actual[[id]] %||% 0L) + 1L, 999L)
      carrito(actual)
    })

    shiny::observeEvent(input$ajustar, {
      partes <- strsplit(input$ajustar, ":", fixed = TRUE)[[1]]
      if (length(partes) != 2 || !partes[2] %in% names(carrito())) return()
      actual <- carrito()
      nueva <- (actual[[partes[2]]] %||% 0L) + if (partes[1] == "mas") 1L else -1L
      actual[[partes[2]]] <- if (nueva > 0L) min(nueva, 999L) else NULL
      carrito(actual)
      error(NULL)
      if (length(actual) == 0) ir_a_vista("catalogo")  # sin nada que cobrar
    })

    shiny::observeEvent(input$ir_cobrar, {
      if (length(lineas_carrito()) == 0) return()
      error(NULL)
      ir_a_vista("cobro")
    })
    shiny::observeEvent(input$volver_catalogo, {
      error(NULL)
      ir_a_vista("catalogo")
    })
    shiny::observeEvent(input$medio, {
      if (input$medio %in% names(MEDIOS_PAGO_UI)) medio(input$medio)
    })

    shiny::observeEvent(input$confirmar, {
      if (vista() != "cobro") return()  # un doble toque llega cuando ya se cobró
      lineas <- lineas_carrito()
      if (length(lineas) == 0) return()
      cuerpo <- list(
        lineas = lapply(lineas, function(l) list(item_id = l$id, cantidad = l$cantidad)),
        medio_pago = medio()
      )
      r <- sesion_llamar(
        s, "POST", "v1/ventas", cuerpo,
        cabeceras = list("Idempotency-Key" = clave_idempotencia(lineas, medio()))
      )
      if (!r$ok) {
        # Si algo ya no está disponible, se recarga la lista para que la persona lo vea.
        if (r$estado == 422L) refresco(refresco() + 1L)
        return(error(r$mensaje))
      }
      error(NULL)
      ultima(r$cuerpo)
      carrito(list())
      base_clave(paste(as.character(openssl::rand_bytes(16)), collapse = ""))
      sesion_actualizar_pasos(s)
      ir_a_vista("listo")
    })

    # Anula una venta con su motivo. TRUE si se anuló (si no, deja el error visible).
    anular <- function(venta, motivo) {
      r <- sesion_llamar(s, "POST", paste0("v1/ventas/", venta$id, "/anular"),
                         list(motivo = motivo))
      if (!r$ok) {
        error(r$mensaje)
        return(FALSE)
      }
      error(NULL)
      refresco(refresco() + 1L)
      sesion_actualizar_pasos(s)  # sin ventas vigentes, "Haz tu primera venta" vuelve a faltar
      shiny::showNotification(paste0("Anulaste la venta ", venta$numero, "."), duration = 5,
                              closeButton = FALSE, id = "venta-aviso")
      TRUE
    }

    shiny::observeEvent(input$abrir_venta, {
      r <- sesion_llamar(s, "GET", paste0("v1/ventas/", input$abrir_venta))
      if (!r$ok) {
        shiny::showNotification(r$mensaje, duration = 5, closeButton = FALSE, id = "venta-aviso")
        return()
      }
      venta_abierta(r$cuerpo)
      por_anular(FALSE)
      error(NULL)
      ir_a_vista("detalle")
    })
    shiny::observeEvent(input$volver_hoy, {
      error(NULL)
      refresco(refresco() + 1L)
      ir_a_vista("hoy")
    })
    shiny::observeEvent(input$anular, {
      error(NULL)
      por_anular(TRUE)
    })
    shiny::observeEvent(input$cancelar_anular, {
      error(NULL)
      por_anular(FALSE)
    })
    shiny::observeEvent(input$confirmar_anular, {
      if (vista() != "detalle" || !por_anular()) return()  # un doble toque llega ya anulada
      motivo <- trimws(input$motivo %||% "")
      if (nchar(motivo) < 3) return(error("Cuéntanos por qué la anulas (mínimo 3 letras)."))
      if (anular(venta_abierta(), motivo)) {
        por_anular(FALSE)
        ir_a_vista("hoy")
      }
    })

    shiny::observeEvent(input$deshacer, {
      error(NULL)
      por_deshacer(TRUE)
    })
    shiny::observeEvent(input$cancelar_deshacer, {
      error(NULL)
      por_deshacer(FALSE)
    })
    shiny::observeEvent(input$confirmar_deshacer, {
      if (vista() != "listo" || !por_deshacer() || is.null(ultima())) return()
      if (anular(ultima(), "Deshecha justo después de cobrar")) {
        por_deshacer(FALSE)
        ultima(NULL)
        ir_a_vista("catalogo")
      }
    })

    shiny::observeEvent(input$otra, {
      por_deshacer(FALSE)
      ir_a_vista("catalogo")
    })
    shiny::observeEvent(input$ver_hoy, {
      por_deshacer(FALSE)
      refresco(refresco() + 1L)
      ir_a_vista("hoy")
    })
  })
}
