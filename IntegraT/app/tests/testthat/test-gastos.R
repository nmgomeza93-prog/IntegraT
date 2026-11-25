# Gastos ("Lo que gastaste"): funciones puras y flujos en un navegador real a 390×844,
# contra la API falsa. Mari (mari@prueba.com) entra con Renta Q 3,500.00 (fija) y Desechables
# Q 45.00 (variable) en el mes actual.

salta_sin_navegador <- function() {
  testthat::skip_if_not_installed("shinytest2")
  testthat::skip_if(is.null(chromote::find_chrome()), "No hay Chrome/Edge disponible")
}

ir_a_gastos <- function(app) {
  app$click(selector = ".nav-inferior__boton[data-destino='mas']")
  esperar_visible(app, "#mas-gastos")
  app$click(selector = "#mas-gastos")
  esperar_visible(app, "#gastos-nuevo")
}

abrir_formulario_gasto <- function(app) {
  app$click(selector = "#gastos-nuevo")
  esperar_visible(app, "#gastos-guardar")
}

llenar_gasto <- function(app, monto, categoria = NULL, nota = NULL) {
  app$set_inputs("gastos-monto" = monto)
  if (!is.null(categoria)) app$set_inputs("gastos-categoria" = categoria)
  if (!is.null(nota)) app$set_inputs("gastos-nota" = nota)
}

# --- Funciones puras -------------------------------------------------------------------

test_that("nombre_mes, mes_desplazado, fecha_corta y fechas locales", {
  expect_equal(nombre_mes("2026-11"), "Noviembre de 2026")
  expect_equal(nombre_mes("2027-01"), "Enero de 2027")
  expect_equal(mes_desplazado("2026-11", -1), "2026-10")
  expect_equal(mes_desplazado("2026-01", -1), "2025-12")  # cruza el año hacia atrás
  expect_equal(mes_desplazado("2026-12", 1), "2027-01")   # y hacia adelante
  expect_equal(mes_desplazado("2026-11", 0), "2026-11")
  expect_equal(fecha_corta("2026-11-24"), "24 nov")
  expect_equal(fecha_corta("2026-01-05"), "5 ene")
  # 02:00 UTC del 1 de diciembre sigue siendo 30 de noviembre en Guatemala (UTC-6)
  momento <- as.POSIXct("2026-12-01 02:00:00", tz = "UTC")
  expect_equal(mes_actual(momento), "2026-11")
  expect_equal(hoy_local(momento), "2026-11-30")
})

test_that("opciones_categoria agrega la categoría archivada del gasto que se edita", {
  cats <- list(list(id = "c1", nombre = "Renta"), list(id = "c2", nombre = "Sueldos"))
  expect_equal(unname(opciones_categoria(cats)), c("c1", "c2"))
  expect_equal(names(opciones_categoria(cats)), c("Renta", "Sueldos"))
  vigente <- list(categoria_id = "c2", categoria_nombre = "Sueldos")
  expect_equal(unname(opciones_categoria(cats, vigente)), c("c1", "c2"))  # no se repite
  archivada <- list(categoria_id = "c9", categoria_nombre = "Gas")
  o <- opciones_categoria(cats, archivada)
  expect_equal(unname(o), c("c1", "c2", "c9"))
  expect_equal(names(o)[3], "Gas (archivada)")
  expect_equal(unname(opciones_categoria(list(), archivada)), "c9")  # aunque no carguen las demás
})

test_that("cada paso del checklist lleva al lugar correcto", {
  vocab <- vocabulario_defecto()
  expect_equal(accion_de_paso("gastos_fijos", vocab)$destino, "gastos")
  expect_equal(accion_de_paso("primera_venta", vocab)$destino, "vender")
  expect_equal(accion_de_paso("primer_producto", vocab)$destino, "productos")
  expect_equal(accion_de_paso("receta_estrella", vocab)$destino, "productos")
  expect_equal(accion_de_paso("primeros_insumos", vocab)$destino, "inventario")
  expect_null(accion_de_paso("un_paso_desconocido", vocab)$destino)  # todavía no existe
})

