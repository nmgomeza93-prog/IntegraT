"""Lecturas de los libros: resultados del mes, libro diario y saldos por cuenta.

Las cifras salen SIEMPRE de los asientos (una sola fuente de verdad). Todo acceso a tablas de
negocio pasa por db.aislamiento.
"""

from collections import defaultdict
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from integrat.contabilidad.esquemas import (
    AsientoOut,
    CuentaOut,
    LibroDiarioOut,
    LineaAsientoOut,
    PlanCuentasOut,
    ResultadosOut,
)
from integrat.contabilidad.motor import SEPARADO, abrir_libro
from integrat.db import aislamiento as ais
from integrat.db.tablas import cont_asiento, cont_asiento_linea, cont_cuenta_contable
from integrat.gastos.servicio import MesInvalido, _rango_del_mes
from integrat.tiempo import hoy_del_negocio

CERO = Decimal("0.00")
MAX_ASIENTOS_POR_MES = 2000
ROLES_VENTA = {"VENTAS", "VENTAS_ENVIOS"}
ROLES_PERDIDA = {"MERMA"}

__all__ = ["MesInvalido"]  # se re-exporta para el router


def _dinero(valor: Decimal) -> str:
    return f"{valor:.2f}"


def _movimientos_del_mes(ctx: ais.ContextoNegocio, inicio, siguiente) -> sa.Select:
    """Suma del debe y del haber del mes por cuenta."""
    cuenta = sa.and_(cont_cuenta_contable.c.id == cont_asiento_linea.c.cuenta_contable_id,
                     cont_cuenta_contable.c.negocio_id == ctx.negocio_id)
    asiento = sa.and_(cont_asiento.c.id == cont_asiento_linea.c.asiento_id,
                      cont_asiento.c.negocio_id == ctx.negocio_id)
    return (
        ais.seleccionar(
            ctx, cont_asiento_linea, cont_cuenta_contable.c.tipo,
            cont_cuenta_contable.c.rol_cuenta_codigo.label("rol"),
            sa.func.sum(cont_asiento_linea.c.debe).label("debe"),
            sa.func.sum(cont_asiento_linea.c.haber).label("haber"),
        )
        .select_from(cont_asiento_linea.join(cont_cuenta_contable, cuenta)
                     .join(cont_asiento, asiento))
        .where(cont_asiento.c.fecha >= inicio, cont_asiento.c.fecha < siguiente)
        .group_by(cont_cuenta_contable.c.tipo, cont_cuenta_contable.c.rol_cuenta_codigo)
    )


def resultados_del_mes(con: Connection, ctx: ais.ContextoNegocio, mes: str | None) -> ResultadosOut:
    inicio, siguiente, etiqueta = _rango_del_mes(mes, hoy_del_negocio(con, ctx))
    vendiste = otros = costo = perdido = gastos = CERO
    for f in con.execute(_movimientos_del_mes(ctx, inicio, siguiente)):
        debe, haber = Decimal(f.debe or 0), Decimal(f.haber or 0)
        if f.tipo == "ingreso":
            if f.rol in ROLES_VENTA:
                vendiste += haber - debe
            else:
                otros += haber - debe
        elif f.tipo == "costo":
            if f.rol in ROLES_PERDIDA:
                perdido += debe - haber
            else:
                costo += debe - haber
        elif f.tipo == "gasto":
            gastos += debe - haber
    con_iva_separado = con.execute(
        ais.seleccionar(ctx, cont_asiento, cont_asiento.c.id)
        .where(cont_asiento.c.fecha >= inicio, cont_asiento.c.fecha < siguiente,
               cont_asiento.c.tratamiento_iva == SEPARADO).limit(1)
    ).first() is not None
    return ResultadosOut(
        mes=etiqueta, vendiste=_dinero(vendiste), costo_de_lo_vendido=_dinero(costo),
        se_perdio=_dinero(perdido), gastaste=_dinero(gastos), otros_ingresos=_dinero(otros),
        te_queda=_dinero(vendiste + otros - costo - perdido - gastos),
        sin_iva=con_iva_separado,
    )


