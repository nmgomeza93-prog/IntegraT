# Utilidades generales de la interfaz.

ZONA_HORARIA_DEFECTO <- "America/Guatemala"

DIAS_ES <- c("domingo", "lunes", "martes", "miércoles", "jueves", "viernes", "sábado")
MESES_ES <- c("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
              "agosto", "septiembre", "octubre", "noviembre", "diciembre")

# "Martes 24 de noviembre" (sin depender del idioma del servidor).
fecha_larga_es <- function(fecha = Sys.time(), zona = ZONA_HORARIA_DEFECTO) {
  lt <- as.POSIXlt(fecha, tz = zona)
  dia <- DIAS_ES[lt$wday + 1]
  paste0(toupper(substr(dia, 1, 1)), substring(dia, 2), " ", lt$mday, " de ", MESES_ES[lt$mon + 1])
}

# Operador "o si es nulo" (viene en R base solo desde 4.4).
`%||%` <- function(x, y) if (is.null(x)) y else x

correo_valido <- function(texto) {
  grepl("^[^@[:space:]]+@[^@[:space:]]+[.][^@[:space:]]+$", texto)
}

aviso_pronto <- function(session = shiny::getDefaultReactiveDomain()) {
  shiny::showNotification(
    "Esta opción llega pronto. Estamos construyéndola paso a paso.",
    duration = 4, closeButton = FALSE, session = session
  )
}
