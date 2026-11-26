test_that("ticket promedio", {
  expect_equal(ticket_promedio("130.00", 2), 65)
  expect_equal(ticket_promedio(100, 3), 33.33)
  expect_true(is.na(ticket_promedio("0.00", 0)))
  expect_true(is.na(ticket_promedio(NULL, 2)))
})

test_that("proporción de un total", {
  expect_equal(proporcion_de("40", "100"), 0.4)
  expect_equal(proporcion_de(150, 100), 1)
  expect_true(is.na(proporcion_de(10, 0)))
})
