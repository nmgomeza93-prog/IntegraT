# integrat (API)

API de dominio de IntegraT (FastAPI desde el paso 3). Es el único componente con acceso a la base de datos y a R2.

```bash
python -m uv sync          # crea .venv e instala dependencias
python -m uv run pytest    # pruebas
python -m uv run ruff check .
```

La configuración se lee **solo** de variables de entorno (`../.env`); ver `../.env.example`.
