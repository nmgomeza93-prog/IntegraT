# Flujo completo en un navegador real con tamaño de celular (390×844), contra la API falsa.

salta_sin_navegador <- function() {
  testthat::skip_if_not_installed("shinytest2")
  testthat::skip_if(is.null(chromote::find_chrome()), "No hay Chrome/Edge disponible")
}

test_that("crear cuenta y onboarding de un restaurante termina en su Inicio", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "onboarding-restaurante")

  expect_true(visible(app, "#bienvenida-crear"))
  app$click(selector = "#bienvenida-crear")

  # Registro con un dato inválido: error amable y se queda en la pantalla
  app$set_inputs("registro-nombre" = "Mari", "registro-correo" = "mari@prueba.com",
                 "registro-clave" = "corta")
  app$click(selector = "#registro-crear")
  expect_true(esperar_visible(app, ".mensaje-error"))
  expect_match(app$get_text("#registro-error"), "al menos 8 caracteres")

  # Correo repetido: mensaje de la API
  app$set_inputs("registro-correo" = "repetido@prueba.com",
                 "registro-clave" = "una-clave-larga-1")
  app$click(selector = "#registro-crear")
  Sys.sleep(1)
  expect_match(app$get_text("#registro-error"), "ya tiene una cuenta")

  # Registro bueno -> paso 1: tipo de negocio
  app$set_inputs("registro-correo" = "nuevo@prueba.com")
  app$click(selector = "#registro-crear")
  expect_true(esperar_visible(app, "[data-elige-valor='restaurante']"))
  expect_match(app$get_text("#onboarding-contenido"), "Paso 1 de 3")
  expect_match(app$get_text("#onboarding-contenido"), "Vendo en línea")

  # Un toque en el tipo avanza al paso 2
  app$click(selector = "[data-elige-valor='restaurante']")
  expect_true(esperar_visible(app, "#onboarding-seguir_nombre"))
  expect_match(app$get_text("#onboarding-contenido"), "Paso 2 de 3")

  # Nombre vacío no avanza
  app$click(selector = "#onboarding-seguir_nombre")
  expect_true(esperar_visible(app, ".mensaje-error"))

  # Atrás y adelante conserva la elección
  app$set_inputs("onboarding-nombre" = "Comedor Doña Mari")
  app$click(selector = "#onboarding-seguir_nombre")
  expect_true(esperar_visible(app, "[data-elige-valor='no_se']"))
  expect_match(app$get_text("#onboarding-contenido"), "¿Das factura")
  app$click(selector = "#onboarding-atras")
  expect_true(esperar_visible(app, "#onboarding-seguir_nombre"))
  expect_equal(app$get_value(input = "onboarding-nombre"), "Comedor Doña Mari")
  app$click(selector = "#onboarding-seguir_nombre")
  expect_true(esperar_visible(app, "[data-elige-valor='no_se']"))

  # Un toque en "¿Das factura?" crea el negocio y muestra el checklist del restaurante
  app$click(selector = "[data-elige-valor='no_se']")
  expect_true(esperar_visible(app, "#onboarding-ir_app"))
  expect_match(app$get_text("#onboarding-contenido"), "¡Listo, Comedor Doña Mari!")
  expect_match(app$get_text("#onboarding-contenido"), "Agrega tus 5 platillos más vendidos")
  expect_equal(negocios_creados(url), 1L)

  # Ir a mi negocio: nombre en el encabezado y vocabulario de restaurante en la navegación
  app$click(selector = "#onboarding-ir_app")
  expect_true(esperar_visible(app, ".nav-inferior"))
  expect_equal(app$get_text(".app-encabezado__negocio"), "Comedor Doña Mari")
  expect_match(app$get_text(".nav-inferior__boton[data-destino='productos']"), "Menú")
  expect_match(app$get_text("#inicio-ir_productos"), "platillo")
  expect_match(app$get_text(".app-contenido"), "Agrega tus 5 platillos más vendidos")
})

