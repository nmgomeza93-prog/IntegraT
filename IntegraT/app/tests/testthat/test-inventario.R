# Inventario ("Tu inventario"): funciones puras y flujos en un navegador real a 390×844, contra
# la API falsa. Mari (mari@prueba.com) entra con Harina (10 lb, Q 15.00 la libra, mínimo 3) y
# Aceite (1 L, mínimo 2: "te queda poco").

salta_sin_navegador <- function() {
  testthat::skip_if_not_installed("shinytest2")
  testthat::skip_if(is.null(chromote::find_chrome()), "No hay Chrome/Edge disponible")
}

ir_a_inventario <- function(app) {
  app$click(selector = ".nav-inferior__boton[data-destino='mas']")
  esperar_visible(app, "#mas-inventario")
  app$click(selector = "#mas-inventario")
  esperar_visible(app, "#inventario-nuevo")
}

abrir_insumo <- function(app, id) {
  esperar_visible(app, sprintf(".inventario [data-elige-valor='%s']", id))
  app$click(selector = sprintf(".inventario [data-elige-valor='%s']", id))
  esperar_visible(app, "#inventario-mover_entrada")
}

# Abre la hoja de un movimiento desde la ficha y llena la cantidad (y el costo si es compra)
anotar_movimiento <- function(app, boton, cantidad, costo = NULL, nota = NULL) {
  app$click(selector = sprintf("#inventario-%s", boton))
  esperar_visible(app, "#inventario-guardar_mov")
  app$set_inputs("inventario-cantidad" = cantidad)
  if (!is.null(costo)) app$set_inputs("inventario-costo_mov" = costo)
  if (!is.null(nota)) app$set_inputs("inventario-nota_mov" = nota)
  app$click(selector = "#inventario-guardar_mov")
}

# --- Funciones puras -------------------------------------------------------------------

test_that("normalizar_cantidad acepta números con hasta 4 decimales", {
  expect_equal(normalizar_cantidad("10"), "10")
  expect_equal(normalizar_cantidad(" 2,5 "), "2.5")
  expect_equal(normalizar_cantidad("0.0001"), "0.0001")
  expect_null(normalizar_cantidad("mucho"))
  expect_null(normalizar_cantidad("1.00001"))
  expect_null(normalizar_cantidad("-3"))
  expect_null(normalizar_cantidad(""))
  expect_null(normalizar_cantidad(NULL))
})

test_that("las unidades se muestran cortas y se ofrecen por tipo", {
  expect_equal(cantidad_con_unidad("10", "LB"), "10 lb")
  expect_equal(cantidad_con_unidad("2", "L"), "2 L")
  expect_equal(abreviar_unidad("XYZ"), "xyz")
  unidades <- list(list(codigo = "LB", nombre = "Libra", tipo = "masa"),
                   list(codigo = "L", nombre = "Litro", tipo = "volumen"),
                   list(codigo = "KG", nombre = "Kilogramo", tipo = "masa"))
  todas <- opciones_unidad(unidades)
  expect_equal(unname(todas), c("LB", "L", "KG"))
  expect_equal(names(todas)[1], "Libra (lb)")
  expect_equal(unname(opciones_unidad(unidades, "masa")), c("LB", "KG"))
})

test_that("texto_insumo avisa cuando queda poco o falta", {
  expect_equal(texto_insumo(list(nombre = "Harina", estado = "ok")), "Harina")
  expect_equal(texto_insumo(list(nombre = "Aceite", estado = "poco")), "Aceite · Te queda poco")
  expect_equal(texto_insumo(list(nombre = "Sal", estado = "falta")), "Sal · Te falta")
})

# --- Flujos en el navegador ------------------------------------------------------------

test_that("la lista muestra existencias, avisos y el valor del inventario", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "inventario-lista")
  entrar_como_mari(app)

  expect_true(ir_a_inventario(app))
  expect_true(esperar_texto(app, ".inventario", "Q 190.00"))
  expect_match(app$get_text(".inventario"), "Tu inventario")
  expect_match(app$get_text(".inventario"), "2 insumos · 1 por reponer")
  expect_match(app$get_text(".inventario"), "Harina")
  expect_match(app$get_text(".inventario"), "10 lb")
  expect_match(app$get_text(".inventario"), "Aceite · Te queda poco")
  expect_match(app$get_text(".inventario"), "1 L")
  # Inventario fue abierto desde Más: "Más" queda marcado en la barra inferior
  expect_equal(app$get_js("document.querySelector(\"[data-destino='mas']\").getAttribute('aria-current')"), "page")
  expect_true(app$get_js("document.documentElement.scrollWidth <= window.innerWidth"))
})

