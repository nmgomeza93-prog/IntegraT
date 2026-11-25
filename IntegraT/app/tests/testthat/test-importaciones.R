# Importaciones con la plantilla de factura (docs/PLAN_IMPORTACION.md), contra la API falsa a 390×844.
# La API falsa devuelve una vista previa fija (2 productos, uno con tallas S y M); el contrato real y
# la lectura del archivo los cubren las pruebas de api/tests/test_importaciones.py.

salta_sin_navegador <- function() {
  testthat::skip_if_not_installed("shinytest2")
  testthat::skip_if(is.null(chromote::find_chrome()), "No hay Chrome/Edge disponible")
}

archivo_de_prueba <- function(nombre = "factura.xlsx", env = parent.frame()) {
  ruta <- file.path(withr::local_tempdir(.local_envir = env), nombre)
  writeBin(as.raw(c(0x50, 0x4b, 0x03, 0x04)), ruta)  # el contenido no importa a la API falsa
  ruta
}

ir_a_importaciones <- function(app) {
  app$click(selector = ".nav-inferior__boton[data-destino='mas']")
  esperar_visible(app, "#mas-importaciones")
  app$click(selector = "#mas-importaciones")
  esperar_visible(app, "#importaciones-archivo")
}

# --- Funciones puras -------------------------------------------------------------------

test_that("textos de la importación", {
  expect_equal(nombre_plataforma("shein"), "SHEIN")
  expect_equal(nombre_plataforma("mercadolibre"), "Mercadolibre")
  l <- list(atributos = list(Talla = "M", Color = "Rosa"), cantidad = 2L, precio_unitario = "70.3")
  expect_equal(texto_linea_previa(l, "MXN"), "M · Rosa · ×2 · MXN 70.30")
  expect_match(paste(as.character(texto_estado_importacion("en_camino")), collapse = ""), "En camino")
})

# --- Flujo en el navegador -------------------------------------------------------------

test_that("subir la plantilla, revisar, queda en camino y me llegó el paquete", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "importaciones")
  entrar_como_mari(app)
  expect_true(ir_a_importaciones(app))
  expect_match(app$get_text(".importaciones"), "No tienes paquetes en camino")

  # Un PDF no sirve.
  app$upload_file("importaciones-archivo" = archivo_de_prueba("factura.pdf"))
  expect_true(esperar_texto(app, ".importaciones", "Sube la plantilla en Excel"))

  app$upload_file("importaciones-archivo" = archivo_de_prueba())
  expect_true(esperar_texto(app, ".importaciones", "Revisa tu importación"))
  texto <- app$get_text(".importaciones")
  expect_match(texto, "SHEIN")
  expect_match(texto, "Cuadra")
  expect_match(texto, "S · Rosa · ×1 · MXN 150.00")

  # Sin el cobro en quetzales no se guarda.
  app$click(selector = "#importaciones-confirmar")
  expect_true(esperar_texto(app, ".importaciones", "cuánto te cobró la tarjeta"))
  app$set_inputs("importaciones-cobro_q" = "207.60", "importaciones-nom_1" = "Pijama SilkySpell")
  app$click(selector = "#importaciones-confirmar")
  expect_true(esperar_texto(app, ".importaciones", "En camino"))
  expect_match(app$get_text(".importaciones"), "Q 207.60")
  expect_equal(contadores_api(url)$importaciones, 1L)

  # Detalle y "Me llegó el paquete" con una talla que no llegó.
  app$click(selector = ".importaciones [data-elige-valor='imp-1']")
  expect_true(esperar_visible(app, "#importaciones-ir_recibir"))
  expect_match(app$get_text(".importaciones"), "Pijama SilkySpell")
  app$click(selector = "#importaciones-ir_recibir")
  esperar_visible(app, "#importaciones-confirmar_recibir")
  app$set_inputs("importaciones-courier" = "30", "importaciones-guia" = "GT-1",
                 "importaciones-todo" = FALSE)
  esperar_visible(app, "#importaciones-llego_3")
  app$set_inputs("importaciones-llego_3" = "0")
  app$click(selector = "#importaciones-confirmar_recibir")
  expect_true(esperar_texto(app, ".importaciones", "Llegó incompleta"))
  expect_match(app$get_text(".importaciones"), "vende en Q 92.50")
  expect_equal(contadores_api(url)$importaciones_parciales, 1L)
})
