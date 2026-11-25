# Inicio: "¿cómo va mi negocio hoy?" (docs/DISENO_UX.md §4.1). Los primeros pasos se marcan solos
# según lo que la persona ya hizo, y "Tu mes" muestra lo que calcula la API desde los asientos
# (docs/PLAN_CONTABILIDAD.md): la app no suma ni resta dinero, solo lo muestra.

# Qué hace el botón de cada primer paso: a dónde va y cómo se llama.
accion_de_paso <- function(clave, vocab) {
  switch(clave,
    cinco_platillos = , primer_producto = list(
      destino = "productos", icono = "plus-lg", texto = paste("Agregar un", vocab$item_singular)
    ),
    primera_venta = list(destino = "vender", icono = "cart", texto = "Ir a vender"),
    gastos_fijos = list(destino = "gastos", icono = "cash-coin", texto = "Anotar un gasto"),
    primeros_insumos = list(destino = "inventario", icono = "basket", texto = "Anotar un insumo"),
    primera_compra = list(destino = "compras", icono = "receipt", texto = "Registrar una compra"),
    receta_estrella = list(destino = "productos", icono = "journal-text",
                           texto = paste("Elegir un", vocab$item_singular)),
    list(destino = NULL, icono = "arrow-right", texto = "Ver cómo")
  )
}

# Monto con signo legible: "−Q 30.00" en lugar de "Q -30.00".
dinero_con_signo <- function(valor) {
  if (valor < 0) paste0("−", formato_dinero(abs(valor))) else formato_dinero(valor)
}

# Tarjeta "Tu mes" a partir de la respuesta de GET /v1/resultados.
tarjeta_tu_mes <- function(r) {
  n <- function(campo) as.numeric(r[[campo]] %||% "0")
  queda <- n("te_queda")
  movimientos <- c(n("vendiste"), n("costo_de_lo_vendido"), n("gastaste"), n("se_perdio"),
                   n("otros_ingresos"))
  estado <- if (all(movimientos == 0)) {
    etiqueta_estado("Sin movimientos", "neutro")
  } else if (queda >= 0) {
    etiqueta_estado("Vas ganando", "bien")
  } else {
    etiqueta_estado("Vas perdiendo", "alerta")
  }
  fila <- function(texto, valor, clase = NULL) {
    htmltools::tags$li(
      class = paste(c("tu-mes__fila", clase), collapse = " "),
      htmltools::tags$span(texto), htmltools::tags$span(class = "tu-mes__monto", valor)
    )
  }
  htmltools::tags$section(
    class = "tarjeta tarjeta-numero tu-mes", `aria-label` = "Tu mes",
    htmltools::tags$div(class = "tarjeta-numero__etiqueta",
                        htmltools::tags$span(paste("Tu mes ·", nombre_mes(r$mes))), estado),
    htmltools::tags$p(
      class = paste("tarjeta-numero__valor", if (queda < 0) "tu-mes__valor--negativo"),
      dinero_con_signo(queda)
    ),
    htmltools::tags$p(class = "tarjeta-numero__contexto", "Lo que te queda"),
    htmltools::tags$ul(
      class = "tu-mes__lista",
      fila("Lo que vendiste", formato_dinero(n("vendiste"))),
      fila("Lo que te costó", dinero_con_signo(-n("costo_de_lo_vendido"))),
      fila("Lo que gastaste", dinero_con_signo(-n("gastaste"))),
      if (n("se_perdio") != 0) fila("Lo que se perdió", dinero_con_signo(-n("se_perdio"))),
      if (n("otros_ingresos") != 0) fila("Otros ingresos", dinero_con_signo(n("otros_ingresos")))
    ),
    if (isTRUE(r$sin_iva)) {
      htmltools::tags$p(class = "tu-mes__nota",
                        "Sin IVA: el IVA que cobras no es ganancia, se paga a la SAT.")
    }
  )
}

