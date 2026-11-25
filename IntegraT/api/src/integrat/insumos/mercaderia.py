"""Mercadería para revender: un producto que se compra hecho usa el inventario de insumos.

Activarla crea un insumo en unidades con el nombre del producto, ligado por `item_id`, y una receta
de 1 unidad. Así comprar sube la existencia, vender la descuenta y el costo promedio es el costo del
producto, sin tocar ventas ni recetas (docs/PLAN_COMPRAS.md).

Con variantes (talla, color…; docs/PLAN_VARIANTES.md) hay un insumo POR VARIANTE
(`item_variante_id`) con su receta de 1 unidad solo para esa variante: cada talla tiene su
existencia y su costo.
`sincronizar` lo mantiene al día cuando cambian las variantes del producto.
"""

import uuid

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from integrat.db import aislamiento as ais
from integrat.db.tablas import ops_insumo, ops_item_variante, ops_receta_linea
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
        recetas.buscar_item(con, ctx, item_id, bloquear=True)  # una activación a la vez
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
    sincronizar(con, ctx, item_id, forzar=True)
    return obtener(con, ctx, item_id)


def _crear_insumo(con, ctx, item_id: uuid.UUID, nombre: str,
                  variante_id: uuid.UUID | None) -> None:
    insumo_id = uuid7()
    con.execute(ais.insertar(ctx, ops_insumo, {
        "id": insumo_id, "nombre": _nombre_libre(con, ctx, nombre), "unidad_codigo": UNIDAD,
        "item_id": item_id, "item_variante_id": variante_id,
    }))
    con.execute(ais.insertar(ctx, ops_receta_linea, {
        "id": uuid7(), "item_id": item_id, "insumo_id": insumo_id, "cantidad": 1,
        "unidad_codigo": UNIDAD, "item_variante_id": variante_id,
    }))


def _archivar_insumo(con, ctx, insumo_id: uuid.UUID) -> None:
    ahora = ahora_utc()
    con.execute(ais.actualizar(ctx, ops_receta_linea, ops_receta_linea.c.insumo_id == insumo_id)
                .values(eliminado_en=ahora, eliminado_por=ctx.usuario_id))
    con.execute(ais.actualizar(ctx, ops_insumo, ops_insumo.c.id == insumo_id)
                .values(eliminado_en=ahora, eliminado_por=ctx.usuario_id))


def _reactivar_implicito(con, ctx, item_id: uuid.UUID) -> bool:
    """Sin variantes otra vez: recupera el insumo de antes del producto (con su existencia)."""
    anterior = con.execute(
        ais.seleccionar(ctx, ops_insumo, ops_insumo.c.id, incluir_eliminados=True)
        .where(ops_insumo.c.item_id == item_id, ops_insumo.c.item_variante_id.is_(None),
               ops_insumo.c.eliminado_en.is_not(None))
        .order_by(ops_insumo.c.eliminado_en.desc()).limit(1)
    ).first()
    if anterior is None:
        return False
    for tabla, condicion in ((ops_insumo, ops_insumo.c.id == anterior.id),):
        con.execute(sa.update(tabla).where(condicion, tabla.c.negocio_id == ctx.negocio_id)
                    .values(eliminado_en=None, eliminado_por=None, actualizado_por=ctx.usuario_id))
    con.execute(ais.insertar(ctx, ops_receta_linea, {
        "id": uuid7(), "item_id": item_id, "insumo_id": anterior.id, "cantidad": 1,
        "unidad_codigo": UNIDAD}))
    return True


def sincronizar(con: Connection, ctx: ais.ContextoNegocio, item_id: uuid.UUID, *,
                forzar: bool = False) -> None:
    """Un insumo por variante (o uno solo si el producto no tiene variantes).

    Solo actúa si el producto es mercadería (o `forzar`, al activarla). Los insumos que sobran se
    archivan con sus movimientos; los que faltan se crean en cero.
    """
    vivos = con.execute(
        ais.seleccionar(ctx, ops_insumo, ops_insumo.c.id, ops_insumo.c.item_variante_id)
        .where(ops_insumo.c.item_id == item_id)
    ).all()
    if not vivos and not forzar:
        return
    item = recetas.buscar_item(con, ctx, item_id)
    explicitas = con.execute(
        ais.seleccionar(ctx, ops_item_variante, ops_item_variante.c.id, ops_item_variante.c.nombre)
        .where(ops_item_variante.c.item_id == item_id,
               ops_item_variante.c.atributos.is_not(None))
        .order_by(ops_item_variante.c.creado_en)
    ).all()
    deseadas: dict[uuid.UUID | None, str] = (
        {v.id: f"{item.nombre} · {v.nombre}" for v in explicitas} if explicitas
        else {None: item.nombre})
    actuales = {i.item_variante_id: i.id for i in vivos}
    for clave, insumo_id in actuales.items():
        if clave not in deseadas:
            _archivar_insumo(con, ctx, insumo_id)
    for clave, nombre in deseadas.items():
        if clave in actuales:
            continue
        # Al quitar las variantes vuelve el insumo de antes; al activar la mercadería, uno nuevo.
        if clave is None and not forzar and _reactivar_implicito(con, ctx, item_id):
            continue
        _crear_insumo(con, ctx, item_id, nombre, clave)


def desactivar_en_cascada(con: Connection, ctx: ais.ContextoNegocio, item_id: uuid.UUID) -> None:
    """Archiva los insumos ligados (uno o uno por variante) y su receta. Los movimientos quedan."""
    for ligado in con.execute(
        ais.seleccionar(ctx, ops_insumo, ops_insumo.c.id).where(ops_insumo.c.item_id == item_id)
    ).all():
        _archivar_insumo(con, ctx, ligado.id)


def desactivar(con: Connection, ctx: ais.ContextoNegocio, item_id: uuid.UUID) -> MercaderiaOut:
    try:
        recetas.buscar_item(con, ctx, item_id, bloquear=True)
    except recetas.ItemNoEncontrado:
        raise ItemNoEncontrado from None
    desactivar_en_cascada(con, ctx, item_id)
    return obtener(con, ctx, item_id)
