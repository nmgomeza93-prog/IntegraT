"""Aplicación FastAPI de IntegraT.

Ejecutar en desarrollo (desde api/):
    python -m uv run uvicorn integrat.main:app --reload
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import integrat
from integrat.auth.router import router as router_auth
from integrat.caja.router import router as router_caja
from integrat.catalogos.router import router as router_catalogos
from integrat.compras.router import router as router_compras
from integrat.config import config_app
from integrat.contabilidad.router import router as router_contabilidad
from integrat.gastos.router import router as router_gastos
from integrat.insumos.router import router as router_insumos
from integrat.items.router import router as router_items
from integrat.logs import configurar_logs
from integrat.middleware import LimiteCuerpo
from integrat.negocios.router import router as router_negocios
from integrat.salud.router import router as router_salud
from integrat.ventas.router import router as router_ventas

PREFIJO = "/v1"


def crear_app() -> FastAPI:
    configurar_logs()
    cfg = config_app()
    # La documentación interactiva solo existe en desarrollo: en piloto y producción no se
    # regala el mapa de la API a quien llegue por internet.
    en_dev = cfg.app_env == "dev"
    app = FastAPI(
        title="IntegraT API",
        version=integrat.__version__,
        description="API de dominio de IntegraT. Única puerta de acceso a los datos.",
        openapi_url=f"{PREFIJO}/openapi.json" if en_dev else None,
        docs_url="/docs" if en_dev else None,
        redoc_url=None,
    )
    app.add_middleware(LimiteCuerpo, maximo=cfg.api_max_cuerpo_kb * 1024)
    # CORS solo si se configuran orígenes: quien llama a la API es el servidor de Shiny, no el
    # navegador, así que en el piloto API_ALLOWED_ORIGINS debe quedar vacío.
    origenes = cfg.origenes_permitidos
    if origenes:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origenes,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
        )
    for router in (router_salud, router_auth, router_catalogos, router_negocios, router_items,
                   router_ventas, router_gastos, router_insumos, router_compras,
                   router_contabilidad, router_caja):
        app.include_router(router, prefix=PREFIJO)
    return app


app = crear_app()
