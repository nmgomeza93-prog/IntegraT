test_that("la meta usa el margen real del mes cuando hay ventas con costo", {
  m <- meta_del_mes("3500.00", "10000.00", "4000.00", "0.35")
  expect_equal(m$estado, "ok")
  expect_equal(m$margen, 0.6)
  expect_false(m$margen_estimado)
  expect_equal(m$meta, 5833.33)
  expect_equal(m$avance, 1)  # ya la pasó
  expect_equal(m$falta, 0)
})

test_that("sin ventas con costo usa el margen objetivo y la marca estimada", {
  m <- meta_del_mes(3500, 1000, 0, 0.35)
  expect_true(m$margen_estimado)
  expect_equal(m$meta, 10000)
  expect_equal(m$avance, 0.1)
  expect_equal(m$falta, 9000)
  expect_true(meta_del_mes(3500, 0, 0)$margen_estimado)
})

test_that("sin gastos fijos o sin margen no hay meta", {
  expect_equal(meta_del_mes("0.00", 500, 100)$estado, "sin_fijos")
  expect_true(is.na(meta_del_mes(0, 500, 100)$meta))
  expect_equal(meta_del_mes(1000, 500, 500)$estado, "sin_margen")   # costo = ventas
  expect_equal(meta_del_mes(1000, 500, 700)$estado, "sin_margen")   # vende con pérdida
})

test_that("tolera textos vacíos o raros como cero", {
  expect_equal(meta_del_mes(NULL, "", "abc")$estado, "sin_fijos")
})
