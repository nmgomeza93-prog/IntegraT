# Sesión del usuario. El token vive SOLO en la memoria del servidor de Shiny (un objeto
# reactivo por sesión del navegador); nunca se envía al navegador ni se guarda en disco.

sesion_nueva <- function() {
  shiny::reactiveValues(
    acceso = NULL, refresco = NULL, usuario = NULL, negocio_id = NULL, negocio = NULL
  )
}

# `cuerpo` es la respuesta de /v1/auth/registro, /login o /refrescar.
sesion_abrir <- function(s, cuerpo) {
  s$acceso <- cuerpo$access_token
  s$refresco <- cuerpo$refresh_token
  s$negocio_id <- cuerpo$negocio_id
  if (!is.null(cuerpo$usuario)) s$usuario <- cuerpo$usuario
  invisible(s)
}

sesion_cerrar <- function(s) {
  s$acceso <- NULL
  s$refresco <- NULL
  s$usuario <- NULL
  s$negocio_id <- NULL
  s$negocio <- NULL
  invisible(s)
}

# Salir a propósito: primero se revoca el token de refresco en el servidor y luego se borra
# la sesión local. Si la API no responde, igual se sale (la sesión local siempre se cierra).
sesion_salir <- function(s) {
  refresco <- shiny::isolate(s$refresco)
  if (!is.null(refresco)) {
    api_llamar("POST", "v1/auth/salir", list(refresh_token = refresco), tiempo_max = 3)
  }
  sesion_cerrar(s)
}

# Llama a la API con el token de la sesión. Si el token venció, lo renueva una vez con el
# token de refresco y repite la llamada; si tampoco sirve, cierra la sesión.
sesion_llamar <- function(s, metodo, ruta, cuerpo = NULL, cabeceras = NULL) {
  resultado <- api_llamar(metodo, ruta, cuerpo, token = shiny::isolate(s$acceso),
                          cabeceras = cabeceras)
  refresco <- shiny::isolate(s$refresco)
  if (resultado$estado == 401L && !is.null(refresco)) {
    renovada <- api_llamar("POST", "v1/auth/refrescar", list(refresh_token = refresco))
    if (renovada$ok) {
      sesion_abrir(s, renovada$cuerpo)
      resultado <- api_llamar(metodo, ruta, cuerpo, token = renovada$cuerpo$access_token,
                              cabeceras = cabeceras)
    } else if (renovada$estado == 401L) {
      sesion_cerrar(s)
    }
  }
  resultado
}

# Tras entrar (registro o login): si ya tiene negocio lo carga y abre la app; si no, onboarding.
# Devuelve list(ok, mensaje) para que la pantalla muestre el error si lo hubo.
sesion_continuar <- function(s, ir_pantalla) {
  negocio_id <- shiny::isolate(s$negocio_id)
  if (is.null(negocio_id)) {
    ir_pantalla("onboarding")
    return(list(ok = TRUE, mensaje = NULL))
  }
  r <- sesion_llamar(s, "GET", paste0("v1/negocios/", negocio_id))
  if (!r$ok) return(list(ok = FALSE, mensaje = r$mensaje))
  s$negocio <- r$cuerpo
  ir_pantalla("app")
  list(ok = TRUE, mensaje = NULL)
}
