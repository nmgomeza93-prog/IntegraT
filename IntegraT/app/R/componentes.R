# Componentes base del sistema de diseño (docs/DISENO_UX.md §5.4).
# Reglas: un botón primario por pantalla; estados = color + icono + palabra; nada de tablas en móvil.

icono <- function(nombre, titulo = NULL) {
  bsicons::bs_icon(nombre, a11y = if (is.null(titulo)) "deco" else "sem", title = titulo)
}

boton_primario <- function(id, texto, icono_nombre = NULL) {
  htmltools::tags$button(
    id = id, type = "button",
    class = "boton-primario action-button",
    if (!is.null(icono_nombre)) icono(icono_nombre),
    htmltools::tags$span(texto)
  )
}

boton_secundario <- function(id, texto, icono_nombre = NULL) {
  htmltools::tags$button(
    id = id, type = "button",
    class = "boton-secundario action-button",
    if (!is.null(icono_nombre)) icono(icono_nombre),
    htmltools::tags$span(texto)
  )
}

# Estado con significado: tipo = "bien" | "atencion" | "alerta" | "neutro"
etiqueta_estado <- function(texto, tipo = c("bien", "atencion", "alerta", "neutro")) {
  tipo <- match.arg(tipo)
  icono_tipo <- switch(tipo,
    bien = "check-circle-fill",
    atencion = "exclamation-triangle-fill",
    alerta = "x-octagon-fill",
    neutro = "dash-circle"
  )
  htmltools::tags$span(class = paste0("estado estado--", tipo), icono(icono_tipo), texto)
}

tarjeta_numero <- function(etiqueta, valor, contexto = NULL, estado = NULL) {
  htmltools::tags$section(
    class = "tarjeta tarjeta-numero",
    `aria-label` = etiqueta,
    htmltools::tags$div(class = "tarjeta-numero__etiqueta", htmltools::tags$span(etiqueta), estado),
    htmltools::tags$p(class = "tarjeta-numero__valor", valor),
    if (!is.null(contexto)) htmltools::tags$p(class = "tarjeta-numero__contexto", contexto)
  )
}

tarjeta_consejo <- function(texto, accion = NULL) {
  htmltools::tags$section(
    class = "tarjeta tarjeta-consejo",
    htmltools::tags$p(class = "tarjeta-consejo__titulo", icono("lightbulb"), " Qué hacer ahora"),
    htmltools::tags$p(class = "tarjeta-consejo__texto", texto),
    accion
  )
}

estado_vacio <- function(icono_nombre, titulo, texto, accion = NULL) {
  htmltools::tags$div(
    class = "estado-vacio",
    htmltools::tags$div(class = "estado-vacio__icono", icono(icono_nombre)),
    htmltools::tags$h2(class = "estado-vacio__titulo", titulo),
    htmltools::tags$p(class = "estado-vacio__texto", texto),
    accion
  )
}

# Hoja inferior: se abre con un elemento que tenga data-abre-hoja="<id>".
hoja_inferior <- function(id, titulo, ...) {
  htmltools::tagList(
    htmltools::tags$div(
      id = id, class = "hoja", role = "dialog", `aria-modal` = "true",
      `aria-hidden` = "true", `aria-labelledby` = paste0(id, "-titulo"),
      htmltools::tags$div(class = "hoja__agarradera"),
      htmltools::tags$h2(id = paste0(id, "-titulo"), class = "hoja__titulo", titulo),
      ...
    ),
    htmltools::tags$div(class = "hoja-fondo", `data-cierra-hoja` = NA)
  )
}

accion_rapida <- function(accion, icono_nombre, texto, detalle = NULL) {
  htmltools::tags$button(
    type = "button", class = "accion-rapida", `data-accion` = accion,
    htmltools::tags$span(class = "accion-rapida__icono", icono(icono_nombre)),
    htmltools::tags$span(
      texto,
      if (!is.null(detalle)) htmltools::tags$span(class = "accion-rapida__detalle", detalle)
    )
  )
}

