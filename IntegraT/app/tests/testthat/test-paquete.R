# El paquete que se sube a shinyapps.io: solo lo permitido y sin secretos (infra/desplegar_app.R).

script <- testthat::test_path("..", "..", "..", "infra", "desplegar_app.R")
dir_app <- testthat::test_path("..", "..")
testthat::skip_if_not(file.exists(script), "infra/desplegar_app.R no está disponible")
source(script, local = TRUE)

copia_de_app <- function(env = parent.frame()) {
  destino <- withr::local_tempdir(.local_envir = env)
  file.copy(file.path(dir_app, c("app.R", "config.yml", "R", "www")), destino, recursive = TRUE)
  destino
}

con_url_valida <- function(destino) {
  txt <- readLines(file.path(destino, "config.yml"), encoding = "UTF-8")
  txt <- sub("https://<DIRECCION-DE-RAILWAY>", "https://api.ejemplo.com", txt, fixed = TRUE)
  writeLines(txt, file.path(destino, "config.yml"))
}

test_that("el paquete lleva solo app.R, config.yml, R/ y www/", {
  archivos <- archivos_paquete(dir_app)
  expect_true(all(c("app.R", "config.yml", "R/api_cliente.R") %in% archivos))
  expect_true(all(grepl("^(app[.]R|config[.]yml|R/|www/)", archivos)))
  expect_false(any(grepl("tests|[.]env|renv|[.]Rproj", archivos)))
})

test_that("el código real de la app no contiene secretos", {
  archivos <- archivos_paquete(dir_app)
  problemas <- revisar_paquete(archivos, dir_app)
  # Lo único admitido antes de configurar Railway: la dirección de producción sin poner
  expect_true(all(grepl("config.yml: shinyapps", problemas)), info = paste(problemas, collapse = "\n"))
})


test_that("con una dirección HTTPS válida la revisión queda limpia", {
  destino <- copia_de_app()
  con_url_valida(destino)
  expect_equal(revisar_paquete(archivos_paquete(destino), destino), character())
})

test_that("rechaza direcciones con marcador, sin HTTPS o con barra final", {
  destino <- copia_de_app()
  for (u in c("https://<DIRECCION-DE-RAILWAY>", "http://api.ejemplo.com", "https://api.ejemplo.com/")) {
    txt <- readLines(file.path(destino, "config.yml"), encoding = "UTF-8")
    txt[length(txt)] <- sprintf("  api_base_url: \"%s\"", u)
    writeLines(txt, file.path(destino, "config.yml"))
    expect_true(any(grepl("config.yml: shinyapps", revisar_paquete(archivos_paquete(destino), destino))), info = u)
  }
})

test_that("falla si el paquete trae un .env o un secreto", {
  destino <- copia_de_app()
  con_url_valida(destino)
  writeLines("DB_PASSWORD=algo", file.path(destino, "R", ".env"))
  writeLines('clave <- "sk-ant-abcdefghijklmnop"', file.path(destino, "R", "extra.R"))
  writeLines("API_JWT_SECRET=valor-largo-de-prueba", file.path(destino, "www", "notas.txt"))
  p <- revisar_paquete(c(archivos_paquete(destino), "R/.env"), destino)
  expect_true(any(grepl("sospechoso: R/.env", p)))
  expect_true(any(grepl("secreto en R/extra.R", p)))
  expect_true(any(grepl("secreto en www/notas.txt", p)))
})
