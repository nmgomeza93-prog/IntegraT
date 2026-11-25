# Catálogo (Productos / Menú): funciones puras y flujos en un navegador real a 390×844,
# contra la API falsa.

salta_sin_navegador <- function() {
  testthat::skip_if_not_installed("shinytest2")
  testthat::skip_if(is.null(chromote::find_chrome()), "No hay Chrome/Edge disponible")
}

ir_a_catalogo <- function(app) {
  app$click(selector = ".nav-inferior__boton[data-destino='productos']")
  esperar_visible(app, "#productos-nuevo")  # el catálogo ya cargó (vacío o con ítems)
}

# --- Funciones puras -------------------------------------------------------------------

test_that("normalizar_precio acepta precios normales y rechaza lo demás", {
  expect_equal(normalizar_precio("45"), "45")
  expect_equal(normalizar_precio("45.5"), "45.5")
  expect_equal(normalizar_precio(" Q 45,50 "), "45.50")
  expect_equal(normalizar_precio("0"), "0")
  for (malo in c("", "abc", "-5", "45.999", "1.200,50", "4 5 .", NA_character_)) {
    expect_null(normalizar_precio(malo))
  }
  expect_null(normalizar_precio(NULL))
})

test_that("sin_tildes y agrupar_items", {
  expect_equal(sin_tildes("Pepián CAFÉ Piña"), "pepian cafe pina")
  cats <- list(list(id = "c1", nombre = "Bebidas"), list(id = "c2", nombre = "Postres"))
  items <- list(
    list(id = "i1", nombre = "Flan", categoria_id = "c2"),
    list(id = "i2", nombre = "Café", categoria_id = "c1"),
    list(id = "i3", nombre = "Pepián", categoria_id = NULL)
  )
  g <- agrupar_items(items, cats)
  expect_equal(vapply(g, function(x) x$titulo, ""), c("Bebidas", "Postres", "Sin categoría"))
  expect_equal(g[[2]]$items[[1]]$nombre, "Flan")
  # Sin categorías en el negocio: una sola lista, sin título de grupo
  g2 <- agrupar_items(lapply(items, function(i) list(id = i$id, nombre = i$nombre, categoria_id = NULL)), list())
  expect_equal(vapply(g2, function(x) x$titulo, ""), "")
  expect_length(g2[[1]]$items, 3)
})

# --- Flujos en el navegador ------------------------------------------------------------

test_that("un restaurante nuevo ve el menú vacío y agrega su primer platillo", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "catalogo-primer-platillo")
  crear_cuenta_y_negocio(app)

  expect_true(ir_a_catalogo(app))
  expect_true(esperar_texto(app, ".catalogo", "Aún no tienes platillos"))
  app$click(selector = "#productos-nuevo")
  expect_true(esperar_visible(app, "#productos-guardar"))
  expect_match(app$get_text(".catalogo"), "Nuevo platillo")
  expect_match(app$get_text(".catalogo"), "Nombre del platillo")

  # Nombre vacío y precio inválido: errores amables, se queda en el formulario
  app$click(selector = "#productos-guardar")
  expect_true(esperar_visible(app, ".mensaje-error"))
  expect_match(app$get_text("#productos-error"), "Escribe el nombre del platillo")
  llenar_item(app, "Pepián", "mucho")
  app$click(selector = "#productos-guardar")
  Sys.sleep(0.5)
  expect_match(app$get_text("#productos-error"), "Escribe el precio con números")
  expect_equal(items_vivos(url), 0L)

  # Datos buenos: guarda y vuelve a la lista, agrupado por categoría
  llenar_item(app, "Pepián", "45", categoria = "c-2")
  app$click(selector = "#productos-guardar")
  expect_true(esperar_texto(app, ".catalogo", "Q 45.00"))
  expect_equal(app$get_text(".catalogo__grupo"), "Platos fuertes")
  expect_match(app$get_text(".catalogo .lista-opciones"), "Pepián")
  expect_match(app$get_text(".catalogo .lista-opciones"), "Q 45.00")
  expect_equal(items_vivos(url), 1L)
  expect_true(app$get_js("document.documentElement.scrollWidth <= window.innerWidth"))
})

