test_that("la app se construye sin errores", {
  ruta_app <- testthat::test_path("..", "..")
  app <- shiny::shinyAppDir(ruta_app)
  expect_s3_class(app, "shiny.appobj")
})
