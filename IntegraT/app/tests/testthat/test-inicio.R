# Inicio con datos reales (docs/PLAN_INICIO.md): "Hoy" (ventas y caja) y "Tu meta del mes", cuya
# fórmula es de integrat.analitica (meta_del_mes). Mari entra sin ventas y con Renta Q 3,500.00 fija.

salta_sin_navegador <- function() {
  testthat::skip_if_not_installed("shinytest2")
  testthat::skip_if(is.null(chromote::find_chrome()), "No hay Chrome/Edge disponible")
}

texto_de <- function(etiqueta) paste(as.character(etiqueta), collapse = "")
ok <- function(cuerpo) list(ok = TRUE, estado = 200L, cuerpo = cuerpo, mensaje = NULL)

# --- Funciones puras -------------------------------------------------------------------

test_that("la app carga la fórmula de la meta desde integrat.analitica", {
  expect_true(is.function(meta_del_mes))
  expect_equal(meta_del_mes(3500, 0, 0, 0.35)$meta, 10000)
})

test_that("Hoy muestra lo vendido y la caja (o el botón para abrirla)", {
  ventas <- ok(list(resumen = list(cantidad = 3L, total = "135.00")))
  cerrada <- ok(list(abierta = NULL, ultimo_cierre = NULL))
  abierta <- ok(list(abierta = list(efectivo_esperado = "335.00")))

  con_caja <- texto_de(tarjeta_hoy(ventas, abierta, "abrir"))
  expect_match(con_caja, "Q 135.00")
  expect_match(con_caja, "3 ventas")
  expect_match(con_caja, "Q 335.00")
  expect_no_match(con_caja, "Abrir la caja")

  sin_caja <- texto_de(tarjeta_hoy(ok(list(resumen = list(cantidad = 0L, total = "0.00"))),
                                   cerrada, "abrir"))
  expect_match(sin_caja, "Aún no registras ventas hoy")
  expect_match(sin_caja, "Abrir la caja")
})

test_that("Tu meta del mes: estimada, lograda, sin fijos y sin margen", {
  base <- list(gastos_fijos = "3500.00", vendiste = "1000.00", costo_de_lo_vendido = "0.00",
               margen_objetivo = "0.3500")
  estimada <- texto_de(tarjeta_meta(base))
  expect_match(estimada, "Q 10,000.00")
  expect_match(estimada, "Estimada")
  expect_match(estimada, "Llevas 10 %")
  expect_match(estimada, "Te faltan Q 9,000.00")

  lograda <- texto_de(tarjeta_meta(modifyList(base, list(vendiste = "10000.00",
                                                         costo_de_lo_vendido = "4000.00"))))
  expect_match(lograda, "Lograda")
  expect_no_match(lograda, "Estimada")

  expect_match(texto_de(tarjeta_meta(modifyList(base, list(gastos_fijos = "0.00")))),
               "cuando anotes tus gastos fijos")
  expect_match(texto_de(tarjeta_meta(modifyList(base, list(costo_de_lo_vendido = "1200.00")))),
               "Revisa tus precios")
})

# --- Flujo en el navegador -------------------------------------------------------------

test_that("el Inicio muestra Hoy y la meta, y Abrir la caja lleva a la caja", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "inicio-real")
  entrar_como_mari(app)

  expect_true(esperar_texto(app, ".hoy", "Vendiste hoy"))
  expect_match(app$get_text(".hoy"), "Q 0.00")
  expect_true(esperar_texto(app, ".meta", "Q 10,000.00"))  # 3,500 de fijos al 35 % estimado
  expect_match(app$get_text(".meta"), "Estimada")

  app$click(selector = "#inicio-abrir_caja")
  expect_true(esperar_visible(app, "#caja-abrir"))
})
