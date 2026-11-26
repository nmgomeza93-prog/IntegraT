# Mi negocio (Más → Mi negocio), contra la API falsa. Las validaciones de fondo son de la API.

salta_sin_navegador <- function() {
  testthat::skip_if_not_installed("shinytest2")
  testthat::skip_if(is.null(chromote::find_chrome()), "No hay Chrome/Edge disponible")
}

test_that("los vacíos se borran y el NIT solo viaja si se pide", {
  valores <- list(nombre = " Comedor ", telefono = "", correo = "a@b.com", direccion = " ",
                  nit = "1234567-9", nombre_fiscal = "")
  sin_fiscal <- cuerpo_negocio(valores, incluir_fiscal = FALSE)
  expect_equal(sin_fiscal$nombre, "Comedor")
  expect_null(sin_fiscal$telefono)
  expect_false("nit" %in% names(sin_fiscal))
  con_fiscal <- cuerpo_negocio(valores, incluir_fiscal = TRUE)
  expect_equal(con_fiscal$nit, "1234567-9")
  json <- jsonlite::toJSON(con_fiscal, auto_unbox = TRUE, null = "null")
  expect_match(json, '"nombre_fiscal":null', fixed = TRUE)
})

test_that("cambiar el nombre y los datos del negocio; el encabezado se actualiza", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "mi-negocio")
  entrar_como_mari(app)

  app$click(selector = ".nav-inferior__boton[data-destino='mas']")
  esperar_visible(app, "#mas-negocio")
  app$click(selector = "#mas-negocio")
  esperar_visible(app, "#negocio-guardar")
  expect_equal(app$get_value(input = "negocio-nombre"), "Comedor Doña Mari")

  app$set_inputs("negocio-nombre" = "C")
  app$click(selector = "#negocio-guardar")
  expect_true(esperar_texto(app, ".mi-negocio", "Escribe el nombre"))
  app$set_inputs("negocio-nombre" = "Comedor Mari", "negocio-telefono" = "5555 1234",
                 "negocio-nit" = "1234567-X")
  app$click(selector = "#negocio-guardar")
  expect_true(esperar_texto(app, ".mi-negocio", "Revisa el NIT"))
  expect_equal(app$get_value(input = "negocio-telefono"), "5555 1234")  # no se borró
  app$set_inputs("negocio-nit" = "1234567-9")
  app$click(selector = "#negocio-guardar")
  expect_true(esperar_visible(app, "#mas-negocio"))
  expect_true(esperar_texto(app, ".app-encabezado__negocio", "Comedor Mari"))
  datos <- contadores_api(url)$negocio_datos
  expect_equal(datos$nombre, "Comedor Mari")
  expect_equal(datos$telefono, "+50255551234")
  expect_equal(datos$nit, "12345679")

  # Al volver, muestra lo guardado.
  app$click(selector = "#mas-negocio")
  esperar_visible(app, "#negocio-guardar")
  expect_true(esperar_texto(app, ".mi-negocio", "Para tus facturas"))
  expect_equal(app$get_value(input = "negocio-nit"), "1234567-9")
})
