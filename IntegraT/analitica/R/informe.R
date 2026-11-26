#' Ticket promedio: cuánto deja, en promedio, cada venta del mes
#'
#' `ticket = total / ventas`. Recibe lo que entrega la API (`GET /v1/informes/mes`); con 0 ventas
#' devuelve NA (no hay promedio que mostrar).
#'
#' @param total Lo vendido en el mes (número o texto decimal).
#' @param ventas Cuántas ventas vigentes hubo.
#' @return Número redondeado a 2 decimales, o NA.
#' @export
ticket_promedio <- function(total, ventas) {
  t <- suppressWarnings(as.numeric(total))
  n <- suppressWarnings(as.numeric(ventas))
  if (length(t) != 1L || length(n) != 1L || is.na(t) || is.na(n) || n <= 0) return(NA_real_)
  round(t / n, 2)
}

#' Parte de un total que representa un monto (para "el 40 % de lo que vendiste")
#'
#' @param monto Parte (número o texto decimal).
#' @param total Total (número o texto decimal).
#' @return Proporción entre 0 y 1, o NA si el total es 0.
#' @export
proporcion_de <- function(monto, total) {
  m <- suppressWarnings(as.numeric(monto))
  t <- suppressWarnings(as.numeric(total))
  if (length(m) != 1L || length(t) != 1L || is.na(m) || is.na(t) || t <= 0) return(NA_real_)
  max(0, min(1, m / t))
}
