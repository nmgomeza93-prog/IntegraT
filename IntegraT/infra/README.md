# infra

- `docker-compose.yml`: MySQL en memoria para las pruebas automáticas (pytest y CI).
- `docker/paquetes_app.R`: instala en la imagen de la app solo los paquetes de R que usa (versiones de `renv.lock`).
- `azure/`: receta de despliegue en Azure (`crear.sh`, `publicar.sh`, `README.md`).
- `desplegar_app.R` y `railway.md`: histórico (shinyapps.io y Railway, reemplazados por D-24).

El desarrollo local con Docker vive en `../compose.yaml`. Las imágenes: `../api/Dockerfile` y `../app/Dockerfile`.
Nunca se guardan secretos aquí: en local salen de `../.env`; en Azure, de Key Vault.
