# Contabilidad en la app: "Tu mes" en el Inicio, "Tus impuestos" en Más y "Me dieron factura" en
# los gastos (docs/PLAN_CONTABILIDAD.md). Las cifras las calcula la API; la app solo las muestra.
# Mari (mari@prueba.com) entra sin ventas y con Q 3,545.00 de gastos en el mes.

salta_sin_navegador <- function() {
  testthat::skip_if_not_installed("shinytest2")
  testthat::skip_if(is.null(chromote::find_chrome()), "No hay Chrome/Edge disponible")
}

texto_de <- function(etiqueta) paste(as.character(etiqueta), collapse = "")

# --- Funciones puras -------------------------------------------------------------------

test_that("dinero_con_signo pone el signo antes de la moneda", {
  expect_equal(dinero_con_signo(30), "Q 30.00")
  expect_equal(dinero_con_signo(-1234.5), "−Q 1,234.50")
  expect_equal(dinero_con_signo(0), "Q 0.00")
})

test_that("Tu mes dice si vas ganando, perdiendo o si no hay movimientos", {
  base <- list(mes = "2026-11", vendiste = "0.00", costo_de_lo_vendido = "0.00",
               se_perdio = "0.00", gastaste = "0.00", otros_ingresos = "0.00",
               te_queda = "0.00", sin_iva = FALSE)
  vacio <- texto_de(tarjeta_tu_mes(base))
  expect_match(vacio, "Sin movimientos")
  expect_match(vacio, "Noviembre de 2026")
  expect_no_match(vacio, "Lo que se perdió")  # solo aparece si hubo pérdidas

  ganando <- texto_de(tarjeta_tu_mes(modifyList(base, list(
    vendiste = "1000.00", costo_de_lo_vendido = "300.00", gastaste = "200.00",
    te_queda = "500.00"))))
  expect_match(ganando, "Vas ganando")
  expect_match(ganando, "Q 500.00")
  expect_match(ganando, "−Q 300.00")  # lo que te costó, restando

  perdiendo <- texto_de(tarjeta_tu_mes(modifyList(base, list(
    gastaste = "45.00", se_perdio = "5.00", te_queda = "-50.00", sin_iva = TRUE))))
  expect_match(perdiendo, "Vas perdiendo")
  expect_match(perdiendo, "tu-mes__valor--negativo")
  expect_match(perdiendo, "Lo que se perdió")
  expect_match(perdiendo, "Sin IVA")
})

# --- Flujos en el navegador ------------------------------------------------------------

test_that("el Inicio muestra Tu mes con lo que calcula la API y se pone al día", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "tu-mes")
  entrar_como_mari(app)

  expect_true(esperar_texto(app, ".tu-mes", "Vas perdiendo"))
  expect_match(app$get_text(".tu-mes"), "−Q 3,545.00")
  expect_match(app$get_text(".tu-mes"), "Lo que te queda")
  expect_no_match(app$get_text(".tu-mes"), "Sin IVA")

  # Otra sección y de vuelta al Inicio: se vuelve a pedir el resumen.
  antes <- contadores_api(url)$resultados
  app$click(selector = ".nav-inferior__boton[data-destino='mas']")
  esperar_visible(app, "#mas-gastos")
  app$click(selector = ".nav-inferior__boton[data-destino='inicio']")
  for (i in 1:25) {
    if (contadores_api(url)$resultados > antes) break
    Sys.sleep(0.2)
  }
  expect_gt(contadores_api(url)$resultados, antes)
})

test_that("Tus impuestos guarda el régimen y el general pregunta por la factura", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "impuestos")
  entrar_como_mari(app)

  # Sin régimen general, el gasto no pregunta por la factura.
  app$click(selector = ".nav-inferior__boton[data-destino='mas']")
  esperar_visible(app, "#mas-gastos")
  app$click(selector = "#mas-gastos")
  esperar_visible(app, "#gastos-nuevo")
  app$click(selector = "#gastos-nuevo")
  esperar_visible(app, "#gastos-guardar")
  expect_false(visible(app, "#gastos-factura"))
  app$click(selector = "#gastos-atras")

  app$click(selector = ".nav-inferior__boton[data-destino='mas']")
  esperar_visible(app, "#mas-impuestos")
  app$click(selector = "#mas-impuestos")
  expect_true(esperar_visible(app, "#impuestos-guardar"))
  expect_match(app$get_text(".impuestos"), "¿Cómo pagas impuestos?")
  expect_true(app$get_js(
    "document.querySelector(\".impuestos [data-elige-valor='no_se']\").getAttribute('aria-pressed') === 'true'"))
  app$click(selector = ".impuestos [data-elige-valor='general']")
  app$click(selector = "#impuestos-guardar")
  expect_true(esperar_visible(app, "#mas-gastos"))  # vuelve a Más
  expect_equal(contadores_api(url)$regimen, "general")

  # Ahora el gasto pregunta por la factura y la manda a la API.
  app$click(selector = "#mas-gastos")
  esperar_visible(app, "#gastos-nuevo")
  app$click(selector = "#gastos-nuevo")
  esperar_visible(app, "#gastos-guardar")
  expect_true(visible(app, "#gastos-factura"))
  app$set_inputs("gastos-monto" = "224", "gastos-factura" = TRUE)
  app$click(selector = "#gastos-guardar")
  expect_true(esperar_visible(app, "#gastos-nuevo"))
  expect_equal(contadores_api(url)$gastos_con_factura, 1L)

  # El Inicio avisa que las cifras van sin IVA.
  app$click(selector = ".nav-inferior__boton[data-destino='inicio']")
  expect_true(esperar_texto(app, ".tu-mes", "Sin IVA"))

  # Al volver a Tus impuestos, queda marcado lo que se guardó.
  app$click(selector = ".nav-inferior__boton[data-destino='mas']")
  esperar_visible(app, "#mas-impuestos")
  app$click(selector = "#mas-impuestos")
  esperar_visible(app, "#impuestos-guardar")
  expect_true(app$get_js(
    "document.querySelector(\".impuestos [data-elige-valor='general']\").getAttribute('aria-pressed') === 'true'"))
})