# Tarjeta "Hoy": lo vendido hoy (GET /v1/ventas) y la caja (GET /v1/caja). `abrir_id`: botón para
# abrir la caja cuando está cerrada.
tarjeta_hoy <- function(ventas, caja, abrir_id) {
  resumen <- if (isTRUE(ventas$ok)) ventas$cuerpo$resumen else NULL
  cantidad <- as.integer(resumen$cantidad %||% 0L)
  total <- as.numeric(resumen$total %||% "0")
  contexto <- if (is.null(resumen)) {
    ventas$mensaje
  } else if (cantidad == 0) {
    "Aún no registras ventas hoy."
  } else {
    paste(cantidad, if (cantidad == 1) "venta" else "ventas")
  }
  abierta <- if (isTRUE(caja$ok)) caja$cuerpo$abierta else NULL
  htmltools::tags$section(
    class = "tarjeta tarjeta-numero hoy", `aria-label` = "Hoy",
    htmltools::tags$div(
      class = "tarjeta-numero__etiqueta", htmltools::tags$span("Vendiste hoy"),
      if (cantidad > 0) etiqueta_estado("Vas bien", "bien") else etiqueta_estado("Empieza hoy", "neutro")
    ),
    htmltools::tags$p(class = "tarjeta-numero__valor", formato_dinero(total)),
    htmltools::tags$p(class = "tarjeta-numero__contexto", contexto),
    if (!is.null(abierta)) {
      htmltools::tags$p(class = "hoy__caja", icono("safe"), " En la caja debería haber ",
                        htmltools::tags$strong(formato_dinero(as.numeric(abierta$efectivo_esperado))))
    } else if (isTRUE(caja$ok)) {
      boton_secundario(abrir_id, "Abrir la caja", "unlock")
    }
  )
}

# Tarjeta "Tu meta del mes": la fórmula es de integrat.analitica (meta_del_mes); la app solo muestra.
tarjeta_meta <- function(r) {
  m <- meta_del_mes(r$gastos_fijos, r$vendiste, r$costo_de_lo_vendido, r$margen_objetivo)
  if (identical(m$estado, "sin_fijos")) {
    return(tarjeta_numero(
      "Tu meta del mes", "—",
      contexto = "La calculamos cuando anotes tus gastos fijos: así sabrás cuánto vender para no perder."))
  }
  if (identical(m$estado, "sin_margen")) {
    return(tarjeta_numero(
      "Tu meta del mes", "—",
      contexto = "Con lo que te cuesta lo que vendes, no te queda margen. Revisa tus precios.",
      estado = etiqueta_estado("Revisa precios", "alerta")))
  }
  porcentaje <- round(100 * m$avance)
  htmltools::tags$section(
    class = "tarjeta tarjeta-numero meta", `aria-label` = "Tu meta del mes",
    htmltools::tags$div(
      class = "tarjeta-numero__etiqueta", htmltools::tags$span("Tu meta del mes"),
      if (m$falta == 0) etiqueta_estado("¡Lograda!", "bien")
      else if (isTRUE(m$margen_estimado)) etiqueta_estado("Estimada", "neutro")
    ),
    htmltools::tags$p(class = "tarjeta-numero__valor", formato_dinero(m$meta)),
    htmltools::tags$progress(class = "meta__barra", max = 100, value = porcentaje,
                             `aria-label` = paste0(porcentaje, " % de la meta")),
    htmltools::tags$p(
      class = "tarjeta-numero__contexto",
      if (m$falta == 0) "Ya vendiste lo necesario para cubrir tus gastos fijos."
      else paste0("Llevas ", porcentaje, " %. Te faltan ", formato_dinero(m$falta),
                  " para no perder este mes.")
    ),
    if (isTRUE(m$margen_estimado)) {
      htmltools::tags$p(class = "tu-mes__nota",
                        "Estimada con un margen de ", round(100 * m$margen), " %. ",
                        "Se ajusta sola cuando tus ventas tengan costo (recetas).")
    }
  )
}

