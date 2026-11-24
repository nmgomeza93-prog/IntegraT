# API falsa para probar la app sin base de datos: imita las respuestas de /v1 (mismas formas
# que la API real; el contrato real lo cubren las pruebas de api/tests). Corre en un proceso
# aparte con httpuv y se apaga sola al terminar la prueba.
#
# Cuentas de prueba:
#   mari@prueba.com / clave-correcta-1  -> ya tiene un restaurante
#   repetido@prueba.com                 -> el registro responde 409 (correo repetido)
# Atajos para probar la renovación de sesión:
#   token de acceso "token-vencido" -> toda llamada responde 401
#   refresh_token  "refresco-valido" -> /auth/refrescar entrega una sesión nueva
# GET /_creados devuelve cuántos negocios se crearon (para probar el doble toque) y
# cuántas veces se llamó a /v1/auth/salir.

iniciar_api_falsa <- function(env = parent.frame()) {
  puerto <- httpuv::randomPort()
  proceso <- callr::r_bg(function(puerto) {
    `%||%` <- function(x, y) if (is.null(x)) y else x
    json <- function(estado, datos) {
      list(status = estado, headers = list("Content-Type" = "application/json"),
           body = jsonlite::toJSON(datos, auto_unbox = TRUE, null = "null"))
    }
    leer <- function(req) {
      crudo <- rawToChar(req$rook.input$read())
      if (nzchar(crudo)) jsonlite::fromJSON(crudo, simplifyVector = FALSE) else list()
    }
    usuario <- function(nombre, correo) list(id = "u-1", nombre = nombre, correo = correo)
    sesion <- function(nombre, correo, negocio_id = NULL) {
      list(token_type = "bearer", access_token = "token-valido", expira_en = 900,
           refresh_token = "refresco-valido-0123456789", negocio_id = negocio_id,
           usuario = usuario(nombre, correo))
    }
    vocab <- list(
      restaurante = list(item_singular = "platillo", item_plural = "platillos",
                         catalogo = "Menú", catalogo_icono = "journal-text"),
      ventas_en_linea = list(item_singular = "producto", item_plural = "productos",
                             catalogo = "Productos", catalogo_icono = "box-seam")
    )
    pasos <- list(
      restaurante = list(
        list(clave = "cinco_platillos", texto = "Agrega tus 5 platillos más vendidos",
             icono = "journal-text", hecho = FALSE),
        list(clave = "primera_venta", texto = "Haz tu primera venta", icono = "cart",
             hecho = FALSE)),
      ventas_en_linea = list(
        list(clave = "primer_producto", texto = "Agrega tu primer producto con una foto",
             icono = "camera", hecho = FALSE))
    )
    negocio <- function(id, nombre, tipo, factura) {
      list(id = id, nombre = nombre, tipo_negocio_codigo = tipo, pais_codigo = "GT",
           moneda_codigo = "GTQ", zona_horaria = "America/Guatemala", da_factura = factura,
           capacidades = list("recetas", "mesas"), vocabulario = vocab[[tipo]],
           primeros_pasos = pasos[[tipo]])
    }
    estado <- new.env()
    estado$creados <- 0L
    estado$salidas <- 0L
    estado$claves <- list()

    app <- list(call = function(req) {
      ruta <- req$PATH_INFO
      metodo <- req$REQUEST_METHOD
      auth <- req$HTTP_AUTHORIZATION %||% ""

      if (ruta == "/_creados") {
        return(json(200, list(creados = estado$creados, salidas = estado$salidas)))
      }
      if (ruta == "/v1/auth/salir" && metodo == "POST") {
        estado$salidas <- estado$salidas + 1L
        # La API real responde 204; httpuv + curl se confunden con un 204 sin cuerpo en una
        # conexión reutilizada, y a la app solo le importa que la llamada no falle.
        return(json(200, list()))
      }
      if (ruta == "/v1/salud") {
        return(json(200, list(estado = "ok", version = "0", entorno = "dev",
                              bd = list(conectada = TRUE))))
      }
      if (ruta == "/v1/tipos-negocio") {
        return(json(200, list(
          list(codigo = "ventas_en_linea", nombre = "Vendo en línea",
               descripcion = "Vendes por WhatsApp, Instagram o tienda web.", icono = "bag"),
          list(codigo = "restaurante", nombre = "Tengo un restaurante o comedor",
               descripcion = "Vendes comida y bebida.", icono = "cup-hot"))))
      }
      if (ruta == "/v1/auth/registro" && metodo == "POST") {
        d <- leer(req)
        if (identical(d$correo, "repetido@prueba.com")) {
          return(json(409, list(detail = "Ese correo ya tiene una cuenta. Prueba iniciar sesión.")))
        }
        return(json(201, sesion(d$nombre, d$correo)))
      }
      if (ruta == "/v1/auth/login" && metodo == "POST") {
        d <- leer(req)
        if (identical(d$correo, "mari@prueba.com") && identical(d$clave, "clave-correcta-1")) {
          return(json(200, sesion("Mari", d$correo, negocio_id = "n-mari")))
        }
        return(json(401, list(detail = "Correo o contraseña incorrectos.")))
      }
      if (ruta == "/v1/auth/refrescar" && metodo == "POST") {
        d <- leer(req)
        if (identical(d$refresh_token, "refresco-valido")) {
          return(json(200, sesion("Mari", "mari@prueba.com", negocio_id = "n-mari")))
        }
        return(json(401, list(detail = "Tu sesión venció. Inicia sesión otra vez.")))
      }

      # Desde aquí todo exige token
      if (!startsWith(auth, "Bearer ") || grepl("token-vencido", auth)) {
        return(json(401, list(detail = "Tu sesión venció. Inicia sesión otra vez.")))
      }
      if (ruta == "/v1/negocios" && metodo == "POST") {
        d <- leer(req)
        if (!d$tipo_negocio_codigo %in% names(vocab)) {
          return(json(422, list(detail = "Ese tipo de negocio no existe.")))
        }
        Sys.sleep(0.4)  # para que un doble toque llegue antes de terminar
        clave <- req$HTTP_IDEMPOTENCY_KEY %||% NULL
        if (!is.null(clave) && !is.null(estado$claves[[clave]])) {
          return(json(201, estado$claves[[clave]]))  # misma clave: mismo negocio, no se crea otro
        }
        estado$creados <- estado$creados + 1L
        n <- negocio("n-nuevo", d$nombre, d$tipo_negocio_codigo, d$da_factura)
        n$acceso <- list(token_type = "bearer", access_token = "token-con-negocio",
                         expira_en = 900, negocio_id = "n-nuevo")
        if (!is.null(clave)) estado$claves[[clave]] <- n
        # "Falla una vez": se crea, pero la respuesta se pierde (la primera vez responde 503).
        if (identical(d$nombre, "Falla una vez") && estado$creados == 1L) {
          return(json(503, list(detail = "El servicio no está listo. Intenta más tarde.")))
        }
        return(json(201, n))
      }
      if (ruta == "/v1/negocios/n-mari") {
        return(json(200, negocio("n-mari", "Comedor Doña Mari", "restaurante", "no")))
      }
      json(404, list(detail = "No encontramos eso."))
    })
    httpuv::runServer("127.0.0.1", puerto, app)
  }, args = list(puerto = puerto), supervise = TRUE)

  url <- sprintf("http://127.0.0.1:%d", puerto)
  withr::defer(proceso$kill(), envir = env)

  # Esperar a que responda (máx. 10 s)
  for (i in 1:100) {
    listo <- tryCatch({
      httr2::req_perform(httr2::request(paste0(url, "/v1/salud")))
      TRUE
    }, error = function(e) FALSE)
    if (listo) break
    Sys.sleep(0.1)
  }
  if (!listo) stop("La API falsa no arrancó: ", paste(proceso$read_all_error(), collapse = " "))
  url
}

