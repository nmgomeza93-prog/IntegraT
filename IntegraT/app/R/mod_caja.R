# Caja del día (Más → "Caja del día" y ➕ → "Cerrar el día"): abrir con el efectivo con que se
# empieza, ver cuánto debería haber y cerrar contando lo que hay (docs/PLAN_CAJA.md).
# El efectivo esperado y la diferencia los calcula la API desde los libros; la app solo muestra.

# Renglones del resumen de la caja: campo de la API -> texto.
RENGLONES_CAJA <- list(
  ventas = "Ventas en efectivo", gastos = "Gastos en efectivo", compras = "Compras en efectivo",
  inventario = "Compras anotadas en el inventario", dueno = "Lo que pusiste o sacaste",
  otros = "Otros movimientos"
)

# Texto de una diferencia de caja: "Cuadra", "Faltaron Q 20.00" o "Sobraron Q 5.00".
texto_diferencia <- function(diferencia) {
  d <- as.numeric(diferencia %||% "0")
  if (d == 0) return("Cuadra")
  if (d < 0) paste("Faltaron", formato_dinero(abs(d))) else paste("Sobraron", formato_dinero(d))
}

estado_diferencia <- function(diferencia) {
  d <- as.numeric(diferencia %||% "0")
  if (d == 0) etiqueta_estado("Cuadra", "bien")
  else if (d < 0) etiqueta_estado(texto_diferencia(d), "alerta")
  else etiqueta_estado(texto_diferencia(d), "atencion")
}

# Lista del resumen: solo los renglones que se movieron, más lo cobrado sin efectivo.
lista_resumen_caja <- function(sesion) {
  r <- sesion$resumen
  filas <- list(fila_lista("box-arrow-in-right", "Abriste con",
                           formato_dinero(as.numeric(sesion$monto_apertura))))
  for (campo in names(RENGLONES_CAJA)) {
    valor <- as.numeric(r[[campo]] %||% "0")
    if (valor != 0) filas[[length(filas) + 1L]] <- fila_lista(
      if (valor > 0) "plus-circle" else "dash-circle", RENGLONES_CAJA[[campo]],
      dinero_con_signo(valor))
  }
  sin_efectivo <- as.numeric(r$ventas_tarjeta) + as.numeric(r$ventas_transferencia)
  htmltools::tagList(
    htmltools::tags$ul(class = "lista-opciones", filas),
    if (sin_efectivo > 0) {
      htmltools::tags$p(class = "entrada__texto",
                        "Además vendiste ", formato_dinero(as.numeric(r$ventas_tarjeta)),
                        " con tarjeta y ", formato_dinero(as.numeric(r$ventas_transferencia)),
                        " por transferencia (eso no está en la caja).")
    }
  )
}

mod_caja_ui <- function(id) {
  ns <- shiny::NS(id)
  htmltools::tags$div(class = "caja", shiny::uiOutput(ns("contenido")))
}

