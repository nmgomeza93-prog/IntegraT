# Imagen de la app Shiny de IntegraT (local con Docker Compose y Azure Container Apps).
# Construir (desde la raíz IntegraT/):
#   producción:  docker build -t integrat-app -f app/Dockerfile .
#   desarrollo:  docker build -t integrat-app:dev --target dev -f app/Dockerfile .
# La app no lleva secretos: su única configuración es API_BASE_URL (variable de entorno).

# ---------- paquetes: compila/descarga los paquetes de R de la app (versiones de renv.lock) ----------
FROM rocker/r-ver:4.3.0 AS paquetes
RUN apt-get update \
    && apt-get install -y --no-install-recommends libcurl4-openssl-dev libssl-dev \
    && rm -rf /var/lib/apt/lists/*
# Binarios de Linux de Posit Package Manager (instala en minutos, no compila).
ENV RENV_CONFIG_REPOS_OVERRIDE=https://packagemanager.posit.co/cran/__linux__/jammy/latest \
    RENV_CONFIG_CACHE_ENABLED=FALSE
WORKDIR /build
COPY renv.lock infra/docker/paquetes_app.R ./
RUN Rscript paquetes_app.R renv.lock /opt/integrat/library

# ---------- base: R, librerías del sistema de ejecución y los paquetes ya instalados ----------
FROM rocker/r-ver:4.3.0 AS base
# libuv1: la pide el paquete fs. curl: para el chequeo de salud.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl libuv1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 integrat
COPY --from=paquetes /opt/integrat/library /opt/integrat/library
ENV R_LIBS=/opt/integrat/library \
    API_BASE_URL=http://127.0.0.1:8000
# Si falta una librería del sistema, que falle aquí (al construir) y no al abrir la app.
RUN Rscript -e "for (p in rownames(installed.packages('/opt/integrat/library'))) loadNamespace(p)"
# Misma estructura que el repo: la app busca las fórmulas en ../analitica/R (app/R/analitica.R).
WORKDIR /srv/integrat/app
EXPOSE 3838

# ---------- dev: el código se monta desde tu PC y Shiny recarga al guardar ----------
FROM base AS dev
CMD ["Rscript", "-e", "options(shiny.autoreload = TRUE); shiny::runApp('/srv/integrat/app', host = '0.0.0.0', port = 3838, launch.browser = FALSE)"]

# ---------- prod: solo lo que se publica (sin pruebas) ----------
FROM base AS prod
COPY --chown=integrat app/app.R app/config.yml ./
COPY --chown=integrat app/R ./R
COPY --chown=integrat app/www ./www
COPY --chown=integrat analitica/R /srv/integrat/analitica/R
USER integrat
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT:-3838}/" > /dev/null || exit 1
CMD ["sh", "-c", "exec Rscript -e \"shiny::runApp('/srv/integrat/app', host = '0.0.0.0', port = as.integer(Sys.getenv('PORT', '3838')), launch.browser = FALSE)\""]
