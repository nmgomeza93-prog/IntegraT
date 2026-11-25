# Vender: funciones puras y flujos en un navegador real a 390×844, contra la API falsa.
# Mari (mari@prueba.com) entra con Pepián (Q 45.00) y Horchata (Q 10.00).

salta_sin_navegador <- function() {
  testthat::skip_if_not_installed("shinytest2")
  testthat::skip_if(is.null(chromote::find_chrome()), "No hay Chrome/Edge disponible")
}

ir_a_vender <- function(app) {
  app$click(selector = ".nav-inferior__boton[data-destino='vender']")
  esperar_visible(app, "#vender-ver_hoy")
}

tocar <- function(app, id_item, veces = 1) {
  selector <- sprintf(".vender [data-elige-input][data-elige-valor='%s']", id_item)
  esperar_visible(app, selector)  # la lista llega un instante después del encabezado
  for (i in seq_len(veces)) app$click(selector = selector)
}

# Pasa de la lista al cobro (espera a que la barra del carrito ya esté).
a_cobro <- function(app) {
  esperar_visible(app, "#vender-ir_cobrar")
  app$click(selector = "#vender-ir_cobrar")
  esperar_visible(app, "#vender-confirmar")
}

texto_barra <- function(app) {
  app$get_js("(document.querySelector('.barra-carrito__texto') || {}).textContent || ''")
}

# --- Funciones puras -------------------------------------------------------------------

test_that("texto_cantidad, total_lineas y hora_local", {
  expect_equal(texto_cantidad(1, "platillo", "platillos"), "1 platillo")
  expect_equal(texto_cantidad(3, "platillo", "platillos"), "3 platillos")
  expect_equal(total_lineas(list(list(precio = 45.5, cantidad = 2L), list(precio = 10, cantidad = 3L))), 121)
  expect_equal(total_lineas(list(list(precio = 0.1, cantidad = 3L))), 0.3)  # sin ruido de decimales
  expect_equal(hora_local("2026-11-24T20:01:03.751486Z"), "14:01")  # Guatemala es UTC-6
  expect_equal(hora_local("2026-11-24T02:30:00+00:00"), "20:30")      # y es del día anterior
})

# --- Flujos en el navegador ------------------------------------------------------------

test_that("armar una venta, cobrar con tarjeta y ver lo vendido hoy", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "vender-flujo")
  entrar_como_mari(app)

  expect_true(ir_a_vender(app))
  expect_true(esperar_texto(app, ".vender", "Horchata"))  # la lista llega tras el encabezado
  expect_match(app$get_text(".vender"), "Pepián")
  expect_false(visible(app, ".barra-carrito"))

  tocar(app, "i-1", 2)  # dos Pepián
  tocar(app, "i-2")     # una Horchata
  expect_true(esperar_texto(app, ".barra-carrito__texto", "3 platillos · Q 100.00"))
  expect_true(any(grepl("×2", app$get_text(".cantidad-insignia"))))

  expect_true(a_cobro(app))
  expect_match(app$get_text(".total-venta"), "Q 100.00")
  expect_true(visible(app, "[data-elige-valor='efectivo'][aria-pressed='true']"))  # por defecto
  app$click(selector = "[data-elige-valor='tarjeta']")
  expect_true(esperar_visible(app, "[data-elige-valor='tarjeta'][aria-pressed='true']"))
  expect_match(app$get_text("#vender-confirmar"), "Cobrar Q 100.00")

  app$click(selector = "#vender-confirmar")
  expect_true(esperar_texto(app, ".vender", "¡Vendiste Q 100.00!"))
  expect_match(app$get_text(".vender"), "Venta 1 · Tarjeta")
  expect_equal(ventas_creadas(url), 1L)
  expect_true(app$get_js("document.documentElement.scrollWidth <= window.innerWidth"))

  # Otra venta: carrito vacío y el último medio de pago ya viene elegido
  app$click(selector = "#vender-otra")
  expect_true(esperar_visible(app, "#vender-ver_hoy"))
  expect_false(visible(app, ".barra-carrito"))
  tocar(app, "i-2")
  expect_true(a_cobro(app))
  expect_true(visible(app, "[data-elige-valor='tarjeta'][aria-pressed='true']"))

  # Lo vendido hoy: solo cuenta la venta ya cobrada
  app$click(selector = "#vender-volver_catalogo")
  expect_true(esperar_visible(app, "#vender-ver_hoy"))
  app$click(selector = "#vender-ver_hoy")
  expect_true(esperar_texto(app, ".vender", "Total de hoy"))
  expect_match(app$get_text(".vender"), "Q 100.00")
  expect_match(app$get_text(".vender"), "1 venta")
  expect_match(app$get_text(".vender"), "Tarjeta")
  expect_match(app$get_text(".vender"), "Venta 1 ·")
})