mod_caja_server <- function(id, s, ir_a, seccion = shiny::reactive("caja")) {
  shiny::moduleServer(id, function(input, output, session) {
    ns <- session$ns
    vista <- shiny::reactiveVal("estado")  # "estado", "contar", "revisar", "cerrada" o "historial"
    error <- shiny::reactiveVal(NULL)
    refresco <- shiny::reactiveVal(0L)
    contado <- shiny::reactiveVal(NULL)
    nota <- shiny::reactiveVal("")
    cierre <- shiny::reactiveVal(NULL)  # el cierre recién hecho
    base_clave <- shiny::reactiveVal(NULL)

    nueva_base <- function() base_clave(paste(as.character(openssl::rand_bytes(16)), collapse = ""))

    shiny::observeEvent(s$negocio_id, {
      vista("estado")
      error(NULL)
      contado(NULL)
      cierre(NULL)
      nueva_base()
    }, ignoreNULL = FALSE)

    # "Cerrar el día" de las acciones rápidas: si la caja está abierta, va directo a contar.
    shiny::observeEvent(s$abrir_cierre, {
      if (s$abrir_cierre == 0L) return()
      error(NULL)
      contado(NULL)
      nota("")
      r <- sesion_llamar(s, "GET", "v1/caja")
      abierta <- r$ok && !is.null(r$cuerpo$abierta)
      refresco(refresco() + 1L)
      ir_a_vista(if (abierta) "contar" else "estado")  # cerrada: primero hay que abrirla
    }, ignoreInit = TRUE)

    ir_a_vista <- function(nueva) {
      vista(nueva)
      session$sendCustomMessage("subir", TRUE)
    }

    datos <- shiny::reactive({
      refresco()
      s$negocio_id
      shiny::req(identical(seccion() %||% "caja", "caja"))
      shiny::req(shiny::isolate(s$acceso))
      sesion_llamar(s, "GET", "v1/caja")
    })

    cierres <- shiny::reactive({
      shiny::req(vista() == "historial")
      refresco()
      sesion_llamar(s, "GET", "v1/caja/cierres")
    })

    titulo <- function(texto) htmltools::tags$h1(class = "pantalla__titulo", texto)

    ui_estado <- function() {
      r <- datos()
      if (!r$ok) {
        return(htmltools::tagList(
          titulo("Caja del día"), mensaje_error(r$mensaje),
          boton_secundario(ns("reintentar"), "Intentar de nuevo", "arrow-clockwise")))
      }
      abierta <- r$cuerpo$abierta
      ultimo <- r$cuerpo$ultimo_cierre
      if (is.null(abierta)) {
        return(htmltools::tagList(
          enlace_atras(ns("volver")),
          titulo("Caja del día"),
          estado_vacio("safe", "La caja está cerrada",
                       "Ábrela al empezar el día con el efectivo que tienes para dar vuelto."),
          campo_texto(ns("apertura"), "¿Con cuánto efectivo abres? (Q)", placeholder = "Ejemplo: 200",
                      autocompletar = "off", modo = "decimal"),
          mensaje_error(error()),
          boton_primario(ns("abrir"), "Abrir la caja", "unlock"),
          if (!is.null(ultimo)) {
            tarjeta_numero("Último cierre", formato_dinero(as.numeric(ultimo$efectivo_contado)),
                           contexto = paste0(fecha_corta(ultimo$fecha), " · contaste en la caja"),
                           estado = estado_diferencia(ultimo$diferencia))
          },
          enlace_accion(ns("ver_historial"), "Ver los cierres del mes", "clock-history")
        ))
      }
      htmltools::tagList(
        enlace_atras(ns("volver")),
        titulo("Caja del día"),
        tarjeta_numero("Debería haber en la caja",
                       formato_dinero(as.numeric(abierta$efectivo_esperado)),
                       contexto = paste("Abierta desde las", hora_local(abierta$abierta_en)),
                       estado = etiqueta_estado("Abierta", "bien")),
        lista_resumen_caja(abierta),
        boton_primario(ns("ir_contar"), "Cerrar el día", "safe"),
        enlace_accion(ns("ver_historial"), "Ver los cierres del mes", "clock-history")
      )
    }

    ui_contar <- function() {
      abierta <- datos()$cuerpo$abierta
      htmltools::tagList(
        enlace_atras(ns("atras")),
        titulo("Cuenta tu efectivo"),
        htmltools::tags$p(class = "entrada__texto",
                          "Cuenta los billetes y monedas de la caja y escribe el total."),
        campo_texto(ns("contado"), "¿Cuánto efectivo hay? (Q)", valor = contado() %||% "",
                    placeholder = "Ejemplo: 345.50", autocompletar = "off", modo = "decimal"),
        campo_texto(ns("nota"), "Nota (opcional)", valor = nota(),
                    placeholder = "Ejemplo: le di cambio a la vecina", autocompletar = "off"),
        mensaje_error(error()),
        boton_primario(ns("revisar"), "Revisar", "arrow-right"),
        if (is.null(abierta)) mensaje_error("La caja ya no está abierta.")
      )
    }

    ui_revisar <- function() {
      abierta <- datos()$cuerpo$abierta
      esperado <- as.numeric(abierta$efectivo_esperado)
      contado_num <- as.numeric(contado())
      htmltools::tagList(
        enlace_atras(ns("atras_contar")),
        titulo("Revisa antes de cerrar"),
        htmltools::tags$ul(
          class = "lista-opciones",
          fila_lista("calculator", "Debería haber", formato_dinero(esperado)),
          fila_lista("cash-stack", "Contaste", formato_dinero(contado_num))
        ),
        tarjeta_numero("Diferencia", texto_diferencia(round(contado_num - esperado, 2)),
                       contexto = "Si no cuadra, queda anotado como faltante o sobrante.",
                       estado = estado_diferencia(round(contado_num - esperado, 2))),
        mensaje_error(error()),
        boton_primario(ns("confirmar"), "Cerrar el día", "check-lg")
      )
    }

    ui_cerrada <- function() {
      c <- cierre()
      htmltools::tagList(
        titulo("Día cerrado"),
        tarjeta_numero("Contaste", formato_dinero(as.numeric(c$efectivo_contado)),
                       contexto = paste("Debía haber", formato_dinero(as.numeric(c$efectivo_esperado))),
                       estado = estado_diferencia(c$diferencia)),
        lista_resumen_caja(c),
        boton_primario(ns("listo"), "Listo", "check-lg")
      )
    }

    ui_historial <- function() {
      r <- cierres()
      lista <- if (r$ok) r$cuerpo$cierres else list()
      htmltools::tagList(
        enlace_atras(ns("atras")),
        titulo("Cierres del mes"),
        if (!r$ok) mensaje_error(r$mensaje)
        else if (length(lista) == 0) {
          estado_vacio("clock-history", "Aún no cierras la caja este mes",
                       "Cuando cierres el día, aquí verás cada cierre.")
        } else {
          htmltools::tags$ul(
            class = "lista-opciones",
            lapply(lista, function(c) {
              fila_lista("safe", paste(fecha_corta(c$fecha), "·",
                                       formato_dinero(as.numeric(c$efectivo_contado))),
                         texto_diferencia(c$diferencia))
            })
          )
        }
      )
    }

    output$contenido <- shiny::renderUI({
      switch(vista(), contar = ui_contar(), revisar = ui_revisar(), cerrada = ui_cerrada(),
             historial = ui_historial(), ui_estado())
    })

    # --- Acciones ----------------------------------------------------------------------
    shiny::observeEvent(input$volver, ir_a("mas"))
    shiny::observeEvent(input$reintentar, refresco(refresco() + 1L))
    shiny::observeEvent(input$atras, {
      error(NULL)
      ir_a_vista("estado")
    })
    shiny::observeEvent(input$atras_contar, {
      error(NULL)
      ir_a_vista("contar")
    })
    shiny::observeEvent(input$ver_historial, ir_a_vista("historial"))
    shiny::observeEvent(input$listo, {
      cierre(NULL)
      ir_a_vista("estado")
    })

    shiny::observeEvent(input$abrir, {
      monto <- normalizar_precio(input$apertura)
      if (is.null(monto)) {
        return(error("Escribe con cuánto efectivo abres, por ejemplo 200 o 0."))
      }
      r <- sesion_llamar(s, "POST", "v1/caja/abrir", list(monto_apertura = monto))
      if (!r$ok && r$estado != 409L) return(error(r$mensaje))  # 409: ya estaba abierta
      error(NULL)
      refresco(refresco() + 1L)
      shiny::showNotification(paste("Abriste la caja con", formato_dinero(as.numeric(monto))),
                              duration = 4, closeButton = FALSE, id = "caja-aviso")
    })

    shiny::observeEvent(input$ir_contar, {
      error(NULL)
      contado(NULL)
      nota("")
      ir_a_vista("contar")
    })

    shiny::observeEvent(input$revisar, {
      monto <- normalizar_precio(input$contado)
      if (is.null(monto)) {
        return(error("Escribe cuánto efectivo contaste, por ejemplo 345.50 o 0."))
      }
      contado(monto)
      nota(trimws(input$nota %||% ""))
      error(NULL)
      refresco(refresco() + 1L)  # el esperado más reciente
      ir_a_vista("revisar")
    })

    shiny::observeEvent(input$confirmar, {
      if (vista() != "revisar") return()  # un doble toque llega cuando ya se cerró
      huella <- openssl::sha256(charToRaw(paste(base_clave(), contado(), nota(), sep = "|")))
      r <- sesion_llamar(
        s, "POST", "v1/caja/cerrar",
        list(efectivo_contado = contado(), nota = if (nzchar(nota())) nota() else NULL),
        cabeceras = list("Idempotency-Key" = paste0("cierre-", substr(as.character(huella), 1, 40)))
      )
      if (!r$ok) return(error(r$mensaje))
      error(NULL)
      cierre(r$cuerpo)
      nueva_base()
      refresco(refresco() + 1L)
      s$cuentas_v <- shiny::isolate(s$cuentas_v) + 1L
      ir_a_vista("cerrada")
    })
  })
}
