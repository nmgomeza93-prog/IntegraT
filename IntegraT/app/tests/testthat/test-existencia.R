# Vender según la existencia (docs/ANALISIS_INVENTARIO_Y_CLIENTES.md), contra la API falsa.
# Mari (restaurante) empieza con la regla "avisar"; Pepián es i-1 y Horchata i-2. El atajo /_stock
# de la API falsa fija cuánto queda de un ítem (en la API real lo dan compras e importaciones).

salta_sin_navegador <- function() {
  testthat::skip_if_not_installed("shinytest2")
  testthat::skip_if(is.null(chromote::find_chrome()), "No hay Chrome/Edge disponible")
}

fijar_stock <- function(url, item_id, n) {
  httr2::request(paste0(url, "/_stock")) |>
    httr2::req_auth_bearer_token("token-valido") |>
    httr2::req_body_json(list(item_id = item_id, n = n)) |> httr2::req_perform()
}

# --- Funciones puras -------------------------------------------------------------------

test_that("estado_existencia dice cuánto queda y si se puede tocar", {
  expect_equal(estado_existencia(3L, TRUE, TRUE),
               list(texto = "Quedan 3", agotado = FALSE, poco = FALSE))
  expect_equal(estado_existencia(2L, TRUE, TRUE, "poco"),
               list(texto = "Quedan 2 \u00b7 por agotarse", agotado = FALSE, poco = TRUE))
  expect_equal(estado_existencia(0L, TRUE, TRUE),
               list(texto = "Agotado", agotado = TRUE, poco = FALSE))
  expect_equal(estado_existencia(0L, TRUE, FALSE),
               list(texto = "Agotado", agotado = FALSE, poco = FALSE))
  expect_equal(estado_existencia(NULL, FALSE, TRUE),
               list(texto = "Sin inventario", agotado = TRUE, poco = FALSE))
  expect_equal(estado_existencia(NULL, FALSE, FALSE),
               list(texto = NULL, agotado = FALSE, poco = FALSE))
})

test_that("los avisos de por agotarse nombran lo que queda poco", {
  expect_null(aviso_por_agotarse(list()))
  expect_match(paste(as.character(aviso_por_agotarse(list("Camisa", "Gorra"))), collapse = ""),
               "Camisa y Gorra")
  alertas <- list(productos = list(list(nombre = "Pijama \u00b7 S", estado = "agotado", disponible = 0L),
                                   list(nombre = "Gorra", estado = "poco", disponible = 1L)),
                  ingredientes = list())
  texto <- paste(as.character(tarjeta_por_agotarse(alertas, "ir")), collapse = "")
  expect_match(texto, "1 agotado")
  expect_match(texto, "Quedan 1")
  expect_null(tarjeta_por_agotarse(list(productos = list(), ingredientes = list()), "ir"))
})

# --- Flujo en el navegador -------------------------------------------------------------

test_that("con 'No dejar vender', lo agotado no se toca y el carrito no pasa de lo que hay", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "existencia")
  entrar_como_mari(app)
  fijar_stock(url, "i-1", 2L)  # 2 Pepianes; la Horchata no controla inventario

  # Cambiar la regla en Más → "Si no hay inventario".
  app$click(selector = ".nav-inferior__boton[data-destino='mas']")
  esperar_visible(app, "#mas-reglas_venta")
  app$click(selector = "#mas-reglas_venta")
  expect_true(esperar_visible(app, "#reglas_venta-guardar"))
  app$click(selector = ".reglas-venta [data-elige-valor='bloquear']")
  app$click(selector = "#reglas_venta-guardar")
  expect_true(esperar_visible(app, "#mas-reglas_venta"))
  expect_equal(contadores_api(url)$regla_venta, "bloquear")

  app$click(selector = ".nav-inferior__boton[data-destino='vender']")
  expect_true(esperar_texto(app, ".vender", "Quedan 2"))
  expect_match(app$get_text(".vender"), "Sin inventario")
  expect_true(app$get_js("document.querySelector(\".vender [data-elige-valor='i-2']\").disabled"))

  # Tres toques al Pepián: el carrito se queda en 2.
  for (k in 1:3) {
    app$click(selector = ".vender [data-elige-valor='i-1']")
    Sys.sleep(0.4)
  }
  expect_true(esperar_texto(app, ".vender", "×2"))
  expect_no_match(app$get_text(".vender"), "×3")

  # Si mientras tanto se vendieron por otro lado, la API no deja cobrar y lo dice.
  fijar_stock(url, "i-1", 1L)
  app$click(selector = "#vender-ir_cobrar")
  esperar_visible(app, "#vender-confirmar")
  app$click(selector = "#vender-confirmar")
  expect_true(esperar_texto(app, ".vender", "solo quedan 1"))
})


test_that("el Inicio y la venta avisan lo que está por agotarse", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "por-agotarse")
  entrar_como_mari(app)
  fijar_stock(url, "i-1", 3L)  # Pepián: 3; el mínimo de la API falsa es 2

  app$click(selector = ".nav-inferior__boton[data-destino='vender']")
  esperar_visible(app, ".vender [data-elige-valor='i-1']")
  app$click(selector = ".vender [data-elige-valor='i-1']")
  expect_true(esperar_texto(app, ".vender", "\u00d71"))
  app$click(selector = "#vender-ir_cobrar")
  esperar_visible(app, "#vender-confirmar")
  app$click(selector = "#vender-confirmar")
  expect_true(esperar_texto(app, ".vender", "Te queda poco de: Pep"))

  app$click(selector = ".nav-inferior__boton[data-destino='inicio']")
  expect_true(esperar_texto(app, ".por-agotarse", "Por agotarse"))
  expect_match(app$get_text(".por-agotarse"), "Quedan 2")
  app$click(selector = "#inicio-ver_inventario")
  expect_true(esperar_visible(app, ".inventario"))
})
