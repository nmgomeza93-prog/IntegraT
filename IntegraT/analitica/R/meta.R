#' Meta del mes: cuánto vender para no perder (punto de equilibrio simple)
#'
#' `meta = gastos_fijos / margen`, con `margen = 1 - costo_ventas / ventas` del mes
#' (PROPUESTA_ARQUITECTURA.md §8). Si todavía no hay ventas con costo, usa el margen objetivo del
#' negocio y la meta queda marcada como estimada. Recibe los datos que entrega la API
#' (`GET /v1/resultados`); no toca la base de datos.
#'
#' @param gastos_fijos Gastos fijos del mes (número o texto decimal).
#' @param ventas Lo vendido en el mes (sin IVA en el régimen general).
#' @param costo_ventas Lo que costó lo vendido en el mes.
#' @param margen_objetivo Margen de respaldo, entre 0 y 1 (0.35 por defecto).
#' @return Lista con `estado` ("ok", "sin_fijos" o "sin_margen"), `meta`, `margen`,
#'   `margen_estimado`, `avance` (0 a 1, tope 1) y `falta` (0 si ya se alcanzó).
#' @export
meta_del_mes <- function(gastos_fijos, ventas, costo_ventas, margen_objetivo = 0.35) {
  numero <- function(x) {
    v <- suppressWarnings(as.numeric(x))
    if (length(v) != 1L || is.na(v)) 0 else v
  }
  fijos <- numero(gastos_fijos)
  vendido <- numero(ventas)
  costo <- numero(costo_ventas)
  objetivo <- numero(margen_objetivo)

  estimado <- !(vendido > 0 && costo > 0)
  margen <- if (estimado) objetivo else 1 - costo / vendido
  base <- list(estado = "ok", meta = NA_real_, margen = margen, margen_estimado = estimado,
               avance = NA_real_, falta = NA_real_)
  if (fijos <= 0) return(utils::modifyList(base, list(estado = "sin_fijos")))
  if (margen <= 0) return(utils::modifyList(base, list(estado = "sin_margen")))

  meta <- round(fijos / margen, 2)
  utils::modifyList(base, list(
    meta = meta,
    avance = min(1, max(0, vendido / meta)),
    falta = round(max(0, meta - vendido), 2)
  ))
}