# --- Flujos en el navegador ------------------------------------------------------------

test_that("el mes muestra el total, fijos y variables y el reparto por categoría", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "gastos-mes")
  entrar_como_mari(app)

  expect_true(ir_a_gastos(app))
  expect_true(esperar_texto(app, ".gastos", "Q 3,545.00"))
  expect_match(app$get_text(".gastos"), "Lo que gastaste")
  expect_match(app$get_text(".gastos"), nombre_mes(mes_actual()))
  expect_match(app$get_text(".gastos"), "2 gastos · Fijos Q 3,500.00 · Variables Q 45.00")
  expect_match(app$get_text(".gastos"), "99 % de tus gastos")
  expect_match(app$get_text(".gastos"), "Renta")
  expect_match(app$get_text(".gastos"), "Desechables")
  # Gastos fue abierto desde Más: "Más" queda marcado en la barra inferior
  expect_equal(app$get_js("document.querySelector(\"[data-destino='mas']\").getAttribute('aria-current')"), "page")
  expect_true(app$get_js("document.documentElement.scrollWidth <= window.innerWidth"))
  # El botón del mes siguiente está apagado en el mes actual
  expect_true(app$get_js("document.querySelector('#gastos-mes_siguiente').disabled"))
})

test_that("anotar un gasto: valida, guarda, recuerda el medio y actualiza el total", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "gastos-anotar")
  entrar_como_mari(app)
  ir_a_gastos(app)
  abrir_formulario_gasto(app)
  expect_match(app$get_text(".gastos"), "Anotar un gasto")
  expect_equal(app$get_value(input = "gastos-fecha"), hoy_local())

  # Errores amables
  app$click(selector = "#gastos-guardar")
  expect_true(esperar_visible(app, ".mensaje-error"))
  expect_match(app$get_text("#gastos-error"), "Escribe cuánto gastaste")
  llenar_gasto(app, "mucho")
  app$click(selector = "#gastos-guardar")
  Sys.sleep(0.5)
  expect_match(app$get_text("#gastos-error"), "Escribe cuánto gastaste")
  expect_equal(gastos_vivos(url), 2L)

  # Datos buenos con tarjeta y nota
  llenar_gasto(app, "125.50", categoria = "g-3", nota = "Recibo de luz")
  app$click(selector = "[data-elige-valor='tarjeta']")
  expect_true(esperar_visible(app, "[data-elige-valor='tarjeta'][aria-pressed='true']"))
  expect_false(visible(app, "[data-elige-valor='efectivo'][aria-pressed='true']"))
  app$click(selector = "#gastos-guardar")
  expect_true(esperar_texto(app, ".gastos", "Q 3,670.50"))
  expect_match(app$get_text(".gastos"), "Luz, agua y gas · Recibo de luz")
  expect_equal(gastos_vivos(url), 3L)

  # El último medio usado ya viene elegido
  abrir_formulario_gasto(app)
  expect_true(visible(app, "[data-elige-valor='tarjeta'][aria-pressed='true']"))
})

test_that("un doble toque en Guardar anota un solo gasto", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "gastos-doble-toque")
  entrar_como_mari(app)
  ir_a_gastos(app)
  abrir_formulario_gasto(app)
  llenar_gasto(app, "80", categoria = "g-2")
  app$run_js("var b = document.querySelector('#gastos-guardar'); b.click(); b.click();")
  expect_true(esperar_texto(app, ".gastos", "Q 3,625.00"))
  Sys.sleep(1)
  expect_equal(gastos_creados(url), 1L)
  expect_equal(gastos_vivos(url), 3L)
})

