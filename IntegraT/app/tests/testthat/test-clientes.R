# Tus clientes y "¿A quién le vendes?" (docs/ANALISIS_INVENTARIO_Y_CLIENTES.md, C2), contra la API
# falsa. Las validaciones de fondo (NIT, CUI, correo) son de la API: aquí solo se muestran sus mensajes.

salta_sin_navegador <- function() {
  testthat::skip_if_not_installed("shinytest2")
  testthat::skip_if(is.null(chromote::find_chrome()), "No hay Chrome/Edge disponible")
}

# --- Funciones puras -------------------------------------------------------------------

test_that("el teléfono y el NIT se muestran como se escriben", {
  expect_equal(telefono_visible("+50255551234"), "5555 1234")
  expect_equal(telefono_visible("+13055550100"), "+13055550100")
  expect_null(telefono_visible(NULL))
  expect_equal(texto_fiscal("NIT", "12345679"), "NIT 1234567-9")
  expect_equal(texto_fiscal("CUI", "1234567890101"), "CUI 1234567890101")
  expect_equal(texto_fiscal("CF", NULL), "Consumidor final")
  expect_equal(valor_campo_visible("si_no", TRUE), "Sí")
  expect_equal(valor_campo_visible("fecha", "1990-05-17"), "17 may 1990")
  expect_null(valor_campo_visible("texto", NULL))
})

test_that("el formulario manda null en lo vacío y no manda NIT a un Consumidor final", {
  campos <- list(list(id = "c1", tipo = "texto"), list(id = "c2", tipo = "si_no"))
  cuerpo <- cuerpo_cliente(list(nombre = " María ", telefono = "", correo = "m@x.com",
                                tipo_id_fiscal = "CF", id_fiscal = "123",
                                campos = list("@maria", TRUE)), campos)
  expect_equal(cuerpo$nombre, "María")
  expect_null(cuerpo$telefono)
  expect_null(cuerpo$id_fiscal)
  expect_equal(cuerpo$datos, list(c1 = "@maria", c2 = TRUE))
  # Vaciar un campo propio manda null (para borrarlo en la API), no lo omite.
  vaciado <- cuerpo_cliente(list(nombre = "Ana", campos = list("", FALSE)), campos)
  expect_match(jsonlite::toJSON(vaciado, auto_unbox = TRUE, null = "null"), '"c1":null',
               fixed = TRUE)
  json <- jsonlite::toJSON(cuerpo, auto_unbox = TRUE, null = "null")
  expect_match(json, '"telefono":null')
  # Sin campos propios, los datos van como {} (la API espera un objeto, no una lista).
  sin_campos <- jsonlite::toJSON(cuerpo_cliente(list(nombre = "Ana"), list()), auto_unbox = TRUE)
  expect_match(sin_campos, '"datos":{}', fixed = TRUE)
})

test_that("al archivar se explica qué pasa con sus ventas", {
  expect_no_match(texto_archivar("Ana", 0L, 0), "ventas no se borran")
  texto <- texto_archivar("María", 3L, 450)
  expect_match(texto, "María tiene 3 compras por Q 450.00")
  expect_match(texto, "no se borran ni cambian")
  expect_match(texto, "Ver archivados")
})

# --- Flujo en el navegador -------------------------------------------------------------

test_that("agregar un cliente, avisar si se repite y venderle", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "clientes")
  entrar_como_mari(app)

  app$click(selector = ".nav-inferior__boton[data-destino='mas']")
  esperar_visible(app, "#mas-clientes")
  app$click(selector = "#mas-clientes")
  expect_true(esperar_texto(app, ".clientes", "Aún no tienes clientes"))
  app$click(selector = "#clientes-agregar")
  esperar_visible(app, "#clientes-guardar")
  app$set_inputs("clientes-nombre" = "María López", "clientes-telefono" = "5555-1234")
  app$click(selector = "#clientes-guardar")
  expect_true(esperar_texto(app, ".clientes", "Te ha comprado"))
  expect_match(app$get_text(".clientes"), "5555 1234")
  expect_equal(contadores_api(url)$clientes, 1L)

  # El mismo teléfono: avisa y deja guardarlo de todos modos.
  app$click(selector = "#clientes-volver_lista")
  esperar_visible(app, "#clientes-agregar")
  app$click(selector = "#clientes-agregar")
  esperar_visible(app, "#clientes-guardar")
  app$set_inputs("clientes-nombre" = "Mamá de María", "clientes-telefono" = "55551234")
  app$click(selector = "#clientes-guardar")
  expect_true(esperar_texto(app, ".clientes", "Ya tienes a María López con ese teléfono"))
  esperar_visible(app, "#clientes-guardar_igual")
  app$click(selector = "#clientes-guardar_igual")
  expect_true(esperar_texto(app, ".clientes", "Te ha comprado"))
  expect_equal(contadores_api(url)$clientes, 2L)

  # Vender a María: se busca al cobrar y la venta dice a quién.
  app$click(selector = ".nav-inferior__boton[data-destino='vender']")
  esperar_visible(app, ".vender [data-elige-valor='i-1']")
  app$click(selector = ".vender [data-elige-valor='i-1']")
  expect_true(esperar_texto(app, ".vender", "×1"))
  app$click(selector = "#vender-ir_cobrar")
  expect_true(esperar_texto(app, ".vender", "Consumidor final"))
  app$click(selector = "#vender-elegir_cliente")
  esperar_visible(app, "#vender-buscar_cliente")
  app$set_inputs("vender-buscar_cliente" = "maria lo")
  expect_true(esperar_visible(app, ".vender [data-elige-valor='cl-1']"))
  app$click(selector = ".vender [data-elige-valor='cl-1']")
  esperar_visible(app, "#vender-confirmar")
  expect_match(app$get_text(".vender"), "María López")
  app$click(selector = "#vender-confirmar")
  expect_true(esperar_texto(app, ".vender", "· María López"))
  expect_equal(contadores_api(url)$cliente_ultima_venta, "cl-1")
})

