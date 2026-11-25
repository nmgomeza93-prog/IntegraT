# Gastos ("Lo que gastaste"): el mes con su resumen por categoría, anotar, corregir y archivar
# (docs/PLAN_GASTOS.md). La app solo muestra los totales que calcula la API.

MEDIOS_GASTO_UI <- list(
  efectivo = "Efectivo",
  tarjeta = "Tarjeta",
  transferencia = "Transferencia"
)

# "2026-11" -> "Noviembre de 2026"
nombre_mes <- function(mes) {
  partes <- strsplit(mes, "-", fixed = TRUE)[[1]]
  nombre <- MESES_ES[as.integer(partes[2])]
  paste0(toupper(substr(nombre, 1, 1)), substring(nombre, 2), " de ", partes[1])
}

# "2026-11" y delta = -1 -> "2026-10"
mes_desplazado <- function(mes, delta) {
  partes <- as.integer(strsplit(mes, "-", fixed = TRUE)[[1]])
  indice <- partes[1] * 12L + (partes[2] - 1L) + as.integer(delta)
  sprintf("%04d-%02d", indice %/% 12L, indice %% 12L + 1L)
}

mes_actual <- function(ahora = Sys.time(), zona = ZONA_HORARIA_DEFECTO) {
  format(ahora, "%Y-%m", tz = zona)
}

hoy_local <- function(ahora = Sys.time(), zona = ZONA_HORARIA_DEFECTO) {
  format(ahora, "%Y-%m-%d", tz = zona)
}

# "2026-11-24" -> "24 nov"
fecha_corta <- function(fecha) {
  partes <- as.integer(strsplit(fecha, "-", fixed = TRUE)[[1]])
  paste(partes[3], substr(MESES_ES[partes[2]], 1, 3))
}

# Opciones del selector de categoría (id con nombre). Al editar un gasto cuya categoría ya fue
# archivada, esa categoría se agrega al final para que guardar no lo cambie de categoría sin avisar.
opciones_categoria <- function(categorias, gasto = NULL) {
  ids <- vapply(categorias, function(c) c$id, "")
  nombres <- vapply(categorias, function(c) c$nombre, "")
  actual <- gasto[["categoria_id"]]
  if (!is.null(actual) && !actual %in% ids) {
    ids <- c(ids, actual)
    nombres <- c(nombres, paste0(gasto[["categoria_nombre"]], " (archivada)"))
  }
  stats::setNames(ids, nombres)
}

# Campo de fecha del navegador (selector nativo del celular). No admite fechas futuras.
campo_fecha <- function(id, etiqueta, valor, maximo) {
  base <- shiny::textInput(id, etiqueta, value = valor, width = "100%")
  consulta <- htmltools::tagQuery(base)$find("input")
  base <- consulta$removeAttrs("type")$addAttrs(type = "date", max = maximo)$allTags()
  htmltools::tags$div(class = "campo", base)
}

mod_gastos_ui <- function(id) {
  ns <- shiny::NS(id)
  htmltools::tags$div(class = "gastos", shiny::uiOutput(ns("contenido")))
}

