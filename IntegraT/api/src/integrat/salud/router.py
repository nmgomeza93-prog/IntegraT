"""GET /v1/salud: estado de la API y de la base de datos, sin exponer datos sensibles."""

import logging
import time
from typing import Annotated, Literal

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel
from sqlalchemy.engine import Engine

import integrat
from integrat.config import config_app
from integrat.dependencias import obtener_engine

log = logging.getLogger(__name__)
router = APIRouter(tags=["salud"])


class EstadoBD(BaseModel):
    conectada: bool
    latencia_ms: int | None = None
    migracion: str | None = None


class EstadoSalud(BaseModel):
    estado: Literal["ok", "degradado"]
    version: str
    entorno: str
    bd: EstadoBD


def _revisar_bd(engine: Engine) -> EstadoBD:
    inicio = time.perf_counter()
    try:
        with engine.connect() as con:
            con.execute(sa.text("SELECT 1"))
            migracion = con.execute(
                sa.text("SELECT version_num FROM alembic_version LIMIT 1")
            ).scalar_one_or_none()
    except Exception as e:  # noqa: BLE001 - cualquier fallo = BD no disponible
        # Solo el tipo de error: el mensaje del driver puede incluir usuario y host.
        log.warning("Salud: la base de datos no responde (%s)", type(e).__name__)
        return EstadoBD(conectada=False)
    return EstadoBD(
        conectada=True,
        latencia_ms=round((time.perf_counter() - inicio) * 1000),
        migracion=migracion,
    )


@router.get("/salud", response_model=EstadoSalud, summary="Estado de la API y la base de datos")
def salud(response: Response, engine: Annotated[Engine, Depends(obtener_engine)]) -> EstadoSalud:
    bd = _revisar_bd(engine)
    if not bd.conectada:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return EstadoSalud(
        estado="ok" if bd.conectada else "degradado",
        version=integrat.__version__,
        entorno=config_app().app_env,
        bd=bd,
    )
