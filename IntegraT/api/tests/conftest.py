"""Fixtures de pruebas. Usan SOLO la base local `integrat_test` (Docker), nunca la real.

Antes de correr las pruebas de base de datos:
    docker compose -f infra/docker-compose.yml --env-file .env up -d --wait mysql-test
"""

import pytest
import sqlalchemy as sa
from bd_utils import migrar, vaciar_base

from integrat.config import ConfigBDPruebas
from integrat.db.conexion import crear_engine


@pytest.fixture(scope="session")
def engine_pruebas():
    cfg = ConfigBDPruebas()  # type: ignore[call-arg]
    engine = crear_engine(cfg)
    try:
        with engine.connect() as con:
            con.execute(sa.text("SELECT 1"))
    except sa.exc.OperationalError as e:
        pytest.fail(
            "No hay conexión con la base local de pruebas. Levántala con:\n"
            "  docker compose -f infra/docker-compose.yml --env-file .env up -d --wait mysql-test\n"
            f"Detalle: {type(e.__cause__).__name__}"
        )
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def bd_migrada(engine_pruebas):
    """Base de pruebas vacía, migrada a la última versión y con semillas."""
    from integrat.db.semillas import cargar_semillas

    vaciar_base(engine_pruebas)
    migrar(engine_pruebas)
    cargar_semillas(engine_pruebas)
    return engine_pruebas