test_that("un doble toque en Guardar crea un solo ítem", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "catalogo-doble-toque")
  crear_cuenta_y_negocio(app)
  ir_a_catalogo(app)
  app$click(selector = "#productos-nuevo")
  expect_true(esperar_visible(app, "#productos-guardar"))
  llenar_item(app, "Tamales", "12")
  app$run_js("var b = document.querySelector('#productos-guardar'); b.click(); b.click();")
  expect_true(esperar_visible(app, "#productos-nuevo"))
  Sys.sleep(1)
  expect_equal(items_creados(url), 1L)
  expect_equal(items_vivos(url), 1L)
})

test_that("si la respuesta se pierde, reintentar no duplica el ítem", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "catalogo-reintento")
  crear_cuenta_y_negocio(app)
  ir_a_catalogo(app)
  app$click(selector = "#productos-nuevo")
  expect_true(esperar_visible(app, "#productos-guardar"))
  llenar_item(app, "Falla una vez", "20")

  app$click(selector = "#productos-guardar")  # se crea, pero la respuesta es un error
  expect_true(esperar_visible(app, ".mensaje-error"))
  expect_equal(items_vivos(url), 1L)
  app$click(selector = "#productos-guardar")  # mismos datos, misma clave
  expect_true(esperar_texto(app, ".catalogo", "Falla una vez"))
  expect_equal(items_vivos(url), 1L)
  expect_match(app$get_text(".catalogo .lista-opciones"), "Falla una vez")
})

test_that("se puede ver, editar y archivar un platillo existente", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "catalogo-editar")
  entrar_como_mari(app)

  expect_true(ir_a_catalogo(app))
  expect_true(esperar_visible(app, ".catalogo .lista-opciones"))
  expect_equal(app$get_js("Array.from(document.querySelectorAll('.catalogo__grupo')).map(e => e.textContent)"),
               list("Platos fuertes", "Bebidas"))

  # Abrir, cambiar el precio y guardar
  app$click(selector = "[data-elige-valor='i-1']")
  expect_true(esperar_visible(app, "#productos-guardar"))
  expect_match(app$get_text(".catalogo"), "Editar platillo")
  expect_equal(app$get_value(input = "productos-nombre"), "Pepián")
  expect_equal(app$get_value(input = "productos-precio"), "45.00")
  app$set_inputs("productos-precio" = "50")
  app$click(selector = "#productos-guardar")
  expect_true(esperar_texto(app, ".catalogo", "Q 50.00"))

  # Archivar pide confirmación; "No" lo deja como estaba
  app$click(selector = "[data-elige-valor='i-1']")
  expect_true(esperar_visible(app, "#productos-archivar"))
  app$click(selector = "#productos-archivar")
  expect_true(esperar_visible(app, "#productos-confirmar_archivar"))
  expect_match(app$get_text(".catalogo"), "¿Archivar «Pepián»?")
  app$click(selector = "#productos-cancelar_archivar")
  expect_true(esperar_visible(app, "#productos-archivar"))
  expect_equal(items_vivos(url), 2L)

  app$click(selector = "#productos-archivar")
  expect_true(esperar_visible(app, "#productos-confirmar_archivar"))
  app$click(selector = "#productos-confirmar_archivar")
  expect_true(esperar_texto(app, ".catalogo", "Horchata"))
  expect_equal(items_vivos(url), 1L)
  expect_false(grepl("Pepián", app$get_text(".catalogo")))
  expect_match(app$get_text(".catalogo .lista-opciones"), "Horchata")
})

