# Instala en una carpeta SOLO los paquetes de R que usa la app Shiny (y sus dependencias), con las
# versiones exactas de renv.lock. Así la imagen no lleva lo de pruebas (shinytest2, chromote...).
#
# Uso (dentro de app/Dockerfile):  Rscript paquetes_app.R <renv.lock> <carpeta destino>
# Si la app empieza a usar un paquete nuevo con `paquete::`, agrégalo a RAICES.

RAICES <- c("shiny", "htmltools", "bslib", "bsicons", "httr2", "openssl", "curl", "jsonlite", "yaml")

args <- commandArgs(trailingOnly = TRUE)
lockfile <- args[[1]]
destino <- args[[2]]
dir.create(destino, recursive = TRUE, showWarnings = FALSE)

# renv y jsonlite solo para instalar: van a una carpeta temporal que no queda en la imagen final.
temporal <- file.path(tempdir(), "herramientas")
dir.create(temporal)
install.packages(c("renv", "jsonlite"), lib = temporal, quiet = TRUE)
.libPaths(c(temporal, .libPaths()))

paquetes <- jsonlite::read_json(lockfile)$Packages
faltan <- setdiff(RAICES, names(paquetes))
if (length(faltan)) stop("No están en renv.lock: ", paste(faltan, collapse = ", "))

# Cierre de dependencias según el campo Requirements del lockfile.
todos <- character()
pendientes <- RAICES
while (length(pendientes)) {
  p <- pendientes[[1]]
  pendientes <- pendientes[-1]
  if (p %in% todos || !p %in% names(paquetes)) next  # "R" y paquetes base no están en el lockfile
  todos <- c(todos, p)
  pendientes <- c(pendientes, unlist(paquetes[[p]]$Requirements))
}
cat(sprintf("Instalando %d paquetes: %s\n", length(todos), paste(sort(todos), collapse = " ")))

renv::restore(lockfile = lockfile, library = destino, packages = todos, prompt = FALSE,
              clean = FALSE)

# Verificación en un proceso nuevo (en este ya está cargado el jsonlite del instalador):
# cada paquete raíz carga desde `destino` y tiene la versión del lockfile.
esperadas <- vapply(RAICES, function(p) paquetes[[p]]$Version, "")
codigo <- sprintf(paste0(
  ".libPaths(c('%s', .Library)); esperadas <- c(%s); ",
  "for (p in names(esperadas)) { v <- as.character(packageVersion(p)); ",
  "if (v != esperadas[[p]]) stop(p, ': se esperaba ', esperadas[[p]], ' y quedó ', v); ",
  "suppressPackageStartupMessages(library(p, character.only = TRUE)) }; ",
  "cat('Paquetes de la app listos.\n')"),
  destino, paste(sprintf("'%s' = '%s'", names(esperadas), esperadas), collapse = ", "))
estado <- system2(file.path(R.home("bin"), "Rscript"), c("-e", shQuote(codigo)))
if (estado != 0) stop("La verificación de paquetes falló.")
