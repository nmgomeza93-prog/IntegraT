"""Mercadería para revender: un producto que se compra hecho usa el inventario de insumos.

Activarla crea un insumo en unidades con el nombre del producto, ligado por `item_id`, y una receta
de 1 unidad. Así comprar sube la existencia, vender la descuenta y el costo promedio es el costo del
producto, sin tocar ventas ni recetas (docs/PLAN_COMPRAS.md).
"""

import uuid

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from integrat.db import aislamiento as ais
from integrat.db.tablas import ops_insumo, ops_receta_linea
from integrat.db.tipos import ahora_utc, uuid7
from integrat.insumos import recetas
from integrat.insumos import servicio as inventario
from integrat.insumos.esquemas import MercaderiaOut

UNIDAD = "UN"
MAX_NOMBRE = 80
SUFIJO = " (para vender)"


class ItemNoEncontrado(Exception):
    pass


class ConReceta(Exception):
    """El producto ya tiene una receta armada a mano."""


def item_con_mercaderia(con: Connection, ctx: ais.ContextoNegocio, item_id: uuid.UUID):
    """El insumo vivo ligado al producto, o None."""
    return con.execute(
        ais.seleccionar(ctx, ops_insumo, ops_insumo.c.id).where(ops_insumo.c.item_id == item_id)
    ).first()


def obtener(con: Connection, ctx: ais.ContextoNegocio, item_id: uuid.UUID) -> MercaderiaOut:
    try:
        recetas.buscar_item(con, ctx, item_id)
    except recetas.ItemNoEncontrado:
        raise ItemNoEncontrado from None
    ligado = item_con_mercaderia(con, ctx, item_id)
    if ligado is None:
        return MercaderiaOut(activa=False, insumo=None)
    return MercaderiaOut(activa=True, insumo=inventario.obtener_insumo(con, ctx, ligado.id))


def _nombre_libre(con: Connection, ctx: ais.ContextoNegocio, nombre_item: str) -> str:
    candidato = nombre_item[:MAX_NOMBRE]
    if not inventario.nombre_repetido(con, ctx, candidato, None):
        return candidato
    base = nombre_item[:MAX_NOMBRE - len(SUFIJO) - 3]
    candidato = base + SUFIJO
    numero = 2
    while inventario.nombre_repetido(con, ctx, candidato, None):
        candidato = f"{base}{SUFIJO} {numero}"
        numero += 1
    return candidato


def activar(con: Connection, ctx: ais.ContextoNegocio, item_id: uuid.UUID) -> MercaderiaOut:
    try:
        item = recetas.buscar_item(con, ctx, item_id, bloquear=True)  # una activación a la vez
    except recetas.ItemNoEncontrado:
        raise ItemNoEncontrado from None
    if item_con_mercaderia(con, ctx, item_id) is not None:
        return obtener(con, ctx, item_id)
    hay_receta = con.execute(
        ais.seleccionar(ctx, ops_receta_linea, sa.func.count())
        .where(ops_receta_linea.c.item_id == item_id)
    ).scalar_one()
    if hay_receta:
        raise ConReceta
    insumo_id = uuid7()
    con.execute(ais.insertar(ctx, ops_insumo, {
        "id": insumo_id, "nombre": _nombre_libre(con, ctx, item.nombre), "unidad_codigo": UNIDAD,
        "item_id": item_id,
    }))
    con.execute(ais.insertar(ctx, ops_receta_linea, {
        "id": uuid7(), "item_id": item_id, "insumo_id": insumo_id, "cantidad": 1,
        "unidad_codigo": UNIDAD,
    }))
    return obtener(con, ctx, item_id)


def desactivar_en_cascada(con: Connection, ctx: ais.ContextoNegocio, item_id: uuid.UUID) -> None:
    """Archiva el insumo ligado y su receta. Sus movimientos se conservan."""
    ligado = item_con_mercaderia(con, ctx, item_id)
    if ligado is None:
        return
    ahora = ahora_utc()
    con.execute(
        ais.actualizar(ctx, ops_receta_linea, ops_receta_linea.c.item_id == item_id)
        .values(eliminado_en=ahora, eliminado_por=ctx.usuario_id)
    )
    con.execute(
        ais.actualizar(ctx, ops_insumo, ops_insumo.c.id == ligado.id)
        .values(eliminado_en=ahora, eliminado_por=ctx.usuario_id)
    )


def desactivar(con: Connection, ctx: ais.ContextoNegocio, item_id: uuid.UUID) -> MercaderiaOut:
    try:
        recetas.buscar_item(con, ctx, item_id, bloquear=True)
    except recetas.ItemNoEncontrado:
        raise ItemNoEncontrado from None
    desactivar_en_cascada(con, ctx, item_id)
    return obtener(con, ctx, item_id)