test_that("si alguien más cambió el ítem, la app avisa y no pisa nada", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "catalogo-conflicto")
  crear_cuenta_y_negocio(app)
  ir_a_catalogo(app)
  app$click(selector = "#productos-nuevo")
  expect_true(esperar_visible(app, "#productos-guardar"))
  llenar_item(app, "Conflicto", "30")
  app$click(selector = "#productos-guardar")
  expect_true(esperar_visible(app, ".catalogo .lista-opciones"))

  app$click(selector = ".catalogo .lista-opciones [data-elige-input]")
  expect_true(esperar_visible(app, "#productos-guardar"))
  app$set_inputs("productos-precio" = "99")
  app$click(selector = "#productos-guardar")
  expect_true(esperar_visible(app, ".mensaje-error"))
  expect_match(app$get_text("#productos-error"), "Alguien más cambió esto")
  expect_true(visible(app, "#productos-guardar"))  # sigue en el formulario
})

test_that("con 8 o más ítems aparece el buscador y filtra sin importar tildes", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "catalogo-buscar")
  crear_cuenta_y_negocio(app, tipo = "ventas_en_linea", nombre_negocio = "Tienda de Ana")
  ir_a_catalogo(app)
  expect_true(esperar_texto(app, ".catalogo", "Aún no tienes productos"))

  nombres <- c("Camisa", "Pantalón", "Blusa", "Falda", "Gorra", "Bufanda", "Calcetines", "Cinturón")
  for (n in nombres) {
    app$click(selector = "#productos-nuevo")
    expect_true(esperar_visible(app, "#productos-guardar"))
    expect_false(visible(app, "#productos-categoria"))  # la tienda aún no tiene categorías
    llenar_item(app, n, "100")
    app$click(selector = "#productos-guardar")
    expect_true(esperar_texto(app, ".catalogo", n))
  }
  expect_true(esperar_visible(app, "#productos-buscar"))
  expect_equal(app$get_js("document.querySelectorAll('.catalogo .lista-opciones__item').length"), 8L)
  expect_equal(app$get_js("document.querySelectorAll('.catalogo__grupo').length"), 0L)  # sin categorías

  app$set_inputs("productos-buscar" = "PANTALON")
  expect_true(esperar_js(app, "document.querySelectorAll('.catalogo .lista-opciones__item').length === 1"))
  expect_match(app$get_text(".catalogo .lista-opciones"), "Pantalón")
  app$set_inputs("productos-buscar" = "zzz")
  expect_true(esperar_texto(app, ".catalogo", "No encontramos nada con ese nombre"))
})

test_that("se puede crear una categoría desde el formulario sin perder lo escrito", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "catalogo-categoria-nueva")
  crear_cuenta_y_negocio(app)
  ir_a_catalogo(app)
  app$click(selector = "#productos-nuevo")
  expect_true(esperar_visible(app, "#productos-guardar"))
  llenar_item(app, "Caldo de res", "35")

  app$click(selector = "#productos-abrir_nueva_cat")
  expect_true(esperar_visible(app, "#productos-crear_cat"))
  app$click(selector = "#productos-crear_cat")  # vacío
  expect_true(esperar_visible(app, ".mensaje-error"))
  app$set_inputs("productos-nueva_cat" = "bebidas")  # ya existe (sin importar mayúsculas)
  app$click(selector = "#productos-crear_cat")
  expect_true(esperar_texto(app, "#productos-nueva_categoria", "Ya tienes una categoría"))

  app$set_inputs("productos-nueva_cat" = "Sopas")
  app$click(selector = "#productos-crear_cat")
  # El formulario se recarga: la categoría nueva queda elegida y lo escrito sigue ahí
  expect_true(esperar_visible(app, "#productos-abrir_nueva_cat"))
  expect_equal(app$get_value(input = "productos-nombre"), "Caldo de res")
  expect_equal(app$get_value(input = "productos-precio"), "35")
  expect_match(app$get_js("document.querySelector('#productos-categoria').selectedOptions[0].textContent"),
               "Sopas")

  app$click(selector = "#productos-guardar")
  expect_true(esperar_texto(app, ".catalogo", "Caldo de res"))
  expect_equal(app$get_js("Array.from(document.querySelectorAll('.catalogo__grupo')).map(e => e.textContent)"),
               list("Sopas"))
})

