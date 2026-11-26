"""Informe del mes: datos agregados de las ventas (qué, a quién y cómo se cobró).

Solo sumas y conteos (datos); las fórmulas financieras (ticket promedio, comparaciones) viven en
el paquete de R integrat.analitica. Ganancias y gastos: /v1/resultados y /v1/gastos.
"""

from datetime import UTC, datetime, time
from decimal import Decimal

import sqlalchemy as sa
from pydantic import BaseModel
from sqlalchemy.engine import Connection

from integrat.db import aislamiento as ais
from integrat.db.tablas import ops_cliente, ops_pago, ops_venta, ops_venta_linea
from integrat.gastos.servicio import MesInvalido, _rango_del_mes
from integrat.tiempo import hoy_del_negocio, zona_del_negocio

__all__ = ["MesInvalido", "InformeMesOut", "informe_del_mes"]

TOP = 10


class ProductoDelMes(BaseModel):
    nombre: str
    cantidad: int
    total: str


class ClienteDelMes(BaseModel):
    cliente_id: str | None  # None = Consumidor final
    nombre: str
    compras: int
    total: str


class MedioDelMes(BaseModel):
    medio_pago: str
    ventas: int
    total: str


class InformeMesOut(BaseModel):
    mes: str
    ventas: int            # vigentes (sin anuladas)
    total: str
    anuladas: int
    productos: list[ProductoDelMes]   # los 10 que más vendieron (por dinero)
    clientes: list[ClienteDelMes]     # los 10 que más compraron; Consumidor final aparte
    consumidor_final: ClienteDelMes
    medios: list[MedioDelMes]


def _dinero(valor) -> str:
    return f"{Decimal(valor or 0):.2f}"


def informe_del_mes(con: Connection, ctx: ais.ContextoNegocio, mes: str | None) -> InformeMesOut:
    inicio, siguiente, etiqueta = _rango_del_mes(mes, hoy_del_negocio(con, ctx))
    zona = zona_del_negocio(con, ctx)

    def utc(dia):
        return datetime.combine(dia, time.min, zona).astimezone(UTC).replace(tzinfo=None)

    del_mes = (ops_venta.c.fecha_hora >= utc(inicio), ops_venta.c.fecha_hora < utc(siguiente))
    vigentes = ais.seleccionar(ctx, ops_venta).where(
        *del_mes, ops_venta.c.estado == "pagada").subquery()

    cantidad, total = con.execute(
        sa.select(sa.func.count(), sa.func.coalesce(sa.func.sum(vigentes.c.total), 0))).one()
    anuladas = con.execute(ais.seleccionar(ctx, ops_venta, sa.func.count()).where(
        *del_mes, ops_venta.c.estado == "anulada")).scalar_one()

    linea = ops_venta_linea
    productos = con.execute(
        sa.select(linea.c.nombre, sa.func.sum(linea.c.cantidad).label("cantidad"),
                  sa.func.sum(linea.c.total).label("total"))
        .select_from(linea.join(vigentes, vigentes.c.id == linea.c.venta_id))
        .where(linea.c.negocio_id == ctx.negocio_id)
        .group_by(linea.c.nombre)
        .order_by(sa.desc("total"), linea.c.nombre).limit(TOP)
    ).all()

    por_cliente = con.execute(
        sa.select(vigentes.c.cliente_id, sa.func.count().label("compras"),
                  sa.func.sum(vigentes.c.total).label("total"))
        .group_by(vigentes.c.cliente_id)
    ).all()
    ids = [f.cliente_id for f in por_cliente if f.cliente_id is not None]
    nombres = {f.id: f.nombre for f in con.execute(
        ais.seleccionar(ctx, ops_cliente, ops_cliente.c.id, ops_cliente.c.nombre,
                        incluir_eliminados=True).where(ops_cliente.c.id.in_(ids)))} if ids else {}
    clientes = sorted(
        (ClienteDelMes(cliente_id=str(f.cliente_id), nombre=nombres.get(f.cliente_id, "Cliente"),
                       compras=f.compras, total=_dinero(f.total))
         for f in por_cliente if f.cliente_id is not None),
        key=lambda c: (-Decimal(c.total), c.nombre.casefold()))[:TOP]
    sin_cliente = next((f for f in por_cliente if f.cliente_id is None), None)

    medios = con.execute(
        sa.select(ops_pago.c.medio_pago, sa.func.count().label("ventas"),
                  sa.func.sum(ops_pago.c.monto).label("total"))
        .select_from(ops_pago.join(vigentes, vigentes.c.id == ops_pago.c.venta_id))
        .where(ops_pago.c.negocio_id == ctx.negocio_id)
        .group_by(ops_pago.c.medio_pago).order_by(sa.desc("total"))
    ).all()

    return InformeMesOut(
        mes=etiqueta, ventas=cantidad, total=_dinero(total), anuladas=anuladas,
        productos=[ProductoDelMes(nombre=p.nombre, cantidad=int(p.cantidad),
                                  total=_dinero(p.total)) for p in productos],
        clientes=clientes,
        consumidor_final=ClienteDelMes(
            cliente_id=None, nombre="Consumidor final",
            compras=sin_cliente.compras if sin_cliente else 0,
            total=_dinero(sin_cliente.total if sin_cliente else 0)),
        medios=[MedioDelMes(medio_pago=m.medio_pago, ventas=m.ventas, total=_dinero(m.total))
                for m in medios],
    )