test_that("un doble toque en '¿Das factura?' crea un solo negocio", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "onboarding-doble-toque")

  app$click(selector = "#bienvenida-crear")
  app$set_inputs("registro-nombre" = "Ana", "registro-correo" = "ana@prueba.com",
                 "registro-clave" = "una-clave-larga-1")
  app$click(selector = "#registro-crear")
  expect_true(esperar_visible(app, "[data-elige-valor='ventas_en_linea']"))
  app$click(selector = "[data-elige-valor='ventas_en_linea']")
  expect_true(esperar_visible(app, "#onboarding-seguir_nombre"))
  app$set_inputs("onboarding-nombre" = "Tienda de Ana")
  app$click(selector = "#onboarding-seguir_nombre")
  expect_true(esperar_visible(app, "[data-elige-valor='si']"))

  app$run_js("var b = document.querySelector(\"[data-elige-valor='si']\"); b.click(); b.click();")
  expect_true(esperar_visible(app, "#onboarding-ir_app"))
  Sys.sleep(1)
  expect_equal(negocios_creados(url), 1L)

  app$click(selector = "#onboarding-ir_app")
  expect_true(esperar_visible(app, ".nav-inferior"))
  expect_match(app$get_text(".nav-inferior__boton[data-destino='productos']"), "Productos")
})

test_that("si la respuesta se pierde, reintentar no crea un segundo negocio", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "onboarding-reintento")

  app$click(selector = "#bienvenida-crear")
  app$set_inputs("registro-nombre" = "Mari", "registro-correo" = "reintento@prueba.com",
                 "registro-clave" = "una-clave-larga-1")
  app$click(selector = "#registro-crear")
  expect_true(esperar_visible(app, "[data-elige-valor='restaurante']"))
  app$click(selector = "[data-elige-valor='restaurante']")
  expect_true(esperar_visible(app, "#onboarding-seguir_nombre"))
  app$set_inputs("onboarding-nombre" = "Falla una vez")
  app$click(selector = "#onboarding-seguir_nombre")
  expect_true(esperar_visible(app, "[data-elige-valor='no_se']"))

  # Primer toque: el negocio se crea en el servidor pero la respuesta es un error
  app$click(selector = "[data-elige-valor='no_se']")
  expect_true(esperar_visible(app, ".mensaje-error"))
  expect_false(visible(app, "#onboarding-ir_app"))
  expect_equal(negocios_creados(url), 1L)

  # Segundo toque (mismos datos, misma clave): devuelve el mismo negocio, no crea otro
  app$click(selector = "[data-elige-valor='no_se']")
  expect_true(esperar_visible(app, "#onboarding-ir_app"))
  expect_match(app$get_text("#onboarding-contenido"), "¡Listo, Falla una vez!")
  expect_equal(negocios_creados(url), 1L)
})

test_that("iniciar sesión con un negocio existente entra directo a la app", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "login")

  app$click(selector = "#bienvenida-entrar")
  app$set_inputs("login-correo" = "mari@prueba.com", "login-clave" = "clave-incorrecta")
  app$click(selector = "#login-entrar")
  expect_true(esperar_visible(app, ".mensaje-error"))
  expect_match(app$get_text("#login-error"), "Correo o contraseña incorrectos")

  app$set_inputs("login-clave" = "clave-correcta-1")
  app$click(selector = "#login-entrar")
  expect_true(esperar_visible(app, ".nav-inferior"))
  expect_equal(app$get_text(".app-encabezado__negocio"), "Comedor Doña Mari")
  expect_equal(negocios_creados(url), 0L)

  # Salir de la cuenta vuelve a la bienvenida y no deja nada de la sesión anterior
  app$click(selector = ".nav-inferior__boton[data-destino='mas']")
  expect_true(esperar_visible(app, "#mas-salir"))
  app$click(selector = "#mas-salir")
  expect_true(esperar_visible(app, "#bienvenida-crear"))
  expect_false(visible(app, ".nav-inferior"))
  expect_equal(sesiones_cerradas(url), 1L)  # se revocó el token de refresco en el servidor
  expect_equal(app$get_value(input = "login-clave"), "")
})

test_that("sin conexión con la API la app muestra un mensaje amable", {
  salta_sin_navegador()
  app <- abrir_app("http://127.0.0.1:9", "sin-api")

  app$click(selector = "#bienvenida-entrar")
  app$set_inputs("login-correo" = "mari@prueba.com", "login-clave" = "clave-correcta-1")
  app$click(selector = "#login-entrar")
  expect_true(esperar_visible(app, ".mensaje-error"))
  expect_match(app$get_text("#login-error"), "No pudimos conectar")
  expect_true(app$get_js("document.documentElement.scrollWidth <= window.innerWidth"))
})
