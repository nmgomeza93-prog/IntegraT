# Tus clientes (dentro de Más): lista con búsqueda, ficha con lo que ha comprado, agregar y cambiar,
# y los campos propios del negocio (docs/ANALISIS_INVENTARIO_Y_CLIENTES.md, C2). Las validaciones
# (teléfono, correo, NIT, CUI, duplicados) las hace la API; aquí solo se muestran sus mensajes.

TIPOS_FISCALES_UI <- c("Consumidor final" = "CF", "NIT" = "NIT", "CUI (DPI)" = "CUI")
TIPOS_CAMPO_UI <- c("Texto" = "texto", "Número" = "numero", "Fecha" = "fecha", "Sí o no" = "si_no")

# "+50255551234" -> "5555 1234"; otros países se muestran tal cual.
telefono_visible <- function(telefono) {
  if (!is.character(telefono) || !nzchar(telefono)) return(NULL)
  if (startsWith(telefono, "+502") && nchar(telefono) == 12) {
    return(paste(substr(telefono, 5, 8), substr(telefono, 9, 12)))
  }
  telefono
}

# "NIT 1234567-9", "CUI 1234567890101" o "Consumidor final".
texto_fiscal <- function(tipo, id_fiscal) {
  if (!is.character(id_fiscal) || identical(tipo, "CF")) return("Consumidor final")
  if (identical(tipo, "NIT")) {
    n <- nchar(id_fiscal)
    return(paste0("NIT ", substr(id_fiscal, 1, n - 1), "-", substr(id_fiscal, n, n)))
  }
  paste("CUI", id_fiscal)
}

# Valor de un campo propio para leer: Sí/No, "17 may 1990", o el texto.
valor_campo_visible <- function(tipo, valor) {
  if (is.null(valor)) return(NULL)
  if (identical(tipo, "si_no")) return(if (isTRUE(valor)) "Sí" else "No")
  if (identical(tipo, "fecha")) return(paste(fecha_corta(valor), substr(valor, 1, 4)))
  as.character(valor)
}

# Lo que se manda a la API desde el formulario (los vacíos van como null para borrarlos).
cuerpo_cliente <- function(valores, campos) {
  vacio_a_null <- function(x) {
    x <- trimws(x %||% "")
    if (nzchar(x)) x else NULL
  }
  tipo <- valores$tipo_id_fiscal %||% "CF"
  datos <- stats::setNames(list(), character())  # vacío = {} en JSON (no [])
  for (i in seq_along(campos)) {
    c <- campos[[i]]
    v <- valores$campos[[i]]
    datos[[c$id]] <- if (identical(c$tipo, "si_no")) isTRUE(v) else vacio_a_null(v)
  }
  list(
    nombre = trimws(valores$nombre %||% ""),
    telefono = vacio_a_null(valores$telefono),
    correo = vacio_a_null(valores$correo),
    direccion = vacio_a_null(valores$direccion),
    tipo_id_fiscal = tipo,
    id_fiscal = if (tipo == "CF") NULL else vacio_a_null(valores$id_fiscal),
    nombre_fiscal = if (tipo == "CF") NULL else vacio_a_null(valores$nombre_fiscal),
    notas = vacio_a_null(valores$notas),
    datos = datos
  )
}

# Qué pasa al archivar: nada se borra; si tiene compras, sus ventas lo siguen nombrando.
texto_archivar <- function(nombre, cantidad, total) {
  base <- "Dejará de aparecer en tu lista y al vender. Puedes recuperarlo cuando quieras en \"Ver archivados\"."
  if (cantidad == 0) return(base)
  paste0(nombre, " tiene ", cantidad, if (cantidad == 1) " compra" else " compras", " por ",
         formato_dinero(total), ". Esas ventas no se borran ni cambian: siguen diciendo que fueron ",
         "para ", nombre, " y cuentan en tus números. ", base)
}

mod_clientes_ui <- function(id) {
  ns <- shiny::NS(id)
  htmltools::tags$div(class = "clientes", shiny::uiOutput(ns("contenido")))
}

