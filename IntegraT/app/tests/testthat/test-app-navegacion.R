# Prueba de la app en un navegador real con tamaño de celular (390×844).
test_that("la navegación inferior cambia de sección y el ➕ abre la hoja de acciones", {
  skip_if_not_installed("shinytest2")
  skip_if(is.null(chromote::find_chrome()), "No hay Chrome/Edge disponible")
  withr::local_envvar(
    API_BASE_URL = "http://127.0.0.1:9",  # sin API: la app debe seguir funcionando
    NOT_CRAN = "true"                     # shinytest2 se salta la prueba si no está definido
  )

  app <- shinytest2::AppDriver$new(
    testthat::test_path("..", ".."),
    name = "navegacion", width = 390, height = 844, load_timeout = 30000
  )
  on.exit(app$stop(), add = TRUE)

  visible <- function(selector) {
    app$get_js(sprintf(
      "(function(){var e=document.querySelector(\"%s\"); return !!e && e.offsetParent !== null;})()",
      selector
    ))
  }

  # Inicio por defecto
  expect_true(visible("#inicio-ir_productos"))

  # Ir a Vender
  app$click(selector = ".nav-inferior__boton[data-destino='vender']")
  app$wait_for_idle()
  expect_true(visible("#vender-agregar"))
  expect_equal(
    app$get_js("document.querySelector(\"[data-destino='vender']\").getAttribute('aria-current')"),
    "page"
  )

  # Ir a Más
  app$click(selector = ".nav-inferior__boton[data-destino='mas']")
  app$wait_for_idle()
  expect_true(visible("[data-tamano-texto='grande']"))

  # Tamaño de letra grande
  app$click(selector = "[data-tamano-texto='grande']")
  expect_true(app$get_js("document.documentElement.classList.contains('texto-grande')"))

  # El botón ➕ abre la hoja de acciones
  app$click(selector = "[data-abre-hoja='hoja-acciones']")
  expect_true(app$get_js("document.getElementById('hoja-acciones').classList.contains('abierta')"))

  # Sin API: estado amable
  expect_match(app$get_text("#estado_conexion"), "Sin conexión")

  # Sin desbordamiento horizontal en el celular
  expect_true(app$get_js("document.documentElement.scrollWidth <= window.innerWidth"))
})
