# Carga las fórmulas de `integrat.analitica` (punto de equilibrio, meta del mes...) sin instalar el
# paquete: cada fórmula tiene un solo dueño (PROPUESTA_ARQUITECTURA.md §3), y ese dueño es
# analitica/R. En desarrollo y pruebas se leen de la carpeta hermana `../analitica/R`; en el paquete
# que se sube a shinyapps.io, `infra/desplegar_app.R` las copia a `analitica/`.

ubicar_analitica <- function() {
  candidatos <- c("analitica", file.path("..", "analitica", "R"),
                  file.path("..", "..", "..", "analitica", "R"), file.path("analitica", "R"))
  for (dir in candidatos) {
    if (file.exists(file.path(dir, "meta.R"))) return(dir)
  }
  stop("No encontré las fórmulas de integrat.analitica (analitica/R).")
}

for (archivo_analitica in list.files(ubicar_analitica(), pattern = "\\.R$", full.names = TRUE)) {
  sys.source(archivo_analitica, envir = environment(), keep.source = FALSE)
}
rm(archivo_analitica)
