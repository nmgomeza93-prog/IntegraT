# Compras a mano ("Lo que compraste", dentro de Más y desde la acción rápida "Registrar compra"):
# registrar con varias líneas y una pantalla de revisión, ver el mes, el detalle, anular y los
# proveedores (docs/PLAN_COMPRAS.md). La API suma el total, sube el inventario y recalcula el costo;
# la suma de la pantalla de revisión solo es un adelanto de lo que se va a guardar.

PROVEEDOR_NUEVO <- "__nuevo__"

# Total de las líneas escritas (solo para mostrarlo antes de guardar): "Q 280.00"
total_compra <- function(lineas) {
  formato_dinero(sum(vapply(lineas, function(l) as.numeric(l$costo_total), 0)))
}

# Opciones del selector de insumo: id con nombre
opciones_insumo <- function(insumos) {
  stats::setNames(vapply(insumos, function(i) i$id, ""), vapply(insumos, function(i) i$nombre, ""))
}

# Opciones del selector de proveedor: "Sin proveedor", los guardados y "Otro proveedor nuevo".
opciones_proveedor <- function(proveedores) {
  c("Sin proveedor" = "",
    stats::setNames(vapply(proveedores, function(p) p$id, ""),
                    vapply(proveedores, function(p) p$nombre, "")),
    "Otro proveedor nuevo" = PROVEEDOR_NUEVO)
}

# "Don Pedro · Factura A-123" o "Sin proveedor"
texto_compra <- function(compra) {
  proveedor <- if (is.character(compra$proveedor_nombre)) compra$proveedor_nombre else "Sin proveedor"
  if (is.character(compra$numero_factura)) paste0(proveedor, " · Factura ", compra$numero_factura)
  else proveedor
}

mod_compras_ui <- function(id) {
  ns <- shiny::NS(id)
  htmltools::tags$div(class = "compras", shiny::uiOutput(ns("contenido")))
}