test_that("una tienda sin categorías puede crear la primera desde el formulario", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "catalogo-primera-categoria")
  crear_cuenta_y_negocio(app, tipo = "ventas_en_linea", nombre_negocio = "Tienda de Ana")
  ir_a_catalogo(app)
  app$click(selector = "#productos-nuevo")
  expect_true(esperar_visible(app, "#productos-guardar"))
  expect_false(visible(app, "#productos-categoria"))
  app$click(selector = "#productos-abrir_nueva_cat")
  expect_true(esperar_visible(app, "#productos-crear_cat"))
  app$set_inputs("productos-nueva_cat" = "Ropa")
  app$click(selector = "#productos-crear_cat")
  expect_true(esperar_visible(app, "#productos-categoria"))  # ahora sí hay selector
  expect_match(app$get_js("document.querySelector('#productos-categoria').selectedOptions[0].textContent"),
               "Ropa")
})

test_that("el checklist del Inicio se marca solo al agregar el primer producto", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "catalogo-checklist")
  crear_cuenta_y_negocio(app, tipo = "ventas_en_linea", nombre_negocio = "Tienda de Ana")

  hechos <- "document.querySelectorAll('.app-contenido .checklist__item--hecho').length"
  # El Inicio pide también "Tu mes" a la API: se espera a que el consejo esté dibujado.
  expect_true(esperar_texto(app, ".tarjeta-consejo", "Agrega tu primer producto"))
  expect_equal(app$get_js(hechos), 0L)
  expect_match(app$get_text("#inicio-hacer_paso"), "Agregar un producto")

  app$click(selector = "#inicio-hacer_paso")  # lleva directo al catálogo
  expect_true(esperar_visible(app, "#productos-nuevo"))
  app$click(selector = "#productos-nuevo")
  expect_true(esperar_visible(app, "#productos-guardar"))
  llenar_item(app, "Camisa", "99")
  app$click(selector = "#productos-guardar")
  expect_true(esperar_texto(app, ".catalogo", "Camisa"))

  app$click(selector = ".nav-inferior__boton[data-destino='inicio']")
  expect_true(esperar_js(app, paste0(hechos, " === 1")))
  expect_true(esperar_texto(app, ".tarjeta-consejo", "Haz tu primera venta"))  # el siguiente paso
  expect_match(app$get_text("#inicio-hacer_paso"), "Ir a vender")
})

test_that("el checklist del restaurante pide 5 platillos y avisa hasta completarlos", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "catalogo-checklist-restaurante")
  crear_cuenta_y_negocio(app)
  hechos <- "document.querySelectorAll('.app-contenido .checklist__item--hecho').length"

  ir_a_catalogo(app)
  for (n in c("Pepián", "Caldo", "Tamales", "Frijoles")) {
    app$click(selector = "#productos-nuevo")
    expect_true(esperar_visible(app, "#productos-guardar"))
    llenar_item(app, n, "20")
    app$click(selector = "#productos-guardar")
    expect_true(esperar_texto(app, ".catalogo", n))
  }
  app$click(selector = ".nav-inferior__boton[data-destino='inicio']")
  expect_true(esperar_texto(app, ".tarjeta-consejo", "5 platillos"))
  expect_equal(app$get_js(hechos), 0L)  # 4 de 5: todavía no

  ir_a_catalogo(app)
  app$click(selector = "#productos-nuevo")
  expect_true(esperar_visible(app, "#productos-guardar"))
  llenar_item(app, "Chuchitos", "8")
  app$click(selector = "#productos-guardar")
  expect_true(esperar_texto(app, ".catalogo", "Chuchitos"))
  app$click(selector = ".nav-inferior__boton[data-destino='inicio']")
  expect_true(esperar_js(app, paste0(hechos, " >= 1")))
  # El siguiente paso pendiente pasa a ser el de la receta o la venta
  expect_true(esperar_js(app, paste0(
    "(document.querySelector('.tarjeta-consejo') || {}).textContent !== undefined && ",
    "!document.querySelector('.tarjeta-consejo').textContent.includes('5 platillos')")))
})
