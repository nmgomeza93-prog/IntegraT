# Receta y costo de un platillo (dentro de su ficha), aviso de insumos agotados al vender y los
# pasos del checklist del restaurante. Mari entra con Pepián (Q 45.00), Horchata (Q 10.00), Harina
# (10 lb, Q 15.00 la libra) y Aceite (1 L, Q 40.00 el litro).

salta_sin_navegador <- function() {
  testthat::skip_if_not_installed("shinytest2")
  testthat::skip_if(is.null(chromote::find_chrome()), "No hay Chrome/Edge disponible")
}

abrir_receta <- function(app, id_item = "i-1") {
  app$click(selector = ".nav-inferior__boton[data-destino='productos']")
  esperar_visible(app, sprintf(".catalogo [data-elige-valor='%s']", id_item))
  app$click(selector = sprintf(".catalogo [data-elige-valor='%s']", id_item))
  esperar_visible(app, "#productos-ver_receta")
  app$click(selector = "#productos-ver_receta")
  esperar_visible(app, "#productos-receta_agregar")
}

agregar_a_receta <- function(app, insumo, cantidad) {
  app$set_inputs("productos-receta_insumo" = insumo, "productos-receta_cantidad" = cantidad)
  app$click(selector = "#productos-receta_agregar")
}

# --- Funciones puras -------------------------------------------------------------------

test_that("texto_margen arma la frase con lo que calcula la API", {
  r <- list(precio_venta = "45.00", margen = "31.25", margen_porcentaje = 69L)
  expect_equal(texto_margen(r), "Lo vendes en Q 45.00 · Te quedan Q 31.25 (69 %)")
  expect_equal(texto_margen(list(precio_venta = "45.00", margen = "-5.00", margen_porcentaje = NULL)),
               "Lo vendes en Q 45.00 · Te quedan Q -5.00")
  expect_null(texto_margen(list(precio_venta = "45.00", margen = NULL)))
})

test_that("aviso_insumos_en_falta nombra lo que se acabó y no dice nada si no falta", {
  expect_null(aviso_insumos_en_falta(list()))
  expect_null(aviso_insumos_en_falta(NULL))
  uno <- as.character(aviso_insumos_en_falta(list("Harina")))
  expect_match(uno, "se acabó: Harina\\.")
  tres <- as.character(aviso_insumos_en_falta(list("Aceite", "Harina", "Sal")))
  expect_match(tres, "Aceite, Harina y Sal")
})

# --- Flujos en el navegador ------------------------------------------------------------

test_that("armar la receta muestra el costo y lo que te queda, y se puede quitar un insumo", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "receta-armar")
  entrar_como_mari(app)
  expect_true(abrir_receta(app))
  expect_match(app$get_text(".catalogo"), "Receta y costo")
  expect_match(app$get_text(".catalogo"), "Dinos qué lleva cada platillo")

  # Error amable
  app$click(selector = "#productos-receta_agregar")
  expect_true(esperar_texto(app, "#productos-error", "Escribe cuánto lleva"))

  agregar_a_receta(app, "in-1", "0.5")
  expect_true(esperar_texto(app, ".catalogo", "Q 7.50"))
  expect_match(app$get_text(".catalogo"), "Hacer uno te cuesta")
  expect_match(app$get_text(".catalogo"), "Lo vendes en Q 45.00 · Te quedan Q 37.50 \\(83 %\\)")
  expect_match(app$get_text(".catalogo"), "0.5 lb")
  # Harina ya está en la receta: solo queda Aceite por agregar
  expect_equal(app$get_js("document.querySelectorAll('#productos-receta_insumo option').length"), 1L)

  # Al cambiar de insumo, la unidad ofrece solo las de su tipo (litro: líquidos)
  expect_true(esperar_js(app, "document.querySelector('#productos-receta_unidad').value === 'L'"))
  expect_equal(app$get_js("Array.from(document.querySelectorAll('#productos-receta_unidad option')).map(o => o.value).join(',')"),
               "ML,L,GAL")
  agregar_a_receta(app, "in-2", "0.25")
  expect_true(esperar_texto(app, ".catalogo", "Q 17.50"))
  expect_match(app$get_text(".catalogo"), "Te quedan Q 27.50 \\(61 %\\)")
  expect_match(app$get_text(".catalogo"), "Ya usaste todos tus insumos")

  # Quitar un insumo recalcula
  app$click(selector = "[data-elige-input='productos-quitar_linea'][data-elige-valor='in-1']")
  expect_true(esperar_js(app, "document.querySelectorAll('.linea-receta').length === 1"))
  expect_match(app$get_text(".catalogo"), "Hacer uno te cuesta[[:space:]]*Q 10[.]00")
  expect_false(grepl("0.5 lb", app$get_text(".catalogo")))
  expect_true(app$get_js("document.documentElement.scrollWidth <= window.innerWidth"))

  # La receta sigue ahí al volver a abrirla
  app$click(selector = "#productos-atras_receta")
  expect_true(esperar_visible(app, "#productos-ver_receta"))
  app$click(selector = "#productos-ver_receta")
  expect_true(esperar_texto(app, ".catalogo", "Aceite"))
  expect_match(app$get_text(".catalogo"), "0.25 L")
})