def libro_diario(con: Connection, ctx: ais.ContextoNegocio, mes: str | None) -> LibroDiarioOut:
    inicio, siguiente, etiqueta = _rango_del_mes(mes, hoy_del_negocio(con, ctx))
    asientos = con.execute(
        ais.seleccionar(ctx, cont_asiento)
        .where(cont_asiento.c.fecha >= inicio, cont_asiento.c.fecha < siguiente)
        .order_by(cont_asiento.c.numero).limit(MAX_ASIENTOS_POR_MES)
    ).all()
    lineas: dict = defaultdict(list)
    total_debe = total_haber = CERO
    ids = [a.id for a in asientos]
    if ids:
        cuenta = sa.and_(cont_cuenta_contable.c.id == cont_asiento_linea.c.cuenta_contable_id,
                         cont_cuenta_contable.c.negocio_id == ctx.negocio_id)
        for f in con.execute(
            ais.seleccionar(ctx, cont_asiento_linea, cont_asiento_linea.c.asiento_id,
                            cont_asiento_linea.c.debe, cont_asiento_linea.c.haber,
                            cont_cuenta_contable.c.codigo, cont_cuenta_contable.c.nombre)
            .select_from(cont_asiento_linea.join(cont_cuenta_contable, cuenta))
            .where(cont_asiento_linea.c.asiento_id.in_(ids))
            .order_by(cont_asiento_linea.c.creado_en, cont_asiento_linea.c.id)
        ):
            total_debe += f.debe
            total_haber += f.haber
            lineas[f.asiento_id].append(LineaAsientoOut(
                cuenta_codigo=f.codigo, cuenta_nombre=f.nombre, debe=_dinero(f.debe),
                haber=_dinero(f.haber)))
    return LibroDiarioOut(
        mes=etiqueta, total_debe=_dinero(total_debe), total_haber=_dinero(total_haber),
        asientos=[
            AsientoOut(id=a.id, numero=a.numero, fecha=a.fecha, descripcion=a.descripcion_simple,
                       tipo_evento=a.tipo_evento, reverso_de_asiento_id=a.reverso_de_asiento_id,
                       lineas=lineas[a.id])
            for a in asientos
        ],
    )


def plan_con_saldos(con: Connection, ctx: ais.ContextoNegocio) -> PlanCuentasOut:
    """El plan de cuentas con el saldo de cada cuenta de movimiento hasta hoy."""
    abrir_libro(con, ctx)  # negocios anteriores a la contabilidad: siembra su plan
    sumas = {
        f.cuenta_contable_id: (Decimal(f.debe or 0), Decimal(f.haber or 0))
        for f in con.execute(
            ais.seleccionar(ctx, cont_asiento_linea, cont_asiento_linea.c.cuenta_contable_id,
                            sa.func.sum(cont_asiento_linea.c.debe).label("debe"),
                            sa.func.sum(cont_asiento_linea.c.haber).label("haber"))
            .group_by(cont_asiento_linea.c.cuenta_contable_id)
        )
    }
    cuentas = []
    for c in con.execute(
        ais.seleccionar(ctx, cont_cuenta_contable).order_by(cont_cuenta_contable.c.codigo)
    ):
        debe, haber = sumas.get(c.id, (CERO, CERO))
        saldo = debe - haber if c.naturaleza == "deudora" else haber - debe
        cuentas.append(CuentaOut(
            codigo=c.codigo, nombre=c.nombre, nombre_simple=c.nombre_simple, tipo=c.tipo,
            naturaleza=c.naturaleza, acepta_movimientos=bool(c.acepta_movimientos),
            rol=c.rol_cuenta_codigo, saldo=_dinero(saldo)))
    return PlanCuentasOut(al=hoy_del_negocio(con, ctx), cuentas=cuentas)
