"""Aplicación FastAPI de IntegraT.

Ejecutar en desarrollo (desde api/):
    python -m uv run uvicorn integrat.main:app --reload
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import integrat
from integrat.config import config_app
from integrat.logs import configurar_logs
from integrat.salud.router import router as router_salud

PREFIJO = "/v1"


def crear_app() -> FastAPI:
    configurar_logs()
    app = FastAPI(
        title="IntegraT API",
        version=integrat.__version__,
        description="API de dominio de IntegraT. Única puerta de acceso a los datos.",
        openapi_url=f"{PREFIJO}/openapi.json",
        docs_url="/docs",
        redoc_url=None,
    )
    origenes = config_app().origenes_permitidos
    if origenes:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origenes,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
        )
    app.include_router(router_salud, prefix=PREFIJO)
    return app


app = crear_app()
