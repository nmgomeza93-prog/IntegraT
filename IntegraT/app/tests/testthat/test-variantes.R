# Variantes (docs/PLAN_VARIANTES.md): tallas y colores en la ficha del producto y elegir la variante
# al vender, contra la API falsa a 390×844. Mari entra con Pepián (i-1, Q 45.00); la API falsa
# ofrece los atributos Talla (S, M, L) y Color (Negro, Rosa).

salta_sin_navegador <- function() {
  testthat::skip_if_not_installed("shinytest2")
  testthat::skip_if(is.null(chromote::find_chrome()), "No hay Chrome/Edge disponible")
}

# --- Funciones puras -------------------------------------------------------------------

test_that("atributos_para_item ofrece los de la categoría, los de sus variantes o todos", {
  atributos <- list(list(nombre = "Talla", valores = list()), list(nombre = "Color", valores = list()),
                    list(nombre = "Número", valores = list()))
  nombres <- function(x) vapply(x, function(a) a$nombre, "")
  cats <- list(list(id = "c-1", atributos = list("Color", "Talla")))
  expect_equal(nombres(atributos_para_item(list(categoria_id = "c-1"), cats, atributos)),
               c("Color", "Talla"))  # en el orden de la categoría
  con_variantes <- list(categoria_id = NULL,
                        variantes = list(list(atributos = list(Número = "38"))))
  expect_equal(nombres(atributos_para_item(con_variantes, cats, atributos)), "Número")
  expect_equal(nombres(atributos_para_item(list(), cats, atributos)), c("Talla", "Color", "Número"))
})

# --- Flujo en el navegador -------------------------------------------------------------

test_that("dar tallas a un producto y venderlo eligiendo la talla", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "variantes")
  entrar_como_mari(app)

  app$click(selector = ".nav-inferior__boton[data-destino='productos']")
  esperar_visible(app, ".catalogo [data-elige-valor='i-1']")
  app$click(selector = ".catalogo [data-elige-valor='i-1']")
  expect_true(esperar_visible(app, "#productos-ver_variantes"))
  app$click(selector = "#productos-ver_variantes")
  expect_true(esperar_visible(app, "#productos-guardar_variante"))
  expect_match(app$get_text(".catalogo"), "Si lo vendes en varias tallas")

  # Sin elegir nada: aviso amable.
  app$click(selector = "#productos-guardar_variante")
  expect_true(esperar_texto(app, ".catalogo", "Elige al menos una talla"))

  # Talla S a Q 40 y una talla que no está (XL) a Q 50.
  app$click(selector = ".catalogo [data-elige-valor='Talla::S']")
  app$set_inputs("productos-var_precio" = "40")
  app$click(selector = "#productos-guardar_variante")
  expect_true(esperar_texto(app, ".lista-variantes", "Q 40.00"))
  app$set_inputs("productos-otro_1" = "XL", "productos-var_precio" = "50")
  app$click(selector = "#productos-guardar_variante")
  expect_true(esperar_texto(app, ".lista-variantes", "XL"))


  # Al vender, tocar el Pepián pide la talla.
  app$click(selector = ".nav-inferior__boton[data-destino='vender']")
  esperar_visible(app, ".vender [data-elige-valor='i-1']")
  expect_match(app$get_text(".vender"), "desde")
  app$click(selector = ".vender [data-elige-valor='i-1']")
  expect_true(esperar_visible(app, ".elegir-variante"))
  expect_match(app$get_text(".elegir-variante"), "XL")
  app$click(selector = ".elegir-variante [data-elige-valor='i-1|var-2']")  # XL, Q 50
  expect_true(esperar_texto(app, ".vender", "×1"))
  expect_false(visible(app, ".elegir-variante"))
  app$click(selector = "#vender-ir_cobrar")
  expect_true(esperar_texto(app, ".vender", "Pepián · XL"))
  expect_match(app$get_text(".vender"), "Q 50.00")
  app$click(selector = "#vender-confirmar")
  expect_true(esperar_visible(app, "#vender-otra"))  # cobrada
})
