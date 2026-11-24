# Cliente de la API y sesión (sin navegador): contra la API falsa.

test_that("api_llamar devuelve ok y el cuerpo cuando la API responde bien", {
  withr::local_envvar(API_BASE_URL = iniciar_api_falsa())
  r <- api_llamar("GET", "v1/tipos-negocio")
  expect_true(r$ok)
  expect_equal(r$estado, 200L)
  expect_equal(vapply(r$cuerpo, function(t) t$codigo, ""), c("ventas_en_linea", "restaurante"))
})

test_that("api_llamar traduce los errores a mensajes amables", {
  withr::local_envvar(API_BASE_URL = iniciar_api_falsa())
  r <- api_llamar("POST", "v1/auth/login", list(correo = "x@y.com", clave = "mala"))
  expect_false(r$ok)
  expect_equal(r$estado, 401L)
  expect_equal(r$mensaje, "Correo o contraseña incorrectos.")
})

test_that("api_llamar no lanza error si la API no está", {
  withr::local_envvar(API_BASE_URL = "http://127.0.0.1:9")
  r <- api_llamar("GET", "v1/tipos-negocio", tiempo_max = 2)
  expect_false(r$ok)
  expect_equal(r$estado, 0L)
  expect_equal(r$mensaje, MENSAJE_SIN_CONEXION)
})

test_that("mensaje_error_api nunca muestra detalles técnicos", {
  expect_equal(mensaje_error_api(409, list(detail = "Ese correo ya existe.")), "Ese correo ya existe.")
  expect_match(mensaje_error_api(422, list(detail = list(list(loc = "body")))), "Revisa los datos")
  expect_match(mensaje_error_api(500, NULL), "problema de nuestro lado")
  expect_match(mensaje_error_api(404, NULL), "No pudimos completar")
})

test_that("sesion_llamar renueva el token vencido y repite la llamada", {
  withr::local_envvar(API_BASE_URL = iniciar_api_falsa())
  s <- sesion_nueva()
  s$acceso <- "token-vencido"
  s$refresco <- "refresco-valido"
  r <- sesion_llamar(s, "GET", "v1/negocios/n-mari")
  expect_true(r$ok)
  expect_equal(r$cuerpo$nombre, "Comedor Doña Mari")
  expect_equal(shiny::isolate(s$acceso), "token-valido")
})

test_that("sesion_llamar cierra la sesión si el refresco ya no sirve", {
  withr::local_envvar(API_BASE_URL = iniciar_api_falsa())
  s <- sesion_nueva()
  s$acceso <- "token-vencido"
  s$refresco <- "refresco-robado"
  r <- sesion_llamar(s, "GET", "v1/negocios/n-mari")
  expect_false(r$ok)
  expect_null(shiny::isolate(s$acceso))
  expect_null(shiny::isolate(s$refresco))
})

test_that("sesion_salir revoca el token en la API y borra la sesión; sin API igual sale", {
  url <- iniciar_api_falsa()
  withr::local_envvar(API_BASE_URL = url)
  s <- sesion_nueva()
  s$acceso <- "token-valido"
  s$refresco <- "refresco-valido"
  sesion_salir(s)
  expect_equal(sesiones_cerradas(url), 1L)
  expect_null(shiny::isolate(s$acceso))
  expect_null(shiny::isolate(s$refresco))

  withr::local_envvar(API_BASE_URL = "http://127.0.0.1:9")
  s$acceso <- "token-valido"
  s$refresco <- "refresco-valido"
  sesion_salir(s)  # la API no responde: no debe fallar
  expect_null(shiny::isolate(s$acceso))
})

test_that("sesion_continuar lleva al onboarding si no hay negocio y a la app si lo hay", {
  withr::local_envvar(API_BASE_URL = iniciar_api_falsa())
  destinos <- character()
  ir <- function(d) destinos <<- c(destinos, d)

  nueva <- sesion_nueva()
  nueva$acceso <- "token-valido"
  expect_true(sesion_continuar(nueva, ir)$ok)

  con_negocio <- sesion_nueva()
  con_negocio$acceso <- "token-valido"
  con_negocio$negocio_id <- "n-mari"
  expect_true(sesion_continuar(con_negocio, ir)$ok)
  expect_equal(shiny::isolate(con_negocio$negocio$nombre), "Comedor Doña Mari")
  expect_equal(destinos, c("onboarding", "app"))
})

test_that("vocab_negocio usa el vocabulario del tipo y rellena lo que falte", {
  v <- vocab_negocio(list(vocabulario = list(catalogo = "Menú", item_singular = "platillo")))
  expect_equal(v$catalogo, "Menú")
  expect_equal(v$item_singular, "platillo")
  expect_equal(v$catalogo_icono, vocabulario_defecto()$catalogo_icono)  # relleno
  expect_equal(vocab_negocio(list()), vocabulario_defecto())
})

test_that("correo_valido acepta correos normales y rechaza el resto", {
  expect_true(all(correo_valido(c("a@b.com", "mari.gomez@correo.com.gt"))))
  expect_false(any(correo_valido(c("", "sin-arroba", "a@b", "a b@c.com", "@c.com"))))
})