test_that("crear un cliente al cobrar, con nombre y teléfono, y la siguiente venta vuelve a Consumidor final", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "cliente-al-cobrar")
  entrar_como_mari(app)

  vender_uno <- function() {
    app$click(selector = ".nav-inferior__boton[data-destino='vender']")
    esperar_visible(app, ".vender [data-elige-valor='i-1']")
    app$click(selector = ".vender [data-elige-valor='i-1']")
    esperar_texto(app, ".vender", "×1")
    app$click(selector = "#vender-ir_cobrar")
    esperar_visible(app, "#vender-elegir_cliente")
  }
  vender_uno()
  app$click(selector = "#vender-elegir_cliente")
  esperar_visible(app, "#vender-nuevo_cliente")
  app$click(selector = "#vender-nuevo_cliente")
  esperar_visible(app, "#vender-guardar_cliente")
  app$set_inputs("vender-cliente_nombre" = "Pedro", "vender-cliente_telefono" = "1234")
  app$click(selector = "#vender-guardar_cliente")
  expect_true(esperar_texto(app, ".vender", "8 dígitos"))
  app$set_inputs("vender-cliente_telefono" = "4444 1234")
  app$click(selector = "#vender-guardar_cliente")
  esperar_visible(app, "#vender-confirmar")
  expect_match(app$get_text(".vender"), "Pedro")
  app$click(selector = "#vender-confirmar")
  expect_true(esperar_texto(app, ".vender", "· Pedro"))
  expect_equal(contadores_api(url)$cliente_ultima_venta, "cl-1")

  app$click(selector = "#vender-otra")
  vender_uno()
  expect_match(app$get_text(".vender"), "Consumidor final")
})

test_that("archivar a un cliente con ventas no pierde nada, se recupera, y la app se pone al día", {
  salta_sin_navegador()
  url <- iniciar_api_falsa()
  app <- abrir_app(url, "clientes-archivar")
  entrar_como_mari(app)

  # Agregar a María (sin campos propios: antes fallaba con "Revisa los datos").
  app$click(selector = ".nav-inferior__boton[data-destino='mas']")
  esperar_visible(app, "#mas-clientes")
  app$click(selector = "#mas-clientes")
  esperar_visible(app, "#clientes-agregar")
  app$click(selector = "#clientes-agregar")
  esperar_visible(app, "#clientes-guardar")
  app$set_inputs("clientes-nombre" = "M")
  app$click(selector = "#clientes-guardar")
  expect_true(esperar_texto(app, ".clientes", "Escribe el nombre"))
  app$set_inputs("clientes-nombre" = "María López")
  app$click(selector = "#clientes-guardar")
  expect_true(esperar_texto(app, ".clientes", "Todavía no le has vendido"))

  # Venderle en Vender; al volver a Clientes, su ficha ya muestra la compra (sin salir ni entrar).
  app$click(selector = ".nav-inferior__boton[data-destino='vender']")
  esperar_visible(app, ".vender [data-elige-valor='i-1']")
  app$click(selector = ".vender [data-elige-valor='i-1']")
  esperar_texto(app, ".vender", "×1")
  app$click(selector = "#vender-ir_cobrar")
  esperar_visible(app, "#vender-elegir_cliente")
  app$click(selector = "#vender-elegir_cliente")
  expect_true(esperar_visible(app, ".vender [data-elige-valor='cl-1']"))
  app$click(selector = ".vender [data-elige-valor='cl-1']")
  esperar_visible(app, "#vender-confirmar")
  app$click(selector = "#vender-confirmar")
  expect_true(esperar_texto(app, ".vender", "· María López"))
  app$click(selector = ".nav-inferior__boton[data-destino='mas']")
  esperar_visible(app, "#mas-clientes")
  app$click(selector = "#mas-clientes")
  expect_true(esperar_texto(app, ".clientes", "1 compra"))

  # Archivar: explica que sus ventas no se pierden; queda marcada y se recupera.
  app$click(selector = "#clientes-archivar")
  expect_true(esperar_texto(app, ".clientes", "no se borran ni cambian"))
  app$click(selector = "#clientes-confirmar_archivar")
  expect_true(esperar_texto(app, ".clientes", "Archivado"))
  expect_match(app$get_text(".clientes"), "1 compra")
  expect_equal(contadores_api(url)$clientes, 0L)
  app$click(selector = "#clientes-recuperar")
  expect_true(esperar_visible(app, "#clientes-editar"))
  expect_equal(contadores_api(url)$clientes, 1L)
})