test_that("si la respuesta se pierde, reintentar no anota dos veces", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "gastos-reintento")
  entrar_como_mari(app)
  ir_a_gastos(app)
  abrir_formulario_gasto(app)
  llenar_gasto(app, "20", categoria = "g-4", nota = "Se pierde")
  app$click(selector = "#gastos-guardar")  # se anota, pero la respuesta es un error
  expect_true(esperar_visible(app, ".mensaje-error"))
  expect_equal(gastos_vivos(url), 3L)
  app$click(selector = "#gastos-guardar")  # mismos datos, misma clave
  expect_true(esperar_texto(app, ".gastos", "Q 3,565.00"))
  expect_equal(gastos_creados(url), 1L)
  expect_equal(gastos_vivos(url), 3L)
})

test_that("se puede editar y archivar un gasto", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "gastos-editar")
  entrar_como_mari(app)
  ir_a_gastos(app)
  expect_true(esperar_visible(app, ".gastos .lista-opciones [data-elige-valor='gx-2']"))

  app$click(selector = "[data-elige-valor='gx-2']")
  expect_true(esperar_visible(app, "#gastos-guardar"))
  expect_match(app$get_text(".gastos"), "Editar gasto")
  expect_equal(app$get_value(input = "gastos-monto"), "45.00")
  app$set_inputs("gastos-monto" = "60")
  app$click(selector = "#gastos-guardar")
  expect_true(esperar_texto(app, ".gastos", "Q 3,560.00"))

  # Archivar pide confirmación; "No" lo deja como estaba
  app$click(selector = "[data-elige-valor='gx-2']")
  expect_true(esperar_visible(app, "#gastos-archivar"))
  app$click(selector = "#gastos-archivar")
  expect_true(esperar_visible(app, "#gastos-confirmar_archivar"))
  expect_match(app$get_text(".gastos"), "¿Archivar el gasto de Q 60.00?")
  app$click(selector = "#gastos-cancelar_archivar")
  expect_true(esperar_visible(app, "#gastos-archivar"))
  expect_equal(gastos_vivos(url), 2L)

  app$click(selector = "#gastos-archivar")
  expect_true(esperar_visible(app, "#gastos-confirmar_archivar"))
  app$click(selector = "#gastos-confirmar_archivar")
  expect_true(esperar_texto(app, ".gastos", "Q 3,500.00"))
  expect_equal(gastos_vivos(url), 1L)
  expect_false(grepl("Desechables", app$get_text(".gastos")))
})

test_that("si alguien más cambió el gasto, la app avisa y no pisa nada", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "gastos-conflicto")
  entrar_como_mari(app)
  ir_a_gastos(app)
  abrir_formulario_gasto(app)
  llenar_gasto(app, "30", categoria = "g-4", nota = "Conflicto")
  app$click(selector = "#gastos-guardar")
  expect_true(esperar_texto(app, ".gastos", "Q 3,575.00"))

  app$click(selector = "[data-elige-valor='gx-n11']")  # el que acaba de anotar
  expect_true(esperar_visible(app, "#gastos-guardar"))
  app$set_inputs("gastos-monto" = "99")
  app$click(selector = "#gastos-guardar")
  expect_true(esperar_visible(app, ".mensaje-error"))
  expect_match(app$get_text("#gastos-error"), "Alguien más cambió esto")
  expect_true(visible(app, "#gastos-guardar"))  # sigue en el formulario
})

test_that("se navega entre meses y el mes siguiente no pasa del actual", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "gastos-meses")
  entrar_como_mari(app)
  ir_a_gastos(app)
  expect_true(esperar_texto(app, ".gastos", "Q 3,545.00"))

  app$click(selector = "#gastos-mes_anterior")
  anterior <- nombre_mes(mes_desplazado(mes_actual(), -1))
  expect_true(esperar_texto(app, ".gastos", anterior))
  expect_match(app$get_text(".gastos"), "No hay gastos en")
  expect_false(app$get_js("document.querySelector('#gastos-mes_siguiente').disabled"))

  app$click(selector = "#gastos-mes_siguiente")
  expect_true(esperar_texto(app, ".gastos", "Q 3,545.00"))
  expect_true(app$get_js("document.querySelector('#gastos-mes_siguiente').disabled"))
})

