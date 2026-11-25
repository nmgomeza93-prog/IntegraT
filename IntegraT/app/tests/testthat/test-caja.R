# Caja del día y Tu dinero y el negocio (docs/PLAN_CAJA.md), contra la API falsa a 390×844.
# El efectivo esperado y la diferencia los calcula la API; la app solo los muestra.

salta_sin_navegador <- function() {
  testthat::skip_if_not_installed("shinytest2")
  testthat::skip_if(is.null(chromote::find_chrome()), "No hay Chrome/Edge disponible")
}

ir_a_mas_opcion <- function(app, opcion, espera) {
  app$click(selector = ".nav-inferior__boton[data-destino='mas']")
  esperar_visible(app, paste0("#mas-", opcion))
  app$click(selector = paste0("#mas-", opcion))
  esperar_visible(app, espera)
}

# --- Funciones puras -------------------------------------------------------------------

test_that("la diferencia de caja se dice en palabras", {
  expect_equal(texto_diferencia("0.00"), "Cuadra")
  expect_equal(texto_diferencia("-20.00"), "Faltaron Q 20.00")
  expect_equal(texto_diferencia("5.5"), "Sobraron Q 5.50")
  expect_equal(texto_diferencia(NULL), "Cuadra")
})

test_that("hora_local pasa de UTC a la hora de Guatemala", {
  expect_equal(hora_local("2026-11-25T20:05:00Z"), "14:05")
  expect_equal(hora_local("2026-11-25T20:05:00.123456+00:00"), "14:05")
  expect_equal(hora_local(NULL), "")
})

test_that("el resumen de la caja muestra solo lo que se movió", {
  sesion <- list(monto_apertura = "200.00", resumen = list(
    ventas = "90.00", gastos = "-25.00", compras = "0.00", inventario = "0.00", dueno = "0.00",
    otros = "0.00", cantidad_ventas = 2L, ventas_tarjeta = "30.00", ventas_transferencia = "0.00"))
  texto <- paste(as.character(lista_resumen_caja(sesion)), collapse = "")
  expect_match(texto, "Abriste con")
  expect_match(texto, "Ventas en efectivo")
  expect_match(texto, "−Q 25.00")
  expect_no_match(texto, "Compras en efectivo")
  expect_match(texto, "con tarjeta")
})

# --- Flujos en el navegador ------------------------------------------------------------

test_that("abrir la caja, vender y cerrar el día con un faltante", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "caja-dia")
  entrar_como_mari(app)

  expect_true(ir_a_mas_opcion(app, "caja", "#caja-abrir"))
  expect_match(app$get_text(".caja"), "La caja está cerrada")
  app$set_inputs("caja-apertura" = "abc")
  app$click(selector = "#caja-abrir")
  expect_true(esperar_texto(app, ".caja", "Escribe con cuánto efectivo abres"))
  app$set_inputs("caja-apertura" = "200")
  app$click(selector = "#caja-abrir")
  expect_true(esperar_texto(app, ".caja", "Debería haber en la caja"))
  expect_match(app$get_text(".caja"), "Q 200.00")
  expect_true(contadores_api(url)$caja_abierta)

  # Cerrar: contar, revisar la diferencia y confirmar.
  app$click(selector = "#caja-ir_contar")
  esperar_visible(app, "#caja-revisar")
  app$set_inputs("caja-contado" = "180")
  app$click(selector = "#caja-revisar")
  expect_true(esperar_texto(app, ".caja", "Faltaron Q 20.00"))
  app$click(selector = "#caja-confirmar")
  expect_true(esperar_texto(app, ".caja", "Día cerrado"))
  expect_match(app$get_text(".caja"), "Faltaron Q 20.00")
  expect_equal(contadores_api(url)$cierres, 1L)
  expect_false(contadores_api(url)$caja_abierta)

  app$click(selector = "#caja-listo")
  expect_true(esperar_texto(app, ".caja", "Último cierre"))
  app$click(selector = "#caja-ver_historial")
  expect_true(esperar_texto(app, ".caja", "Cierres del mes"))
  expect_match(app$get_text(".caja"), "Faltaron Q 20.00")
})

test_that("Cerrar el día del botón + va directo a contar si la caja está abierta", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "caja-accion-rapida")
  entrar_como_mari(app)

  # Con la caja cerrada, lleva a abrirla.
  app$click(selector = ".nav-inferior__boton--accion")
  esperar_visible(app, "[data-accion='cerrar_dia']")
  app$click(selector = "[data-accion='cerrar_dia']")
  expect_true(esperar_visible(app, "#caja-abrir"))
  app$set_inputs("caja-apertura" = "50")
  app$click(selector = "#caja-abrir")
  expect_true(esperar_texto(app, ".caja", "Debería haber"))

  app$click(selector = ".nav-inferior__boton[data-destino='inicio']")
  app$click(selector = ".nav-inferior__boton--accion")
  esperar_visible(app, "[data-accion='cerrar_dia']")
  app$click(selector = "[data-accion='cerrar_dia']")
  expect_true(esperar_visible(app, "#caja-revisar"))
  expect_match(app$get_text(".caja"), "Cuenta tu efectivo")
})

test_that("Tu dinero y el negocio anota lo que pones y lo que sacas, y lo borra", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "dueno")
  entrar_como_mari(app)

  expect_true(ir_a_mas_opcion(app, "dueno", "#dueno-nuevo_aporte"))
  expect_match(app$get_text(".dueno"), "Sacar no es un gasto")

  app$click(selector = "#dueno-nuevo_aporte")
  esperar_visible(app, "#dueno-guardar")
  expect_match(app$get_text(".dueno"), "Pusiste dinero en el negocio")
  app$set_inputs("dueno-monto" = "1000")
  app$click(selector = ".dueno [data-elige-valor='banco']")
  app$click(selector = "#dueno-guardar")
  expect_true(esperar_visible(app, "#dueno-nuevo_retiro"))

  app$click(selector = "#dueno-nuevo_retiro")
  esperar_visible(app, "#dueno-guardar")
  app$set_inputs("dueno-monto" = "300", "dueno-nota" = "Para la casa")
  app$click(selector = "#dueno-guardar")
  expect_true(esperar_texto(app, ".dueno", "Para la casa"))
  expect_match(app$get_text(".dueno"), "Q 1,000.00")
  expect_match(app$get_text(".dueno"), "−Q 300.00")
  expect_equal(contadores_api(url)$dueno, 2L)

  # Tocar un movimiento pregunta si se borra.
  app$click(selector = ".dueno [data-elige-valor='d-2']")
  expect_true(esperar_visible(app, "#dueno-confirmar_borrar"))
  app$click(selector = "#dueno-confirmar_borrar")
  for (i in 1:25) {
    if (contadores_api(url)$dueno == 1L) break
    Sys.sleep(0.2)
  }
  expect_equal(contadores_api(url)$dueno, 1L)
  expect_true(esperar_js(app, "!document.querySelector('.dueno').textContent.includes('Para la casa')"))
})
