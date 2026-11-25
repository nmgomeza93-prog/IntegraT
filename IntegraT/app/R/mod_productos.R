# Productos / Menú (según el tipo de negocio): lista por categoría, agregar, editar y archivar.
# Una pantalla, una tarea (docs/DISENO_UX.md): la lista y el formulario se turnan en la sección.
# El dinero viaja como texto ("45.00"); aquí solo se convierte para MOSTRARLO.

# "45", "45.5", "Q 45,50" -> "45.50" aceptado por la API; NULL si no es un precio válido.
normalizar_precio <- function(texto) {
  limpio <- gsub("[Qq[:space:]]", "", texto %||% "")
  limpio <- sub(",", ".", limpio, fixed = TRUE)
  if (!grepl("^[0-9]{1,9}([.][0-9]{1,2})?$", limpio)) return(NULL)
  limpio
}

# Para buscar sin importar mayúsculas ni tildes.
sin_tildes <- function(texto) {
  chartr("áéíóúüñÁÉÍÓÚÜÑ", "aeiouunaeiouun", tolower(texto))
}

# Ordena los ítems por categoría (en el orden de la API); lo que no tiene categoría va al final.
# Devuelve una lista de grupos list(titulo, items); el título es "" si el negocio no tiene
# categorías (lista plana).
agrupar_items <- function(items, categorias) {
  grupos <- list()
  ubicados <- character()
  for (cat in categorias) {
    propios <- Filter(function(i) identical(i[["categoria_id"]], cat[["id"]]), items)
    if (length(propios) > 0) grupos[[length(grupos) + 1L]] <- list(titulo = cat[["nombre"]], items = propios)
    ubicados <- c(ubicados, vapply(propios, function(i) i[["id"]] %||% "", ""))
  }
  # Lo que no quedó en ninguna categoría (sin categoría o con una que ya no existe)
  sueltos <- Filter(function(i) !(i[["id"]] %||% "") %in% ubicados || is.null(i[["id"]]), items)
  if (length(sueltos) > 0) {
    titulo <- if (length(grupos) > 0) "Sin categoría" else ""
    grupos[[length(grupos) + 1L]] <- list(titulo = titulo, items = sueltos)
  }
  grupos
}

# "Lo vendes en Q 45.00 · Te quedan Q 31.25 (69 %)" a partir de lo que calcula la API.
texto_margen <- function(r) {
  if (is.null(r$precio_venta) || is.null(r$margen)) return(NULL)
  paste0("Lo vendes en ", formato_dinero(as.numeric(r$precio_venta)), " · Te quedan ",
         formato_dinero(as.numeric(r$margen)),
         if (!is.null(r$margen_porcentaje)) paste0(" (", r$margen_porcentaje, " %)"))
}

mod_productos_ui <- function(id, vocab) {
  ns <- shiny::NS(id)
  htmltools::tags$div(class = "catalogo", shiny::uiOutput(ns("contenido")))
}

