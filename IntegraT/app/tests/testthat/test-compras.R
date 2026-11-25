# Compras a mano ("Lo que compraste"): funciones puras y flujos en un navegador real a 390×844,
# contra la API falsa. Mari (mari@prueba.com) entra con el proveedor Don Pedro, Harina (10 lb a
# Q 15.00) y Aceite (1 L a Q 40.00).

salta_sin_navegador <- function() {
  testthat::skip_if_not_installed("shinytest2")
  testthat::skip_if(is.null(chromote::find_chrome()), "No hay Chrome/Edge disponible")
}

ir_a_compras <- function(app) {
  app$click(selector = ".nav-inferior__boton[data-destino='mas']")
  esperar_visible(app, "#mas-compras")
  app$click(selector = "#mas-compras")
  esperar_visible(app, "#compras-nueva")
}

abrir_formulario_compra <- function(app) {
  app$click(selector = "#compras-nueva")
  esperar_visible(app, "#compras-revisar")
}

agregar_linea <- function(app, insumo, cantidad, costo) {
  app$set_inputs("compras-ins" = insumo, "compras-cant" = cantidad, "compras-costo" = costo)
  app$click(selector = "#compras-agregar_linea")
}

# Una compra completa de Harina hasta la pantalla de revisión
compra_hasta_revisar <- function(app, factura = NULL) {
  abrir_formulario_compra(app)
  agregar_linea(app, "in-1", "10", "200")
  esperar_texto(app, "#compras-lineas", "Q 200.00")
  if (!is.null(factura)) app$set_inputs("compras-factura" = factura)
  app$click(selector = "#compras-revisar")
  esperar_visible(app, "#compras-guardar")
}

# --- Funciones puras -------------------------------------------------------------------

test_that("total_compra suma lo que costó cada línea", {
  lineas <- list(list(costo_total = "200.00"), list(costo_total = "80.50"))
  expect_equal(total_compra(lineas), "Q 280.50")
  expect_equal(total_compra(list()), "Q 0.00")
})

test_that("las opciones de proveedor traen 'Sin proveedor' y 'Otro proveedor nuevo'", {
  o <- opciones_proveedor(list(list(id = "p1", nombre = "Don Pedro")))
  expect_equal(unname(o), c("", "p1", PROVEEDOR_NUEVO))
  expect_equal(names(o), c("Sin proveedor", "Don Pedro", "Otro proveedor nuevo"))
  expect_equal(unname(opciones_insumo(list(list(id = "i1", nombre = "Harina")))), "i1")
})

test_that("texto_compra nombra al proveedor y la factura", {
  expect_equal(texto_compra(list(proveedor_nombre = "Don Pedro", numero_factura = "A-1")),
               "Don Pedro · Factura A-1")
  expect_equal(texto_compra(list(proveedor_nombre = "Don Pedro", numero_factura = NULL)), "Don Pedro")
  expect_equal(texto_compra(list(proveedor_nombre = NULL, numero_factura = NULL)), "Sin proveedor")
})

# --- Flujos en el navegador ------------------------------------------------------------

test_that("la pantalla de compras abre vacía desde Más y avisa qué hacer", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "compras-vacio")
  entrar_como_mari(app)
  expect_true(ir_a_compras(app))
  expect_true(esperar_texto(app, ".compras", "No hay compras en"))
  expect_match(app$get_text(".compras"), "Lo que compraste")
  expect_match(app$get_text(".compras"), nombre_mes(mes_actual()))
  expect_equal(app$get_js("document.querySelector(\"[data-destino='mas']\").getAttribute('aria-current')"), "page")
  expect_true(app$get_js("document.documentElement.scrollWidth <= window.innerWidth"))
  expect_true(app$get_js("document.querySelector('#compras-mes_siguiente').disabled"))
})