mod_inicio_ui <- function(id, vocab, pasos = NULL) {
  ns <- shiny::NS(id)
  htmltools::tags$div(
    class = "pila",
    shiny::uiOutput(ns("pasos")),
    shiny::uiOutput(ns("hoy")),
    shiny::uiOutput(ns("meta")),
    shiny::uiOutput(ns("tu_mes")),
    shiny::uiOutput(ns("consejo"))
  )
}

# `seccion`: reactivo con la sección visible; "Tu mes" se pide de nuevo cada vez que se vuelve
# al Inicio (así refleja lo que se vendió, gastó o compró en las otras secciones).
mod_inicio_server <- function(id, s, ir_a, seccion = shiny::reactive("inicio")) {
  shiny::moduleServer(id, function(input, output, session) {
    ns <- session$ns

    resultados <- shiny::reactive({
      shiny::req(s$negocio)
      s$cuentas_v
      shiny::req(identical(seccion() %||% "inicio", "inicio"))
      sesion_llamar(s, "GET", "v1/resultados")
    })

    hoy <- shiny::reactive({
      shiny::req(s$negocio)
      s$cuentas_v
      shiny::req(identical(seccion() %||% "inicio", "inicio"))
      list(ventas = sesion_llamar(s, "GET", "v1/ventas"), caja = sesion_llamar(s, "GET", "v1/caja"))
    })

    output$hoy <- shiny::renderUI({
      h <- hoy()
      tarjeta_hoy(h$ventas, h$caja, ns("abrir_caja"))
    })
    shiny::observeEvent(input$abrir_caja, ir_a("caja"))

    output$meta <- shiny::renderUI({
      r <- resultados()
      if (!r$ok) return(NULL)  # el cajero no ve las ganancias; los errores ya los dice "Tu mes"
      tarjeta_meta(r$cuerpo)
    })

    output$tu_mes <- shiny::renderUI({
      r <- resultados()
      if (r$ok) return(tarjeta_tu_mes(r$cuerpo))
      if (r$estado == 403L) return(NULL)  # el cajero no ve las ganancias
      tarjeta_numero("Tu mes", "—", contexto = r$mensaje)
    })

    # Los pasos más recientes (los que dejó el catálogo) o, si no hay, los del negocio al entrar.
    pasos <- shiny::reactive({
      actuales <- s$pasos
      if (!is.null(actuales) && identical(actuales$negocio_id, s$negocio_id)) {
        return(actuales$pasos)
      }
      s$negocio$primeros_pasos
    })

    siguiente <- function() {
      pendientes <- Filter(function(p) !isTRUE(p$hecho), pasos())
      if (length(pendientes) > 0) pendientes[[1]] else NULL
    }

    output$pasos <- shiny::renderUI({
      if (length(pasos()) == 0) return(NULL)
      htmltools::tags$section(
        class = "tarjeta",
        htmltools::tags$h2(class = "hoja__titulo", "Tus primeros pasos"),
        lista_pasos(pasos())
      )
    })

    output$consejo <- shiny::renderUI({
      shiny::req(s$negocio)
      paso <- siguiente()
      if (is.null(paso)) {
        if (length(pasos()) == 0) return(NULL)
        return(tarjeta_consejo("¡Muy bien! Ya completaste tus primeros pasos."))
      }
      accion <- accion_de_paso(paso$clave, vocab_negocio(s$negocio))
      tarjeta_consejo(paso$texto, accion = boton_secundario(ns("hacer_paso"), accion$texto,
                                                             accion$icono))
    })

    shiny::observeEvent(input$hacer_paso, {
      paso <- siguiente()
      if (is.null(paso)) return()
      destino <- accion_de_paso(paso$clave, vocab_negocio(s$negocio))$destino
      if (is.null(destino)) aviso_pronto() else ir_a(destino)
    })
  })
}
