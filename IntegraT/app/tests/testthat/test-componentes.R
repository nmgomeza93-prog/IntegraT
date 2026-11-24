html <- function(x) as.character(htmltools::renderTags(x)$html)

test_that("el botón primario es un action-button con su texto", {
  h <- html(boton_primario("guardar", "Cobrar", "cash"))
  expect_match(h, 'class="boton-primario action-button"', fixed = TRUE)
  expect_match(h, 'id="guardar"', fixed = TRUE)
  expect_match(h, "Cobrar", fixed = TRUE)
})

test_that("los estados combinan color, icono y palabra", {
  for (tipo in c("bien", "atencion", "alerta", "neutro")) {
    h <- html(etiqueta_estado("Texto", tipo))
    expect_match(h, paste0("estado--", tipo), fixed = TRUE)
    expect_match(h, "<svg", fixed = TRUE)
    expect_match(h, "Texto", fixed = TRUE)
  }
})

test_that("la tarjeta de número muestra etiqueta, valor y contexto", {
  h <- html(tarjeta_numero("Hoy", formato_dinero(1245), "Vendiste Q2,980"))
  expect_match(h, "Q 1,245.00", fixed = TRUE)
  expect_match(h, 'aria-label="Hoy"', fixed = TRUE)
  expect_match(h, "Vendiste Q2,980", fixed = TRUE)
})

test_that("la hoja inferior es un diálogo accesible y oculto al inicio", {
  h <- html(hoja_inferior("h1", "Título", htmltools::tags$p("x")))
  expect_match(h, 'role="dialog"', fixed = TRUE)
  expect_match(h, 'aria-hidden="true"', fixed = TRUE)
  expect_match(h, 'aria-labelledby="h1-titulo"', fixed = TRUE)
})

test_that("la navegación inferior tiene 5 elementos y usa el vocabulario del negocio", {
  vocab <- vocabulario_defecto()
  vocab$catalogo <- "Menú"
  h <- html(nav_inferior(vocab))
  expect_equal(lengths(regmatches(h, gregexpr("<li>", h))), 5)
  expect_match(h, "Menú", fixed = TRUE)
  expect_match(h, 'aria-current="page"', fixed = TRUE)
})

test_that("formato de dinero y fecha en español", {
  expect_equal(formato_dinero(0), "Q 0.00")
  expect_equal(formato_dinero(1234567.891), "Q 1,234,567.89")
  expect_equal(fecha_larga_es(as.POSIXct("2026-11-24 12:00", tz = "UTC")), "Martes 24 de noviembre")
})

test_that("sin API la app muestra un estado amable, no un error", {
  withr::local_envvar(API_BASE_URL = "http://127.0.0.1:9")
  salud <- api_salud(tiempo_max = 1)
  expect_false(salud$api)
  expect_match(html(estado_conexion_ui(salud)), "Sin conexión", fixed = TRUE)
})