mod_gastos_server <- function(id, s, ir_a) {
  shiny::moduleServer(id, function(input, output, session) {
    ns <- session$ns
    vista <- shiny::reactiveVal("mes")   # "mes", "nuevo" o "editar"
    mes_pedido <- shiny::reactiveVal(NULL)  # NULL = el mes actual
    editando <- shiny::reactiveVal(NULL)
    error <- shiny::reactiveVal(NULL)
    por_archivar <- shiny::reactiveVal(FALSE)
    refresco <- shiny::reactiveVal(0L)
    base_clave <- shiny::reactiveVal(NULL)
    medio <- shiny::reactiveVal("efectivo")      # el último usado queda elegido
    # En el régimen general se pregunta si el gasto trae factura (IVA por cobrar).
    regimen_general <- function() identical(shiny::isolate(regimen_iva_actual(s)), "general")
    ultima_categoria <- shiny::reactiveVal(NULL)
    # Crear una categoría desde el formulario sin perder lo escrito
    cat_abierta <- shiny::reactiveVal(FALSE)
    error_cat <- shiny::reactiveVal(NULL)
    borrador <- shiny::reactiveVal(NULL)
    seleccion_cat <- shiny::reactiveVal(NULL)

    # Cuando cambia la persona o el negocio, la sección empieza de cero.
    shiny::observeEvent(s$negocio_id, {
      vista("mes")
      mes_pedido(NULL)
      editando(NULL)
      error(NULL)
      por_archivar(FALSE)
      medio("efectivo")
      ultima_categoria(NULL)
      limpiar_formulario()
      base_clave(paste(as.character(openssl::rand_bytes(16)), collapse = ""))
    }, ignoreNULL = FALSE)

    # "Registrar gasto" de la hoja de acciones rápidas: abre directo el formulario.
    shiny::observeEvent(s$abrir_gasto, {
      if (s$abrir_gasto == 0L) return()
      editando(NULL)
      error(NULL)
      por_archivar(FALSE)
      limpiar_formulario()
      vista("nuevo")
    }, ignoreInit = TRUE)

    datos <- shiny::reactive({
      refresco()
      s$negocio_id
      pedido <- mes_pedido()
      shiny::req(shiny::isolate(s$acceso))
      list(
        mes = sesion_llamar(s, "GET", "v1/gastos", consulta = if (!is.null(pedido)) list(mes = pedido)),
        categorias = sesion_llamar(s, "GET", "v1/gastos/categorias")
      )
    })

    lista_categorias <- function() {
      if (isTRUE(datos()$categorias$ok)) datos()$categorias$cuerpo else list()
    }

    limpiar_formulario <- function() {
      cat_abierta(FALSE)
      error_cat(NULL)
      borrador(NULL)
      seleccion_cat(NULL)
    }

    clave_idempotencia <- function(monto, categoria, medio_pago, fecha, nota, factura = FALSE) {
      huella <- openssl::sha256(charToRaw(paste(
        base_clave(), monto, categoria, medio_pago, fecha, nota, factura, sep = "|"
      )))
      paste0("gasto-", substr(as.character(huella), 1, 40))
    }

    ir_a_vista <- function(nueva) {
      vista(nueva)
      session$sendCustomMessage("subir", TRUE)
    }

    # --- Pantalla del mes --------------------------------------------------------------
    ui_mes <- function() {
      d <- datos()
      volver <- enlace_atras(ns("volver"), "Más")
      if (!d$mes$ok) {
        return(htmltools::tagList(
          volver,
          htmltools::tags$h1(class = "pantalla__titulo", "Lo que gastaste"),
          estado_vacio("wifi-off", "No pudimos cargar tus gastos", d$mes$mensaje,
                       boton_secundario(ns("reintentar"), "Intentar de nuevo", "arrow-repeat"))
        ))
      }
      mes <- d$mes$cuerpo
      resumen <- mes$resumen
      es_actual <- identical(mes$mes, mes_actual())
      htmltools::tagList(
        volver,
        htmltools::tags$h1(class = "pantalla__titulo", "Lo que gastaste"),
        htmltools::tags$div(
          class = "selector-mes",
          htmltools::tags$button(
            id = ns("mes_anterior"), type = "button", class = "boton-cantidad action-button",
            `aria-label` = "Mes anterior", icono("chevron-left")
          ),
          htmltools::tags$span(class = "selector-mes__nombre", nombre_mes(mes$mes)),
          htmltools::tags$button(
            id = ns("mes_siguiente"), type = "button", class = "boton-cantidad action-button",
            `aria-label` = "Mes siguiente", disabled = if (es_actual) NA,
            icono("chevron-right")
          )
        ),
        boton_primario(ns("nuevo"), "Anotar un gasto", "plus-lg"),
        if (resumen$cantidad == 0) {
          estado_vacio(
            "cash-coin", paste("No hay gastos en", tolower(nombre_mes(mes$mes))),
            "Anota la renta, los sueldos y lo que vas gastando: así sabrás cuánto te queda."
          )
        } else {
          htmltools::tagList(
            tarjeta_numero(
              paste("Gastaste en", tolower(strsplit(nombre_mes(mes$mes), " de ")[[1]][1])),
              formato_dinero(as.numeric(resumen$total)),
              contexto = paste0(
                texto_cantidad(resumen$cantidad, "gasto", "gastos"), " · Fijos ",
                formato_dinero(as.numeric(resumen$total_fijos)), " · Variables ",
                formato_dinero(as.numeric(resumen$total_variables))
              )
            ),
            htmltools::tags$h2(class = "hoja__titulo separado", "¿En qué gastaste más?"),
            htmltools::tags$ul(
              class = "lista-categorias",
              lapply(resumen$por_categoria, function(c) {
                htmltools::tags$li(
                  class = "categoria-gasto",
                  htmltools::tags$div(
                    class = "categoria-gasto__fila",
                    htmltools::tags$span(class = "categoria-gasto__nombre", c$nombre),
                    htmltools::tags$span(class = "categoria-gasto__monto",
                                         formato_dinero(as.numeric(c$total)))
                  ),
                  htmltools::tags$progress(
                    class = "categoria-gasto__barra", max = 100, value = c$porcentaje,
                    `aria-label` = paste0(c$nombre, ": ", c$porcentaje, " %")
                  ),
                  htmltools::tags$span(class = "categoria-gasto__porcentaje",
                                       paste0(c$porcentaje, " % de tus gastos"))
                )
              })
            ),
            htmltools::tags$h2(class = "hoja__titulo separado", "Todos tus gastos"),
            htmltools::tags$ul(
              class = "lista-opciones",
              lapply(mes$gastos, function(g) {
                item_lista(
                  "cash-coin",
                  paste0(fecha_corta(g$fecha), " · ", g$categoria_nombre,
                         if (is.character(g$descripcion)) paste0(" · ", g$descripcion)),
                  formato_dinero(as.numeric(g$monto)),
                  `data-elige-input` = ns("abrir"), `data-elige-valor` = g$id
                )
              })
            )
          )
        }
      )
    }

    # --- Formulario --------------------------------------------------------------------
    ui_formulario <- function() {
      g <- editando()
      categorias <- lista_categorias()
      opciones <- opciones_categoria(categorias, g)
      elegida <- shiny::isolate(seleccion_cat()) %||% g[["categoria_id"]] %||%
        shiny::isolate(ultima_categoria()) %||% (if (length(opciones) > 0) opciones[[1]] else "")
      seleccionado <- if (is.null(g)) shiny::isolate(medio()) else g$medio_pago
      b <- shiny::isolate(borrador())
      htmltools::tagList(
        enlace_atras(ns("atras")),
        htmltools::tags$h1(class = "pantalla__titulo", if (is.null(g)) "Anotar un gasto" else "Editar gasto"),
        htmltools::tags$div(
          class = "pila",
          campo_texto(ns("monto"), "¿Cuánto gastaste? (Q)",
                      valor = b$monto %||% g$monto %||% "", placeholder = "Ejemplo: 125 o 125.50",
                      autocompletar = "off", modo = "decimal"),
          if (length(opciones) > 0) {
            htmltools::tags$div(
              class = "campo",
              shiny::selectInput(ns("categoria"), "¿En qué lo gastaste?", choices = opciones,
                                 selected = elegida, selectize = FALSE, width = "100%")
            )
          },
          shiny::uiOutput(ns("nueva_categoria")),
          htmltools::tags$div(
            class = "campo",
            htmltools::tags$label(id = ns("medio-etiqueta"), "¿Cómo lo pagaste?"),
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
          campo_fecha(ns("fecha"), "¿Cuándo?", valor = b$fecha %||% g$fecha %||% hoy_local(),
                      maximo = hoy_local()),
          campo_texto(ns("nota"), "Nota (opcional)", valor = b$nota %||% g$descripcion %||% "",
                      placeholder = "Ejemplo: renta de noviembre", autocompletar = "off"),
          # Solo en el régimen general importa: con factura, el IVA se recupera.
          if (regimen_general()) {
            htmltools::tags$div(
              class = "casilla",
              shiny::checkboxInput(ns("factura"), "Me dieron factura con mi NIT",
                                   value = isTRUE(b$factura %||% g$con_factura), width = "100%")
            )
          },
          shiny::uiOutput(ns("error")),
          boton_primario(ns("guardar"), "Guardar", "check-lg"),
          if (!is.null(g)) ui_archivar(g)
        )
      )
    }

    ui_archivar <- function(g) {
      if (!por_archivar()) {
        return(boton_secundario(ns("archivar"), "Archivar este gasto", "archive"))
      }
      htmltools::tags$section(
        class = "tarjeta",
        htmltools::tags$h2(class = "hoja__titulo",
                           paste0("¿Archivar el gasto de ", formato_dinero(as.numeric(g$monto)), "?")),
        htmltools::tags$p(class = "entrada__texto",
                          "Ya no contará en tus gastos del mes. No se borra nada."),
        htmltools::tags$div(
          class = "pila",
          boton_primario(ns("confirmar_archivar"), "Sí, archivar", "archive"),
          boton_secundario(ns("cancelar_archivar"), "No, dejarlo", "x-lg")
        )
      )
    }

    output$contenido <- shiny::renderUI({
      switch(vista(), mes = ui_mes(), ui_formulario())
    })
    output$error <- shiny::renderUI(mensaje_error(error()))

    output$nueva_categoria <- shiny::renderUI({
      if (!cat_abierta()) {
        return(enlace_accion(ns("abrir_nueva_cat"), "Nueva categoría", "plus-lg"))
      }
      htmltools::tags$div(
        class = "pila",
        campo_texto(ns("nueva_cat"), "Nombre de la categoría", autocompletar = "off",
                    placeholder = "Ejemplo: Gasolina"),
        htmltools::tags$div(
          class = "casilla",
          shiny::checkboxInput(ns("nueva_cat_fija"), "Es un gasto fijo (se repite cada mes)",
                               value = FALSE, width = "100%")
        ),
        mensaje_error(error_cat()),
        boton_secundario(ns("crear_cat"), "Crear categoría", "check-lg"),
        enlace_accion(ns("cancelar_nueva_cat"), "Mejor no", "x-lg")
      )
    })

    # --- Acciones ----------------------------------------------------------------------
    shiny::observeEvent(input$volver, ir_a("mas"))
    shiny::observeEvent(input$reintentar, refresco(refresco() + 1L))

    shiny::observeEvent(input$mes_anterior, {
      mes <- datos()$mes$cuerpo$mes %||% mes_actual()
      mes_pedido(mes_desplazado(mes, -1L))
    })
    shiny::observeEvent(input$mes_siguiente, {
      mes <- datos()$mes$cuerpo$mes %||% mes_actual()
      siguiente <- mes_desplazado(mes, 1L)
      if (siguiente <= mes_actual()) mes_pedido(siguiente)
    })

    shiny::observeEvent(input$nuevo, {
      editando(NULL)
      error(NULL)
      por_archivar(FALSE)
      limpiar_formulario()
      ir_a_vista("nuevo")
    })
    shiny::observeEvent(input$abrir, {
      encontrados <- Filter(function(g) identical(g$id, input$abrir),
                            datos()$mes$cuerpo$gastos)
      if (length(encontrados) == 0) return()
      editando(encontrados[[1]])
      error(NULL)
      por_archivar(FALSE)
      limpiar_formulario()
      ir_a_vista("editar")
    })
    shiny::observeEvent(input$atras, {
      editando(NULL)
      error(NULL)
      limpiar_formulario()
      ir_a_vista("mes")
    })
    shiny::observeEvent(input$medio, {
      if (input$medio %in% names(MEDIOS_GASTO_UI)) medio(input$medio)
    })

    shiny::observeEvent(input$abrir_nueva_cat, {
      error_cat(NULL)
      cat_abierta(TRUE)
    })
    shiny::observeEvent(input$cancelar_nueva_cat, cat_abierta(FALSE))
    shiny::observeEvent(input$crear_cat, {
      nombre <- trimws(input$nueva_cat %||% "")
      if (nchar(nombre) < 2) return(error_cat("Escribe el nombre de la categoría."))
      r <- sesion_llamar(s, "POST", "v1/gastos/categorias",
                         list(nombre = nombre, es_fijo = isTRUE(input$nueva_cat_fija)))
      if (!r$ok) return(error_cat(r$mensaje))
      # El formulario se recarga con la categoría nueva elegida y sin perder lo escrito
      borrador(list(monto = input$monto %||% "", fecha = input$fecha %||% hoy_local(),
                    nota = input$nota %||% "", factura = isTRUE(input$factura)))
      seleccion_cat(r$cuerpo$id)
      cat_abierta(FALSE)
      error_cat(NULL)
      refresco(refresco() + 1L)
    })

    shiny::observeEvent(input$guardar, {
      if (vista() == "mes") return()  # un doble toque llega cuando ya se guardó
      g <- editando()
      monto <- normalizar_precio(input$monto)
      if (is.null(monto) || as.numeric(monto) <= 0) {
        return(error("Escribe cuánto gastaste con números, por ejemplo 125 o 125.50."))
      }
      categoria <- input$categoria %||% g[["categoria_id"]] %||% ""
      if (!nzchar(categoria)) return(error("Elige en qué lo gastaste o crea una categoría."))
      fecha <- trimws(input$fecha %||% "")
      if (!grepl("^[0-9]{4}-[0-9]{2}-[0-9]{2}$", fecha)) return(error("Elige la fecha del gasto."))
      if (fecha > hoy_local()) return(error("La fecha no puede ser de mañana en adelante."))
      nota <- trimws(input$nota %||% "")
      elegido <- medio()
      factura <- regimen_general() && isTRUE(input$factura)

      if (is.null(g)) {
        r <- sesion_llamar(
          s, "POST", "v1/gastos",
          list(monto = monto, categoria_id = categoria, medio_pago = elegido, fecha = fecha,
               descripcion = if (nzchar(nota)) nota else NULL, con_factura = factura),
          cabeceras = list(
            "Idempotency-Key" = clave_idempotencia(monto, categoria, elegido, fecha, nota, factura)
          )
        )
      } else {
        r <- sesion_llamar(
          s, "PATCH", paste0("v1/gastos/", g$id),
          c(list(version = g$version, monto = monto, categoria_id = categoria,
                 medio_pago = elegido, fecha = fecha,
                 descripcion = if (nzchar(nota)) nota else NULL),
            if (regimen_general()) list(con_factura = factura))
        )
      }
      if (!r$ok) return(error(r$mensaje))
      error(NULL)
      ultima_categoria(categoria)
      mes_pedido(substr(fecha, 1, 7))  # se ve el mes donde quedó el gasto
      limpiar_formulario()
      editando(NULL)
      refresco(refresco() + 1L)
      sesion_actualizar_pasos(s)
      ir_a_vista("mes")
      if (is.null(g)) base_clave(paste(as.character(openssl::rand_bytes(16)), collapse = ""))
      shiny::showNotification(
        paste0(if (is.null(g)) "Anotaste " else "Guardaste ", formato_dinero(as.numeric(monto)),
               " en ", r$cuerpo$categoria_nombre, "."),
        duration = 5, closeButton = FALSE, id = "gasto-aviso"
      )
    })

    shiny::observeEvent(input$archivar, por_archivar(TRUE))
    shiny::observeEvent(input$cancelar_archivar, por_archivar(FALSE))
    shiny::observeEvent(input$confirmar_archivar, {
      g <- editando()
      if (is.null(g) || vista() != "editar") return()
      r <- sesion_llamar(s, "DELETE", paste0("v1/gastos/", g$id))
      if (!r$ok) {
        por_archivar(FALSE)
        return(error(r$mensaje))
      }
      refresco(refresco() + 1L)
      sesion_actualizar_pasos(s)
      editando(NULL)
      por_archivar(FALSE)
      ir_a_vista("mes")
      shiny::showNotification("Archivaste el gasto.", duration = 5, closeButton = FALSE,
                              id = "gasto-aviso")
    })
  })
}
