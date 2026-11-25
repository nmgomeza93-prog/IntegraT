# Tu dinero y el negocio (dentro de Más): lo que el dueño pone ("aporte") o saca para él
# ("retiro"). Sacar dinero no es un gasto: no baja lo que te queda (docs/PLAN_CAJA.md).

TIPOS_DUENO_UI <- list(
  aporte = list(boton = "Pusiste dinero", titulo = "Pusiste dinero en el negocio",
                icono = "box-arrow-in-down", pregunta = "¿Cuánto pusiste? (Q)"),
  retiro = list(boton = "Sacaste dinero", titulo = "Sacaste dinero para ti",
                icono = "box-arrow-up", pregunta = "¿Cuánto sacaste? (Q)")
)
MEDIOS_DUENO_UI <- c(efectivo = "Efectivo", banco = "Banco")

mod_dueno_ui <- function(id) {
  ns <- shiny::NS(id)
  htmltools::tags$div(class = "dueno", shiny::uiOutput(ns("contenido")))
}

mod_dueno_server <- function(id, s, ir_a) {
  shiny::moduleServer(id, function(input, output, session) {
    ns <- session$ns
    vista <- shiny::reactiveVal("mes")  # "mes" o "nuevo"
    tipo <- shiny::reactiveVal("aporte")
    medio <- shiny::reactiveVal("efectivo")
    error <- shiny::reactiveVal(NULL)
    refresco <- shiny::reactiveVal(0L)
    por_borrar <- shiny::reactiveVal(NULL)
    base_clave <- shiny::reactiveVal(NULL)

    shiny::observeEvent(s$negocio_id, {
      vista("mes")
      error(NULL)
      por_borrar(NULL)
      base_clave(paste(as.character(openssl::rand_bytes(16)), collapse = ""))
    }, ignoreNULL = FALSE)

    ir_a_vista <- function(nueva) {
      vista(nueva)
      session$sendCustomMessage("subir", TRUE)
    }

    datos <- shiny::reactive({
      refresco()
      s$al_dia  # al entrar, al día con lo que se guardó en otra pantalla
      s$negocio_id
      shiny::req(shiny::isolate(s$acceso))
      sesion_llamar(s, "GET", "v1/dueno")
    })

    ui_mes <- function() {
      r <- datos()
      if (!r$ok) {
        return(htmltools::tagList(
          enlace_atras(ns("volver")),
          htmltools::tags$h1(class = "pantalla__titulo", "Tu dinero y el negocio"),
          mensaje_error(r$mensaje)))
      }
      m <- r$cuerpo
      htmltools::tagList(
        enlace_atras(ns("volver")),
        htmltools::tags$h1(class = "pantalla__titulo", "Tu dinero y el negocio"),
        htmltools::tags$p(class = "entrada__texto",
                          "Anota cuando pones dinero tuyo en el negocio o sacas para tu casa. ",
                          "Sacar no es un gasto del negocio."),
        htmltools::tags$div(
          class = "pila",
          boton_primario(ns("nuevo_aporte"), TIPOS_DUENO_UI$aporte$boton,
                         TIPOS_DUENO_UI$aporte$icono),
          boton_secundario(ns("nuevo_retiro"), TIPOS_DUENO_UI$retiro$boton,
                           TIPOS_DUENO_UI$retiro$icono)
        ),
        if (length(m$movimientos) == 0) {
          estado_vacio("wallet2", paste("Nada anotado en", tolower(nombre_mes(m$mes))),
                       "Cuando pongas o saques dinero, aparecerá aquí.")
        } else {
          htmltools::tagList(
            tarjeta_numero(nombre_mes(m$mes), formato_dinero(as.numeric(m$total_aportes)),
                           contexto = paste("pusiste · sacaste",
                                            formato_dinero(as.numeric(m$total_retiros)))),
            htmltools::tags$ul(
              class = "lista-opciones",
              lapply(m$movimientos, function(mv) {
                ui <- TIPOS_DUENO_UI[[mv$tipo]]
                signo <- if (mv$tipo == "retiro") -1 else 1
                item_lista(ui$icono,
                           paste0(if (mv$tipo == "aporte") "Pusiste" else "Sacaste", " · ",
                                  fecha_corta(mv$fecha), " · ", MEDIOS_DUENO_UI[[mv$medio]],
                                  if (!is.null(mv$nota)) paste0(" · ", mv$nota) else ""),
                           dinero_con_signo(signo * as.numeric(mv$monto)),
                           `data-elige-input` = ns("tocado"), `data-elige-valor` = mv$id)
              })
            )
          )
        },
        ui_borrar(m$movimientos)
      )
    }

    ui_borrar <- function(movimientos) {
      id <- por_borrar()
      if (is.null(id)) return(NULL)
      mv <- Filter(function(x) identical(x$id, id), movimientos)
      if (length(mv) == 0) return(NULL)
      mv <- mv[[1]]
      htmltools::tags$section(
        class = "tarjeta",
        htmltools::tags$h2(class = "hoja__titulo",
                           paste0("¿Borrar ", formato_dinero(as.numeric(mv$monto)), " del ",
                                  fecha_corta(mv$fecha), "?")),
        htmltools::tags$p(class = "entrada__texto", "Se quita de tus cuentas. No se puede deshacer."),
        htmltools::tags$div(
          class = "pila",
          boton_primario(ns("confirmar_borrar"), "Sí, borrar", "trash3"),
          boton_secundario(ns("cancelar_borrar"), "No, dejarlo", "x-lg")
        )
      )
    }

    ui_nuevo <- function() {
      t <- TIPOS_DUENO_UI[[tipo()]]
      elegido <- shiny::isolate(medio())
      htmltools::tagList(
        enlace_atras(ns("atras")),
        htmltools::tags$h1(class = "pantalla__titulo", t$titulo),
        htmltools::tags$div(
          class = "pila",
          campo_texto(ns("monto"), t$pregunta, placeholder = "Ejemplo: 500",
                      autocompletar = "off", modo = "decimal"),
          htmltools::tags$div(
            class = "campo",
            htmltools::tags$label(id = ns("medio-etiqueta"), "¿De dónde?"),
            htmltools::tags$div(
              class = "segmentado", role = "group", `aria-labelledby` = ns("medio-etiqueta"),
              lapply(names(MEDIOS_DUENO_UI), function(m) {
                htmltools::tags$button(
                  type = "button", class = "segmentado__opcion",
                  `data-elige-input` = ns("medio"), `data-elige-valor` = m,
                  `aria-pressed` = if (identical(elegido, m)) "true" else "false",
                  MEDIOS_DUENO_UI[[m]])
              })
            )
          ),
          campo_fecha(ns("fecha"), "¿Cuándo?", valor = hoy_local(), maximo = hoy_local()),
          campo_texto(ns("nota"), "Nota (opcional)", autocompletar = "off",
                      placeholder = "Ejemplo: para comprar la estufa"),
          mensaje_error(error()),
          boton_primario(ns("guardar"), "Guardar", "check-lg")
        )
      )
    }

    output$contenido <- shiny::renderUI({
      switch(vista(), nuevo = ui_nuevo(), ui_mes())
    })

    # --- Acciones ----------------------------------------------------------------------
    shiny::observeEvent(input$volver, ir_a("mas"))
    shiny::observeEvent(input$atras, {
      error(NULL)
      ir_a_vista("mes")
    })
    abrir_formulario <- function(nuevo_tipo) {
      tipo(nuevo_tipo)
      error(NULL)
      por_borrar(NULL)
      ir_a_vista("nuevo")
    }
    shiny::observeEvent(input$nuevo_aporte, abrir_formulario("aporte"))
    shiny::observeEvent(input$nuevo_retiro, abrir_formulario("retiro"))
    shiny::observeEvent(input$medio, {
      if (input$medio %in% names(MEDIOS_DUENO_UI)) medio(input$medio)
    })
    shiny::observeEvent(input$tocado, por_borrar(input$tocado))
    shiny::observeEvent(input$cancelar_borrar, por_borrar(NULL))

    shiny::observeEvent(input$confirmar_borrar, {
      id <- por_borrar()
      if (is.null(id)) return()
      r <- sesion_llamar(s, "DELETE", paste0("v1/dueno/", id))
      por_borrar(NULL)
      if (!r$ok && r$estado != 404L) {
        shiny::showNotification(r$mensaje, duration = 5, closeButton = FALSE)
      }
      refresco(refresco() + 1L)
      s$cuentas_v <- shiny::isolate(s$cuentas_v) + 1L
    })

    shiny::observeEvent(input$guardar, {
      if (vista() != "nuevo") return()  # un doble toque llega cuando ya se guardó
      monto <- normalizar_precio(input$monto)
      if (is.null(monto) || as.numeric(monto) <= 0) {
        return(error("Escribe el monto con números, por ejemplo 500 o 125.50."))
      }
      fecha <- trimws(input$fecha %||% "")
      if (!grepl("^[0-9]{4}-[0-9]{2}-[0-9]{2}$", fecha)) return(error("Elige la fecha."))
      if (fecha > hoy_local()) return(error("La fecha no puede ser de mañana en adelante."))
      nota <- trimws(input$nota %||% "")
      huella <- openssl::sha256(charToRaw(paste(base_clave(), tipo(), monto, medio(), fecha, nota,
                                                sep = "|")))
      r <- sesion_llamar(
        s, "POST", "v1/dueno",
        list(tipo = tipo(), monto = monto, medio = medio(), fecha = fecha,
             nota = if (nzchar(nota)) nota else NULL),
        cabeceras = list("Idempotency-Key" = paste0("dueno-", substr(as.character(huella), 1, 40)))
      )
      if (!r$ok) return(error(r$mensaje))
      error(NULL)
      base_clave(paste(as.character(openssl::rand_bytes(16)), collapse = ""))
      refresco(refresco() + 1L)
      s$cuentas_v <- shiny::isolate(s$cuentas_v) + 1L
      ir_a_vista("mes")
      shiny::showNotification(
        paste0(if (tipo() == "aporte") "Anotaste que pusiste " else "Anotaste que sacaste ",
               formato_dinero(as.numeric(monto)), "."),
        duration = 4, closeButton = FALSE, id = "dueno-aviso")
    })
  })
}