negocios_creados <- function(url) {
  httr2::request(paste0(url, "/_creados")) |> httr2::req_perform() |>
    httr2::resp_body_json() |> (\(x) x$creados)()
}

sesiones_cerradas <- function(url) {
  httr2::request(paste0(url, "/_creados")) |> httr2::req_perform() |>
    httr2::resp_body_json() |> (\(x) x$salidas)()
}

abrir_app <- function(url, nombre, env = parent.frame()) {
  withr::local_envvar(API_BASE_URL = url, NOT_CRAN = "true", .local_envir = env)
  app <- shinytest2::AppDriver$new(
    testthat::test_path("..", ".."),
    name = nombre, width = 390, height = 844, load_timeout = 30000
  )
  withr::defer(app$stop(), envir = env)
  app
}

visible <- function(app, selector) {
  app$get_js(sprintf(
    "(function(){var e=document.querySelector(\"%s\"); return !!e && e.getClientRects().length > 0 && getComputedStyle(e).visibility !== 'hidden';})()",
    selector
  ))
}

# Repite una comprobación hasta que se cumpla (los pasos del asistente tardan un instante).
esperar_visible <- function(app, selector, intentos = 50) {
  for (i in seq_len(intentos)) {
    if (isTRUE(visible(app, selector))) return(invisible(TRUE))
    Sys.sleep(0.2)
  }
  FALSE
}

# Recorre registro + onboarding de un restaurante hasta llegar a la app.
crear_cuenta_y_negocio <- function(app, tipo = "restaurante", nombre_negocio = "Comedor Doña Mari",
                                   correo = "nuevo@prueba.com") {
  app$click(selector = "#bienvenida-crear")
  app$set_inputs("registro-nombre" = "Mari", "registro-correo" = correo,
                 "registro-clave" = "una-clave-larga-1")
  app$click(selector = "#registro-crear")
  esperar_visible(app, sprintf("[data-elige-valor='%s']", tipo))
  app$click(selector = sprintf("[data-elige-valor='%s']", tipo))
  esperar_visible(app, "#onboarding-seguir_nombre")
  app$set_inputs("onboarding-nombre" = nombre_negocio)
  app$click(selector = "#onboarding-seguir_nombre")
  esperar_visible(app, "[data-elige-valor='no_se']")
  app$click(selector = "[data-elige-valor='no_se']")
  esperar_visible(app, "#onboarding-ir_app")
  app$click(selector = "#onboarding-ir_app")
  esperar_visible(app, ".nav-inferior")
  invisible(app)
}
