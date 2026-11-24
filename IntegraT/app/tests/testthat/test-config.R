# Dirección de la API: variable de entorno -> config.yml -> localhost.

escribir_config <- function(texto, env = parent.frame()) {
  ruta <- withr::local_tempfile(fileext = ".yml", .local_envir = env)
  writeLines(texto, ruta)
  ruta
}

CONFIG_PRUEBA <- c(
  "default:", "  api_base_url: \"http://127.0.0.1:8000\"",
  "shinyapps:", "  api_base_url: \"https://api.ejemplo.com\""
)

test_that("sin sección activa se usa default", {
  ruta <- escribir_config(CONFIG_PRUEBA)
  expect_equal(url_desde_config(ruta, activo = "default"), "http://127.0.0.1:8000")
})

test_that("la sección shinyapps manda sobre default", {
  ruta <- escribir_config(CONFIG_PRUEBA)
  expect_equal(url_desde_config(ruta, activo = "shinyapps"), "https://api.ejemplo.com")
})

test_that("una sección desconocida cae en default; sin archivo o roto devuelve vacío", {
  ruta <- escribir_config(CONFIG_PRUEBA)
  expect_equal(url_desde_config(ruta, activo = "otra"), "http://127.0.0.1:8000")
  expect_equal(url_desde_config(file.path(tempdir(), "no-existe.yml")), "")
  roto <- escribir_config(c("default: [", "  :::"))
  expect_equal(url_desde_config(roto), "")
})

test_that("la variable API_BASE_URL manda sobre config.yml y se quita la barra final", {
  withr::local_envvar(API_BASE_URL = "https://desde-entorno.com/")
  expect_equal(api_base_url(), "https://desde-entorno.com")
})

test_that("sin variable ni config.yml se usa localhost", {
  withr::local_envvar(API_BASE_URL = NA)
  withr::local_dir(withr::local_tempdir())  # carpeta sin config.yml
  expect_equal(api_base_url(), "http://127.0.0.1:8000")
})
