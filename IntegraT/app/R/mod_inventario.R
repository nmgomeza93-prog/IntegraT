# Inventario ("Tu inventario"): insumos con su existencia y costo, entradas, mermas y ajustes
# (docs/PLAN_INVENTARIO.md). La API guarda las cantidades en unidad base, convierte y calcula el
# costo promedio y el valor: la app solo muestra lo que ella devuelve.

UNIDAD_CORTA <- c(UN = "u", DOC = "doc", G = "g", KG = "kg", LB = "lb", OZ = "oz", QQ = "qq",
                  ML = "ml", L = "L", GAL = "gal")

# Qué se anota con cada botón de la ficha
MOVIMIENTOS_UI <- list(
  entrada = list(boton = "Anoté una compra", icono = "bag-plus", titulo = "Anotar una compra",
                 pregunta = "¿Cuánto entró?"),
  merma = list(boton = "Se perdió algo", icono = "trash3", titulo = "Se perdió algo",
               pregunta = "¿Cuánto se perdió?"),
  ajuste = list(boton = "Corregir la cantidad", icono = "pencil-square",
                titulo = "Corregir la cantidad", pregunta = "¿Cuánto hay en realidad ahora?")
)

# Lo que se muestra en el historial de un insumo
TIPOS_MOVIMIENTO_UI <- c(
  inicial = "Lo que ya tenías", entrada = "Compra", merma = "Se perdió", ajuste = "Corrección",
  consumo_venta = "Vendido", reverso_venta = "Venta anulada", reverso_compra = "Compra anulada"
)

# Ideas para empezar según el tipo de negocio: (nombre, unidad)
SUGERENCIAS_INSUMO <- list(
  restaurante = list(c("Tortillas", "UN"), c("Pollo", "LB"), c("Arroz", "LB"), c("Frijol", "LB"),
                     c("Aceite", "L"), c("Sal", "LB")),
  ventas_en_linea = list(c("Bolsas", "UN"), c("Cajas", "UN"), c("Etiquetas", "UN"),
                         c("Cinta adhesiva", "UN"))
)

# "10", "2.5", "2,5" -> "2.5" aceptado por la API (hasta 4 decimales); NULL si no es un número.
normalizar_cantidad <- function(texto) {
  limpio <- gsub("[[:space:]]", "", texto %||% "")
  limpio <- sub(",", ".", limpio, fixed = TRUE)
  if (!grepl("^[0-9]{1,9}([.][0-9]{1,4})?$", limpio)) return(NULL)
  limpio
}

abreviar_unidad <- function(codigo) {
  corta <- unname(UNIDAD_CORTA[codigo])
  if (length(corta) == 0 || is.na(corta)) tolower(codigo) else corta
}

# "10" y "LB" -> "10 lb"
cantidad_con_unidad <- function(cantidad, codigo) paste(cantidad, abreviar_unidad(codigo))

# Opciones del selector de unidad: codigo con nombre ("Libra (lb)"). Con `tipo`, solo las del mismo
# tipo (no se convierte peso a volumen).
opciones_unidad <- function(unidades, tipo = NULL) {
  if (!is.null(tipo)) unidades <- Filter(function(u) identical(u$tipo, tipo), unidades)
  codigos <- vapply(unidades, function(u) u$codigo, "")
  nombres <- vapply(unidades, function(u) {
    paste0(u$nombre, " (", abreviar_unidad(u$codigo), ")")
  }, "")
  stats::setNames(codigos, nombres)
}

# Texto de la lista: el nombre y, si hace falta, el aviso.
texto_insumo <- function(i) {
  base <- if (is.character(i$item_id)) paste0(i$nombre, " · Para vender") else i$nombre
  switch(i$estado, poco = paste0(base, " · Te queda poco"),
         falta = paste0(base, " · Te falta"), base)
}

mod_inventario_ui <- function(id) {
  ns <- shiny::NS(id)
  htmltools::tags$div(class = "inventario", shiny::uiOutput(ns("contenido")))
}

