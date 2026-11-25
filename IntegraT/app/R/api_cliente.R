# Cliente de la API de IntegraT (httr2). La app Shiny NO se conecta a la base de datos:
# todo pasa por la API (docs/PROPUESTA_ARQUITECTURA.md §3). Única configuración: API_BASE_URL.

# Dirección de la API, en este orden: variable API_BASE_URL -> app/config.yml (sección activa
# según R_CONFIG_ACTIVE; shinyapps.io usa "shinyapps") -> http://127.0.0.1:8000.
api_base_url <- function() {
  url <- Sys.getenv("API_BASE_URL", unset = "")
  if (!nzchar(url)) url <- url_desde_config()
  if (!nzchar(url)) url <- "http://127.0.0.1:8000"
  sub("/+$", "", url)
}

# Lee api_base_url de config.yml: valores de "default" y, encima, los de la sección activa.
# Devuelve "" si no hay archivo o no tiene el valor (nunca lanza error).
url_desde_config <- function(archivo = "config.yml",
                             activo = Sys.getenv("R_CONFIG_ACTIVE", unset = "default")) {
  if (!file.exists(archivo)) return("")
  cfg <- tryCatch(yaml::read_yaml(archivo), error = function(e) NULL)
  url <- cfg[[activo]]$api_base_url %||% cfg$default$api_base_url
  if (is.character(url) && length(url) == 1L && !is.na(url)) url else ""
}

api_peticion <- function(ruta, tiempo_max = 5) {
  httr2::request(api_base_url()) |>
    httr2::req_url_path_append(ruta) |>
    httr2::req_timeout(tiempo_max) |>
    httr2::req_user_agent("integrat-app") |>
    httr2::req_error(is_error = function(resp) FALSE)
}

MENSAJE_SIN_CONEXION <- "No pudimos conectar con IntegraT. Revisa tu internet e intenta de nuevo."

# Texto amable para mostrar cuando la API responde con error (nunca detalles técnicos).
mensaje_error_api <- function(estado, cuerpo) {
  detalle <- cuerpo$detail
  if (is.character(detalle) && length(detalle) == 1 && nzchar(detalle)) return(detalle)
  if (estado == 422) return("Revisa los datos e intenta de nuevo.")
  if (estado >= 500) return("Tuvimos un problema de nuestro lado. Intenta de nuevo en un momento.")
  "No pudimos completar eso. Intenta de nuevo."
}

# Llamada genérica a la API. Nunca lanza error: devuelve
# list(ok, estado, cuerpo, mensaje). `estado` = 0 si no hubo conexión.
# El token (si lo hay) viaja solo en el encabezado Authorization.
api_llamar <- function(metodo, ruta, cuerpo = NULL, token = NULL, tiempo_max = 10,
                       cabeceras = NULL, consulta = NULL) {
  peticion <- httr2::req_method(api_peticion(ruta, tiempo_max), metodo)
  if (length(consulta) > 0) {
    peticion <- do.call(httr2::req_url_query, c(list(peticion), as.list(consulta)))
  }
  if (!is.null(token)) peticion <- httr2::req_auth_bearer_token(peticion, token)
  if (length(cabeceras) > 0) {
    peticion <- do.call(httr2::req_headers, c(list(peticion), as.list(cabeceras)))
  }
  if (!is.null(cuerpo)) peticion <- httr2::req_body_json(peticion, cuerpo)
  resp <- tryCatch(httr2::req_perform(peticion), error = function(e) NULL)
  if (is.null(resp)) {
    return(list(ok = FALSE, estado = 0L, cuerpo = NULL, mensaje = MENSAJE_SIN_CONEXION))
  }
  estado <- httr2::resp_status(resp)
  cuerpo_resp <- tryCatch(httr2::resp_body_json(resp), error = function(e) NULL)
  ok <- estado >= 200 && estado < 300
  list(ok = ok, estado = estado, cuerpo = cuerpo_resp,
       mensaje = if (ok) NULL else mensaje_error_api(estado, cuerpo_resp))
}

# Sube un archivo (multipart, campo `campo`) a la API. Mismo resultado que api_llamar().
api_subir <- function(ruta, archivo, nombre, token = NULL, campo = "archivo", tiempo_max = 30) {
  partes <- stats::setNames(list(curl::form_file(archivo, "application/octet-stream", nombre)), campo)
  peticion <- httr2::req_method(api_peticion(ruta, tiempo_max), "POST")
  if (!is.null(token)) peticion <- httr2::req_auth_bearer_token(peticion, token)
  peticion <- do.call(httr2::req_body_multipart, c(list(peticion), partes))
  resp <- tryCatch(httr2::req_perform(peticion), error = function(e) NULL)
  if (is.null(resp)) {
    return(list(ok = FALSE, estado = 0L, cuerpo = NULL, mensaje = MENSAJE_SIN_CONEXION))
  }
  estado <- httr2::resp_status(resp)
  cuerpo <- tryCatch(httr2::resp_body_json(resp), error = function(e) NULL)
  ok <- estado >= 200 && estado < 300
  list(ok = ok, estado = estado, cuerpo = cuerpo,
       mensaje = if (ok) NULL else mensaje_error_api(estado, cuerpo))
}

# Devuelve list(api = TRUE/FALSE, bd = TRUE/FALSE). Nunca lanza error.
api_salud <- function(tiempo_max = 3) {
  resp <- tryCatch(httr2::req_perform(api_peticion("v1/salud", tiempo_max)), error = function(e) NULL)
  if (is.null(resp)) return(list(api = FALSE, bd = FALSE))
  cuerpo <- tryCatch(httr2::resp_body_json(resp), error = function(e) NULL)
  list(api = TRUE, bd = isTRUE(cuerpo$bd$conectada))
}

# Etiqueta amable del estado de conexión (sin términos técnicos).
estado_conexion_ui <- function(salud) {
  if (isTRUE(salud$api) && isTRUE(salud$bd)) {
    etiqueta_estado("Conectado", "bien")
  } else if (isTRUE(salud$api)) {
    etiqueta_estado("Servidor con problemas", "atencion")
  } else {
    etiqueta_estado("Sin conexión", "alerta")
  }
}