test_that("en el cobro se puede sumar y quitar; sin nada se vuelve a la lista", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "vender-carrito")
  entrar_como_mari(app)
  ir_a_vender(app)

  tocar(app, "i-1")
  expect_true(a_cobro(app))
  expect_match(app$get_text(".total-venta"), "Q 45.00")
  app$click(selector = "[data-elige-valor='mas:i-1']")
  expect_true(esperar_texto(app, ".total-venta", "Q 90.00"))
  expect_equal(app$get_text(".linea-carrito__cantidad"), "2")
  app$click(selector = "[data-elige-valor='menos:i-1']")
  expect_true(esperar_texto(app, ".total-venta", "Q 45.00"))

  app$click(selector = "[data-elige-valor='menos:i-1']")  # llega a 0: se quita
  expect_true(esperar_visible(app, "#vender-ver_hoy"))
  expect_false(visible(app, ".barra-carrito"))
  expect_equal(ventas_creadas(url), 0L)
})

test_that("un doble toque en Cobrar cobra una sola vez", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "vender-doble-toque")
  entrar_como_mari(app)
  ir_a_vender(app)
  tocar(app, "i-1")
  expect_true(a_cobro(app))
  app$run_js("var b = document.querySelector('#vender-confirmar'); b.click(); b.click();")
  expect_true(esperar_texto(app, ".vender", "¡Vendiste Q 45.00!"))
  Sys.sleep(1)
  expect_equal(ventas_creadas(url), 1L)
})

test_that("si la respuesta se pierde, reintentar no cobra dos veces", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "vender-reintento")
  crear_cuenta_y_negocio(app)

  # Un platillo propio para esta prueba
  app$click(selector = ".nav-inferior__boton[data-destino='productos']")
  expect_true(esperar_visible(app, "#productos-nuevo"))
  app$click(selector = "#productos-nuevo")
  expect_true(esperar_visible(app, "#productos-guardar"))
  llenar_item(app, "Se pierde", "20")
  app$click(selector = "#productos-guardar")
  expect_true(esperar_texto(app, ".catalogo", "Se pierde"))

  ir_a_vender(app)
  expect_true(esperar_visible(app, ".vender [data-elige-input]"))
  app$click(selector = ".vender [data-elige-input]")
  expect_true(a_cobro(app))

  app$click(selector = "#vender-confirmar")  # se cobra, pero la respuesta es un error
  expect_true(esperar_visible(app, ".mensaje-error"))
  expect_equal(ventas_creadas(url), 1L)
  app$click(selector = "#vender-confirmar")  # mismo carrito y misma clave
  expect_true(esperar_texto(app, ".vender", "¡Vendiste Q 20.00!"))
  expect_equal(ventas_creadas(url), 1L)
})

test_that("sin productos, Vender invita a agregar el primero", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "vender-vacio")
  crear_cuenta_y_negocio(app)
  app$click(selector = ".nav-inferior__boton[data-destino='vender']")
  expect_true(esperar_visible(app, "#vender-agregar"))
  expect_match(app$get_text(".vender"), "Aún no tienes platillos para vender")
  app$click(selector = "#vender-agregar")
  expect_true(esperar_visible(app, "#productos-nuevo"))  # lo lleva al Menú
})