test_that("registrar una compra: líneas, revisión, guardar y el inventario se pone al día", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "compras-registrar")
  entrar_como_mari(app)
  ir_a_compras(app)
  abrir_formulario_compra(app)
  expect_match(app$get_text(".compras"), "Registrar una compra")
  expect_equal(app$get_value(input = "compras-fecha"), hoy_local())

  # Errores amables
  app$click(selector = "#compras-revisar")
  expect_true(esperar_texto(app, "#compras-error", "Agrega al menos un insumo"))
  app$click(selector = "#compras-agregar_linea")
  expect_true(esperar_texto(app, "#compras-error_linea", "Escribe cuánto compraste"))
  app$set_inputs("compras-cant" = "10")
  app$click(selector = "#compras-agregar_linea")
  expect_true(esperar_texto(app, "#compras-error_linea", "cuánto costó"))
  expect_equal(compras_creadas(url), 0L)

  # Al cambiar a Aceite, la unidad ofrece solo las de los líquidos
  app$set_inputs("compras-ins" = "in-2")
  expect_true(esperar_js(app, "document.querySelector('#compras-uni').value === 'L'"))
  expect_equal(app$get_js("Array.from(document.querySelectorAll('#compras-uni option')).map(o => o.value).join(',')"),
               "ML,L,GAL")

  # Dos líneas; se quita una y se vuelve a agregar
  agregar_linea(app, "in-1", "10", "200")
  expect_true(esperar_texto(app, "#compras-lineas", "Q 200.00"))
  agregar_linea(app, "in-2", "2", "80")
  expect_true(esperar_texto(app, "#compras-lineas", "Total: Q 280.00"))
  app$click(selector = "[data-elige-input='compras-quitar_linea'][data-elige-valor='in-2']")
  expect_true(esperar_texto(app, "#compras-lineas", "Total: Q 200.00"))
  agregar_linea(app, "in-2", "2", "80")
  expect_true(esperar_texto(app, "#compras-lineas", "Total: Q 280.00"))
  expect_match(app$get_text("#compras-lineas"), "10 lb")
  expect_match(app$get_text("#compras-lineas"), "2 L")

  # Proveedor, pago y factura; se revisa
  app$set_inputs("compras-proveedor" = "pr-1", "compras-factura" = "A-123")
  app$click(selector = "[data-elige-valor='tarjeta']")
  expect_true(esperar_visible(app, "[data-elige-valor='tarjeta'][aria-pressed='true']"))
  app$click(selector = "#compras-revisar")
  expect_true(esperar_visible(app, "#compras-guardar"))
  expect_match(app$get_text(".compras"), "Revisa tu compra")
  expect_match(app$get_text(".compras"), "Q 280.00")
  expect_match(app$get_text(".compras"), "Don Pedro")
  expect_match(app$get_text(".compras"), "Tarjeta")
  expect_match(app$get_text(".compras"), "Factura A-123")
  expect_match(app$get_text(".compras"), "Harina")
  expect_equal(compras_creadas(url), 0L)

  # Corregir vuelve con todo lo escrito
  app$click(selector = "#compras-corregir_boton")
  expect_true(esperar_visible(app, "#compras-revisar"))
  expect_true(esperar_texto(app, "#compras-lineas", "Total: Q 280.00"))
  expect_equal(app$get_value(input = "compras-factura"), "A-123")
  expect_equal(app$get_value(input = "compras-proveedor"), "pr-1")
  app$click(selector = "#compras-revisar")
  esperar_visible(app, "#compras-guardar")
  app$click(selector = "#compras-guardar")
  expect_true(esperar_texto(app, ".compras", "Q 280.00"))
  expect_true(esperar_visible(app, "#compras-nueva"))
  expect_match(app$get_text(".compras"), "1 compra")
  expect_match(app$get_text(".compras"), "Don Pedro · Factura A-123")
  expect_equal(compras_creadas(url), 1L)

  # El inventario ya sube: Harina pasó de 10 a 20 lb
  app$click(selector = "#compras-volver")
  esperar_visible(app, "#mas-inventario")
  app$click(selector = "#mas-inventario")
  expect_true(esperar_texto(app, ".inventario", "20 lb"))
})