mod_inventario_server <- function(id, s, ir_a) {
  shiny::moduleServer(id, function(input, output, session) {
    ns <- session$ns
    vista <- shiny::reactiveVal("lista")  # lista, nuevo, ficha, mover o editar
    actual <- shiny::reactiveVal(NULL)    # id del insumo abierto
    tipo_mov <- shiny::reactiveVal("entrada")
    error <- shiny::reactiveVal(NULL)
    por_archivar <- shiny::reactiveVal(FALSE)
    refresco <- shiny::reactiveVal(0L)
    base_clave <- shiny::reactiveVal(NULL)

    # Cuando cambia la persona o el negocio, la sección empieza de cero.
    shiny::observeEvent(s$negocio_id, {
      vista("lista")
      actual(NULL)
      error(NULL)
      por_archivar(FALSE)
      base_clave(paste(as.character(openssl::rand_bytes(16)), collapse = ""))
    }, ignoreNULL = FALSE)

    datos <- shiny::reactive({
      refresco()
      s$negocio_id
      shiny::req(shiny::isolate(s$acceso))
      list(
        lista = sesion_llamar(s, "GET", "v1/insumos"),
        unidades = sesion_llamar(s, "GET", "v1/unidades")
      )
    })

    unidades <- function() if (isTRUE(datos()$unidades$ok)) datos()$unidades$cuerpo else list()

    insumo_abierto <- function() {
      if (is.null(actual()) || !isTRUE(datos()$lista$ok)) return(NULL)
      encontrados <- Filter(function(i) identical(i$id, actual()), datos()$lista$cuerpo$insumos)
      if (length(encontrados) == 0) NULL else encontrados[[1]]
    }

    historial <- shiny::reactive({
      refresco()
      id_abierto <- actual()
      shiny::req(id_abierto, shiny::isolate(s$acceso))
      sesion_llamar(s, "GET", paste0("v1/insumos/", id_abierto, "/movimientos"))
    })

    clave_idempotencia <- function(...) {
      huella <- openssl::sha256(charToRaw(paste(base_clave(), ..., sep = "|")))
      paste0("insumo-", substr(as.character(huella), 1, 40))
    }

    ir_a_vista <- function(nueva) {
      vista(nueva)
      session$sendCustomMessage("subir", TRUE)
    }

    # --- Lista ---------------------------------------------------------------------------
    ui_lista <- function() {
      d <- datos()
      volver <- enlace_atras(ns("volver"), "Más")
      titulo <- htmltools::tags$h1(class = "pantalla__titulo", "Tu inventario")
      if (!d$lista$ok) {
        return(htmltools::tagList(
          volver, titulo,
          estado_vacio("wifi-off", "No pudimos cargar tu inventario", d$lista$mensaje,
                       boton_secundario(ns("reintentar"), "Intentar de nuevo", "arrow-repeat"))
        ))
      }
      lista <- d$lista$cuerpo
      htmltools::tagList(
        volver, titulo,
        boton_primario(ns("nuevo"), "Agregar un insumo", "plus-lg"),
        if (lista$total == 0) {
          estado_vacio(
            "basket", "Aún no tienes insumos",
            "Anota lo que compras para cocinar o empacar. Así sabrás cuánto te queda y cuánto cuesta cada platillo."
          )
        } else {
          htmltools::tagList(
            tarjeta_numero(
              "Valor de tu inventario", formato_dinero(as.numeric(lista$valor_inventario)),
              contexto = paste0(
                texto_cantidad(lista$total, "insumo", "insumos"),
                if (lista$por_reponer > 0) paste0(" · ", lista$por_reponer, " por reponer")
              )
            ),
            htmltools::tags$ul(
              class = "lista-opciones",
              lapply(lista$insumos, function(i) {
                item_lista("basket", texto_insumo(i),
                           cantidad_con_unidad(i$existencia, i$unidad_codigo),
                           `data-elige-input` = ns("abrir"), `data-elige-valor` = i$id)
              })
            )
          )
        }
      )
    }

    # --- Agregar -------------------------------------------------------------------------
    ui_nuevo <- function() {
      sugerencias <- SUGERENCIAS_INSUMO[[s$negocio$tipo_negocio_codigo %||% ""]] %||% list()
      opciones <- opciones_unidad(unidades())
      htmltools::tagList(
        enlace_atras(ns("atras")),
        htmltools::tags$h1(class = "pantalla__titulo", "Agregar un insumo"),
        htmltools::tags$div(
          class = "pila",
          if (length(sugerencias) > 0) {
            htmltools::tags$div(
              class = "campo",
              htmltools::tags$label(id = ns("ideas-etiqueta"), "Ideas para empezar"),
              htmltools::tags$div(
                class = "sugerencias", role = "group", `aria-labelledby` = ns("ideas-etiqueta"),
                lapply(sugerencias, function(x) {
                  htmltools::tags$button(
                    type = "button", class = "sugerencia",
                    `data-elige-input` = ns("sugerencia"),
                    `data-elige-valor` = paste(x, collapse = "|"), x[1]
                  )
                })
              )
            )
          },
          campo_texto(ns("nombre"), "¿Cómo se llama?", placeholder = "Ejemplo: Harina",
                      autocompletar = "off"),
          if (length(opciones) > 0) {
            htmltools::tags$div(
              class = "campo",
              shiny::selectInput(ns("unidad"), "¿En qué lo cuentas?", choices = opciones,
                                 selected = "UN", selectize = FALSE, width = "100%")
            )
          },
          campo_texto(ns("minimo"), "Avísame cuando me quede menos de (opcional)",
                      placeholder = "Ejemplo: 5", autocompletar = "off", modo = "decimal"),
          htmltools::tags$h2(class = "hoja__titulo separado", "¿Ya tienes de esto?"),
          htmltools::tags$p(class = "entrada__texto",
                            "Si ya tienes en la bodega, anótalo ahora. Si no, déjalo vacío."),
          campo_texto(ns("existencia"), "¿Cuánto tienes? (opcional)",
                      placeholder = "Ejemplo: 10", autocompletar = "off", modo = "decimal"),
          campo_texto(ns("costo"), "¿Cuánto te costó todo? (Q)",
                      placeholder = "Ejemplo: 150", autocompletar = "off", modo = "decimal"),
          shiny::uiOutput(ns("error")),
          boton_primario(ns("guardar"), "Guardar", "check-lg")
        )
      )
    }

    # --- Ficha ---------------------------------------------------------------------------
    ui_ficha <- function() {
      i <- insumo_abierto()
      if (is.null(i)) {
        return(htmltools::tagList(
          enlace_atras(ns("atras"), "Inventario"),
          estado_vacio("basket", "No encontramos ese insumo",
                       "Puede que ya lo hayas archivado.")
        ))
      }
      estado <- switch(
        i$estado,
        poco = etiqueta_estado("Te queda poco", "atencion"),
        falta = etiqueta_estado("Te falta", "alerta"),
        etiqueta_estado("Bien", "bien")
      )
      h <- historial()
      htmltools::tagList(
        enlace_atras(ns("atras"), "Inventario"),
        htmltools::tags$h1(class = "pantalla__titulo", i$nombre),
        tarjeta_numero(
          "Tienes", cantidad_con_unidad(i$existencia, i$unidad_codigo),
          contexto = paste0("Cada ", tolower(i$unidad_nombre), " te cuesta Q ", i$costo_unitario,
                            " · Vale ", formato_dinero(as.numeric(i$valor))),
          estado = estado
        ),
        htmltools::tags$div(
          class = "pila",
          boton_primario(ns("mover_entrada"), MOVIMIENTOS_UI$entrada$boton,
                         MOVIMIENTOS_UI$entrada$icono),
          boton_secundario(ns("mover_merma"), MOVIMIENTOS_UI$merma$boton,
                           MOVIMIENTOS_UI$merma$icono),
          boton_secundario(ns("mover_ajuste"), MOVIMIENTOS_UI$ajuste$boton,
                           MOVIMIENTOS_UI$ajuste$icono)
        ),
        htmltools::tags$h2(class = "hoja__titulo separado", "Lo último que pasó"),
        if (!isTRUE(h$ok) || length(h$cuerpo$movimientos) == 0) {
          htmltools::tags$p(class = "entrada__texto", "Aún no hay movimientos.")
        } else {
          htmltools::tags$ul(
            class = "lista-opciones lista-movimientos",
            lapply(utils::head(h$cuerpo$movimientos, 10), function(m) {
              signo <- if (startsWith(m$cantidad, "-")) "" else "+"
              fila_lista(
                switch(m$tipo, merma = "trash3", consumo_venta = "cart", reverso_venta = "arrow-counterclockwise",
                       ajuste = "pencil-square", "bag-plus"),
                TIPOS_MOVIMIENTO_UI[[m$tipo]] %||% m$tipo,
                paste0(signo, cantidad_con_unidad(m$cantidad, i$unidad_codigo))
              )
            })
          )
        },
        htmltools::tags$div(
          class = "pila separado",
          enlace_accion(ns("editar"), "Cambiar nombre o mínimo", "pencil"),
          shiny::uiOutput(ns("error")),
          ui_archivar(i)
        )
      )
    }

    ui_archivar <- function(i) {
      if (!por_archivar()) {
        return(boton_secundario(ns("archivar"), "Archivar este insumo", "archive"))
      }
      htmltools::tags$section(
        class = "tarjeta",
        htmltools::tags$h2(class = "hoja__titulo", paste0("¿Archivar ", i$nombre, "?")),
        htmltools::tags$p(class = "entrada__texto",
                          "Ya no aparecerá en tu inventario ni se descontará al vender. No se borra nada."),
        htmltools::tags$div(
          class = "pila",
          boton_primario(ns("confirmar_archivar"), "Sí, archivar", "archive"),
          boton_secundario(ns("cancelar_archivar"), "No, dejarlo", "x-lg")
        )
      )
    }

    # --- Entrada, merma o ajuste ---------------------------------------------------------
    ui_mover <- function() {
      i <- insumo_abierto()
      if (is.null(i)) return(ui_ficha())
      tipo <- tipo_mov()
      cfg <- MOVIMIENTOS_UI[[tipo]]
      propia <- Filter(function(u) identical(u$codigo, i$unidad_codigo), unidades())
      opciones <- opciones_unidad(unidades(), if (length(propia) > 0) propia[[1]]$tipo)
      htmltools::tagList(
        enlace_atras(ns("atras_mover"), i$nombre),
        htmltools::tags$h1(class = "pantalla__titulo", cfg$titulo),
        htmltools::tags$div(
          class = "pila",
          campo_texto(ns("cantidad"), cfg$pregunta, placeholder = "Ejemplo: 10",
                      autocompletar = "off", modo = "decimal"),
          if (length(opciones) > 1) {
            htmltools::tags$div(
              class = "campo",
              shiny::selectInput(ns("unidad_mov"), "En", choices = opciones,
                                 selected = i$unidad_codigo, selectize = FALSE, width = "100%")
            )
          },
          if (identical(tipo, "entrada")) {
            campo_texto(ns("costo_mov"), "¿Cuánto costó todo? (Q)", placeholder = "Ejemplo: 150",
                        autocompletar = "off", modo = "decimal")
          },
          campo_texto(ns("nota_mov"), "Nota (opcional)", autocompletar = "off"),
          shiny::uiOutput(ns("error")),
          boton_primario(ns("guardar_mov"), "Guardar", "check-lg")
        )
      )
    }

    # --- Cambiar nombre o mínimo ---------------------------------------------------------
    ui_editar <- function() {
      i <- insumo_abierto()
      if (is.null(i)) return(ui_ficha())
      htmltools::tagList(
        enlace_atras(ns("atras_editar"), i$nombre),
        htmltools::tags$h1(class = "pantalla__titulo", "Cambiar insumo"),
        htmltools::tags$div(
          class = "pila",
          campo_texto(ns("nombre_nuevo"), "Nombre", valor = i$nombre, autocompletar = "off"),
          campo_texto(ns("minimo_nuevo"),
                      paste0("Avísame cuando me quede menos de (", abreviar_unidad(i$unidad_codigo), ")"),
                      valor = i$stock_minimo, autocompletar = "off", modo = "decimal"),
          shiny::uiOutput(ns("error")),
          boton_primario(ns("guardar_cambios"), "Guardar", "check-lg")
        )
      )
    }

    output$contenido <- shiny::renderUI({
      switch(vista(), lista = ui_lista(), nuevo = ui_nuevo(), ficha = ui_ficha(),
             mover = ui_mover(), editar = ui_editar())
    })
    output$error <- shiny::renderUI(mensaje_error(error()))

    # --- Acciones ------------------------------------------------------------------------
    shiny::observeEvent(input$volver, ir_a("mas"))
    shiny::observeEvent(input$reintentar, refresco(refresco() + 1L))

    shiny::observeEvent(input$nuevo, {
      error(NULL)
      ir_a_vista("nuevo")
    })
    shiny::observeEvent(input$abrir, {
      actual(input$abrir)
      error(NULL)
      por_archivar(FALSE)
      ir_a_vista("ficha")
    })
    shiny::observeEvent(input$atras, {
      error(NULL)
      por_archivar(FALSE)
      actual(NULL)
      ir_a_vista("lista")
    })
    shiny::observeEvent(input$atras_mover, {
      error(NULL)
      ir_a_vista("ficha")
    })
    shiny::observeEvent(input$atras_editar, {
      error(NULL)
      ir_a_vista("ficha")
    })

    shiny::observeEvent(input$sugerencia, {
      partes <- strsplit(input$sugerencia, "|", fixed = TRUE)[[1]]
      shiny::updateTextInput(session, "nombre", value = partes[1])
      shiny::updateSelectInput(session, "unidad", selected = partes[2])
    })

    shiny::observeEvent(input$guardar, {
      if (vista() != "nuevo") return()  # un doble toque llega cuando ya se guardó
      nombre <- trimws(input$nombre %||% "")
      if (nchar(nombre) < 2) return(error("Escribe cómo se llama el insumo."))
      unidad <- input$unidad %||% "UN"
      cuerpo <- list(nombre = nombre, unidad_codigo = unidad)

      minimo_texto <- trimws(input$minimo %||% "")
      if (nzchar(minimo_texto)) {
        minimo <- normalizar_cantidad(minimo_texto)
        if (is.null(minimo)) return(error("Escribe el mínimo con números, por ejemplo 5 o 2.5."))
        cuerpo$stock_minimo <- minimo
      }
      existencia_texto <- trimws(input$existencia %||% "")
      costo_texto <- trimws(input$costo %||% "")
      if (nzchar(existencia_texto)) {
        existencia <- normalizar_cantidad(existencia_texto)
        if (is.null(existencia) || as.numeric(existencia) <= 0) {
          return(error("Escribe cuánto tienes con números, por ejemplo 10 o 2.5."))
        }
        costo <- normalizar_precio(costo_texto)
        if (is.null(costo)) return(error("Dinos cuánto te costó todo lo que tienes, por ejemplo 150."))
        cuerpo$existencia_inicial <- existencia
        cuerpo$costo_total_inicial <- costo
      } else if (nzchar(costo_texto)) {
        return(error("Dinos cuánto tienes para guardar su costo, o borra el costo."))
      }

      r <- sesion_llamar(s, "POST", "v1/insumos", cuerpo)
      if (!r$ok) return(error(r$mensaje))
      error(NULL)
      refresco(refresco() + 1L)
      sesion_actualizar_pasos(s)
      actual(NULL)
      ir_a_vista("lista")
      shiny::showNotification(paste0("Agregaste ", r$cuerpo$nombre, " a tu inventario."),
                              duration = 5, closeButton = FALSE, id = "inventario-aviso")
    })

    for (tipo in names(MOVIMIENTOS_UI)) {
      local({
        t <- tipo
        shiny::observeEvent(input[[paste0("mover_", t)]], {
          tipo_mov(t)
          error(NULL)
          ir_a_vista("mover")
        })
      })
    }

    shiny::observeEvent(input$guardar_mov, {
      if (vista() != "mover") return()
      i <- insumo_abierto()
      if (is.null(i)) return()
      tipo <- tipo_mov()
      cantidad <- normalizar_cantidad(input$cantidad)
      if (is.null(cantidad) || (tipo != "ajuste" && as.numeric(cantidad) <= 0)) {
        return(error("Escribe la cantidad con números, por ejemplo 10 o 2.5."))
      }
      unidad <- input$unidad_mov %||% i$unidad_codigo
      nota <- trimws(input$nota_mov %||% "")
      cuerpo <- list(tipo = tipo, cantidad = cantidad, unidad_codigo = unidad,
                     nota = if (nzchar(nota)) nota else NULL)
      costo <- ""
      if (identical(tipo, "entrada")) {
        costo <- normalizar_precio(trimws(input$costo_mov %||% ""))
        if (is.null(costo)) return(error("Dinos cuánto costó todo lo que entró, por ejemplo 150."))
        cuerpo$costo_total <- costo
      }
      r <- sesion_llamar(
        s, "POST", paste0("v1/insumos/", i$id, "/movimientos"), cuerpo,
        cabeceras = list("Idempotency-Key" = clave_idempotencia(i$id, tipo, cantidad, unidad,
                                                                 costo, nota))
      )
      if (!r$ok) return(error(r$mensaje))
      error(NULL)
      refresco(refresco() + 1L)
      ir_a_vista("ficha")
      base_clave(paste(as.character(openssl::rand_bytes(16)), collapse = ""))
      nuevo <- r$cuerpo$insumo
      shiny::showNotification(
        paste0("Listo: ahora tienes ", cantidad_con_unidad(nuevo$existencia, nuevo$unidad_codigo),
               " de ", nuevo$nombre, "."),
        duration = 5, closeButton = FALSE, id = "inventario-aviso"
      )
    })

    shiny::observeEvent(input$editar, {
      error(NULL)
      ir_a_vista("editar")
    })
    shiny::observeEvent(input$guardar_cambios, {
      if (vista() != "editar") return()
      i <- insumo_abierto()
      if (is.null(i)) return()
      nombre <- trimws(input$nombre_nuevo %||% "")
      if (nchar(nombre) < 2) return(error("Escribe cómo se llama el insumo."))
      minimo <- normalizar_cantidad(trimws(input$minimo_nuevo %||% ""))
      if (is.null(minimo)) return(error("Escribe el mínimo con números, por ejemplo 5, 2.5 o 0."))
      r <- sesion_llamar(s, "PATCH", paste0("v1/insumos/", i$id),
                         list(version = i$version, nombre = nombre, stock_minimo = minimo))
      if (!r$ok) return(error(r$mensaje))
      error(NULL)
      refresco(refresco() + 1L)
      ir_a_vista("ficha")
      shiny::showNotification("Guardaste los cambios.", duration = 5, closeButton = FALSE,
                              id = "inventario-aviso")
    })

    shiny::observeEvent(input$archivar, por_archivar(TRUE))
    shiny::observeEvent(input$cancelar_archivar, por_archivar(FALSE))
    shiny::observeEvent(input$confirmar_archivar, {
      i <- insumo_abierto()
      if (is.null(i) || vista() != "ficha") return()
      r <- sesion_llamar(s, "DELETE", paste0("v1/insumos/", i$id))
      if (!r$ok) {
        por_archivar(FALSE)
        return(error(r$mensaje))
      }
      refresco(refresco() + 1L)
      sesion_actualizar_pasos(s)
      actual(NULL)
      por_archivar(FALSE)
      ir_a_vista("lista")
      shiny::showNotification("Archivaste el insumo.", duration = 5, closeButton = FALSE,
                              id = "inventario-aviso")
    })
  })
}