mod_clientes_server <- function(id, s, ir_a) {
  shiny::moduleServer(id, function(input, output, session) {
    ns <- session$ns
    vista <- shiny::reactiveVal("lista")  # lista, ficha, formulario o campos
    abierto <- shiny::reactiveVal(NULL)   # la ficha (con compras) del cliente abierto
    editando <- shiny::reactiveVal(FALSE) # el formulario cambia al abierto (si no, crea)
    duplicado <- shiny::reactiveVal(FALSE)
    por_archivar <- shiny::reactiveVal(FALSE)
    error <- shiny::reactiveVal(NULL)
    refresco <- shiny::reactiveVal(0L)
    campos_borrador <- shiny::reactiveVal(list())
    ver_archivados <- shiny::reactiveVal(FALSE)

    ir_a_vista <- function(nueva) {
      error(NULL)
      duplicado(FALSE)
      por_archivar(FALSE)
      vista(nueva)
      session$sendCustomMessage("subir", TRUE)
    }

    shiny::observeEvent(s$negocio_id, {
      vista("lista")
      abierto(NULL)
      error(NULL)
      ver_archivados(FALSE)
    }, ignoreNULL = FALSE)
    shiny::observeEvent(s$al_dia, {
      if (identical(vista(), "ficha") && !is.null(abierto())) abrir(abierto()$id)
    }, ignoreInit = TRUE)

    campos <- shiny::reactive({
      refresco()
      s$al_dia  # al entrar, al día con lo que se guardó en otra pantalla
      s$negocio_id
      r <- sesion_llamar(s, "GET", "v1/clientes/campos")
      if (r$ok) r$cuerpo else list()
    })

    buscar <- shiny::debounce(shiny::reactive(trimws(input$buscar %||% "")), 300)

    output$contenido <- shiny::renderUI({
      shiny::req(s$negocio)
      switch(vista(), lista = ui_lista(), ficha = ui_ficha(),
             formulario = shiny::isolate(ui_formulario()), campos = ui_campos())
    })

    # --- Lista -----------------------------------------------------------------------------
    ui_lista <- function() {
      htmltools::tagList(
        enlace_atras(ns("atras"), "Más"),
        htmltools::tags$div(
          class = "vender__encabezado",
          htmltools::tags$h1(class = "pantalla__titulo",
                             if (ver_archivados()) "Clientes archivados" else "Tus clientes"),
          if (!ver_archivados()) enlace_accion(ns("ir_campos"), "Datos que pides", "ui-checks")
        ),
        htmltools::tags$div(
          class = "campo catalogo__buscador",
          shiny::textInput(ns("buscar"), NULL, placeholder = "Buscar por nombre, teléfono o NIT",
                           width = "100%")
        ),
        shiny::uiOutput(ns("resultados")),
        if (ver_archivados()) {
          htmltools::tags$div(class = "separado",
                              enlace_accion(ns("ver_activos"), "Volver a tus clientes", "people"))
        } else {
          htmltools::tagList(
            htmltools::tags$div(class = "separado",
                                boton_primario(ns("agregar"), "Agregar cliente", "person-plus")),
            enlace_accion(ns("ver_archivados"), "Ver archivados", "archive")
          )
        }
      )
    }

    output$resultados <- shiny::renderUI({
      refresco()
      s$al_dia  # al entrar, al día con lo que se guardó en otra pantalla
      shiny::req(vista() == "lista")
      consulta <- c(if (nzchar(buscar())) list(q = buscar()),
                    if (ver_archivados()) list(archivados = "true"))
      r <- sesion_llamar(s, "GET", "v1/clientes", consulta = consulta)
      if (!r$ok) return(mensaje_error(r$mensaje))
      if (length(r$cuerpo) == 0) {
        if (ver_archivados()) {
          return(estado_vacio("archive", "No tienes clientes archivados",
                              "Los que archives quedan aquí, con todas sus ventas."))
        }
        return(if (nzchar(buscar())) {
          estado_vacio("search", "No encontramos a nadie", "Revisa cómo lo escribiste o agrégalo.")
        } else {
          estado_vacio("people", "Aún no tienes clientes",
                       "Guarda a quién le vendes para ver lo que te compra y encontrarlo rápido.")
        })
      }
      htmltools::tags$ul(
        class = "lista-opciones lista-clientes",
        lapply(r$cuerpo, function(c) {
          item_lista("person", c$nombre, telefono_visible(c$telefono),
                     `data-elige-input` = ns("abrir"), `data-elige-valor` = c$id)
        })
      )
    })

    abrir <- function(cliente_id) {
      r <- sesion_llamar(s, "GET", paste0("v1/clientes/", cliente_id))
      if (!r$ok) {
        shiny::showNotification(r$mensaje, duration = 5, closeButton = FALSE, id = "clientes-aviso")
        return(FALSE)
      }
      abierto(r$cuerpo)
      TRUE
    }

    shiny::observeEvent(input$atras, {
      ver_archivados(FALSE)
      ir_a("mas")
    })
    shiny::observeEvent(input$ver_archivados, ver_archivados(TRUE))
    shiny::observeEvent(input$ver_activos, ver_archivados(FALSE))
    shiny::observeEvent(input$abrir, if (abrir(input$abrir)) ir_a_vista("ficha"))
    shiny::observeEvent(input$agregar, {
      editando(FALSE)
      ir_a_vista("formulario")
    })

    # --- Ficha -----------------------------------------------------------------------------
    ui_ficha <- function() {
      c <- abierto()
      shiny::req(c)
      compras <- c$compras
      filas <- Filter(Negate(is.null), list(
        if (!is.null(telefono_visible(c$telefono))) fila_lista("telephone", telefono_visible(c$telefono)),
        if (is.character(c$correo)) fila_lista("envelope", c$correo),
        if (is.character(c$direccion)) fila_lista("geo-alt", c$direccion),
        fila_lista("receipt", texto_fiscal(c$tipo_id_fiscal, c$id_fiscal),
                   if (is.character(c$nombre_fiscal)) c$nombre_fiscal),
        if (is.character(c$notas)) fila_lista("sticky", c$notas)
      ))
      propios <- Filter(Negate(is.null), lapply(campos(), function(k) {
        v <- valor_campo_visible(k$tipo, c$datos[[k$id]])
        if (is.null(v)) NULL else fila_lista("tag", k$nombre, v)
      }))
      htmltools::tagList(
        enlace_atras(ns("volver_lista"), "Tus clientes"),
        htmltools::tags$h1(class = "pantalla__titulo", c$nombre),
        if (isTRUE(c$archivado)) htmltools::tags$p(etiqueta_estado("Archivado", "neutro")),
        htmltools::tags$p(class = "entrada__texto",
                          paste("Cliente desde el", fecha_corta(substr(c$cliente_desde, 1, 10)),
                                substr(c$cliente_desde, 1, 4))),
        tarjeta_numero(
          "Te ha comprado", formato_dinero(as.numeric(compras$total %||% "0")),
          if (compras$cantidad == 0) "Todavía no le has vendido"
          else paste0(compras$cantidad, if (compras$cantidad == 1) " compra" else " compras",
                      " · la última el ", fecha_corta(substr(compras$ultima, 1, 10)))
        ),
        htmltools::tags$ul(class = "lista-opciones separado", filas, propios),
        if (length(compras$ultimas) > 0) htmltools::tagList(
          htmltools::tags$h2(class = "hoja__titulo separado", "Sus últimas compras"),
          htmltools::tags$ul(
            class = "lista-opciones",
            lapply(compras$ultimas, function(v) {
              fila_lista("bag-check", paste0("Venta ", v$numero, " · ",
                                             fecha_corta(substr(v$fecha_hora, 1, 10))),
                         formato_dinero(as.numeric(v$total)))
            })
          )
        ),
        mensaje_error(error()),
        if (por_archivar()) {
          htmltools::tags$section(
            class = "tarjeta separado",
            htmltools::tags$h2(class = "hoja__titulo", paste0("¿Archivar a ", c$nombre, "?")),
            htmltools::tags$p(class = "entrada__texto",
                              texto_archivar(c$nombre, compras$cantidad,
                                             as.numeric(compras$total %||% "0"))),
            htmltools::tags$div(
              class = "pila",
              boton_primario(ns("confirmar_archivar"), "Sí, archivar", "archive"),
              boton_secundario(ns("cancelar_archivar"), "No", "x-lg")
            )
          )
        } else if (isTRUE(c$archivado)) {
          htmltools::tags$div(
            class = "pila separado",
            htmltools::tags$p(class = "entrada__texto",
                              "Está archivado: no aparece al vender. Sus ventas siguen intactas."),
            boton_primario(ns("recuperar"), "Recuperar cliente", "arrow-counterclockwise")
          )
        } else {
          htmltools::tags$div(
            class = "pila separado",
            boton_primario(ns("editar"), "Cambiar datos", "pencil"),
            boton_secundario(ns("archivar"), "Archivar", "archive")
          )
        }
      )
    }

    shiny::observeEvent(input$volver_lista, {
      refresco(refresco() + 1L)
      ir_a_vista("lista")
    })
    shiny::observeEvent(input$editar, {
      editando(TRUE)
      ir_a_vista("formulario")
    })
    shiny::observeEvent(input$archivar, por_archivar(TRUE))
    shiny::observeEvent(input$recuperar, {
      c <- abierto()
      r <- sesion_llamar(s, "POST", paste0("v1/clientes/", c$id, "/recuperar"))
      if (!r$ok) return(error(r$mensaje))
      abierto(r$cuerpo)
      ver_archivados(FALSE)
      refresco(refresco() + 1L)
      shiny::showNotification(paste0("Listo: ", c$nombre, " vuelve a tu lista."), duration = 4,
                              closeButton = FALSE, id = "clientes-aviso")
    })
    shiny::observeEvent(input$cancelar_archivar, por_archivar(FALSE))
    shiny::observeEvent(input$confirmar_archivar, {
      c <- abierto()
      r <- sesion_llamar(s, "DELETE", paste0("v1/clientes/", c$id))
      if (!r$ok) {
        por_archivar(FALSE)
        return(error(r$mensaje))
      }
      shiny::showNotification(paste0("Archivaste a ", c$nombre, ". Sus ventas siguen intactas."),
                              duration = 5, closeButton = FALSE, id = "clientes-aviso")
      refresco(refresco() + 1L)
      por_archivar(FALSE)
      abrir(c$id)
    })

    # --- Agregar o cambiar -----------------------------------------------------------------
    ui_formulario <- function() {
      c <- if (editando()) abierto() else list()
      tipo <- c$tipo_id_fiscal %||% "CF"
      htmltools::tagList(
        enlace_atras(ns("cancelar_formulario")),
        htmltools::tags$h1(class = "pantalla__titulo",
                           if (editando()) "Cambiar datos" else "Nuevo cliente"),
        campo_texto(ns("nombre"), "Nombre", valor = c$nombre %||% "", autocompletar = "off"),
        campo_texto(ns("telefono"), "Teléfono (opcional)", valor = telefono_visible(c$telefono) %||% "",
                    autocompletar = "off", modo = "tel"),
        campo_texto(ns("correo"), "Correo (opcional)", valor = c$correo %||% "",
                    autocompletar = "off", modo = "email"),
        campo_texto(ns("direccion"), "Dirección para envíos (opcional)", valor = c$direccion %||% ""),
        shiny::selectInput(ns("tipo_id_fiscal"), "Para la factura", choices = TIPOS_FISCALES_UI,
                           selected = tipo, selectize = FALSE, width = "100%"),
        shiny::conditionalPanel(
          condition = sprintf("input['%s'] != 'CF'", ns("tipo_id_fiscal")),
          campo_texto(ns("id_fiscal"), "Número de NIT o CUI", valor = c$id_fiscal %||% "",
                      autocompletar = "off"),
          campo_texto(ns("nombre_fiscal"), "Nombre en la factura (opcional)",
                      valor = c$nombre_fiscal %||% "")
        ),
        lapply(seq_along(campos()), function(i) {
          k <- campos()[[i]]
          valor <- c$datos[[k$id]]
          id_campo <- ns(paste0("campo_", i))
          switch(
            k$tipo,
            si_no = htmltools::tags$div(class = "casilla", shiny::checkboxInput(
              id_campo, k$nombre, value = isTRUE(valor), width = "100%")),
            fecha = campo_fecha(id_campo, paste(k$nombre, "(opcional)"), valor %||% "", "9999-12-31"),
            campo_texto(id_campo, paste(k$nombre, "(opcional)"), valor = valor %||% "",
                        autocompletar = "off", modo = if (k$tipo == "numero") "decimal")
          )
        }),
        campo_texto(ns("notas"), "Notas (opcional)", valor = c$notas %||% ""),
        shiny::uiOutput(ns("error_formulario")),  # aparte: así no se borra lo escrito
        boton_primario(ns("guardar"), "Guardar", "check-lg")
      )
    }
    output$error_formulario <- shiny::renderUI(htmltools::tagList(
      mensaje_error(error()),
      if (duplicado()) boton_secundario(ns("guardar_igual"), "Guardar de todos modos", "check2-all")
    ))

    valores_formulario <- function() {
      list(nombre = input$nombre, telefono = input$telefono, correo = input$correo,
           direccion = input$direccion, tipo_id_fiscal = input$tipo_id_fiscal,
           id_fiscal = input$id_fiscal, nombre_fiscal = input$nombre_fiscal, notas = input$notas,
           campos = lapply(seq_along(campos()), function(i) input[[paste0("campo_", i)]]))
    }

    guardar <- function(aunque_se_repita) {
      cuerpo <- cuerpo_cliente(valores_formulario(), campos())
      if (nchar(cuerpo$nombre) < 2) return(error("Escribe el nombre del cliente."))
      cuerpo$aunque_se_repita <- aunque_se_repita
      r <- if (editando()) {
        sesion_llamar(s, "PATCH", paste0("v1/clientes/", abierto()$id),
                      c(list(version = abierto()$version), cuerpo))
      } else {
        sesion_llamar(s, "POST", "v1/clientes", cuerpo)
      }
      if (!r$ok) {
        duplicado(r$estado == 409L && grepl("Ya tienes a", r$mensaje, fixed = TRUE))
        return(error(r$mensaje))
      }
      shiny::showNotification(if (editando()) "Listo: guardamos los cambios." else
                                paste0("Listo: agregaste a ", r$cuerpo$nombre, "."),
                              duration = 4, closeButton = FALSE, id = "clientes-aviso")
      refresco(refresco() + 1L)
      if (abrir(r$cuerpo$id)) ir_a_vista("ficha") else ir_a_vista("lista")
    }

    shiny::observeEvent(input$guardar, guardar(FALSE))
    shiny::observeEvent(input$guardar_igual, guardar(TRUE))
    shiny::observeEvent(input$cancelar_formulario, {
      ir_a_vista(if (editando()) "ficha" else "lista")
    })

    # --- Datos que pides (campos propios) --------------------------------------------------
    ui_campos <- function() {
      lista <- campos_borrador()
      htmltools::tagList(
        enlace_atras(ns("volver_de_campos"), "Tus clientes"),
        htmltools::tags$h1(class = "pantalla__titulo", "Datos que pides"),
        htmltools::tags$p(class = "entrada__texto",
                          "Además del nombre y el teléfono, ¿qué quieres anotar de tus clientes?"),
        if (length(lista) > 0) htmltools::tags$ul(
          class = "lista-opciones",
          lapply(seq_along(lista), function(i) {
            k <- lista[[i]]
            item_lista("x-circle", k$nombre, names(TIPOS_CAMPO_UI)[TIPOS_CAMPO_UI == k$tipo],
                       `aria-label` = paste("Quitar", k$nombre),
                       `data-elige-input` = ns("quitar_campo"), `data-elige-valor` = i)
          })
        ),
        if (length(lista) < 10) htmltools::tags$section(
          class = "tarjeta separado",
          campo_texto(ns("campo_nombre"), "Nuevo dato, por ejemplo Instagram o Cumpleaños",
                      autocompletar = "off"),
          shiny::selectInput(ns("campo_tipo"), "Tipo", choices = TIPOS_CAMPO_UI,
                             selectize = FALSE, width = "100%"),
          boton_secundario(ns("sumar_campo"), "Agregar a la lista", "plus-lg")
        ),
        mensaje_error(error()),
        boton_primario(ns("guardar_campos"), "Guardar", "check-lg")
      )
    }

    shiny::observeEvent(input$ir_campos, {
      campos_borrador(lapply(campos(), function(k) list(id = k$id, nombre = k$nombre, tipo = k$tipo)))
      ir_a_vista("campos")
    })
    shiny::observeEvent(input$volver_de_campos, ir_a_vista("lista"))
    shiny::observeEvent(input$sumar_campo, {
      nombre <- trimws(input$campo_nombre %||% "")
      if (nchar(nombre) < 2) return(error("Escribe el nombre del dato."))
      error(NULL)
      campos_borrador(c(campos_borrador(), list(list(nombre = nombre, tipo = input$campo_tipo))))
    })
    shiny::observeEvent(input$quitar_campo, {
      i <- as.integer(input$quitar_campo)
      lista <- campos_borrador()
      if (!is.na(i) && i >= 1 && i <= length(lista)) campos_borrador(lista[-i])
    })
    shiny::observeEvent(input$guardar_campos, {
      r <- sesion_llamar(s, "PUT", "v1/clientes/campos", list(campos = campos_borrador()))
      if (!r$ok) return(error(r$mensaje))
      shiny::showNotification("Listo: guardamos los datos que pides.", duration = 4,
                              closeButton = FALSE, id = "clientes-aviso")
      refresco(refresco() + 1L)
      ir_a_vista("lista")
    })
  })
}
