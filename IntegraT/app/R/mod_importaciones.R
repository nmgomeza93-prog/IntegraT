# Importaciones (SHEIN, TEMU… por casillero) con la plantilla de factura (docs/PLAN_IMPORTACION.md).
# Subir la plantilla → revisar (nombres y categorías sugeridos, cobro de la tarjeta en Q) → en camino
# → "Me llegó el paquete" (courier, qué llegó) → productos listos para vender con su precio sugerido.
# La API lee el archivo, reparte costos y crea los productos; la app solo muestra y confirma.

PLATAFORMAS_UI <- c(shein = "SHEIN", temu = "TEMU", amazon = "Amazon", aliexpress = "AliExpress")
MEDIOS_IMPORTACION_UI <- c(tarjeta = "Tarjeta", transferencia = "Transferencia", efectivo = "Efectivo")

nombre_plataforma <- function(codigo) {
  codigo <- codigo %||% "importación"
  if (codigo %in% names(PLATAFORMAS_UI)) unname(PLATAFORMAS_UI[[codigo]]) else tools::toTitleCase(codigo)
}

texto_estado_importacion <- function(estado) {
  switch(estado %||% "",
    en_camino = etiqueta_estado("En camino", "atencion"),
    llegando = etiqueta_estado("Llegó una parte", "atencion"),
    recibida = etiqueta_estado("Recibida", "bien"),
    recibida_parcial = etiqueta_estado("Llegó incompleta", "alerta"),
    anulada = etiqueta_estado("Anulada", "neutro"),
    NULL)
}

# "M · Rosa ×2 · MX$ 70.30"
texto_linea_previa <- function(l, moneda) {
  partes <- c(unlist(l$atributos), paste0("×", l$cantidad),
              paste(moneda, formatC(as.numeric(l$precio_unitario), format = "f", digits = 2)))
  paste(partes, collapse = " · ")
}

mod_importaciones_ui <- function(id) {
  ns <- shiny::NS(id)
  htmltools::tags$div(class = "importaciones", shiny::uiOutput(ns("contenido")))
}

