"""Recetas, costo por platillo y descuento de insumos al vender.

La receta dice cuánto de cada insumo lleva UNA unidad vendida. Al vender, la API descuenta de
cada insumo (en la misma transacción de la venta) y, al anular la venta, lo devuelve al costo con
que salió. Los insumos archivados ya no se descuentan.
"""

import uuid
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from integrat import precios
from integrat.contabilidad.motor import separar_iva, tratamiento_iva
from integrat.db import aislamiento as ais
from integrat.db.tablas import (
    cat_unidad_medida,
    ops_insumo,
    ops_item,
    ops_item_variante,
    ops_movimiento_inventario,
    ops_receta_linea,
)
from integrat.db.tipos import ahora_utc, uuid7
from integrat.insumos import servicio as insumos
from integrat.insumos.esquemas import RecetaIn, RecetaLineaOut, RecetaOut

CENTAVOS = Decimal("0.01")
CERO = Decimal("0")
ORIGEN_VENTA = "venta"


class ItemNoEncontrado(Exception):
    pass


class InsumoInvalido(Exception):
    """Un insumo de la receta no existe en este negocio o está archivado."""


class InsumoRepetido(Exception):
    pass


class MercaderiaActiva(Exception):
    """El producto se compra hecho: su receta se maneja sola (docs/PLAN_COMPRAS.md)."""


# ------------------------------------------------------------------ leer

def buscar_item(con: Connection, ctx: ais.ContextoNegocio, item_id: uuid.UUID, *, bloquear=False):
    consulta = ais.seleccionar(ctx, ops_item, ops_item.c.id, ops_item.c.nombre).where(
        ops_item.c.id == item_id)
    fila = con.execute(consulta.with_for_update() if bloquear else consulta).first()
    if fila is None:
        raise ItemNoEncontrado
    return fila


def _precio(con: Connection, ctx: ais.ContextoNegocio, item_id: uuid.UUID) -> Decimal | None:
    return con.execute(
        ais.seleccionar(ctx, ops_item_variante, ops_item_variante.c.precio_venta)
        .where(ops_item_variante.c.item_id == item_id)
        .order_by(ops_item_variante.c.creado_en, ops_item_variante.c.id).limit(1)
    ).scalar()


def _lineas(con: Connection, ctx: ais.ContextoNegocio, item_id: uuid.UUID):
    """Líneas vivas con su insumo (aunque esté archivado) y la unidad de la línea."""
    return con.execute(
        ais.seleccionar(
            ctx, ops_receta_linea,
            ops_receta_linea.c.insumo_id, ops_receta_linea.c.cantidad,
            ops_receta_linea.c.unidad_codigo,
            ops_insumo.c.nombre.label("insumo_nombre"),
            ops_insumo.c.eliminado_en.label("insumo_eliminado_en"),
            ops_insumo.c.costo_promedio_base,
            cat_unidad_medida.c.nombre.label("unidad_nombre"),
            cat_unidad_medida.c.factor_a_base.label("factor"),
        )
        .select_from(
            ops_receta_linea
            .join(ops_insumo, sa.and_(ops_insumo.c.id == ops_receta_linea.c.insumo_id,
                                      ops_insumo.c.negocio_id == ctx.negocio_id))
            .join(cat_unidad_medida,
                  cat_unidad_medida.c.codigo == ops_receta_linea.c.unidad_codigo))
        .where(ops_receta_linea.c.item_id == item_id)
        .order_by(ops_receta_linea.c.creado_en, ops_receta_linea.c.id)
    ).all()


def _texto_cantidad(valor: Decimal) -> str:
    return insumos.cantidad_texto(valor)