test_that("un proveedor nuevo se crea al vuelo y pide su nombre", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "compras-proveedor-nuevo")
  entrar_como_mari(app)
  ir_a_compras(app)
  abrir_formulario_compra(app)
  expect_false(visible(app, "#compras-prov_nombre"))
  app$set_inputs("compras-proveedor" = "__nuevo__")
  expect_true(esperar_visible(app, "#compras-prov_nombre"))
  agregar_linea(app, "in-1", "5", "100")
  esperar_texto(app, "#compras-lineas", "Q 100.00")
  app$click(selector = "#compras-revisar")
  expect_true(esperar_texto(app, "#compras-error", "nombre del proveedor"))
  app$set_inputs("compras-prov_nombre" = "Doña Luisa", "compras-prov_telefono" = "5555-0000")
  app$click(selector = "#compras-revisar")
  expect_true(esperar_visible(app, "#compras-guardar"))
  expect_match(app$get_text(".compras"), "Doña Luisa")
  app$click(selector = "#compras-guardar")
  expect_true(esperar_texto(app, ".compras", "1 compra"))   # la revisión ya mostraba el nombre
  expect_match(app$get_text(".compras"), "Doña Luisa")
  expect_equal(proveedores_vivos(url), 2L)
})

test_that("un doble toque en Guardar compra anota una sola", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "compras-doble")
  entrar_como_mari(app)
  ir_a_compras(app)
  compra_hasta_revisar(app)
  app$run_js("var b = document.querySelector('#compras-guardar'); b.click(); b.click();")
  expect_true(esperar_texto(app, ".compras", "Q 200.00"))
  Sys.sleep(1)
  expect_equal(compras_creadas(url), 1L)
})

test_that("si la respuesta se pierde, reintentar no compra dos veces", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "compras-reintento")
  entrar_como_mari(app)
  ir_a_compras(app)
  compra_hasta_revisar(app, factura = "Se pierde")
  app$click(selector = "#compras-guardar")             # se anota, pero llega un error
  expect_true(esperar_visible(app, ".mensaje-error"))
  expect_equal(compras_creadas(url), 1L)
  app$click(selector = "#compras-guardar")             # mismos datos, misma clave
  expect_true(esperar_texto(app, ".compras", "1 compra"))
  expect_equal(compras_creadas(url), 1L)
})

test_that("se ve el detalle de una compra y se puede anular con motivo", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "compras-anular")
  entrar_como_mari(app)
  ir_a_compras(app)
  compra_hasta_revisar(app, factura = "B-9")
  app$click(selector = "#compras-guardar")
  esperar_texto(app, ".compras", "1 compra")
  app$click(selector = "[data-elige-input='compras-abrir']")
  expect_true(esperar_visible(app, "#compras-anular"))
  expect_match(app$get_text(".compras"), "Harina")
  expect_match(app$get_text(".compras"), "10 lb")
  expect_match(app$get_text(".compras"), "Q 200.00")

  app$click(selector = "#compras-anular")
  expect_true(esperar_visible(app, "#compras-confirmar_anular"))
  app$click(selector = "#compras-confirmar_anular")           # sin motivo
  expect_true(esperar_texto(app, "#compras-error", "por qué la anulas"))
  expect_equal(anulaciones_compra(url), 0L)
  app$click(selector = "#compras-cancelar_anular")
  expect_true(esperar_visible(app, "#compras-anular"))
  app$click(selector = "#compras-anular")
  esperar_visible(app, "#compras-confirmar_anular")
  app$set_inputs("compras-motivo" = "Me equivoqué")
  app$click(selector = "#compras-confirmar_anular")
  expect_true(esperar_texto(app, ".compras", "Motivo: Me equivoqué"))
  expect_equal(anulaciones_compra(url), 1L)
  expect_false(visible(app, "#compras-anular"))

  # En la lista queda marcada como anulada y ya no suma
  app$click(selector = "#compras-atras_detalle")
  expect_true(esperar_visible(app, "#compras-nueva"))   # ya está en la lista
  expect_true(esperar_texto(app, ".compras", "0 compras"))
  expect_match(app$get_text(".compras"), "· Anulada")
})

