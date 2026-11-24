# Carga el código de app/R para las pruebas unitarias de componentes.
ruta_r <- testthat::test_path("..", "..", "R")
for (archivo in list.files(ruta_r, pattern = "\\.R$", full.names = TRUE)) {
  source(archivo, local = FALSE, encoding = "UTF-8")
}