def obtener_receta(con: Connection, ctx: ais.ContextoNegocio, item_id: uuid.UUID) -> RecetaOut:
    item = buscar_item(con, ctx, item_id)
    filas = _lineas(con, ctx, item_id)
    lineas: list[RecetaLineaOut] = []
    total = CERO
    for f in filas:
        costo = (f.cantidad * f.factor * f.costo_promedio_base).quantize(CENTAVOS, ROUND_HALF_UP)
        total += f.cantidad * f.factor * f.costo_promedio_base
        lineas.append(RecetaLineaOut(
            insumo_id=f.insumo_id, insumo_nombre=f.insumo_nombre,
            archivado=f.insumo_eliminado_en is not None,
            cantidad=_texto_cantidad(f.cantidad), unidad_codigo=f.unidad_codigo,
            unidad_nombre=f.unidad_nombre, costo=f"{costo:.2f}",
            sin_costo=f.costo_promedio_base == 0,
        ))
    total = total.quantize(CENTAVOS, ROUND_HALF_UP)
    precio = _precio(con, ctx, item_id)
    margen = porcentaje = None
    if lineas and precio is not None:
        # El margen se mide sobre el precio SIN IVA: el IVA cobrado no es del negocio.
        neto, _ = separar_iva(Decimal(precio), tratamiento_iva(con, ctx))
        margen = (neto - total).quantize(CENTAVOS, ROUND_HALF_UP)
        if neto > 0:
            porcentaje = int((margen * 100 / neto).quantize(Decimal("1"), ROUND_HALF_UP))
    info = precios.para_items(con, ctx, [item_id]).get(item_id)
    return RecetaOut(
        item_id=item.id, item_nombre=item.nombre, tiene_receta=bool(lineas), lineas=lineas,
        costo_total=f"{total:.2f}",
        costo_completo=not any(linea.sin_costo and not linea.archivado for linea in lineas),
        precio_venta=None if precio is None else f"{Decimal(precio):.2f}",
        margen=None if margen is None else f"{margen:.2f}", margen_porcentaje=porcentaje,
        precio_sugerido=None if info is None or info.precio_sugerido is None
        else f"{info.precio_sugerido:.2f}",
        aviso_precio=None if info is None else info.aviso,
        margen_objetivo_porcentaje=35 if info is None
        else int((info.margen_objetivo * 100).quantize(Decimal("1"), ROUND_HALF_UP)),
        margen_propio=False if info is None else info.margen_propio,
    )


# ------------------------------------------------------------------ escribir

def reemplazar_receta(con: Connection, ctx: ais.ContextoNegocio, item_id: uuid.UUID,
                      datos: RecetaIn) -> RecetaOut:
    buscar_item(con, ctx, item_id, bloquear=True)  # dos cambios a la vez se hacen uno tras otro
    if con.execute(
        ais.seleccionar(ctx, ops_insumo, ops_insumo.c.id).where(ops_insumo.c.item_id == item_id)
    ).first() is not None:
        raise MercaderiaActiva

    ids = [linea.insumo_id for linea in datos.lineas]
    if len(set(ids)) != len(ids):
        raise InsumoRepetido
    unidad_de = {
        f.id: f.unidad_codigo for f in con.execute(
            ais.seleccionar(ctx, ops_insumo, ops_insumo.c.id, ops_insumo.c.unidad_codigo)
            .where(ops_insumo.c.id.in_(ids))
        )
    } if ids else {}
    if len(unidad_de) != len(ids):
        raise InsumoInvalido

    nuevas = []
    for linea in datos.lineas:
        propia = insumos.buscar_unidad(con, unidad_de[linea.insumo_id])
        usada = insumos.buscar_unidad(con, linea.unidad_codigo) if linea.unidad_codigo else propia
        if usada.tipo != propia.tipo:
            raise insumos.UnidadInvalida  # no se convierte peso a volumen
        nuevas.append({"id": uuid7(), "item_id": item_id, "insumo_id": linea.insumo_id,
                       "cantidad": linea.cantidad, "unidad_codigo": usada.codigo})

    con.execute(
        ais.actualizar(ctx, ops_receta_linea, ops_receta_linea.c.item_id == item_id)
        .values(eliminado_en=ahora_utc(), eliminado_por=ctx.usuario_id)
    )
    for valores in nuevas:
        con.execute(ais.insertar(ctx, ops_receta_linea, valores))
    return obtener_receta(con, ctx, item_id)


