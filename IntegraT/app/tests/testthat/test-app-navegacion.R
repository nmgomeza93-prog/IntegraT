# Prueba de la app en un navegador real con tamaño de celular (390×844).
# Se entra con una cuenta de la API falsa para ver la navegación inferior.
test_that("la navegación inferior cambia de sección y el ➕ abre la hoja de acciones", {
  skip_if_not_installed("shinytest2")
  skip_if(is.null(chromote::find_chrome()), "No hay Chrome/Edge disponible")

  url <- iniciar_api_falsa()
  app <- abrir_app(url, "navegacion")

  # Antes de entrar no hay navegación inferior
  expect_false(visible(app, ".nav-inferior"))

  app$click(selector = "#bienvenida-entrar")
  app$set_inputs("login-correo" = "mari@prueba.com", "login-clave" = "clave-correcta-1")
  app$click(selector = "#login-entrar")
  expect_true(esperar_visible(app, ".nav-inferior"))

  # Inicio por defecto
  expect_true(visible(app, "#inicio-ir_productos"))

  # Ir a Vender
  app$click(selector = ".nav-inferior__boton[data-destino='vender']")
  expect_true(esperar_visible(app, "#vender-agregar"))
  expect_equal(
    app$get_js("document.querySelector(\"[data-destino='vender']\").getAttribute('aria-current')"),
    "page"
  )

  # Ir a Más
  app$click(selector = ".nav-inferior__boton[data-destino='mas']")
  expect_true(esperar_visible(app, "[data-tamano-texto='grande']"))

  # Tamaño de letra grande
  app$click(selector = "[data-tamano-texto='grande']")
  expect_true(app$get_js("document.documentElement.classList.contains('texto-grande')"))

  # El botón ➕ abre la hoja de acciones
  app$click(selector = "[data-abre-hoja='hoja-acciones']")
  expect_true(app$get_js("document.getElementById('hoja-acciones').classList.contains('abierta')"))

  # Con la API disponible, el estado dice Conectado
  expect_match(app$get_text("#estado_conexion"), "Conectado")

  # Sin desbordamiento horizontal en el celular
  expect_true(app$get_js("document.documentElement.scrollWidth <= window.innerWidth"))
})
