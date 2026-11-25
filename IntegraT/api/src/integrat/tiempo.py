"""Fechas en la zona horaria del negocio (la base guarda instantes en UTC)."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from integrat.db.aislamiento import ContextoNegocio
from integrat.db.tablas import core_negocio


def zona_del_negocio(con: Connection, ctx: ContextoNegocio) -> ZoneInfo:
    nombre = con.execute(
        sa.select(core_negocio.c.zona_horaria).where(core_negocio.c.id == ctx.negocio_id)
    ).scalar_one()
    return ZoneInfo(nombre)


def hoy_del_negocio(con: Connection, ctx: ContextoNegocio) -> date:
    """El día calendario de hoy en la zona horaria del negocio."""
    return datetime.now(zona_del_negocio(con, ctx)).date()
