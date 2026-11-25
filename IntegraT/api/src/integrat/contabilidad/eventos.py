"""Asientos de cada operación. Se llaman al final de la operación, en su misma transacción.

Cada función arma los importes de la operación y deja que la regla del evento decida las
cuentas (por rol). Ninguna conoce códigos de cuenta.
"""

import uuid
from collections import defaultdict
from datetime import UTC, date
from decimal import Decimal

from sqlalchemy.engine import Connection

from integrat.contabilidad import motor
from integrat.contabilidad.motor import CERO, ROL_POR_MEDIO, centavos
from integrat.db import aislamiento as ais
from integrat.db.tablas import (
    ops_categoria_gasto,
    ops_gasto,
    ops_insumo,
    ops_movimiento_inventario,
    ops_pago,
    ops_venta,
)
from integrat.tiempo import hoy_del_negocio, zona_del_negocio

ORIGEN_VENTA = "venta"
ORIGEN_GASTO = "gasto"
ORIGEN_COMPRA = "compra"
ORIGEN_MOVIMIENTO = "movimiento"
ROL_GASTO_DEFECTO = "GASTO_VARIOS"
INVENTARIO_INSUMOS = "INVENTARIO_INSUMOS"
INVENTARIO_MERCADERIA = "INVENTARIO_MERCADERIA"


def rol_inventario(item_id: uuid.UUID | None) -> str:
    """La mercadería (insumo ligado a un producto) y los insumos van a cuentas distintas."""
    return INVENTARIO_MERCADERIA if item_id is not None else INVENTARIO_INSUMOS


def _clase(rol: str) -> str:
    return "mercaderia" if rol == INVENTARIO_MERCADERIA else "insumos"


# ------------------------------------------------------------------ ventas

def asentar_venta(con: Connection, ctx: ais.ContextoNegocio, venta_id: uuid.UUID) -> None:
    venta = con.execute(
        ais.seleccionar(ctx, ops_venta, ops_venta.c.numero, ops_venta.c.fecha_hora,
                        ops_venta.c.total).where(ops_venta.c.id == venta_id)
    ).one()
    medio = con.execute(
        ais.seleccionar(ctx, ops_pago, ops_pago.c.medio_pago).where(ops_pago.c.venta_id == venta_id)
    ).scalar_one()
    # Costo de lo vendido: lo que la venta sacó del inventario, al costo con que salió.
    costos: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for f in con.execute(
        ais.seleccionar(ctx, ops_movimiento_inventario, ops_movimiento_inventario.c.cantidad_base,
                        ops_movimiento_inventario.c.costo_unitario_base, ops_insumo.c.item_id)
        .select_from(ops_movimiento_inventario.join(
            ops_insumo, ops_insumo.c.id == ops_movimiento_inventario.c.insumo_id))
        .where(ops_movimiento_inventario.c.origen_tipo == ORIGEN_VENTA,
               ops_movimiento_inventario.c.origen_id == venta_id,
               ops_movimiento_inventario.c.tipo == "consumo_venta")
    ):
        costos[_clase(rol_inventario(f.item_id))] += -f.cantidad_base * f.costo_unitario_base
    costo_insumos = centavos(costos["insumos"])
    costo_mercaderia = centavos(costos["mercaderia"])

    trat = motor.tratamiento_iva(con, ctx)
    base, iva = motor.separar_iva(venta.total, trat)
    fecha = venta.fecha_hora.replace(tzinfo=UTC).astimezone(zona_del_negocio(con, ctx)).date()
    motor.registrar(
        con, ctx, evento="VENTA", fecha=fecha, descripcion=f"Venta #{venta.numero}",
        importes={"total": centavos(venta.total), "base": base, "iva": iva,
                  "costo": costo_insumos + costo_mercaderia, "costo_insumos": costo_insumos,
                  "costo_mercaderia": costo_mercaderia},
        comodines={"@pago": ROL_POR_MEDIO[medio]}, origen_tipo=ORIGEN_VENTA, origen_id=venta_id,
        tratamiento=trat,
    )


def revertir_venta(con: Connection, ctx: ais.ContextoNegocio, venta_id: uuid.UUID,
                   numero: int) -> None:
    motor.revertir_origen(con, ctx, ORIGEN_VENTA, venta_id, f"Anulación de la venta #{numero}")


# ------------------------------------------------------------------ gastos