test_that("se puede crear una categoría desde el formulario sin perder lo escrito", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "gastos-categoria-nueva")
  entrar_como_mari(app)
  ir_a_gastos(app)
  abrir_formulario_gasto(app)
  llenar_gasto(app, "75", nota = "Tanque lleno")

  app$click(selector = "#gastos-abrir_nueva_cat")
  expect_true(esperar_visible(app, "#gastos-crear_cat"))
  app$click(selector = "#gastos-crear_cat")  # vacío
  expect_true(esperar_visible(app, ".mensaje-error"))
  app$set_inputs("gastos-nueva_cat" = "renta")  # ya existe
  app$click(selector = "#gastos-crear_cat")
  expect_true(esperar_texto(app, "#gastos-nueva_categoria", "Ya tienes una categoría"))

  app$set_inputs("gastos-nueva_cat" = "Gasolina")
  app$click(selector = "#gastos-crear_cat")
  expect_true(esperar_visible(app, "#gastos-abrir_nueva_cat"))
  expect_equal(app$get_value(input = "gastos-monto"), "75")
  expect_equal(app$get_value(input = "gastos-nota"), "Tanque lleno")
  expect_match(app$get_js("document.querySelector('#gastos-categoria').selectedOptions[0].textContent"),
               "Gasolina")

  app$click(selector = "#gastos-guardar")
  expect_true(esperar_texto(app, ".gastos", "Q 3,620.00"))
  expect_match(app$get_text(".gastos"), "Gasolina")
})

test_that("'Registrar gasto' de las acciones rápidas abre el formulario", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "gastos-accion-rapida")
  entrar_como_mari(app)
  app$click(selector = "[data-abre-hoja='hoja-acciones']")
  expect_true(esperar_visible(app, "[data-accion='registrar_gasto']"))
  app$click(selector = "[data-accion='registrar_gasto']")
  expect_true(esperar_visible(app, "#gastos-guardar"))
  expect_match(app$get_text(".gastos"), "Anotar un gasto")
  expect_false(visible(app, ".hoja.abierta"))  # la hoja se cerró

  # Volver sin guardar lleva a la lista del mes
  app$click(selector = "#gastos-atras")
  expect_true(esperar_visible(app, "#gastos-nuevo"))
})

test_that("un negocio sin gastos invita a anotar el primero y marca el checklist", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "gastos-checklist")
  crear_cuenta_y_negocio(app, tipo = "ventas_en_linea", nombre_negocio = "Tienda de Ana")
  hechos <- "document.querySelectorAll('.app-contenido .checklist__item--hecho').length"
  expect_equal(app$get_js(hechos), 0L)

  ir_a_gastos(app)
  expect_true(esperar_texto(app, ".gastos", "No hay gastos en"))
  abrir_formulario_gasto(app)
  # Una categoría variable no marca "Anota tus gastos fijos"...
  llenar_gasto(app, "50", categoria = "g-1")
  app$click(selector = "#gastos-guardar")
  expect_true(esperar_texto(app, ".gastos", "Publicidad"))
  app$click(selector = ".nav-inferior__boton[data-destino='inicio']")
  expect_equal(app$get_js(hechos), 0L)

  # ...una fija sí
  ir_a_gastos(app)
  abrir_formulario_gasto(app)
  llenar_gasto(app, "300", categoria = "g-6")
  app$click(selector = "#gastos-guardar")
  expect_true(esperar_texto(app, ".gastos", "Renta"))
  app$click(selector = ".nav-inferior__boton[data-destino='inicio']")
  expect_true(esperar_js(app, paste0(hechos, " === 1")))
})
