# Informe del mes (Más → Informe del mes), contra la API falsa.

salta_sin_navegador <- function() {
  testthat::skip_if_not_installed("shinytest2")
  testthat::skip_if(is.null(chromote::find_chrome()), "No hay Chrome/Edge disponible")
}

test_that("porcentaje redondea y deja vacío lo que no se puede calcular", {
  expect_equal(porcentaje(0.4), "40 %")
  expect_equal(porcentaje(NA_real_), "")
})

test_that("el informe muestra lo vendido, quién compró y cómo pagaron", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "informes")
  entrar_como_mari(app)

  vender <- function(medio) {
    app$click(selector = ".nav-inferior__boton[data-destino='vender']")
    esperar_visible(app, ".vender [data-elige-valor='i-1']")
    app$click(selector = ".vender [data-elige-valor='i-1']")
    esperar_texto(app, ".vender", "×1")
    app$click(selector = "#vender-ir_cobrar")
    esperar_visible(app, "#vender-confirmar")
    app$click(selector = sprintf(".vender [data-elige-valor='%s']", medio))
    app$click(selector = "#vender-confirmar")
    esperar_visible(app, "#vender-otra")
    app$click(selector = "#vender-otra")
  }

  # Sin ventas todavía.
  app$click(selector = ".nav-inferior__boton[data-destino='mas']")
  esperar_visible(app, "#mas-informes")
  app$click(selector = "#mas-informes")
  expect_true(esperar_texto(app, ".informes", "Sin ventas en"))

  vender("efectivo")
  vender("tarjeta")

  # Al volver, el informe ya las cuenta (sin salir de la cuenta).
  app$click(selector = ".nav-inferior__boton[data-destino='mas']")
  esperar_visible(app, "#mas-informes")
  app$click(selector = "#mas-informes")
  expect_true(esperar_texto(app, ".informes", "2 ventas"))
  texto <- app$get_text(".informes")
  expect_match(texto, "Lo que más vendiste")
  expect_match(texto, "Pepián ×2")
  expect_match(texto, "Consumidor final")
  expect_match(texto, "Efectivo")
  expect_match(texto, "50 %")

  # El mes anterior, sin ventas; el botón de mes siguiente está apagado en el mes actual.
  app$click(selector = "#informes-mes_anterior")
  expect_true(esperar_texto(app, ".informes", "Sin ventas en"))
  app$click(selector = "#informes-mes_siguiente")
  expect_true(esperar_texto(app, ".informes", "2 ventas"))
  expect_true(app$get_js("document.querySelector('#informes-mes_siguiente').disabled"))
})
