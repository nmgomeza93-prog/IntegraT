"""Precio sugerido y avisos de precio (dueño de la fórmula: la API; docs/PLAN_PRECIO_SUGERIDO.md).

- Costo de una unidad vendida = su receta al costo promedio de cada insumo (como en la ficha).
- Margen objetivo = el propio del ítem o, si no tiene, el del negocio.
- Precio sugerido = costo / (1 − margen), más el IVA si el régimen lo separa (el precio de venta lo
  lleva incluido), redondeado HACIA ARRIBA a Q0.50: nunca queda por debajo del margen.
- Aviso: "pierde" si el precio (sin IVA) no cubre el costo; "bajo" si cubre el costo pero no el
  margen objetivo; "ok" si lo cubre. Sin receta o con insumos sin costo, no hay aviso ni sugerido.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from integrat.contabilidad.motor import Tratamiento, separar_iva, tratamiento_iva
from integrat.db import aislamiento as ais
from integrat.db.tablas import (
    cat_unidad_medida,
    core_negocio,
    ops_insumo,
    ops_item,
    ops_item_variante,
    ops_receta_linea,
)

CENTAVOS = Decimal("0.01")
MEDIO_QUETZAL = Decimal("0.50")
CERO = Decimal("0")


@dataclass(frozen=True)
class InfoPrecio:
    costo: Decimal | None            # None si no tiene receta
    costo_completo: bool
    margen_objetivo: Decimal
    margen_propio: bool
    precio_sugerido: Decimal | None
    margen_actual: Decimal | None    # del precio sin IVA, entre 0 y 1 (puede ser negativo)
    aviso: str | None                # "pierde", "bajo", "ok" o None


def redondear_arriba(valor: Decimal, paso: Decimal = MEDIO_QUETZAL) -> Decimal:
    return ((valor / paso).to_integral_value(rounding=ROUND_CEILING) * paso).quantize(CENTAVOS)


def sugerir(costo: Decimal, margen: Decimal, trat: Tratamiento) -> Decimal | None:
    if costo <= 0 or margen >= 1:
        return None
    sin_iva = costo / (1 - margen)
    con_iva = sin_iva * (1 + trat.tasa) if trat.separa else sin_iva
    return redondear_arriba(con_iva)


def evaluar(precio: Decimal, costo: Decimal, margen_objetivo: Decimal,
            trat: Tratamiento) -> tuple[Decimal | None, str]:
    """(margen actual, aviso) del precio de venta actual frente al costo."""
    neto, _ = separar_iva(precio, trat)
    if neto <= 0:
        return None, "pierde"
    margen = ((neto - costo) / neto).quantize(Decimal("0.0001"), ROUND_HALF_UP)
    if neto < costo:
        return margen, "pierde"
    if margen < margen_objetivo:
        return margen, "bajo"
    return margen, "ok"


def margen_del_negocio(con: Connection, ctx: ais.ContextoNegocio) -> Decimal:
    return Decimal(con.execute(
        sa.select(core_negocio.c.margen_objetivo_defecto)
        .where(core_negocio.c.id == ctx.negocio_id)).scalar_one())


def para_items(con: Connection, ctx: ais.ContextoNegocio,
               item_ids: list[uuid.UUID]) -> dict[uuid.UUID, InfoPrecio]:
    """Costo, sugerido y aviso de varios ítems en pocas consultas (para la lista del catálogo)."""
    if not item_ids:
        return {}
    trat = tratamiento_iva(con, ctx)
    del_negocio = margen_del_negocio(con, ctx)
    datos = {
        f.id: f for f in con.execute(
            ais.seleccionar(ctx, ops_item, ops_item.c.id, ops_item.c.margen_objetivo,
                            ops_item_variante.c.precio_venta, incluir_eliminados=True)
            .select_from(ops_item.join(ops_item_variante, sa.and_(
                ops_item_variante.c.item_id == ops_item.c.id,
                ops_item_variante.c.negocio_id == ctx.negocio_id,
                ops_item_variante.c.eliminado_en.is_(None))))
            .where(ops_item.c.id.in_(item_ids))
        )
    }
    costos: dict[uuid.UUID, Decimal] = defaultdict(lambda: CERO)
    completos: dict[uuid.UUID, bool] = defaultdict(lambda: True)
    for f in con.execute(
        ais.seleccionar(ctx, ops_receta_linea, ops_receta_linea.c.item_id,
                        ops_receta_linea.c.cantidad,
                        cat_unidad_medida.c.factor_a_base.label("factor"),
                        ops_insumo.c.costo_promedio_base,
                        ops_insumo.c.eliminado_en.label("insumo_archivado"))
        .select_from(
            ops_receta_linea
            .join(ops_insumo, sa.and_(ops_insumo.c.id == ops_receta_linea.c.insumo_id,
                                      ops_insumo.c.negocio_id == ctx.negocio_id))
            .join(cat_unidad_medida,
                  cat_unidad_medida.c.codigo == ops_receta_linea.c.unidad_codigo))
        .where(ops_receta_linea.c.item_id.in_(item_ids))
    ):
        costos[f.item_id] += f.cantidad * f.factor * f.costo_promedio_base
        if f.costo_promedio_base == 0 and f.insumo_archivado is None:
            completos[f.item_id] = False

    resultado: dict[uuid.UUID, InfoPrecio] = {}
    for item_id, d in datos.items():
        propio = d.margen_objetivo is not None
        margen_obj = Decimal(d.margen_objetivo) if propio else del_negocio
        tiene_receta = item_id in costos
        costo = costos[item_id].quantize(CENTAVOS, ROUND_HALF_UP) if tiene_receta else None
        completo = completos[item_id]
        sugerido = margen_actual = aviso = None
        if costo is not None and costo > 0 and completo:
            sugerido = sugerir(costo, margen_obj, trat)
            margen_actual, aviso = evaluar(Decimal(d.precio_venta), costo, margen_obj, trat)
        resultado[item_id] = InfoPrecio(
            costo=costo, costo_completo=completo, margen_objetivo=margen_obj,
            margen_propio=propio, precio_sugerido=sugerido, margen_actual=margen_actual,
            aviso=aviso)
    return resultado