def contar_items_con_receta(con: Connection, ctx: ais.ContextoNegocio) -> int:
    return con.execute(
        ais.seleccionar(ctx, ops_receta_linea,
                        sa.func.count(sa.distinct(ops_receta_linea.c.item_id)))
        .select_from(ops_receta_linea.join(
            ops_item, sa.and_(ops_item.c.id == ops_receta_linea.c.item_id,
                              ops_item.c.eliminado_en.is_(None))))
    ).scalar_one()


# ------------------------------------------------------------------ al vender y al anular

def consumir_por_venta(con: Connection, ctx: ais.ContextoNegocio, venta_id: uuid.UUID,
                       cantidades: dict[uuid.UUID, int]) -> list[str]:
    """Descuenta los insumos de lo vendido. Devuelve los que quedaron sin existencia.

    Una venta de ítems sin receta no toca el inventario. Nunca bloquea la venta: si falta insumo,
    la existencia queda negativa y se avisa.
    """
    if not cantidades:
        return []
    filas = con.execute(
        ais.seleccionar(
            ctx, ops_receta_linea, ops_receta_linea.c.item_id, ops_receta_linea.c.insumo_id,
            ops_receta_linea.c.cantidad, cat_unidad_medida.c.factor_a_base.label("factor"),
        )
        .select_from(ops_receta_linea.join(
            cat_unidad_medida, cat_unidad_medida.c.codigo == ops_receta_linea.c.unidad_codigo))
        .where(ops_receta_linea.c.item_id.in_(list(cantidades)))
    ).all()
    por_insumo: dict[uuid.UUID, Decimal] = defaultdict(lambda: CERO)
    for f in filas:
        por_insumo[f.insumo_id] += f.cantidad * f.factor * cantidades[f.item_id]

    sin_existencia: list[str] = []
    for insumo_id in sorted(por_insumo):  # siempre en el mismo orden: sin bloqueos cruzados
        try:
            fila = insumos.bloquear(con, ctx, insumo_id)
        except insumos.NoEncontrado:
            continue  # archivado: ya no se descuenta
        cantidad_base = por_insumo[insumo_id].quantize(insumos.CUATRO, ROUND_HALF_UP)
        if cantidad_base == 0:
            continue
        insumos.aplicar(con, ctx, fila, "consumo_venta", -cantidad_base, None,
                         origen_tipo=ORIGEN_VENTA, origen_id=venta_id)
        if fila.existencia_base - cantidad_base <= 0:
            sin_existencia.append(fila.nombre)
    return sorted(sin_existencia)


def devolver_por_anulacion(con: Connection, ctx: ais.ContextoNegocio, venta_id: uuid.UUID) -> None:
    """Regresa a cada insumo lo que esa venta consumió, al costo con que salió."""
    consumos = con.execute(
        ais.seleccionar(
            ctx, ops_movimiento_inventario, ops_movimiento_inventario.c.insumo_id,
            ops_movimiento_inventario.c.cantidad_base,
            ops_movimiento_inventario.c.costo_unitario_base,
        ).where(ops_movimiento_inventario.c.origen_tipo == ORIGEN_VENTA,
                ops_movimiento_inventario.c.origen_id == venta_id,
                ops_movimiento_inventario.c.tipo == "consumo_venta")
        .order_by(ops_movimiento_inventario.c.insumo_id)
    ).all()
    for consumo in consumos:
        try:
            fila = insumos.bloquear(con, ctx, consumo.insumo_id)
        except insumos.NoEncontrado:
            continue
        insumos.aplicar(con, ctx, fila, "reverso_venta", -consumo.cantidad_base, None,
                         origen_tipo=ORIGEN_VENTA, origen_id=venta_id,
                         costo_movimiento=consumo.costo_unitario_base)