def asentar_gasto(con: Connection, ctx: ais.ContextoNegocio, gasto_id: uuid.UUID) -> None:
    gasto = con.execute(
        ais.seleccionar(ctx, ops_gasto, ops_gasto.c.fecha, ops_gasto.c.monto,
                        ops_gasto.c.medio_pago, ops_gasto.c.con_factura,
                        ops_categoria_gasto.c.nombre, ops_categoria_gasto.c.rol_cuenta_codigo)
        .select_from(ops_gasto.join(
            ops_categoria_gasto, ops_categoria_gasto.c.id == ops_gasto.c.categoria_gasto_id))
        .where(ops_gasto.c.id == gasto_id)
    ).one()
    trat = motor.tratamiento_iva(con, ctx)
    total = centavos(gasto.monto)
    base, iva = motor.separar_iva(total, trat, aplica=bool(gasto.con_factura))
    motor.registrar(
        con, ctx, evento="GASTO", fecha=gasto.fecha, descripcion=f"Gasto: {gasto.nombre}",
        importes={"total": total, "base": base, "iva": iva},
        comodines={"@pago": ROL_POR_MEDIO[gasto.medio_pago],
                   "@gasto": gasto.rol_cuenta_codigo or ROL_GASTO_DEFECTO},
        origen_tipo=ORIGEN_GASTO, origen_id=gasto_id, tratamiento=trat,
    )


def revertir_gasto(con: Connection, ctx: ais.ContextoNegocio, gasto_id: uuid.UUID,
                   motivo: str) -> None:
    motor.revertir_origen(con, ctx, ORIGEN_GASTO, gasto_id, motivo)


# ------------------------------------------------------------------ compras

def asentar_compra(con: Connection, ctx: ais.ContextoNegocio, compra_id: uuid.UUID, *,
                   fecha: date, medio_pago: str, total: Decimal,
                   bases: dict[str, Decimal], trat: motor.Tratamiento) -> None:
    """`bases`: lo que entró al inventario (sin IVA si se separó) por rol de inventario."""
    base_insumos = centavos(bases.get(INVENTARIO_INSUMOS, CERO))
    base_mercaderia = centavos(bases.get(INVENTARIO_MERCADERIA, CERO))
    total = centavos(total)
    motor.registrar(
        con, ctx, evento="COMPRA", fecha=fecha, descripcion="Compra",
        importes={"total": total, "base_insumos": base_insumos,
                  "base_mercaderia": base_mercaderia,
                  "iva": total - base_insumos - base_mercaderia},
        comodines={"@pago": ROL_POR_MEDIO[medio_pago]}, origen_tipo=ORIGEN_COMPRA,
        origen_id=compra_id, tratamiento=trat,
    )


def revertir_compra(con: Connection, ctx: ais.ContextoNegocio, compra_id: uuid.UUID) -> None:
    motor.revertir_origen(con, ctx, ORIGEN_COMPRA, compra_id, "Anulación de una compra")


# ------------------------------------------------------------------ inventario a mano

_EVENTO_POR_TIPO = {
    "inicial": ("INVENTARIO_INICIAL", "Lo que ya tenías"),
    "entrada": ("ENTRADA_INVENTARIO", "Compra anotada"),
    "merma": ("MERMA", "Se perdió"),
}


def asentar_movimiento(con: Connection, ctx: ais.ContextoNegocio, movimiento_id: uuid.UUID,
                       valor: Decimal | None = None) -> None:
    """Asiento de un movimiento hecho a mano. `valor`: lo que costó (entradas e iniciales)."""
    mov = con.execute(
        ais.seleccionar(ctx, ops_movimiento_inventario, ops_movimiento_inventario.c.tipo,
                        ops_movimiento_inventario.c.cantidad_base,
                        ops_movimiento_inventario.c.costo_unitario_base,
                        ops_insumo.c.nombre, ops_insumo.c.item_id)
        .select_from(ops_movimiento_inventario.join(
            ops_insumo, ops_insumo.c.id == ops_movimiento_inventario.c.insumo_id))
        .where(ops_movimiento_inventario.c.id == movimiento_id)
    ).one()
    if mov.tipo == "ajuste":
        evento, texto = (("AJUSTE_SOBRANTE", "Corrección (había más)") if mov.cantidad_base > 0
                         else ("AJUSTE_FALTANTE", "Corrección (había menos)"))
    else:
        evento, texto = _EVENTO_POR_TIPO[mov.tipo]
    if valor is None:
        valor = abs(mov.cantidad_base * mov.costo_unitario_base)
    motor.registrar(
        con, ctx, evento=evento, fecha=hoy_del_negocio(con, ctx),
        descripcion=f"{texto}: {mov.nombre}", importes={"valor": centavos(valor)},
        comodines={"@inventario": rol_inventario(mov.item_id)},
        origen_tipo=ORIGEN_MOVIMIENTO, origen_id=movimiento_id,
    )


def bases_vacias() -> dict[str, Decimal]:
    return {INVENTARIO_INSUMOS: Decimal("0"), INVENTARIO_MERCADERIA: Decimal("0")}