item_lista <- function(icono_nombre, texto, extra = NULL, ...) {
  htmltools::tags$li(
    htmltools::tags$button(
      type = "button", class = "lista-opciones__item", ...,
      icono(icono_nombre),
      htmltools::tags$span(class = "lista-opciones__texto", texto),
      if (!is.null(extra)) htmltools::tags$span(class = "lista-opciones__extra", extra)
    )
  )
}

# Formato de dinero: "Q 1,245.00"
formato_dinero <- function(valor, simbolo = "Q") {
  paste0(simbolo, " ", formatC(valor, format = "f", digits = 2, big.mark = ","))
}

# --- Formularios y pantallas de entrada ---------------------------------------------------

# Campo de texto o de contraseña con etiqueta visible. `autocompletar` e `modo` ayudan
# al teclado del celular (correo, contraseña nueva, etc.).
campo_texto <- function(id, etiqueta, valor = "", placeholder = NULL, autocompletar = NULL,
                        modo = NULL, clave = FALSE) {
  base <- if (clave) {
    shiny::passwordInput(id, etiqueta, value = valor, placeholder = placeholder, width = "100%")
  } else {
    shiny::textInput(id, etiqueta, value = valor, placeholder = placeholder, width = "100%")
  }
  atributos <- Filter(Negate(is.null), list(autocomplete = autocompletar, inputmode = modo))
  if (length(atributos) > 0) {
    consulta <- htmltools::tagQuery(base)$find("input")
    base <- do.call(consulta$addAttrs, atributos)$allTags()
  }
  htmltools::tags$div(class = "campo", base)
}

# Mensaje de error visible y anunciado por lectores de pantalla. NULL = sin mensaje.
mensaje_error <- function(texto) {
  if (is.null(texto) || !nzchar(texto)) return(NULL)
  htmltools::tags$p(class = "mensaje-error", role = "alert", icono("exclamation-triangle-fill"),
                    htmltools::tags$span(texto))
}

enlace_atras <- function(id, texto = "Atrás") {
  htmltools::tags$button(id = id, type = "button", class = "enlace-boton action-button",
                         icono("arrow-left"), htmltools::tags$span(texto))
}

# Opción grande y táctil: al tocarla manda `valor` al input `input_id` (ya con namespace).
opcion_grande <- function(input_id, valor, icono_nombre, titulo, detalle = NULL, activa = FALSE) {
  htmltools::tags$button(
    type = "button", class = "opcion-grande",
    `data-elige-input` = input_id, `data-elige-valor` = valor,
    `aria-pressed` = if (activa) "true" else "false",
    htmltools::tags$span(class = "opcion-grande__icono", icono(icono_nombre)),
    htmltools::tags$span(
      class = "opcion-grande__texto",
      htmltools::tags$span(class = "opcion-grande__titulo", titulo),
      if (!is.null(detalle)) htmltools::tags$span(class = "opcion-grande__detalle", detalle)
    )
  )
}

progreso_pasos <- function(actual, total) {
  htmltools::tags$div(
    class = "progreso-pasos",
    htmltools::tags$p(class = "progreso-pasos__texto", paste0("Paso ", actual, " de ", total)),
    htmltools::tags$div(
      class = "progreso-pasos__barras", `aria-hidden` = "true",
      lapply(seq_len(total), function(i) {
        clase <- "progreso-pasos__barra"
        if (i <= actual) clase <- paste(clase, "progreso-pasos__barra--hecha")
        htmltools::tags$span(class = clase)
      })
    )
  )
}

# Lista de primeros pasos (viene de la plantilla del tipo de negocio).
lista_pasos <- function(pasos) {
  htmltools::tags$ul(
    class = "checklist",
    lapply(pasos, function(p) {
      hecho <- isTRUE(p$hecho)
      htmltools::tags$li(
        class = paste("checklist__item", if (hecho) "checklist__item--hecho"),
        icono(if (hecho) "check-circle-fill" else (p$icono %||% "circle")),
        htmltools::tags$span(p$texto)
      )
    })
  )
}