mod_importaciones_server <- function(id, s, ir_a) {
  shiny::moduleServer(id, function(input, output, session) {
    ns <- session$ns
    vista <- shiny::reactiveVal("lista")   # "lista", "revisar", "detalle" o "recibir"
    previa <- shiny::reactiveVal(NULL)     # respuesta de la vista previa
    abierta <- shiny::reactiveVal(NULL)    # la importación del detalle
    error <- shiny::reactiveVal(NULL)
    refresco <- shiny::reactiveVal(0L)
    medio <- shiny::reactiveVal("tarjeta")
    medio_courier <- shiny::reactiveVal("efectivo")
    reparto <- shiny::reactiveVal("valor")
    llego_todo <- shiny::reactiveVal(TRUE)
    base_clave <- shiny::reactiveVal(NULL)
    nueva_base <- function() base_clave(paste(as.character(openssl::rand_bytes(16)), collapse = ""))

    shiny::observeEvent(s$negocio_id, {
      vista("lista")
      previa(NULL)
      abierta(NULL)
      error(NULL)
      nueva_base()
    }, ignoreNULL = FALSE)

    ir_a_vista <- function(nueva) {
      vista(nueva)
      session$sendCustomMessage("subir", TRUE)
    }

    clave <- function(...) {
      huella <- openssl::sha256(charToRaw(paste(base_clave(), ..., sep = "|")))
      paste0("importacion-", substr(as.character(huella), 1, 40))
    }

    lista <- shiny::reactive({
      refresco()
      s$al_dia  # al entrar, al día con lo que se guardó en otra pantalla
      s$negocio_id
      shiny::req(vista() == "lista", shiny::isolate(s$acceso))
      sesion_llamar(s, "GET", "v1/importaciones")
    })

    categorias <- shiny::reactive({
      shiny::req(vista() == "revisar")
      propias <- sesion_llamar(s, "GET", "v1/categorias")
      sugeridas <- sesion_llamar(s, "GET", "v1/categorias/sugeridas")
      nombres <- c(if (propias$ok) vapply(propias$cuerpo, function(c) c$nombre, ""),
                   if (sugeridas$ok) vapply(sugeridas$cuerpo, function(c) c$nombre, ""))
      unique(nombres)
    })

    titulo <- function(texto) htmltools::tags$h1(class = "pantalla__titulo", texto)

    # --- Lista: subir y lo que viene en camino --------------------------------------------
    tarjeta_importacion <- function(i) {
      item_lista(
        "box-seam",
        paste0(nombre_plataforma(i$plataforma), if (!is.null(i$numero_orden)) paste0(" · ", i$numero_orden),
               " · ", i$unidades, if (i$unidades == 1) " artículo" else " artículos"),
        htmltools::tagList(texto_estado_importacion(i$estado),
                           if (i$estado %in% c("en_camino", "llegando")) paste0(" ", i$dias_en_camino, " días"),
                           " ", formato_dinero(as.numeric(i$total_q))),
        `data-elige-input` = ns("abrir"), `data-elige-valor` = i$id)
    }

    ui_lista <- function() {
      r <- lista()
      htmltools::tagList(
        enlace_atras(ns("volver")),
        titulo("Importaciones"),
        htmltools::tags$p(class = "entrada__texto",
                          "Sube la plantilla de tu factura (SHEIN, TEMU…). Te mostramos los productos ",
                          "antes de guardar, y al llegar el paquete quedan listos para vender."),
        htmltools::tags$div(
          class = "campo subir-plantilla",
          shiny::fileInput(ns("archivo"), "Plantilla de la factura (.xlsx o .csv)",
                           accept = c(".xlsx", ".csv"), buttonLabel = "Elegir archivo",
                           placeholder = "Ningún archivo", width = "100%")
        ),
        mensaje_error(error()),
        if (!r$ok) mensaje_error(r$mensaje) else htmltools::tagList(
          htmltools::tags$h2(class = "hoja__titulo separado", "En camino"),
          if (length(r$cuerpo$en_camino) == 0) {
            htmltools::tags$p(class = "entrada__texto", "No tienes paquetes en camino.")
          } else {
            htmltools::tags$ul(class = "lista-opciones", lapply(r$cuerpo$en_camino, tarjeta_importacion))
          },
          if (length(r$cuerpo$recibidas) > 0) htmltools::tagList(
            htmltools::tags$h2(class = "hoja__titulo separado", "Recibidas"),
            htmltools::tags$ul(class = "lista-opciones", lapply(r$cuerpo$recibidas, tarjeta_importacion))
          )
        )
      )
    }

    # --- Revisar la vista previa ----------------------------------------------------------
    ui_revisar <- function() {
      p <- previa()
      e <- p$encabezado
      cats <- categorias()
      seleccionado <- shiny::isolate(medio())
      htmltools::tagList(
        enlace_atras(ns("atras")),
        titulo("Revisa tu importación"),
        tarjeta_numero(
          paste(nombre_plataforma(e$plataforma), "·", e$numero_orden %||% e$numero_factura %||% ""),
          paste(e$moneda_codigo, formatC(as.numeric(p$cuadre$total_calculado), format = "f",
                                         digits = 2, big.mark = ",")),
          contexto = paste0(length(p$productos), " productos · ", p$unidades, " artículos · ",
                            "envío y cargos ", e$moneda_codigo, " ", p$cuadre$cargos),
          estado = if (isTRUE(p$cuadre$cuadra)) etiqueta_estado("Cuadra", "bien")
                   else etiqueta_estado("No cuadra", "alerta")),
        lapply(p$avisos, function(a) htmltools::tags$p(class = "mensaje-error", role = "alert", a)),
        campo_texto(ns("cobro_q"), paste0("¿Cuánto te cobró tu tarjeta en quetzales? (Q)"),
                    placeholder = "Ejemplo: 1150.40", autocompletar = "off", modo = "decimal"),
        htmltools::tags$p(class = "entrada__texto",
                          "Con eso calculamos el tipo de cambio real de tu compra."),
        htmltools::tags$div(
          class = "campo",
          htmltools::tags$label(id = ns("medio-etiqueta"), "¿Cómo lo pagaste?"),
          htmltools::tags$div(
            class = "segmentado", role = "group", `aria-labelledby` = ns("medio-etiqueta"),
            lapply(names(MEDIOS_IMPORTACION_UI), function(m) {
              htmltools::tags$button(type = "button", class = "segmentado__opcion",
                                     `data-elige-input` = ns("medio"), `data-elige-valor` = m,
                                     `aria-pressed` = if (identical(seleccionado, m)) "true" else "false",
                                     MEDIOS_IMPORTACION_UI[[m]])
            })
          )
        ),
        htmltools::tags$h2(class = "hoja__titulo separado", "Productos"),
        htmltools::tags$p(class = "entrada__texto",
                          "Revisa el nombre y la categoría de cada uno; puedes cambiarlos."),
        lapply(seq_along(p$productos), function(i) {
          prod <- p$productos[[i]]
          opciones <- unique(c("Sin categoría" = "", stats::setNames(cats, cats),
                               if (!is.null(prod$categoria)) stats::setNames(prod$categoria, prod$categoria)))
          htmltools::tags$section(
            class = "tarjeta producto-importado",
            if (isTRUE(prod$existente)) etiqueta_estado("Ya lo tienes", "bien"),
            campo_texto(ns(paste0("nom_", i)), "Nombre", valor = prod$nombre, autocompletar = "off"),
            htmltools::tags$div(
              class = "campo",
              shiny::selectInput(ns(paste0("cat_", i)), "Categoría", choices = opciones,
                                 selected = prod$categoria %||% "", selectize = FALSE, width = "100%")
            ),
            htmltools::tags$ul(
              class = "lineas-importadas",
              lapply(prod$lineas, function(l) htmltools::tags$li(texto_linea_previa(l, e$moneda_codigo)))
            )
          )
        }),
        mensaje_error(error()),
        boton_primario(ns("confirmar"), "Guardar: viene en camino", "truck")
      )
    }

    # --- Detalle y recibir ----------------------------------------------------------------
    ui_detalle <- function() {
      i <- abierta()
      en_camino <- i$estado %in% c("en_camino", "llegando")
      htmltools::tagList(
        enlace_atras(ns("atras")),
        titulo(paste(nombre_plataforma(i$plataforma), i$numero_orden %||% "")),
        tarjeta_numero(
          "Pagaste", formato_dinero(as.numeric(i$total_q)),
          contexto = paste0(i$moneda_codigo, " ", i$total_factura, " al cambio de ", i$tipo_cambio,
                            if (!is.null(i$courier_q)) paste0(" · courier ",
                                                              formato_dinero(as.numeric(i$courier_q)))),
          estado = texto_estado_importacion(i$estado)),
        htmltools::tags$ul(
          class = "lista-opciones",
          fila_lista("receipt", "Factura", i$numero_factura %||% "—"),
          fila_lista("calendar", if (en_camino) "Días en camino" else "Recibida",
                     if (en_camino) as.character(i$dias_en_camino)
                     else substr(i$recibida_en %||% "", 1, 10)),
          if (!is.null(i$guia)) fila_lista("upc", "Guía", i$guia),
          if (isTRUE(i$pendientes > 0) && identical(i$estado, "llegando")) {
            fila_lista("hourglass-split", "Falta que llegue", paste(i$pendientes, "artículos"))
          }
        ),
        if (length(i$entregas) > 0) htmltools::tagList(
          htmltools::tags$h2(class = "hoja__titulo separado", "Entregas"),
          htmltools::tags$ul(
            class = "lista-opciones",
            lapply(i$entregas, function(e) {
              fila_lista("box-seam",
                         paste0("Entrega ", e$numero, " \u00b7 ", e$unidades, " artículos",
                                if (!is.null(e$guia)) paste0(" \u00b7 ", e$guia),
                                if (isTRUE(e$cierra)) " \u00b7 cerró la importación"),
                         paste("courier", formato_dinero(as.numeric(e$courier_q))))
            })
          )
        ),
        htmltools::tags$h2(class = "hoja__titulo separado", "Productos"),
        htmltools::tags$ul(
          class = "lista-opciones",
          lapply(i$lineas, function(l) {
            llego <- if (isTRUE(l$pendiente > 0) || isTRUE(l$cantidad_perdida > 0)) {
              paste0(l$cantidad_recibida %||% 0L, " de ", l$cantidad, " llegaron \u00b7 ")
            } else ""
            detalle <- if (!is.null(l$costo_unitario_q)) {
              paste0(llego, "cuesta ", formato_dinero(as.numeric(l$costo_unitario_q)),
                     if (!is.null(l$precio_sugerido)) paste0(" · vende en ",
                                                             formato_dinero(as.numeric(l$precio_sugerido))))
            } else paste0(llego, "\u00d7", l$cantidad)
            fila_lista("tag", l$nombre, detalle)
          })
        ),
        if (en_camino) boton_primario(
          ns("ir_recibir"),
          if (identical(i$estado, "llegando")) "Llegó otra parte" else "Me llegó el paquete",
          "box-seam"),
        if (identical(i$estado, "en_camino")) {
          boton_secundario(ns("anular"), "Anular esta importación", "x-circle")
        }
      )
    }

    ui_recibir <- function() {
      i <- abierta()
      sel <- shiny::isolate(medio_courier())
      con_peso <- length(i$lineas) > 0 &&
        all(vapply(i$lineas, function(l) !is.null(l$peso), NA))
      sel_reparto <- shiny::isolate(reparto())
      htmltools::tagList(
        enlace_atras(ns("atras_detalle")),
        titulo("Me llegó el paquete"),
        campo_texto(ns("courier"), "¿Cuánto te cobró el courier o casillero? (Q)", placeholder = "Ejemplo: 180",
                    autocompletar = "off", modo = "decimal"),
        campo_texto(ns("envio_local"), "Envío hasta tu casa (Q, opcional)", placeholder = "0",
                    autocompletar = "off", modo = "decimal"),
        htmltools::tags$div(
          class = "campo",
          htmltools::tags$label(id = ns("mc-etiqueta"), "¿Cómo pagaste el courier?"),
          htmltools::tags$div(
            class = "segmentado", role = "group", `aria-labelledby` = ns("mc-etiqueta"),
            lapply(names(MEDIOS_IMPORTACION_UI), function(m) {
              htmltools::tags$button(type = "button", class = "segmentado__opcion",
                                     `data-elige-input` = ns("medio_courier"), `data-elige-valor` = m,
                                     `aria-pressed` = if (identical(sel, m)) "true" else "false",
                                     MEDIOS_IMPORTACION_UI[[m]])
            })
          )
        ),
        campo_texto(ns("guia"), "Número de guía (opcional)", autocompletar = "off"),
        htmltools::tags$div(
          class = "casilla",
          shiny::checkboxInput(ns("todo"), "Llegó todo lo que faltaba", value = TRUE, width = "100%")
        ),
        shiny::uiOutput(ns("que_llego")),
        if (con_peso) htmltools::tags$div(
          class = "campo",
          htmltools::tags$label(id = ns("rep-etiqueta"), "Repartir el courier por"),
          htmltools::tags$div(
            class = "segmentado", role = "group", `aria-labelledby` = ns("rep-etiqueta"),
            htmltools::tags$button(type = "button", class = "segmentado__opcion",
                                   `data-elige-input` = ns("reparto"), `data-elige-valor` = "valor",
                                   `aria-pressed` = if (identical(sel_reparto, "valor")) "true" else "false",
                                   "Valor"),
            htmltools::tags$button(type = "button", class = "segmentado__opcion",
                                   `data-elige-input` = ns("reparto"), `data-elige-valor` = "peso",
                                   `aria-pressed` = if (identical(sel_reparto, "peso")) "true" else "false",
                                   "Peso")
          )
        ),
        mensaje_error(error()),
        boton_primario(ns("confirmar_recibir"), "Guardar: ya lo tengo", "check-lg")
      )
    }

    output$que_llego <- shiny::renderUI({
      if (isTRUE(input$todo)) return(NULL)
      i <- abierta()
      htmltools::tagList(
        htmltools::tags$p(class = "entrada__texto", "Escribe cuántos llegaron en este paquete:"),
        lapply(seq_along(i$lineas), function(k) {
          l <- i$lineas[[k]]
          if (!isTRUE(l$pendiente > 0)) return(NULL)
          campo_texto(ns(paste0("llego_", k)), paste0(l$nombre, " (faltan ", l$pendiente, ")"),
                      valor = l$pendiente, autocompletar = "off", modo = "numeric")
        }),
        htmltools::tags$div(
          class = "casilla",
          shiny::checkboxInput(ns("cerrar"), "Lo que falta ya no va a llegar", value = FALSE,
                               width = "100%")
        )
      )
    })

    output$contenido <- shiny::renderUI({
      switch(vista(), revisar = ui_revisar(), detalle = ui_detalle(), recibir = ui_recibir(),
             ui_lista())
    })

    # --- Acciones -------------------------------------------------------------------------
    shiny::observeEvent(input$volver, ir_a("mas"))
    shiny::observeEvent(input$atras, {
      error(NULL)
      ir_a_vista("lista")
    })
    shiny::observeEvent(input$atras_detalle, {
      error(NULL)
      ir_a_vista("detalle")
    })
    shiny::observeEvent(input$medio, if (input$medio %in% names(MEDIOS_IMPORTACION_UI)) medio(input$medio))
    shiny::observeEvent(input$reparto, if (input$reparto %in% c("valor", "peso")) reparto(input$reparto))
    shiny::observeEvent(input$medio_courier, {
      if (input$medio_courier %in% names(MEDIOS_IMPORTACION_UI)) medio_courier(input$medio_courier)
    })

    shiny::observeEvent(input$archivo, {
      a <- input$archivo
      if (is.null(a)) return()
      r <- sesion_subir(s, "v1/importaciones/vista-previa", a$datapath, a$name)
      if (!r$ok) return(error(r$mensaje))
      error(NULL)
      previa(r$cuerpo)
      nueva_base()
      ir_a_vista("revisar")
    })

    shiny::observeEvent(input$confirmar, {
      if (vista() != "revisar") return()
      p <- previa()
      e <- p$encabezado
      cobro <- normalizar_precio(input$cobro_q)
      if (is.null(cobro) || as.numeric(cobro) <= 0) {
        return(error("Escribe cuánto te cobró la tarjeta en quetzales, por ejemplo 1150.40."))
      }
      productos <- lapply(seq_along(p$productos), function(i) {
        prod <- p$productos[[i]]
        nombre <- trimws(input[[paste0("nom_", i)]] %||% prod$nombre)
        categoria <- input[[paste0("cat_", i)]] %||% prod$categoria %||% ""
        list(nombre = if (nzchar(nombre)) nombre else prod$nombre,
             categoria = if (nzchar(categoria)) categoria else NULL,
             item_id = prod$item_id,
             lineas = lapply(prod$lineas, function(l) list(
               codigo = l$codigo, descripcion = l$descripcion, atributos = l$atributos,
               cantidad = l$cantidad, precio_unitario = l$precio_unitario,
               item_variante_id = l$item_variante_id, peso = l$peso)))
      })
      cuerpo <- list(plataforma = e$plataforma, numero_factura = e$numero_factura,
                     numero_orden = e$numero_orden, fecha_factura = e$fecha_factura,
                     moneda_codigo = e$moneda_codigo, garantia_envio = e$garantia_envio,
                     costo_importacion = e$costo_importacion, otros_cobros = e$otros_cobros,
                     cobro_q = cobro, medio_pago = medio(), productos = productos)
      r <- sesion_llamar(s, "POST", "v1/importaciones", cuerpo,
                         cabeceras = list("Idempotency-Key" = clave("confirmar", e$numero_orden, cobro)))
      if (!r$ok) return(error(r$mensaje))
      error(NULL)
      previa(NULL)
      refresco(refresco() + 1L)
      s$cuentas_v <- shiny::isolate(s$cuentas_v) + 1L
      ir_a_vista("lista")
      shiny::showNotification("Listo: tu importación viene en camino.", duration = 4,
                              closeButton = FALSE, id = "importacion-aviso")
    })

    shiny::observeEvent(input$abrir, {
      r <- sesion_llamar(s, "GET", paste0("v1/importaciones/", input$abrir))
      if (!r$ok) return(error(r$mensaje))
      error(NULL)
      abierta(r$cuerpo)
      ir_a_vista("detalle")
    })

    shiny::observeEvent(input$ir_recibir, {
      error(NULL)
      nueva_base()
      ir_a_vista("recibir")
    })

    shiny::observeEvent(input$confirmar_recibir, {
      if (vista() != "recibir") return()
      i <- abierta()
      courier <- normalizar_precio(input$courier %||% "0") %||% if (!nzchar(trimws(input$courier %||% ""))) "0"
      envio <- normalizar_precio(input$envio_local %||% "0") %||% if (!nzchar(trimws(input$envio_local %||% ""))) "0"
      if (is.null(courier) || is.null(envio)) {
        return(error("Escribe los montos con números, por ejemplo 180 o 180.50."))
      }
      lineas <- NULL  # sin lista: llegó todo lo que faltaba
      cerrar <- FALSE
      if (!isTRUE(input$todo)) {
        lineas <- list()
        for (k in seq_along(i$lineas)) {
          pend <- i$lineas[[k]]$pendiente %||% 0L
          if (pend <= 0) next
          n <- suppressWarnings(as.integer(input[[paste0("llego_", k)]]))
          if (is.na(n) || n < 0 || n > pend) {
            return(error(paste0("Revisa cuántos llegaron de ", i$lineas[[k]]$nombre, ".")))
          }
          if (n > 0) lineas[[length(lineas) + 1L]] <- list(linea_id = i$lineas[[k]]$id, cantidad = n)
        }
        cerrar <- isTRUE(input$cerrar)
        if (length(lineas) == 0 && !cerrar) return(error("Dinos qué llegó en este paquete."))
      }
      guia <- trimws(input$guia %||% "")
      r <- sesion_llamar(s, "POST", paste0("v1/importaciones/", i$id, "/recibir"),
                         c(list(courier_q = courier, envio_local_q = envio, medio_pago = medio_courier(),
                                guia = if (nzchar(guia)) guia else NULL, cerrar = cerrar,
                                reparto = reparto()),
                           if (!is.null(lineas)) list(lineas = lineas)),
                         cabeceras = list("Idempotency-Key" = clave("recibir", i$id, courier,
                                                                    length(i$entregas))))
      if (!r$ok) return(error(r$mensaje))
      error(NULL)
      abierta(r$cuerpo)
      refresco(refresco() + 1L)
      s$catalogo_v <- shiny::isolate(s$catalogo_v) + 1L
      s$cuentas_v <- shiny::isolate(s$cuentas_v) + 1L
      sesion_actualizar_pasos(s)
      ir_a_vista("detalle")
      shiny::showNotification("¡Listo! Tus productos ya están para vender.", duration = 5,
                              closeButton = FALSE, id = "importacion-aviso")
    })

    shiny::observeEvent(input$anular, {
      i <- abierta()
      r <- sesion_llamar(s, "POST", paste0("v1/importaciones/", i$id, "/anular"),
                         list(motivo = "Anulada desde la app"))
      if (!r$ok) return(error(r$mensaje))
      abierta(r$cuerpo)
      refresco(refresco() + 1L)
      s$cuentas_v <- shiny::isolate(s$cuentas_v) + 1L
    })
  })
}