test_that("agregar un insumo: sugerencias, validación, existencia inicial y doble toque", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "inventario-agregar")
  entrar_como_mari(app)
  ir_a_inventario(app)
  app$click(selector = "#inventario-nuevo")
  expect_true(esperar_visible(app, "#inventario-guardar"))
  expect_match(app$get_text(".inventario"), "Ideas para empezar")

  # Errores amables
  app$click(selector = "#inventario-guardar")
  expect_true(esperar_visible(app, ".mensaje-error"))
  expect_match(app$get_text("#inventario-error"), "Escribe cómo se llama")
  app$set_inputs("inventario-nombre" = "Sal", "inventario-existencia" = "3")
  app$click(selector = "#inventario-guardar")
  expect_true(esperar_texto(app, "#inventario-error", "cuánto te costó"))
  app$set_inputs("inventario-existencia" = "", "inventario-costo" = "20")
  app$click(selector = "#inventario-guardar")
  expect_true(esperar_texto(app, "#inventario-error", "cuánto tienes"))
  expect_equal(insumos_vivos(url), 2L)

  # Una idea llena el nombre y la unidad
  app$click(selector = "[data-elige-valor='Pollo|LB']")
  expect_true(esperar_js(app, "document.querySelector('#inventario-nombre').value === 'Pollo'"))
  expect_equal(app$get_value(input = "inventario-unidad"), "LB")

  # Datos buenos con lo que ya tiene; el doble toque crea uno solo
  app$set_inputs("inventario-minimo" = "5", "inventario-existencia" = "20",
                 "inventario-costo" = "300")
  app$run_js("var b = document.querySelector('#inventario-guardar'); b.click(); b.click();")
  expect_true(esperar_texto(app, ".inventario", "Q 490.00"))
  Sys.sleep(1)
  expect_equal(insumos_creados(url), 1L)
  expect_equal(insumos_vivos(url), 3L)
  expect_match(app$get_text(".inventario"), "Pollo")
  expect_match(app$get_text(".inventario"), "20 lb")

  # Un nombre repetido lo dice la API
  app$click(selector = "#inventario-nuevo")
  esperar_visible(app, "#inventario-guardar")
  app$set_inputs("inventario-nombre" = "harina")
  app$click(selector = "#inventario-guardar")
  expect_true(esperar_texto(app, "#inventario-error", "Ya tienes un insumo con ese nombre"))
})

test_that("anotar una compra promedia el costo y actualiza lo que tienes", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "inventario-compra")
  entrar_como_mari(app)
  ir_a_inventario(app)
  abrir_insumo(app, "in-1")
  expect_match(app$get_text(".inventario"), "10 lb")
  expect_match(app$get_text(".inventario"), "Cada libra te cuesta Q 15.00")
  expect_match(app$get_text(".inventario"), "Lo que ya tenías")

  # Errores amables
  app$click(selector = "#inventario-mover_entrada")
  esperar_visible(app, "#inventario-guardar_mov")
  app$click(selector = "#inventario-guardar_mov")
  expect_true(esperar_texto(app, "#inventario-error", "Escribe la cantidad"))
  app$set_inputs("inventario-cantidad" = "10")
  app$click(selector = "#inventario-guardar_mov")
  expect_true(esperar_texto(app, "#inventario-error", "cuánto costó todo"))
  expect_equal(movimientos_creados(url), 0L)

  app$set_inputs("inventario-costo_mov" = "200")
  app$click(selector = "#inventario-guardar_mov")
  expect_true(esperar_texto(app, ".inventario", "Cada libra te cuesta Q 17.50"))
  expect_match(app$get_text(".inventario"), "20 lb")
  expect_match(app$get_text(".inventario"), "Compra")
  expect_match(app$get_text(".inventario"), "\\+10 lb")
  expect_equal(movimientos_creados(url), 1L)
})