mod_compras_server <- function(id, s, ir_a) {
  shiny::moduleServer(id, function(input, output, session) {
    ns <- session$ns
    vista <- shiny::reactiveVal("lista")  # lista, nueva, revisar, detalle o proveedores
    mes_pedido <- shiny::reactiveVal(NULL)  # NULL = el mes actual
    lineas <- shiny::reactiveVal(list())    # lo que se va comprando
    borrador <- shiny::reactiveVal(NULL)    # proveedor, fecha y factura al ir a revisar
    medio <- shiny::reactiveVal("efectivo")
    abierta <- shiny::reactiveVal(NULL)     # id de la compra del detalle
    error <- shiny::reactiveVal(NULL)
    por_anular <- shiny::reactiveVal(FALSE)
    refresco <- shiny::reactiveVal(0L)
    base_clave <- shiny::reactiveVal(NULL)

    nueva_clave <- function() {
      base_clave(paste(as.character(openssl::rand_bytes(16)), collapse = ""))
    }

    # Cuando cambia la persona o el negocio, la sección empieza de cero.
    shiny::observeEvent(s$negocio_id, {
      vista("lista")
      mes_pedido(NULL)
      lineas(list())
      borrador(NULL)
      medio("efectivo")
      abierta(NULL)
      error(NULL)
      por_anular(FALSE)
      nueva_clave()
    }, ignoreNULL = FALSE)

    # "Registrar compra" de la hoja de acciones rápidas: abre directo el formulario.
    shiny::observeEvent(s$abrir_compra, {
      if (s$abrir_compra == 0L) return()
      lineas(list())
      borrador(NULL)
      error(NULL)
      vista("nueva")
    }, ignoreInit = TRUE)

    datos <- shiny::reactive({
      refresco()
      s$negocio_id
      pedido <- mes_pedido()
      shiny::req(shiny::isolate(s$acceso))
      list(
        mes = sesion_llamar(s, "GET", "v1/compras",
                            consulta = if (!is.null(pedido)) list(mes = pedido)),
        proveedores = sesion_llamar(s, "GET", "v1/proveedores"),
        insumos = sesion_llamar(s, "GET", "v1/insumos"),
        unidades = sesion_llamar(s, "GET", "v1/unidades")
      )
    })

    insumos <- function() if (isTRUE(datos()$insumos$ok)) datos()$insumos$cuerpo$insumos else list()
    proveedores <- function() {
      if (isTRUE(datos()$proveedores$ok)) datos()$proveedores$cuerpo else list()
    }
    unidades <- function() if (isTRUE(datos()$unidades$ok)) datos()$unidades$cuerpo else list()

    unidades_del_insumo <- function(insumo_id) {
      insumo <- Filter(function(i) identical(i$id, insumo_id), insumos())
      if (length(insumo) == 0) return(NULL)
      propia <- Filter(function(u) identical(u$codigo, insumo[[1]]$unidad_codigo), unidades())
      list(
        opciones = opciones_unidad(unidades(), if (length(propia) > 0) propia[[1]]$tipo),
        seleccion = insumo[[1]]$unidad_codigo
      )
    }

    clave_idempotencia <- function(cuerpo) {
      huella <- openssl::sha256(charToRaw(paste(base_clave(), jsonlite::toJSON(cuerpo, auto_unbox = TRUE),
                                                sep = "|")))
      paste0("compra-", substr(as.character(huella), 1, 40))
    }

    ir_a_vista <- function(nueva) {
      vista(nueva)
      session$sendCustomMessage("subir", TRUE)
    }

    # --- Lista del mes -------------------------------------------------------------------
    ui_lista <- function() {
      d <- datos()
      volver <- enlace_atras(ns("volver"), "Más")
      titulo <- htmltools::tags$h1(class = "pantalla__titulo", "Lo que compraste")
      if (!d$mes$ok) {
        return(htmltools::tagList(
          volver, titulo,
          estado_vacio("wifi-off", "No pudimos cargar tus compras", d$mes$mensaje,
                       boton_secundario(ns("reintentar"), "Intentar de nuevo", "arrow-repeat"))
        ))
      }
      mes <- d$mes$cuerpo
      es_actual <- identical(mes$mes, mes_actual())
      htmltools::tagList(
        volver, titulo,
        htmltools::tags$div(
          class = "selector-mes",
          htmltools::tags$button(
            id = ns("mes_anterior"), type = "button", class = "boton-cantidad action-button",
            `aria-label` = "Mes anterior", icono("chevron-left")
          ),
          htmltools::tags$span(class = "selector-mes__nombre", nombre_mes(mes$mes)),
          htmltools::tags$button(
            id = ns("mes_siguiente"), type = "button", class = "boton-cantidad action-button",
            `aria-label` = "Mes siguiente", disabled = if (es_actual) NA, icono("chevron-right")
          )
        ),
        boton_primario(ns("nueva"), "Registrar una compra", "plus-lg"),
        if (mes$resumen$cantidad == 0 && length(mes$compras) == 0) {
          estado_vacio(
            "receipt", paste("No hay compras en", tolower(nombre_mes(mes$mes))),
            "Anota lo que compras para cocinar o vender: tu inventario y tus costos se ponen al día solos."
          )
        } else {
          htmltools::tagList(
            tarjeta_numero(
              paste("Compraste en", tolower(strsplit(nombre_mes(mes$mes), " de ")[[1]][1])),
              formato_dinero(as.numeric(mes$resumen$total)),
              contexto = texto_cantidad(mes$resumen$cantidad, "compra", "compras")
            ),
            htmltools::tags$ul(
              class = "lista-opciones",
              lapply(mes$compras, function(co) {
                item_lista(
                  if (identical(co$estado, "anulada")) "x-circle" else "receipt",
                  paste0(fecha_corta(co$fecha), " · ", texto_compra(co),
                         if (identical(co$estado, "anulada")) " · Anulada"),
                  formato_dinero(as.numeric(co$total)),
                  `data-elige-input` = ns("abrir"), `data-elige-valor` = co$id
                )
              })
            )
          )
        },
        enlace_accion(ns("ir_proveedores"), "Mis proveedores", "people")
      )
    }

    # --- Formulario ----------------------------------------------------------------------
    ui_nueva <- function() {
      b <- shiny::isolate(borrador())
      insumos_ <- insumos()
      if (length(insumos_) == 0 && isTRUE(datos()$insumos$ok)) {
        return(htmltools::tagList(
          enlace_atras(ns("atras")),
          htmltools::tags$h1(class = "pantalla__titulo", "Registrar una compra"),
          estado_vacio("basket", "Primero anota tus insumos",
                       "Una compra sube las existencias de tus insumos. Agrégalos en Inventario y vuelve.",
                       boton_primario(ns("ir_inventario"), "Ir a Inventario", "basket"))
        ))
      }
      primero <- if (length(insumos_) > 0) unidades_del_insumo(insumos_[[1]]$id) else NULL
      seleccionado <- shiny::isolate(medio())
      htmltools::tagList(
        enlace_atras(ns("atras")),
        htmltools::tags$h1(class = "pantalla__titulo", "Registrar una compra"),
        htmltools::tags$div(
          class = "pila",
          htmltools::tags$div(
            class = "campo",
            shiny::selectInput(ns("proveedor"), "¿A quién le compraste?",
                               choices = opciones_proveedor(proveedores()),
                               selected = b$proveedor %||% "", selectize = FALSE, width = "100%")
          ),
          shiny::conditionalPanel(
            condition = sprintf("input['%s'] == '%s'", ns("proveedor"), PROVEEDOR_NUEVO),
            campo_texto(ns("prov_nombre"), "Nombre del proveedor", valor = b$prov_nombre %||% "",
                        placeholder = "Ejemplo: Don Pedro", autocompletar = "off"),
            campo_texto(ns("prov_telefono"), "Teléfono (opcional)", valor = b$prov_telefono %||% "",
                        autocompletar = "off", modo = "tel")
          ),
          htmltools::tags$h2(class = "hoja__titulo separado", "Lo que compraste"),
          shiny::uiOutput(ns("lineas")),
          htmltools::tags$section(
            class = "tarjeta",
            htmltools::tags$h2(class = "hoja__titulo", "Agregar un insumo"),
            htmltools::tags$div(
              class = "pila",
              htmltools::tags$div(
                class = "campo",
                shiny::selectInput(ns("ins"), "Insumo", choices = opciones_insumo(insumos_),
                                   selectize = FALSE, width = "100%")
              ),
              campo_texto(ns("cant"), "¿Cuánto compraste?", placeholder = "Ejemplo: 10",
                          autocompletar = "off", modo = "decimal"),
              htmltools::tags$div(
                class = "campo",
                shiny::selectInput(ns("uni"), "En", choices = primero$opciones,
                                   selected = primero$seleccion, selectize = FALSE, width = "100%")
              ),
              campo_texto(ns("costo"), "¿Cuánto costó todo esto? (Q)", placeholder = "Ejemplo: 150",
                          autocompletar = "off", modo = "decimal"),
              shiny::uiOutput(ns("error_linea")),
              boton_secundario(ns("agregar_linea"), "Agregar a la compra", "plus-lg")
            )
          ),
          htmltools::tags$h2(class = "hoja__titulo separado", "Pago y fecha"),
          htmltools::tags$div(
            class = "campo",
            htmltools::tags$label(id = ns("medio-etiqueta"), "¿Cómo pagaste?"),
            htmltools::tags$div(
              class = "segmentado", role = "group", `aria-labelledby` = ns("medio-etiqueta"),
              lapply(names(MEDIOS_GASTO_UI), function(m) {
                htmltools::tags$button(
                  type = "button", class = "segmentado__opcion",
                  `data-elige-input` = ns("medio"), `data-elige-valor` = m,
                  `aria-pressed` = if (identical(seleccionado, m)) "true" else "false",
                  MEDIOS_GASTO_UI[[m]]
                )
              })
            )
          ),
          campo_fecha(ns("fecha"), "¿Cuándo?", valor = b$fecha %||% hoy_local(),
                      maximo = hoy_local()),
          campo_texto(ns("factura"), "Número de factura (opcional)", valor = b$factura %||% "",
                      autocompletar = "off"),
          shiny::uiOutput(ns("error")),
          boton_primario(ns("revisar"), "Revisar la compra", "check2-square")
        )
      )
    }

    output$lineas <- shiny::renderUI({
      actuales <- lineas()
      if (length(actuales) == 0) {
        return(htmltools::tags$p(class = "entrada__texto", "Aún no agregas nada."))
      }
      htmltools::tagList(
        htmltools::tags$ul(
          class = "lista-opciones lista-receta",
          lapply(actuales, function(l) {
            htmltools::tags$li(
              class = "linea-receta",
              htmltools::tags$span(
                class = "linea-receta__texto", l$nombre,
                htmltools::tags$span(class = "linea-receta__detalle",
                                     cantidad_con_unidad(l$cantidad, l$unidad_codigo))
              ),
              htmltools::tags$span(class = "linea-receta__costo",
                                   formato_dinero(as.numeric(l$costo_total))),
              htmltools::tags$button(
                type = "button", class = "boton-cantidad",
                `data-elige-input` = ns("quitar_linea"), `data-elige-valor` = l$insumo_id,
                `aria-label` = paste("Quitar", l$nombre), icono("x-lg")
              )
            )
          })
        ),
        htmltools::tags$p(class = "compras__total", paste("Total:", total_compra(actuales)))
      )
    })

    # --- Revisión ------------------------------------------------------------------------
    ui_revisar <- function() {
      b <- borrador()
      actuales <- lineas()
      proveedor <- if (identical(b$proveedor, PROVEEDOR_NUEVO)) {
        trimws(b$prov_nombre %||% "")
      } else if (nzchar(b$proveedor %||% "")) {
        elegido <- Filter(function(p) identical(p$id, b$proveedor), proveedores())
        if (length(elegido) > 0) elegido[[1]]$nombre else "Sin proveedor"
      } else {
        "Sin proveedor"
      }
      htmltools::tagList(
        enlace_atras(ns("corregir"), "Corregir"),
        htmltools::tags$h1(class = "pantalla__titulo", "Revisa tu compra"),
        htmltools::tags$div(
          class = "pila",
          tarjeta_numero(
            "Vas a anotar", total_compra(actuales),
            contexto = paste0(proveedor, " · ", fecha_corta(b$fecha), " · ",
                              MEDIOS_GASTO_UI[[medio()]],
                              if (nzchar(b$factura %||% "")) paste0(" · Factura ", b$factura))
          ),
          htmltools::tags$ul(
            class = "lista-opciones",
            lapply(actuales, function(l) {
              fila_lista("basket", l$nombre,
                         paste0(cantidad_con_unidad(l$cantidad, l$unidad_codigo), " · ",
                                formato_dinero(as.numeric(l$costo_total))))
            })
          ),
          htmltools::tags$p(class = "entrada__texto",
                            "Al guardar, tu inventario sube y el costo de cada insumo se actualiza."),
          shiny::uiOutput(ns("error")),
          boton_primario(ns("guardar"), "Guardar la compra", "check-lg"),
          boton_secundario(ns("corregir_boton"), "Corregir", "pencil")
        )
      )
    }

    # --- Detalle -------------------------------------------------------------------------
    ui_detalle <- function() {
      todas <- if (isTRUE(datos()$mes$ok)) datos()$mes$cuerpo$compras else list()
      encontradas <- Filter(function(co) identical(co$id, abierta()), todas)
      volver <- enlace_atras(ns("atras_detalle"), "Compras")
      if (length(encontradas) == 0) {
        return(htmltools::tagList(volver, estado_vacio("receipt", "No encontramos esa compra", "")))
      }
      co <- encontradas[[1]]
      anulada <- identical(co$estado, "anulada")
      htmltools::tagList(
        volver,
        htmltools::tags$h1(class = "pantalla__titulo", paste("Compra del", fecha_corta(co$fecha))),
        htmltools::tags$div(
          class = "pila",
          tarjeta_numero(
            "Total", formato_dinero(as.numeric(co$total)),
            contexto = paste0(texto_compra(co), " · ", MEDIOS_GASTO_UI[[co$medio_pago]]),
            estado = if (anulada) etiqueta_estado("Anulada", "neutro")
          ),
          htmltools::tags$ul(
            class = "lista-opciones",
            lapply(co$lineas, function(l) {
              fila_lista("basket", l$nombre,
                         paste0(cantidad_con_unidad(l$cantidad, l$unidad_codigo), " · ",
                                formato_dinero(as.numeric(l$costo_total))))
            })
          ),
          if (anulada) {
            htmltools::tags$p(class = "entrada__texto",
                              paste0("Motivo: ", co$motivo_anulacion))
          } else {
            ui_anular()
          }
        )
      )
    }

    ui_anular <- function() {
      if (!por_anular()) {
        return(boton_secundario(ns("anular"), "Anular esta compra", "x-circle"))
      }
      htmltools::tags$section(
        class = "tarjeta",
        htmltools::tags$h2(class = "hoja__titulo", "¿Anular esta compra?"),
        htmltools::tags$p(class = "entrada__texto",
                          "Tu inventario vuelve a como estaba antes de esta compra. No se borra nada."),
        htmltools::tags$div(
          class = "pila",
          campo_texto(ns("motivo"), "¿Por qué la anulas?", placeholder = "Ejemplo: Me equivoqué",
                      autocompletar = "off"),
          shiny::uiOutput(ns("error")),
          boton_primario(ns("confirmar_anular"), "Sí, anular", "x-circle"),
          boton_secundario(ns("cancelar_anular"), "No, dejarla", "x-lg")
        )
      )
    }

    # --- Proveedores ---------------------------------------------------------------------
    ui_proveedores <- function() {
      lista <- proveedores()
      htmltools::tagList(
        enlace_atras(ns("atras_proveedores"), "Compras"),
        htmltools::tags$h1(class = "pantalla__titulo", "Mis proveedores"),
        htmltools::tags$div(
          class = "pila",
          if (length(lista) == 0) {
            htmltools::tags$p(class = "entrada__texto", "Aún no tienes proveedores.")
          } else {
            htmltools::tags$ul(
              class = "lista-opciones",
              lapply(lista, function(p) {
                fila_lista("person", p$nombre, if (is.character(p$telefono)) p$telefono)
              })
            )
          },
          htmltools::tags$h2(class = "hoja__titulo separado", "Agregar un proveedor"),
          campo_texto(ns("nuevo_prov_nombre"), "Nombre", placeholder = "Ejemplo: Don Pedro",
                      autocompletar = "off"),
          campo_texto(ns("nuevo_prov_telefono"), "Teléfono (opcional)", autocompletar = "off",
                      modo = "tel"),
          shiny::uiOutput(ns("error")),
          boton_primario(ns("guardar_proveedor"), "Guardar proveedor", "check-lg")
        )
      )
    }

    output$contenido <- shiny::renderUI({
      switch(vista(), lista = ui_lista(), nueva = ui_nueva(), revisar = ui_revisar(),
             detalle = ui_detalle(), proveedores = ui_proveedores())
    })
    output$error <- shiny::renderUI(mensaje_error(error()))
    error_linea <- shiny::reactiveVal(NULL)
    output$error_linea <- shiny::renderUI(mensaje_error(error_linea()))

    # --- Acciones ------------------------------------------------------------------------
    shiny::observeEvent(input$volver, ir_a("mas"))
    shiny::observeEvent(input$reintentar, refresco(refresco() + 1L))
    shiny::observeEvent(input$ir_inventario, ir_a("inventario"))

    shiny::observeEvent(input$mes_anterior, {
      mes <- datos()$mes$cuerpo$mes %||% mes_actual()
      mes_pedido(mes_desplazado(mes, -1L))
    })
    shiny::observeEvent(input$mes_siguiente, {
      mes <- datos()$mes$cuerpo$mes %||% mes_actual()
      siguiente <- mes_desplazado(mes, 1L)
      if (siguiente <= mes_actual()) mes_pedido(siguiente)
    })

    shiny::observeEvent(input$nueva, {
      lineas(list())
      borrador(NULL)
      error(NULL)
      error_linea(NULL)
      ir_a_vista("nueva")
    })
    shiny::observeEvent(input$atras, {
      error(NULL)
      ir_a_vista("lista")
    })
    shiny::observeEvent(input$medio, {
      if (input$medio %in% names(MEDIOS_GASTO_UI)) medio(input$medio)
    })

    # Al cambiar de insumo, la unidad se ajusta a su tipo (peso, líquido o piezas)
    shiny::observeEvent(input$ins, {
      u <- unidades_del_insumo(input$ins)
      if (is.null(u)) return()
      shiny::updateSelectInput(session, "uni", choices = u$opciones, selected = u$seleccion)
    })

    shiny::observeEvent(input$agregar_linea, {
      if (vista() != "nueva") return()
      insumo_id <- input$ins %||% ""
      encontrado <- Filter(function(i) identical(i$id, insumo_id), insumos())
      if (length(encontrado) == 0) return(error_linea("Elige un insumo."))
      cantidad <- normalizar_cantidad(input$cant)
      if (is.null(cantidad) || as.numeric(cantidad) <= 0) {
        return(error_linea("Escribe cuánto compraste con números, por ejemplo 10 o 2.5."))
      }
      costo <- normalizar_precio(input$costo)
      if (is.null(costo)) {
        return(error_linea("Escribe cuánto costó con números, por ejemplo 150 o 150.50."))
      }
      error_linea(NULL)
      error(NULL)
      actual <- lineas()
      actual[[length(actual) + 1L]] <- list(
        insumo_id = insumo_id, nombre = encontrado[[1]]$nombre, cantidad = cantidad,
        unidad_codigo = input$uni %||% encontrado[[1]]$unidad_codigo, costo_total = costo
      )
      lineas(actual)
      shiny::updateTextInput(session, "cant", value = "")
      shiny::updateTextInput(session, "costo", value = "")
    })

    shiny::observeEvent(input$quitar_linea, {
      lineas(Filter(function(l) !identical(l$insumo_id, input$quitar_linea), lineas()))
    })

    shiny::observeEvent(input$revisar, {
      if (vista() != "nueva") return()
      if (length(lineas()) == 0) return(error("Agrega al menos un insumo a la compra."))
      proveedor <- input$proveedor %||% ""
      if (identical(proveedor, PROVEEDOR_NUEVO) && nchar(trimws(input$prov_nombre %||% "")) < 2) {
        return(error("Escribe el nombre del proveedor."))
      }
      fecha <- trimws(input$fecha %||% "")
      if (!grepl("^[0-9]{4}-[0-9]{2}-[0-9]{2}$", fecha)) return(error("Elige la fecha de la compra."))
      if (fecha > hoy_local()) return(error("La fecha no puede ser de mañana en adelante."))
      borrador(list(proveedor = proveedor, prov_nombre = input$prov_nombre %||% "",
                    prov_telefono = input$prov_telefono %||% "", fecha = fecha,
                    factura = trimws(input$factura %||% "")))
      error(NULL)
      ir_a_vista("revisar")
    })

    shiny::observeEvent(input$corregir, ir_a_vista("nueva"))
    shiny::observeEvent(input$corregir_boton, ir_a_vista("nueva"))

    shiny::observeEvent(input$guardar, {
      if (vista() != "revisar") return()  # un doble toque llega cuando ya se guardó
      b <- borrador()
      actuales <- lineas()
      if (length(actuales) == 0) return()
      cuerpo <- list(
        lineas = lapply(actuales, function(l) {
          list(insumo_id = l$insumo_id, cantidad = l$cantidad, unidad_codigo = l$unidad_codigo,
               costo_total = l$costo_total)
        }),
        medio_pago = medio(), fecha = b$fecha
      )
      if (identical(b$proveedor, PROVEEDOR_NUEVO)) {
        telefono <- trimws(b$prov_telefono %||% "")
        cuerpo$proveedor_nuevo <- c(list(nombre = trimws(b$prov_nombre)),
                                    if (nzchar(telefono)) list(telefono = telefono))
      } else if (nzchar(b$proveedor %||% "")) {
        cuerpo$proveedor_id <- b$proveedor
      }
      if (nzchar(b$factura %||% "")) cuerpo$numero_factura <- b$factura
      r <- sesion_llamar(s, "POST", "v1/compras", cuerpo,
                         cabeceras = list("Idempotency-Key" = clave_idempotencia(cuerpo)))
      if (!r$ok) return(error(r$mensaje))
      error(NULL)
      lineas(list())
      borrador(NULL)
      mes_pedido(substr(b$fecha, 1, 7))  # se ve el mes donde quedó la compra
      refresco(refresco() + 1L)
      sesion_actualizar_pasos(s)
      ir_a_vista("lista")
      nueva_clave()
      shiny::showNotification(
        paste0("Anotaste la compra de ", formato_dinero(as.numeric(r$cuerpo$total)),
               ". Tu inventario ya está al día."),
        duration = 5, closeButton = FALSE, id = "compra-aviso"
      )
    })

    shiny::observeEvent(input$abrir, {
      abierta(input$abrir)
      por_anular(FALSE)
      error(NULL)
      ir_a_vista("detalle")
    })
    shiny::observeEvent(input$atras_detalle, {
      abierta(NULL)
      por_anular(FALSE)
      error(NULL)
      ir_a_vista("lista")
    })
    shiny::observeEvent(input$anular, por_anular(TRUE))
    shiny::observeEvent(input$cancelar_anular, por_anular(FALSE))
    shiny::observeEvent(input$confirmar_anular, {
      if (vista() != "detalle" || is.null(abierta())) return()
      motivo <- trimws(input$motivo %||% "")
      if (nchar(motivo) < 3) return(error("Cuéntanos por qué la anulas (al menos 3 letras)."))
      r <- sesion_llamar(s, "POST", paste0("v1/compras/", abierta(), "/anular"),
                         list(motivo = motivo))
      if (!r$ok) return(error(r$mensaje))
      error(NULL)
      por_anular(FALSE)
      refresco(refresco() + 1L)
      sesion_actualizar_pasos(s)
      shiny::showNotification("Anulaste la compra. Tu inventario volvió a como estaba.",
                              duration = 5, closeButton = FALSE, id = "compra-aviso")
    })

    shiny::observeEvent(input$ir_proveedores, {
      error(NULL)
      ir_a_vista("proveedores")
    })
    shiny::observeEvent(input$atras_proveedores, {
      error(NULL)
      ir_a_vista("lista")
    })
    shiny::observeEvent(input$guardar_proveedor, {
      if (vista() != "proveedores") return()
      nombre <- trimws(input$nuevo_prov_nombre %||% "")
      if (nchar(nombre) < 2) return(error("Escribe el nombre del proveedor."))
      telefono <- trimws(input$nuevo_prov_telefono %||% "")
      r <- sesion_llamar(s, "POST", "v1/proveedores",
                         c(list(nombre = nombre), if (nzchar(telefono)) list(telefono = telefono)))
      if (!r$ok) return(error(r$mensaje))
      error(NULL)
      refresco(refresco() + 1L)
      shiny::showNotification(paste0("Agregaste a ", r$cuerpo$nombre, "."), duration = 5,
                              closeButton = FALSE, id = "compra-aviso")
    })
  })
}
