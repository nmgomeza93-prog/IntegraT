# Precio sugerido (docs/PLAN_PRECIO_SUGERIDO.md): la API lo calcula; la app lo muestra, lo aplica y
# deja cambiar el margen. Mari entra con Pepián (i-1, Q 45.00) y Harina (in-1, Q 15.00 la libra).

salta_sin_navegador <- function() {
  testthat::skip_if_not_installed("shinytest2")
  testthat::skip_if(is.null(chromote::find_chrome()), "No hay Chrome/Edge disponible")
}

texto_de <- function(etiqueta) paste(as.character(etiqueta), collapse = "")

abrir_ficha_receta <- function(app, id_item = "i-1") {
  app$click(selector = ".nav-inferior__boton[data-destino='productos']")
  esperar_visible(app, sprintf(".catalogo [data-elige-valor='%s']", id_item))
  app$click(selector = sprintf(".catalogo [data-elige-valor='%s']", id_item))
  esperar_visible(app, "#productos-ver_receta")
  app$click(selector = "#productos-ver_receta")
  esperar_visible(app, "#productos-receta_agregar")
}

# --- Funciones puras -------------------------------------------------------------------

test_that("la marca del catálogo solo aparece si pierde o gana poco", {
  expect_match(texto_de(marca_precio("pierde")), "Pierdes")
  expect_match(texto_de(marca_precio("bajo")), "Margen bajo")
  expect_null(marca_precio("ok"))
  expect_null(marca_precio(NULL))
})

test_that("la tarjeta del precio sugerido ofrece usarlo solo si hace falta", {
  base <- list(precio_venta = "45.00", precio_sugerido = "46.50", aviso_precio = "bajo",
               margen_objetivo_porcentaje = 35L, margen_propio = FALSE)
  bajo <- texto_de(tarjeta_precio_sugerido(base, "usar", "margen"))
  expect_match(bajo, "Q 46.50")
  expect_match(bajo, "Ganas poco")
  expect_match(bajo, "Usar Q 46.50")
  expect_match(bajo, "Para ganar tu 35 %")

  ok <- texto_de(tarjeta_precio_sugerido(modifyList(base, list(precio_venta = "50.00",
                                                               aviso_precio = "ok",
                                                               margen_propio = TRUE)),
                                         "usar", "margen"))
  expect_match(ok, "Buen precio")
  expect_no_match(ok, "Usar Q")
  expect_match(ok, "margen propio")

  expect_null(tarjeta_precio_sugerido(modifyList(base, list(precio_sugerido = NULL)), "u", "m"))
})

# --- Flujos en el navegador ------------------------------------------------------------

test_that("la ficha sugiere un precio, se aplica con un toque y se cambia el margen", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "precio-sugerido")
  entrar_como_mari(app)
  expect_true(abrir_ficha_receta(app))

  # 2 lb de harina = Q 30.00; al 35 % el sugerido es Q 46.50 y Q 45.00 deja poco margen.
  app$set_inputs("productos-receta_insumo" = "in-1", "productos-receta_cantidad" = "2")
  app$click(selector = "#productos-receta_agregar")
  expect_true(esperar_texto(app, ".precio-sugerido", "Q 46.50"))
  expect_match(app$get_text(".precio-sugerido"), "Ganas poco")

  app$click(selector = "#productos-usar_sugerido")
  expect_true(esperar_texto(app, ".precio-sugerido", "Buen precio"))
  expect_false(visible(app, "#productos-usar_sugerido"))

  # Margen propio de 60 %: 30 / 0.4 = Q 75.00.
  app$click(selector = "#productos-abrir_margen")
  esperar_visible(app, "#productos-guardar_margen")
  app$set_inputs("productos-margen_pct" = "95")
  app$click(selector = "#productos-guardar_margen")
  expect_true(esperar_texto(app, ".catalogo", "entre 0 y 90"))
  app$set_inputs("productos-margen_pct" = "60")
  app$click(selector = "#productos-guardar_margen")
  expect_true(esperar_texto(app, ".precio-sugerido", "Q 75.00"))
  expect_match(app$get_text(".precio-sugerido"), "margen propio")

  # En la lista del catálogo, el Pepián queda marcado (Q 46.50 con 60 % es margen bajo).
  app$click(selector = "#productos-atras_receta")
  esperar_visible(app, "#productos-atras")
  app$click(selector = "#productos-atras")  # de la ficha a la lista
  expect_true(esperar_texto(app, ".catalogo", "Margen bajo"))
})

test_that("Tu margen de ganancia cambia el margen del negocio", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "margen-negocio")
  entrar_como_mari(app)

  app$click(selector = ".nav-inferior__boton[data-destino='mas']")
  esperar_visible(app, "#mas-margen")
  app$click(selector = "#mas-margen")
  expect_true(esperar_visible(app, "#margen-guardar"))
  expect_equal(app$get_value(input = "margen-pct"), "35")
  app$set_inputs("margen-pct" = "50")
  app$click(selector = "#margen-guardar")
  expect_true(esperar_visible(app, "#mas-margen"))  # vuelve a Más
  expect_equal(contadores_api(url)$margen, "0.5000")
})
