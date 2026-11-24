test_that("el paquete reporta su versión", {
  expect_match(version_analitica(), "^\\d+\\.\\d+\\.\\d+$")
})
