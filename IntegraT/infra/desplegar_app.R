# Despliegue de la app Shiny a shinyapps.io (piloto).
#
# Uso, desde la raíz IntegraT/:
#   Rscript infra/desplegar_app.R              # solo revisa el paquete y lo lista (no sube nada)
#   Rscript infra/desplegar_app.R --desplegar  # revisa y, si todo está bien, despliega
#
# - El paquete lleva SOLO: app.R, R/, www/ y config.yml (lista explícita, nada más).
# - Si encuentra un archivo sospechoso (.env, llaves) o un secreto dentro del texto, FALLA.
# - Las credenciales de shinyapps.io son las de tu cuenta, guardadas en tu PC con
#   rsconnect::setAccountInfo(); este script no las lee ni las escribe.

DIR_APP <- "app"
NOMBRE_APP <- "integrat"

# Archivos que entran al paquete (rutas relativas a app/).
archivos_paquete <- function(dir_app = DIR_APP) {
  incluir <- c(
    "app.R", "config.yml",
    list.files(file.path(dir_app, "R"), pattern = "\\.R$", full.names = FALSE) |>
      (\(x) file.path("R", x))(),
    list.files(file.path(dir_app, "www"), recursive = TRUE, full.names = FALSE) |>
      (\(x) file.path("www", x))()
  )
  sort(unique(incluir))
}

PATRON_NOMBRE_PELIGROSO <- paste0(
  "(^|/)\\.env|(^|/)\\.Renviron|(^|/)\\.Rprofile|(^|/)\\.Rhistory|\\.RData$|\\.rds$",
  "|\\.pem$|\\.key$|\\.p12$|id_rsa|credencial|secret"
)

PATRONES_SECRETO <- c(
  "sk-ant-[A-Za-z0-9_-]{10,}",                       # clave de Anthropic
  "-----BEGIN [A-Z ]*PRIVATE KEY-----",              # llaves privadas
  "AKIA[0-9A-Z]{16}",                                # llave de acceso de AWS
  "eyJ[A-Za-z0-9_-]{15,}\\.[A-Za-z0-9_-]{15,}\\.",   # un JWT
  "(?i)\\b(DB_PASSWORD|API_JWT_SECRET|R2_[A-Z_]*SECRET[A-Z_]*|ANTHROPIC_API_KEY)\\s*[:=]\\s*[\"']?[^\\s\"'#]+",
  "(?i)mysql://[^\\s/:@]+:[^\\s/@]+@"                # URL de base de datos con clave
)

EXT_TEXTO <- "\\.(R|r|yml|yaml|js|css|html|md|txt|json|svg)$"

# Devuelve un vector con los problemas encontrados (vacío = paquete limpio).
revisar_paquete <- function(archivos, dir_app = DIR_APP) {
  problemas <- character()
  faltan <- archivos[!file.exists(file.path(dir_app, archivos))]
  if (length(faltan)) problemas <- c(problemas, paste("Falta el archivo:", faltan))

  malos <- archivos[grepl(PATRON_NOMBRE_PELIGROSO, archivos, ignore.case = TRUE)]
  if (length(malos)) problemas <- c(problemas, paste("Nombre de archivo sospechoso:", malos))

  for (a in archivos[grepl(EXT_TEXTO, archivos) & file.exists(file.path(dir_app, archivos))]) {
    texto <- paste(readLines(file.path(dir_app, a), warn = FALSE, encoding = "UTF-8"),
                   collapse = "\n")
    for (p in PATRONES_SECRETO) {
      if (grepl(p, texto, perl = TRUE)) {
        problemas <- c(problemas, sprintf("Posible secreto en %s (patrón %s)", a, p))
      }
    }
  }

  # La dirección de producción debe estar puesta, ser HTTPS y no ser un marcador.
  cfg <- tryCatch(yaml::read_yaml(file.path(dir_app, "config.yml")), error = function(e) NULL)
  url <- cfg$shinyapps$api_base_url
  if (!is.character(url) || length(url) != 1L || grepl("[<>]", url) ||
      !grepl("^https://[^/]+", url) || grepl("/$", url)) {
    problemas <- c(problemas, paste(
      "config.yml: shinyapps -> api_base_url debe ser la dirección HTTPS de la API,",
      "sin '/' al final (infra/railway.md)"))
  }
  problemas
}

desplegar <- function(dir_app = DIR_APP, nombre = NOMBRE_APP) {
  archivos <- archivos_paquete(dir_app)
  cat(sprintf("Paquete: %d archivos\n", length(archivos)))
  problemas <- revisar_paquete(archivos, dir_app)
  if (length(problemas)) {
    cat("NO se despliega. Problemas:\n", paste0(" - ", problemas, collapse = "\n"), "\n", sep = "")
    return(invisible(FALSE))
  }
  cat("Revisión limpia: sin archivos ni secretos sospechosos.\n")
  if (!"--desplegar" %in% commandArgs(trailingOnly = TRUE)) {
    cat("Modo revisión: no se subió nada. Usa --desplegar para publicar.\n")
    return(invisible(TRUE))
  }
  rsconnect::deployApp(appDir = dir_app, appFiles = archivos, appName = nombre,
                       appTitle = "IntegraT", forceUpdate = TRUE, launch.browser = FALSE)
  invisible(TRUE)
}

if (sys.nframe() == 0L) {
  ok <- desplegar()
  if (!isTRUE(ok)) quit(status = 1L)
}
