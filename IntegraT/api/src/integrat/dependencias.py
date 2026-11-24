"""Dependencias compartidas de FastAPI (sobreescribibles en pruebas)."""

from sqlalchemy.engine import Engine

from integrat.db.conexion import engine_principal


def obtener_engine() -> Engine:
    return engine_principal()