test_that("una pérdida y una corrección cambian el aviso del insumo", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "inventario-merma")
  entrar_como_mari(app)
  ir_a_inventario(app)
  abrir_insumo(app, "in-1")
  expect_match(app$get_text(".inventario"), "Bien")

  anotar_movimiento(app, "mover_merma", "8", nota = "Se mojó")
  expect_true(esperar_texto(app, ".inventario", "Te queda poco"))   # quedan 2 y el mínimo es 3
  expect_match(app$get_text(".inventario"), "2 lb")
  expect_match(app$get_text(".inventario"), "Se perdió")
  expect_match(app$get_text(".inventario"), "-8 lb")

  anotar_movimiento(app, "mover_ajuste", "0")                       # al contar, no hay nada
  expect_true(esperar_texto(app, ".inventario", "Te falta"))
  expect_match(app$get_text(".inventario"), "Corrección")

  # Y en la lista se ve igual
  app$click(selector = "#inventario-atras")
  expect_true(esperar_texto(app, ".inventario", "Harina · Te falta"))
})

test_that("si la respuesta se pierde, reintentar no anota dos veces", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "inventario-reintento")
  entrar_como_mari(app)
  ir_a_inventario(app)
  abrir_insumo(app, "in-1")
  app$click(selector = "#inventario-mover_entrada")
  esperar_visible(app, "#inventario-guardar_mov")
  app$set_inputs("inventario-cantidad" = "5", "inventario-costo_mov" = "100",
                 "inventario-nota_mov" = "Se pierde")
  app$click(selector = "#inventario-guardar_mov")                   # se anota, pero llega un error
  expect_true(esperar_visible(app, ".mensaje-error"))
  expect_equal(movimientos_creados(url), 1L)
  app$click(selector = "#inventario-guardar_mov")                   # mismos datos, misma clave
  expect_true(esperar_texto(app, ".inventario", "15 lb"))
  expect_equal(movimientos_creados(url), 1L)
})

test_that("se puede cambiar el nombre y el mínimo, y archivar un insumo", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "inventario-editar")
  entrar_como_mari(app)
  ir_a_inventario(app)
  abrir_insumo(app, "in-2")

  app$click(selector = "#inventario-editar")
  expect_true(esperar_visible(app, "#inventario-guardar_cambios"))
  expect_equal(app$get_value(input = "inventario-nombre_nuevo"), "Aceite")
  expect_equal(app$get_value(input = "inventario-minimo_nuevo"), "2")
  app$set_inputs("inventario-nombre_nuevo" = "Aceite de oliva", "inventario-minimo_nuevo" = "0.5")
  app$click(selector = "#inventario-guardar_cambios")
  expect_true(esperar_texto(app, ".inventario", "Aceite de oliva"))
  expect_match(app$get_text(".inventario"), "Bien")                 # 1 L ya supera el mínimo

  # Archivar pide confirmación y no borra al cancelar
  app$click(selector = "#inventario-archivar")
  expect_true(esperar_visible(app, "#inventario-confirmar_archivar"))
  app$click(selector = "#inventario-cancelar_archivar")
  expect_true(esperar_visible(app, "#inventario-archivar"))
  expect_equal(insumos_vivos(url), 2L)
  app$click(selector = "#inventario-archivar")
  esperar_visible(app, "#inventario-confirmar_archivar")
  app$click(selector = "#inventario-confirmar_archivar")
  expect_true(esperar_visible(app, "#inventario-nuevo"))
  expect_true(esperar_texto(app, ".inventario", "1 insumo"))
  expect_equal(insumos_vivos(url), 1L)
  expect_false(grepl("Aceite", app$get_text(".inventario")))
})

test_that("si alguien más cambió el insumo, la app avisa y no pisa nada", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "inventario-conflicto")
  entrar_como_mari(app)
  ir_a_inventario(app)
  app$click(selector = "#inventario-nuevo")
  esperar_visible(app, "#inventario-guardar")
  app$set_inputs("inventario-nombre" = "Conflicto")
  app$click(selector = "#inventario-guardar")
  expect_true(esperar_texto(app, ".inventario", "Conflicto"))
  abrir_insumo(app, "in-n11")
  app$click(selector = "#inventario-editar")
  esperar_visible(app, "#inventario-guardar_cambios")
  app$set_inputs("inventario-minimo_nuevo" = "4")
  app$click(selector = "#inventario-guardar_cambios")
  expect_true(esperar_texto(app, "#inventario-error", "Alguien más cambió esto"))
})