test_that("la primera venta marca su paso en el checklist del Inicio", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "vender-checklist")
  crear_cuenta_y_negocio(app)
  hechos <- "document.querySelectorAll('.app-contenido .checklist__item--hecho').length"
  expect_equal(app$get_js(hechos), 0L)

  app$click(selector = ".nav-inferior__boton[data-destino='productos']")
  expect_true(esperar_visible(app, "#productos-nuevo"))
  app$click(selector = "#productos-nuevo")
  expect_true(esperar_visible(app, "#productos-guardar"))
  llenar_item(app, "Tamales", "12")
  app$click(selector = "#productos-guardar")
  expect_true(esperar_texto(app, ".catalogo", "Tamales"))

  ir_a_vender(app)
  expect_true(esperar_visible(app, ".vender [data-elige-input]"))
  app$click(selector = ".vender [data-elige-input]")
  expect_true(a_cobro(app))
  app$click(selector = "#vender-confirmar")
  expect_true(esperar_texto(app, ".vender", "¡Vendiste Q 12.00!"))

  app$click(selector = ".nav-inferior__boton[data-destino='inicio']")
  expect_true(esperar_js(app, paste0(hechos, " === 1")))
})

# --- Anular y deshacer -----------------------------------------------------------------

# Cobra una venta de efectivo con lo primero que haya en la lista (Mari: Pepián Q 45.00).
cobrar_uno <- function(app, id_item = "i-1") {
  tocar(app, id_item)
  a_cobro(app)
  app$click(selector = "#vender-confirmar")
  esperar_visible(app, "#vender-otra")
}

test_that("anular una venta desde el detalle: pide motivo y deja de contar", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "vender-anular")
  entrar_como_mari(app)
  ir_a_vender(app)
  cobrar_uno(app)
  app$click(selector = "#vender-ver_hoy")
  expect_true(esperar_visible(app, ".vender .lista-opciones [data-elige-input]"))

  # Abrir la venta muestra su detalle
  app$click(selector = ".vender .lista-opciones [data-elige-input]")
  expect_true(esperar_visible(app, "#vender-anular"))
  expect_match(app$get_text(".vender"), "Venta 1")
  expect_match(app$get_text(".vender"), "Pepián")
  expect_match(app$get_text(".total-venta"), "Q 45.00")

  # "No, dejarla": nada cambia
  app$click(selector = "#vender-anular")
  expect_true(esperar_visible(app, "#vender-confirmar_anular"))
  app$click(selector = "#vender-cancelar_anular")
  expect_true(esperar_visible(app, "#vender-anular"))
  expect_equal(anulaciones(url), 0L)

  # Sin motivo no se anula
  app$click(selector = "#vender-anular")
  expect_true(esperar_visible(app, "#vender-confirmar_anular"))
  app$click(selector = "#vender-confirmar_anular")
  expect_true(esperar_visible(app, ".mensaje-error"))
  expect_match(app$get_text("#vender-error"), "por qué la anulas")
  expect_equal(anulaciones(url), 0L)

  # Con motivo: se anula y el total de hoy baja a cero
  app$set_inputs("vender-motivo" = "Me equivoqué de platillo")
  app$click(selector = "#vender-confirmar_anular")
  expect_true(esperar_texto(app, ".vender", "Todavía no vendes nada hoy"))
  expect_equal(anulaciones(url), 1L)
  expect_match(app$get_text(".vender"), "Q 0.00")
  expect_match(app$get_text(".vender .lista-opciones:last-of-type"), "Anulada")

  # Al abrirla otra vez se ve el motivo y ya no se puede anular
  app$click(selector = ".vender .lista-opciones:last-of-type [data-elige-input]")
  expect_true(esperar_texto(app, ".vender", "Motivo: Me equivoqué de platillo"))
  expect_false(visible(app, "#vender-anular"))
  expect_match(app$get_text(".vender"), "Anulada")
})

test_that("un doble toque en 'Sí, anular' anula una sola vez", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "vender-anular-doble")
  entrar_como_mari(app)
  ir_a_vender(app)
  cobrar_uno(app)
  app$click(selector = "#vender-ver_hoy")
  expect_true(esperar_visible(app, ".vender .lista-opciones [data-elige-input]"))
  app$click(selector = ".vender .lista-opciones [data-elige-input]")
  expect_true(esperar_visible(app, "#vender-anular"))
  app$click(selector = "#vender-anular")
  expect_true(esperar_visible(app, "#vender-confirmar_anular"))
  app$set_inputs("vender-motivo" = "Cobré de más")
  app$run_js("var b = document.querySelector('#vender-confirmar_anular'); b.click(); b.click();")
  expect_true(esperar_texto(app, ".vender", "Todavía no vendes nada hoy"))
  Sys.sleep(1)
  expect_equal(anulaciones(url), 1L)
})