mod_productos_server <- function(id, s, ir_a) {
  shiny::moduleServer(id, function(input, output, session) {
    ns <- session$ns
    vista <- shiny::reactiveVal("lista")  # "lista", "nuevo" o "editar"
    editando <- shiny::reactiveVal(NULL)
    error <- shiny::reactiveVal(NULL)
    por_archivar <- shiny::reactiveVal(FALSE)
    refresco <- shiny::reactiveVal(0L)
    base_clave <- shiny::reactiveVal(NULL)
    # Crear una categoría desde el formulario: lo escrito se conserva mientras se recarga
    cat_abierta <- shiny::reactiveVal(FALSE)
    error_cat <- shiny::reactiveVal(NULL)
    borrador <- shiny::reactiveVal(NULL)       # list(nombre, precio) tras crear la categoría
    seleccion_cat <- shiny::reactiveVal(NULL)  # la categoría recién creada
    # Receta del ítem abierto (docs/PLAN_INVENTARIO.md): lo que devuelve la API, sin cálculos aquí
    mercaderia <- shiny::reactiveVal(NULL)     # NULL = no se sabe; si no, lo que dice la API
    receta <- shiny::reactiveVal(NULL)
    datos_receta <- shiny::reactiveVal(NULL)   # list(insumos, unidades) para armar la receta

    vocab <- shiny::reactive(vocab_negocio(shiny::req(s$negocio)))

    # Cuando cambia la persona o el negocio, la sección empieza de cero.
    shiny::observeEvent(s$negocio_id, {
      vista("lista")
      editando(NULL)
      error(NULL)
      por_archivar(FALSE)
      limpiar_formulario()
      base_clave(paste(as.character(openssl::rand_bytes(16)), collapse = ""))
    }, ignoreNULL = FALSE)

    datos <- shiny::reactive({
      refresco()
      s$negocio_id
      shiny::req(shiny::isolate(s$acceso))
      list(
        items = sesion_llamar(s, "GET", "v1/items", consulta = list(limite = 200)),
        categorias = sesion_llamar(s, "GET", "v1/categorias")
      )
    })

    lista_items <- function() datos()$items$cuerpo$items
    lista_categorias <- function() {
      if (isTRUE(datos()$categorias$ok)) datos()$categorias$cuerpo else list()
    }

    # Clave de idempotencia: los mismos datos en el mismo asistente = el mismo ítem (un doble
    # toque o un reintento tras perder la respuesta no lo duplica).
    clave_idempotencia <- function(nombre, precio, categoria) {
      huella <- openssl::sha256(charToRaw(paste(base_clave(), nombre, precio, categoria, sep = "|")))
      paste0("item-", substr(as.character(huella), 1, 40))
    }

    limpiar_formulario <- function() {
      cat_abierta(FALSE)
      error_cat(NULL)
      borrador(NULL)
      seleccion_cat(NULL)
    }

    # Pone al día el checklist del Inicio (se marca solo según lo que hay en el catálogo).
    actualizar_pasos <- function() {
      s$catalogo_v <- shiny::isolate(s$catalogo_v) + 1L  # Vender recarga su lista
      sesion_actualizar_pasos(s)
    }

    ir_a_vista <- function(nueva) {
      vista(nueva)
      session$sendCustomMessage("subir", TRUE)
    }

    # --- Pantallas ---------------------------------------------------------------------
    ui_lista <- function() {
      v <- vocab()
      d <- datos()
      if (!d$items$ok) {
        return(htmltools::tagList(
          htmltools::tags$h1(class = "pantalla__titulo", v$catalogo),
          estado_vacio("wifi-off", paste("No pudimos cargar tus", v$item_plural), d$items$mensaje,
                       boton_secundario(ns("reintentar"), "Intentar de nuevo", "arrow-repeat"))
        ))
      }
      items <- lista_items()
      if (length(items) == 0) {
        return(htmltools::tagList(
          htmltools::tags$h1(class = "pantalla__titulo", v$catalogo),
          estado_vacio(
            v$catalogo_icono, paste("Aún no tienes", v$item_plural),
            "Empieza por el que más vendes: ponle nombre y precio.",
            boton_primario(ns("nuevo"), paste("Agregar mi primer", v$item_singular), "plus-lg")
          )
        ))
      }
      htmltools::tagList(
        htmltools::tags$h1(class = "pantalla__titulo", v$catalogo),
        boton_primario(ns("nuevo"), paste("Agregar otro", v$item_singular), "plus-lg"),
        if (length(items) >= 8) {
          htmltools::tags$div(
            class = "campo catalogo__buscador",
            shiny::textInput(ns("buscar"), NULL, placeholder = paste("Buscar", v$item_singular),
                             width = "100%")
          )
        },
        shiny::uiOutput(ns("lista"))
      )
    }

    output$lista <- shiny::renderUI({
      items <- lista_items()
      consulta <- sin_tildes(trimws(input$buscar %||% ""))
      if (nzchar(consulta)) {
        items <- Filter(function(i) grepl(consulta, sin_tildes(i$nombre), fixed = TRUE), items)
        if (length(items) == 0) {
          return(htmltools::tags$p(class = "catalogo__sin-resultados",
                                   "No encontramos nada con ese nombre."))
        }
      }
      grupos <- agrupar_items(items, lista_categorias())
      htmltools::tagList(lapply(grupos, function(g) {
        htmltools::tagList(
          if (nzchar(g$titulo)) htmltools::tags$h2(class = "catalogo__grupo", g$titulo),
          htmltools::tags$ul(
            class = "lista-opciones",
            lapply(g$items, function(i) {
              item_lista("tag", i$nombre, formato_dinero(as.numeric(i$precio_venta)),
                         `data-elige-input` = ns("abrir"), `data-elige-valor` = i$id)
            })
          )
        )
      }))
    })

    ui_formulario <- function() {
      v <- vocab()
      it <- editando()
      categorias <- lista_categorias()
      opciones <- c("Sin categoría" = "", stats::setNames(
        vapply(categorias, function(c) c$id, ""), vapply(categorias, function(c) c$nombre, "")
      ))
      htmltools::tagList(
        enlace_atras(ns("atras")),
        htmltools::tags$h1(
          class = "pantalla__titulo",
          paste(if (is.null(it)) "Nuevo" else "Editar", v$item_singular)
        ),
        htmltools::tags$div(
          class = "pila",
          campo_texto(ns("nombre"), paste("Nombre del", v$item_singular),
                      valor = shiny::isolate(borrador()$nombre) %||% it$nombre %||% "",
                      autocompletar = "off"),
          campo_texto(ns("precio"), "Precio de venta (Q)",
                      valor = shiny::isolate(borrador()$precio) %||% it$precio_venta %||% "",
                      placeholder = "Ejemplo: 45 o 45.50", autocompletar = "off", modo = "decimal"),
          if (length(categorias) > 0) {
            htmltools::tags$div(
              class = "campo",
              shiny::selectInput(ns("categoria"), "Categoría (opcional)", choices = opciones,
                                 selected = shiny::isolate(seleccion_cat()) %||%
                                   it[["categoria_id"]] %||% "",
                                 selectize = FALSE, width = "100%")
            )
          },
          shiny::uiOutput(ns("nueva_categoria")),
          shiny::uiOutput(ns("error")),
          boton_primario(ns("guardar"), "Guardar", "check-lg"),
          if (!is.null(it)) ui_mercaderia(it),
          if (!is.null(it) && !isTRUE(mercaderia()$activa)) {
            boton_secundario(ns("ver_receta"), "Receta y costo", "basket")
          },
          if (!is.null(it)) ui_archivar(v, it)
        )
      )
    }

    # --- Mercadería: el producto que se compra hecho para revenderlo -----------------------
    ui_mercaderia <- function(it) {
      m <- mercaderia()
      if (is.null(m)) return(NULL)  # sin permiso o sin respuesta: no se ofrece
      if (isTRUE(m$activa)) {
        return(htmltools::tags$section(
          class = "tarjeta",
          htmltools::tags$h2(class = "hoja__titulo", "Lo compras ya hecho"),
          htmltools::tags$p(class = "entrada__texto", paste0(
            "Tienes ", cantidad_con_unidad(m$insumo$existencia, m$insumo$unidad_codigo),
            ". Al comprar sube y al vender baja; tu costo es Q ", m$insumo$costo_unitario, "."
          )),
          boton_secundario(ns("quitar_mercaderia"), "Ya no lo compro hecho", "x-circle")
        ))
      }
      boton_secundario(ns("poner_mercaderia"), "Lo compro ya hecho para revenderlo", "bag-plus")
    }

    # --- Receta: qué insumos lleva cada unidad vendida y cuánto cuesta -------------------
    lineas_para_guardar <- function(excepto = NULL) {
      r <- receta()
      vivas <- Filter(function(l) !isTRUE(l$archivado) && !identical(l$insumo_id, excepto),
                      r$lineas)
      lapply(vivas, function(l) {
        list(insumo_id = l$insumo_id, cantidad = l$cantidad, unidad_codigo = l$unidad_codigo)
      })
    }

    ui_receta <- function() {
      it <- editando()
      r <- receta()
      d <- datos_receta()
      atras <- enlace_atras(ns("atras_receta"), it$nombre)
      titulo <- htmltools::tags$h1(class = "pantalla__titulo", "Receta y costo")
      if (is.null(r) || is.null(d)) {
        return(htmltools::tagList(
          atras, titulo,
          htmltools::tags$div(class = "pila", shiny::uiOutput(ns("error")),
                              boton_secundario(ns("reintentar_receta"), "Intentar de nuevo",
                                               "arrow-repeat"))
        ))
      }
      en_uso <- vapply(r$lineas, function(l) l$insumo_id, "")
      libres <- Filter(function(i) !i$id %in% en_uso, d$insumos)
      htmltools::tagList(
        atras, titulo,
        htmltools::tags$div(
          class = "pila",
          if (isTRUE(r$tiene_receta)) {
            tarjeta_numero(
              "Hacer uno te cuesta", formato_dinero(as.numeric(r$costo_total)),
              contexto = texto_margen(r),
              estado = if (!is.null(r$margen) && as.numeric(r$margen) < 0) {
                etiqueta_estado("Pierdes dinero", "alerta")
              }
            )
          } else {
            htmltools::tags$p(class = "entrada__texto", paste0(
              "Dinos qué lleva cada ", vocab()$item_singular,
              " y te diremos cuánto te cuesta y cuánto te queda."
            ))
          },
          if (isTRUE(r$tiene_receta) && !isTRUE(r$costo_completo)) {
            htmltools::tags$p(class = "entrada__texto", paste0(
              "A algún insumo todavía no le anotas lo que cuesta, así que el costo real es mayor. ",
              "Anota una compra en Inventario."
            ))
          },
          if (isTRUE(r$tiene_receta)) {
            htmltools::tags$ul(
              class = "lista-opciones lista-receta",
              lapply(r$lineas, function(l) {
                htmltools::tags$li(
                  class = "linea-receta",
                  htmltools::tags$span(
                    class = "linea-receta__texto",
                    paste0(l$insumo_nombre, if (isTRUE(l$archivado)) " (archivado)"),
                    htmltools::tags$span(class = "linea-receta__detalle",
                                         cantidad_con_unidad(l$cantidad, l$unidad_codigo))
                  ),
                  htmltools::tags$span(class = "linea-receta__costo",
                                       formato_dinero(as.numeric(l$costo))),
                  htmltools::tags$button(
                    type = "button", class = "boton-cantidad",
                    `data-elige-input` = ns("quitar_linea"), `data-elige-valor` = l$insumo_id,
                    `aria-label` = paste("Quitar", l$insumo_nombre), icono("x-lg")
                  )
                )
              })
            )
          },
          htmltools::tags$h2(class = "hoja__titulo separado", "Agregar un insumo"),
          if (length(d$insumos) == 0) {
            htmltools::tagList(
              htmltools::tags$p(class = "entrada__texto",
                                "Primero anota tus insumos en Inventario."),
              boton_secundario(ns("ir_inventario"), "Ir a Inventario", "basket")
            )
          } else if (length(libres) == 0) {
            htmltools::tags$p(class = "entrada__texto", "Ya usaste todos tus insumos.")
          } else {
            primero <- libres[[1]]
            tipo <- Filter(function(u) identical(u$codigo, primero$unidad_codigo), d$unidades)
            htmltools::tagList(
              htmltools::tags$div(
                class = "campo",
                shiny::selectInput(
                  ns("receta_insumo"), "Insumo",
                  choices = stats::setNames(vapply(libres, function(i) i$id, ""),
                                            vapply(libres, function(i) i$nombre, "")),
                  selectize = FALSE, width = "100%")
              ),
              campo_texto(ns("receta_cantidad"),
                          paste("¿Cuánto lleva cada", vocab()$item_singular, "?"),
                          placeholder = "Ejemplo: 0.5", autocompletar = "off", modo = "decimal"),
              htmltools::tags$div(
                class = "campo",
                shiny::selectInput(
                  ns("receta_unidad"), "En",
                  choices = opciones_unidad(d$unidades, if (length(tipo) > 0) tipo[[1]]$tipo),
                  selected = primero$unidad_codigo, selectize = FALSE, width = "100%")
              ),
              shiny::uiOutput(ns("error")),
              boton_primario(ns("receta_agregar"), "Agregar a la receta", "plus-lg")
            )
          }
        )
      )
    }

    cargar_receta <- function() {
      it <- editando()
      r <- sesion_llamar(s, "GET", paste0("v1/items/", it$id, "/receta"))
      i <- sesion_llamar(s, "GET", "v1/insumos")
      u <- sesion_llamar(s, "GET", "v1/unidades")
      if (!r$ok) return(error(r$mensaje))
      if (!i$ok) return(error(i$mensaje))
      if (!u$ok) return(error(u$mensaje))
      error(NULL)
      receta(r$cuerpo)
      datos_receta(list(insumos = i$cuerpo$insumos, unidades = u$cuerpo))
    }

    guardar_receta <- function(lineas) {
      it <- editando()
      r <- sesion_llamar(s, "PUT", paste0("v1/items/", it$id, "/receta"), list(lineas = lineas))
      if (!r$ok) return(error(r$mensaje))
      error(NULL)
      receta(r$cuerpo)
      sesion_actualizar_pasos(s)  # la primera receta marca el paso del checklist
      invisible(TRUE)
    }

    ui_archivar <- function(v, it) {
      if (!por_archivar()) {
        return(boton_secundario(ns("archivar"), paste("Archivar este", v$item_singular), "archive"))
      }
      htmltools::tags$section(
        class = "tarjeta",
        htmltools::tags$h2(class = "hoja__titulo", paste0("¿Archivar «", it$nombre, "»?")),
        htmltools::tags$p(class = "entrada__texto",
                          "Ya no aparecerá en tu lista. No se borra nada."),
        htmltools::tags$div(
          class = "pila",
          boton_primario(ns("confirmar_archivar"), "Sí, archivar", "archive"),
          boton_secundario(ns("cancelar_archivar"), "No, dejarlo", "x-lg")
        )
      )
    }

    output$contenido <- shiny::renderUI({
      switch(vista(), lista = ui_lista(), receta = ui_receta(), ui_formulario())
    })
    output$error <- shiny::renderUI(mensaje_error(error()))

    output$nueva_categoria <- shiny::renderUI({
      if (!cat_abierta()) {
        return(enlace_accion(ns("abrir_nueva_cat"), "Nueva categoría", "plus-lg"))
      }
      htmltools::tags$div(
        class = "pila",
        campo_texto(ns("nueva_cat"), "Nombre de la categoría", autocompletar = "off",
                    placeholder = "Ejemplo: Sopas"),
        mensaje_error(error_cat()),
        boton_secundario(ns("crear_cat"), "Crear categoría", "check-lg"),
        enlace_accion(ns("cancelar_nueva_cat"), "Mejor no", "x-lg")
      )
    })

    # --- Acciones ----------------------------------------------------------------------
    shiny::observeEvent(input$reintentar, refresco(refresco() + 1L))

    shiny::observeEvent(input$abrir_nueva_cat, {
      error_cat(NULL)
      cat_abierta(TRUE)
    })
    shiny::observeEvent(input$cancelar_nueva_cat, cat_abierta(FALSE))
    shiny::observeEvent(input$crear_cat, {
      nombre <- trimws(input$nueva_cat %||% "")
      if (nchar(nombre) < 2) return(error_cat("Escribe el nombre de la categoría."))
      r <- sesion_llamar(s, "POST", "v1/categorias", list(nombre = nombre))
      if (!r$ok) return(error_cat(r$mensaje))
      # El formulario se recarga con la categoría nueva ya elegida y sin perder lo escrito
      borrador(list(nombre = input$nombre %||% "", precio = input$precio %||% ""))
      seleccion_cat(r$cuerpo$id)
      cat_abierta(FALSE)
      error_cat(NULL)
      refresco(refresco() + 1L)
    })

    shiny::observeEvent(input$nuevo, {
      editando(NULL)
      error(NULL)
      por_archivar(FALSE)
      limpiar_formulario()
      ir_a_vista("nuevo")
    })

    shiny::observeEvent(input$abrir, {
      encontrados <- Filter(function(i) identical(i$id, input$abrir), lista_items())
      if (length(encontrados) == 0) return()
      editando(encontrados[[1]])
      error(NULL)
      por_archivar(FALSE)
      limpiar_formulario()
      m <- sesion_llamar(s, "GET", paste0("v1/items/", encontrados[[1]]$id, "/mercaderia"))
      mercaderia(if (m$ok) m$cuerpo else NULL)
      ir_a_vista("editar")
    })

    shiny::observeEvent(input$atras, {
      editando(NULL)
      error(NULL)
      limpiar_formulario()
      ir_a_vista("lista")
    })

    shiny::observeEvent(input$guardar, {
      if (vista() == "lista") return()  # un doble toque llega cuando ya se guardó
      v <- vocab()
      it <- editando()
      nombre <- trimws(input$nombre %||% "")
      if (nchar(nombre) < 2) return(error(paste0("Escribe el nombre del ", v$item_singular, ".")))
      precio <- normalizar_precio(input$precio)
      if (is.null(precio)) {
        return(error("Escribe el precio con números, por ejemplo 45 o 45.50."))
      }
      categoria <- input$categoria %||% ""
      categoria_id <- if (nzchar(categoria)) categoria else NULL

      if (is.null(it)) {
        r <- sesion_llamar(
          s, "POST", "v1/items",
          list(nombre = nombre, precio_venta = precio, categoria_id = categoria_id),
          cabeceras = list("Idempotency-Key" = clave_idempotencia(nombre, precio, categoria))
        )
      } else {
        r <- sesion_llamar(
          s, "PATCH", paste0("v1/items/", it$id),
          list(version = it$version, nombre = nombre, precio_venta = precio,
               categoria_id = categoria_id)
        )
      }
      if (!r$ok) return(error(r$mensaje))
      error(NULL)
      limpiar_formulario()
      refresco(refresco() + 1L)
      actualizar_pasos()
      editando(NULL)
      ir_a_vista("lista")
      texto <- paste0(if (is.null(it)) "Agregaste «" else "Guardaste «", nombre, "».")
      if (is.character(r$cuerpo$aviso)) texto <- paste(texto, r$cuerpo$aviso)
      shiny::showNotification(texto, duration = 5, closeButton = FALSE, id = "catalogo-aviso")
    })

    cambiar_mercaderia <- function(activa) {
      it <- editando()
      if (is.null(it) || vista() != "editar") return()
      r <- sesion_llamar(s, "PUT", paste0("v1/items/", it$id, "/mercaderia"), list(activa = activa))
      if (!r$ok) return(error(r$mensaje))
      error(NULL)
      mercaderia(r$cuerpo)
      sesion_actualizar_pasos(s)  # el insumo ligado cuenta para el paso de los insumos
      shiny::showNotification(
        if (activa) "Listo: ahora puedes anotar compras de este producto."
        else "Listo: ya no se maneja como mercadería.",
        duration = 5, closeButton = FALSE, id = "catalogo-aviso"
      )
    }
    shiny::observeEvent(input$poner_mercaderia, cambiar_mercaderia(TRUE))
    shiny::observeEvent(input$quitar_mercaderia, cambiar_mercaderia(FALSE))

    shiny::observeEvent(input$ver_receta, {
      if (is.null(editando())) return()
      receta(NULL)
      datos_receta(NULL)
      error(NULL)
      cargar_receta()
      ir_a_vista("receta")
    })
    shiny::observeEvent(input$reintentar_receta, cargar_receta())
    shiny::observeEvent(input$atras_receta, {
      error(NULL)
      ir_a_vista("editar")
    })
    shiny::observeEvent(input$ir_inventario, ir_a("inventario"))

    # Al cambiar de insumo, la unidad se ajusta a su tipo (peso, líquido o piezas)
    shiny::observeEvent(input$receta_insumo, {
      d <- datos_receta()
      insumo <- Filter(function(i) identical(i$id, input$receta_insumo), d$insumos)
      if (length(insumo) == 0) return()
      propia <- Filter(function(u) identical(u$codigo, insumo[[1]]$unidad_codigo), d$unidades)
      shiny::updateSelectInput(
        session, "receta_unidad",
        choices = opciones_unidad(d$unidades, if (length(propia) > 0) propia[[1]]$tipo),
        selected = insumo[[1]]$unidad_codigo
      )
    })

    shiny::observeEvent(input$receta_agregar, {
      if (vista() != "receta" || is.null(receta())) return()
      insumo_id <- input$receta_insumo %||% ""
      if (!nzchar(insumo_id)) return()
      if (insumo_id %in% vapply(receta()$lineas, function(l) l$insumo_id, "")) return()  # doble toque
      cantidad <- normalizar_cantidad(input$receta_cantidad)
      if (is.null(cantidad) || as.numeric(cantidad) <= 0) {
        return(error("Escribe cuánto lleva con números, por ejemplo 0.5 o 250."))
      }
      nueva <- list(insumo_id = insumo_id, cantidad = cantidad,
                    unidad_codigo = input$receta_unidad %||% NULL)
      guardar_receta(c(lineas_para_guardar(), list(nueva)))
    })

    shiny::observeEvent(input$quitar_linea, {
      if (vista() != "receta" || is.null(receta())) return()
      guardar_receta(lineas_para_guardar(excepto = input$quitar_linea))
    })

    shiny::observeEvent(input$archivar, por_archivar(TRUE))
    shiny::observeEvent(input$cancelar_archivar, por_archivar(FALSE))
    shiny::observeEvent(input$confirmar_archivar, {
      it <- editando()
      if (is.null(it) || vista() != "editar") return()
      r <- sesion_llamar(s, "DELETE", paste0("v1/items/", it$id))
      if (!r$ok) {
        por_archivar(FALSE)
        return(error(r$mensaje))
      }
      refresco(refresco() + 1L)
      actualizar_pasos()
      editando(NULL)
      por_archivar(FALSE)
      ir_a_vista("lista")
      shiny::showNotification(paste0("Archivaste «", it$nombre, "»."), duration = 5,
                              closeButton = FALSE, id = "catalogo-aviso")
    })
  })
}