test_that("un doble toque en Agregar no repite el insumo", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "receta-doble")
  entrar_como_mari(app)
  abrir_receta(app)
  app$set_inputs("productos-receta_insumo" = "in-1", "productos-receta_cantidad" = "1")
  app$run_js("var b = document.querySelector('#productos-receta_agregar'); b.click(); b.click();")
  expect_true(esperar_texto(app, ".catalogo", "Q 15.00"))
  Sys.sleep(0.8)
  expect_false(grepl("dos veces", app$get_text(".catalogo")))
  expect_equal(app$get_js("document.querySelectorAll('.linea-receta').length"), 1L)
})

test_that("al vender un platillo con receta, la app avisa si se acabó un insumo", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "receta-venta")
  entrar_como_mari(app)
  abrir_receta(app)
  agregar_a_receta(app, "in-2", "1")             # Aceite: hay 1 L y cada Pepián lleva 1 L
  expect_true(esperar_texto(app, ".catalogo", "Q 40.00"))

  app$click(selector = ".nav-inferior__boton[data-destino='vender']")
  selector <- ".vender [data-elige-input][data-elige-valor='i-1']"
  esperar_visible(app, selector)
  app$click(selector = selector)
  esperar_visible(app, "#vender-ir_cobrar")
  app$click(selector = "#vender-ir_cobrar")
  esperar_visible(app, "#vender-confirmar")
  app$click(selector = "#vender-confirmar")
  expect_true(esperar_visible(app, "#vender-otra"))
  expect_match(app$get_text(".vender"), "¡Vendiste Q 45.00!")
  expect_match(app$get_text(".aviso-insumos"), "Se acabó")
  expect_match(app$get_text(".aviso-insumos"), "se acabó: Aceite")

  # Una venta que no agota nada no avisa
  app$click(selector = "#vender-otra")
  selector <- ".vender [data-elige-input][data-elige-valor='i-2']"
  esperar_visible(app, selector)
  app$click(selector = selector)
  esperar_visible(app, "#vender-ir_cobrar")
  app$click(selector = "#vender-ir_cobrar")
  esperar_visible(app, "#vender-confirmar")
  app$click(selector = "#vender-confirmar")
  expect_true(esperar_visible(app, "#vender-otra"))
  expect_false(visible(app, ".aviso-insumos"))
})

test_that("el checklist del restaurante lleva a Inventario y al platillo estrella", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "receta-checklist")
  entrar_como_mari(app)
  # Mari ya tiene insumos, así que el primer paso pendiente es el de los 5 platillos
  expect_true(esperar_texto(app, ".app-contenido", "Anota tus insumos principales"))
  expect_true(esperar_texto(app, ".app-contenido", "Dinos qué lleva tu platillo estrella"))
})