test_that("si no tienes permiso para anular, la app lo dice y deja todo como estaba", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "vender-anular-sin-permiso")
  entrar_como_mari(app)
  ir_a_vender(app)
  cobrar_uno(app)
  app$click(selector = "#vender-ver_hoy")
  expect_true(esperar_visible(app, ".vender .lista-opciones [data-elige-input]"))
  app$click(selector = ".vender .lista-opciones [data-elige-input]")
  expect_true(esperar_visible(app, "#vender-anular"))
  app$click(selector = "#vender-anular")
  expect_true(esperar_visible(app, "#vender-confirmar_anular"))
  app$set_inputs("vender-motivo" = "sin permiso")
  app$click(selector = "#vender-confirmar_anular")
  expect_true(esperar_visible(app, ".mensaje-error"))
  expect_match(app$get_text("#vender-error"), "No tienes permiso")
  expect_true(visible(app, "#vender-confirmar_anular"))  # sigue en el detalle
  expect_equal(anulaciones(url), 0L)
})

test_that("deshacer la venta recién cobrada pide confirmación y la anula", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "vender-deshacer")
  entrar_como_mari(app)
  ir_a_vender(app)
  cobrar_uno(app)
  expect_match(app$get_text(".vender"), "¡Vendiste Q 45.00!")

  app$click(selector = "#vender-deshacer")
  expect_true(esperar_visible(app, "#vender-confirmar_deshacer"))
  expect_match(app$get_text(".vender"), "¿Deshacer la venta 1?")
  app$click(selector = "#vender-cancelar_deshacer")  # "No, dejarla"
  expect_true(esperar_visible(app, "#vender-otra"))
  expect_equal(anulaciones(url), 0L)

  app$click(selector = "#vender-deshacer")
  expect_true(esperar_visible(app, "#vender-confirmar_deshacer"))
  app$click(selector = "#vender-confirmar_deshacer")
  expect_true(esperar_visible(app, "#vender-ver_hoy"))  # vuelve a la lista para vender
  expect_equal(anulaciones(url), 1L)

  app$click(selector = "#vender-ver_hoy")
  expect_true(esperar_texto(app, ".vender", "Todavía no vendes nada hoy"))
  expect_match(app$get_text(".vender"), "Anulada")
})

test_that("anular la única venta devuelve 'Haz tu primera venta' al checklist", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "vender-anular-checklist")
  crear_cuenta_y_negocio(app)
  hechos <- "document.querySelectorAll('.app-contenido .checklist__item--hecho').length"

  app$click(selector = ".nav-inferior__boton[data-destino='productos']")
  expect_true(esperar_visible(app, "#productos-nuevo"))
  app$click(selector = "#productos-nuevo")
  expect_true(esperar_visible(app, "#productos-guardar"))
  llenar_item(app, "Tamales", "12")
  app$click(selector = "#productos-guardar")
  expect_true(esperar_texto(app, ".catalogo", "Tamales"))

  ir_a_vender(app)
  expect_true(esperar_visible(app, ".vender [data-elige-input]"))
  app$click(selector = ".vender [data-elige-input]")
  expect_true(a_cobro(app))
  app$click(selector = "#vender-confirmar")
  expect_true(esperar_visible(app, "#vender-deshacer"))
  app$click(selector = ".nav-inferior__boton[data-destino='inicio']")
  expect_true(esperar_js(app, paste0(hechos, " === 1")))

  app$click(selector = ".nav-inferior__boton[data-destino='vender']")
  expect_true(esperar_visible(app, "#vender-deshacer"))
  app$click(selector = "#vender-deshacer")
  expect_true(esperar_visible(app, "#vender-confirmar_deshacer"))
  app$click(selector = "#vender-confirmar_deshacer")
  expect_true(esperar_visible(app, "#vender-ver_hoy"))
  app$click(selector = ".nav-inferior__boton[data-destino='inicio']")
  expect_true(esperar_js(app, paste0(hechos, " === 0")))
})
