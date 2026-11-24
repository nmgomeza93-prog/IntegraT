"""Utilidades de base de datos para las pruebas (solo integrat_test)."""

from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config

RAIZ_API = Path(__file__).resolve().parents[1]


def config_alembic(conexion) -> Config:
    cfg = Config(str(RAIZ_API / "alembic.ini"))
    cfg.set_main_option("script_location", str(RAIZ_API / "migrations"))
    cfg.attributes["connection"] = conexion
    return cfg


def vaciar_base(engine) -> None:
    """Borra todas las tablas de integrat_test (solo esa base: lo garantiza ConfigBDPruebas)."""
    with engine.begin() as con:
        con.execute(sa.text("SET FOREIGN_KEY_CHECKS = 0"))
        tablas = con.execute(sa.text(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = DATABASE()"
        )).scalars().all()
        for tabla in tablas:
            con.execute(sa.text(f"DROP TABLE `{tabla}`"))
        con.execute(sa.text("SET FOREIGN_KEY_CHECKS = 1"))


def migrar(engine, destino: str = "head") -> None:
    with engine.begin() as con:
        command.upgrade(config_alembic(con), destino)


def desmigrar(engine, destino: str = "base") -> None:
    with engine.begin() as con:
        command.downgrade(config_alembic(con), destino)