test_that("los proveedores se listan y se agregan", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "compras-proveedores")
  entrar_como_mari(app)
  ir_a_compras(app)
  app$click(selector = "#compras-ir_proveedores")
  expect_true(esperar_visible(app, "#compras-guardar_proveedor"))
  expect_match(app$get_text(".compras"), "Don Pedro")
  expect_match(app$get_text(".compras"), "5555-1234")
  app$click(selector = "#compras-guardar_proveedor")
  expect_true(esperar_texto(app, "#compras-error", "nombre del proveedor"))
  app$set_inputs("compras-nuevo_prov_nombre" = "don pedro")
  app$click(selector = "#compras-guardar_proveedor")
  expect_true(esperar_texto(app, "#compras-error", "Ya tienes un proveedor con ese nombre"))
  app$set_inputs("compras-nuevo_prov_nombre" = "Doña Luisa", "compras-nuevo_prov_telefono" = "5555-0000")
  app$click(selector = "#compras-guardar_proveedor")
  expect_true(esperar_texto(app, ".compras", "Doña Luisa"))
  expect_equal(proveedores_vivos(url), 2L)
})

test_that("'Registrar compra' de las acciones rápidas abre directo el formulario", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "compras-rapida")
  entrar_como_mari(app)
  app$click(selector = "[data-abre-hoja='hoja-acciones']")
  expect_true(esperar_visible(app, "[data-accion='registrar_compra']"))
  app$click(selector = "[data-accion='registrar_compra']")
  expect_true(esperar_visible(app, "#compras-revisar"))
  expect_match(app$get_text(".compras"), "Registrar una compra")
})

test_that("texto_insumo marca la mercadería que se compra para revender", {
  expect_equal(texto_insumo(list(nombre = "Gaseosa", estado = "ok", item_id = "i-9")),
               "Gaseosa · Para vender")
  expect_equal(texto_insumo(list(nombre = "Gaseosa", estado = "falta", item_id = "i-9")),
               "Gaseosa · Para vender · Te falta")
  expect_equal(texto_insumo(list(nombre = "Harina", estado = "poco", item_id = NULL)),
               "Harina · Te queda poco")
})

test_that("un producto se puede marcar como mercadería y aparece en el inventario", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "compras-mercaderia")
  entrar_como_mari(app)
  app$click(selector = ".nav-inferior__boton[data-destino='productos']")
  esperar_visible(app, ".catalogo [data-elige-valor='i-2']")
  app$click(selector = ".catalogo [data-elige-valor='i-2']")          # Horchata
  expect_true(esperar_visible(app, "#productos-poner_mercaderia"))
  expect_true(visible(app, "#productos-ver_receta"))                  # mientras no sea mercadería

  app$click(selector = "#productos-poner_mercaderia")
  expect_true(esperar_visible(app, "#productos-quitar_mercaderia"))
  expect_match(app$get_text(".catalogo"), "Lo compras ya hecho")
  expect_match(app$get_text(".catalogo"), "Tienes 0 u")
  expect_false(visible(app, "#productos-ver_receta"))                 # su receta se maneja sola
  expect_equal(insumos_vivos(url), 3L)

  # Más → Inventario lo muestra como mercadería
  app$click(selector = ".nav-inferior__boton[data-destino='mas']")
  esperar_visible(app, "#mas-inventario")
  app$click(selector = "#mas-inventario")
  expect_true(esperar_texto(app, ".inventario", "Horchata · Para vender · Te falta"))

  # Y se puede quitar
  app$click(selector = ".nav-inferior__boton[data-destino='productos']")   # sigue abierta su ficha
  expect_true(esperar_visible(app, "#productos-quitar_mercaderia"))
  app$click(selector = "#productos-quitar_mercaderia")
  expect_true(esperar_visible(app, "#productos-poner_mercaderia"))
  expect_equal(insumos_vivos(url), 2L)
})

test_that("el checklist trae el paso de la primera compra y lleva a Compras", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "compras-checklist")
  entrar_como_mari(app)
  expect_true(esperar_texto(app, ".app-contenido", "Registra tu primera compra"))
  expect_equal(accion_de_paso("primera_compra", vocabulario_defecto())$destino, "compras")
})
