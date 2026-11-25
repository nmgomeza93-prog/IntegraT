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


_GRAVEDAD = {"pierde": 0, "bajo": 1, "ok": 2}


def _info(costo: Decimal | None, completo: bool, precio: Decimal, margen_obj: Decimal,
          propio: bool, trat) -> InfoPrecio:
    sugerido = margen_actual = aviso = None
    if costo is not None and costo > 0 and completo:
        sugerido = sugerir(costo, margen_obj, trat)
        margen_actual, aviso = evaluar(precio, costo, margen_obj, trat)
    return InfoPrecio(costo=costo, costo_completo=completo, margen_objetivo=margen_obj,
                      margen_propio=propio, precio_sugerido=sugerido,
                      margen_actual=margen_actual, aviso=aviso)


def calcular(con: Connection, ctx: ais.ContextoNegocio, item_ids: list[uuid.UUID]
             ) -> tuple[dict[uuid.UUID, InfoPrecio], dict[uuid.UUID, InfoPrecio]]:
    """Costo, sugerido y aviso por ítem y por variante, en pocas consultas.

    Cada variante cuesta las líneas comunes de la receta más las suyas (su mercadería). Un ítem
    sin variantes toma la de su variante implícita; uno con variantes, el aviso más grave de ellas
    (sin un sugerido único: cada variante tiene el suyo). Devuelve (por ítem, por variante).
    """
    if not item_ids:
        return {}, {}
    trat = tratamiento_iva(con, ctx)
    del_negocio = margen_del_negocio(con, ctx)
    variantes = con.execute(
        ais.seleccionar(ctx, ops_item, ops_item.c.id.label("item_id"), ops_item.c.margen_objetivo,
                        ops_item_variante.c.id.label("variante_id"),
                        ops_item_variante.c.precio_venta, ops_item_variante.c.atributos,
                        incluir_eliminados=True)
        .select_from(ops_item.join(ops_item_variante, sa.and_(
            ops_item_variante.c.item_id == ops_item.c.id,
            ops_item_variante.c.negocio_id == ctx.negocio_id,
            ops_item_variante.c.eliminado_en.is_(None))))
        .where(ops_item.c.id.in_(item_ids))
        .order_by(ops_item_variante.c.creado_en)
    ).all()
    lineas = con.execute(
        ais.seleccionar(ctx, ops_receta_linea, ops_receta_linea.c.item_id,
                        ops_receta_linea.c.item_variante_id, ops_receta_linea.c.cantidad,
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
    ).all()

    por_variante: dict[uuid.UUID, InfoPrecio] = {}
    por_item: dict[uuid.UUID, InfoPrecio] = {}
    agrupadas: dict[uuid.UUID, list] = defaultdict(list)
    for v in variantes:
        agrupadas[v.item_id].append(v)
    for item_id, filas in agrupadas.items():
        propio = filas[0].margen_objetivo is not None
        margen_obj = Decimal(filas[0].margen_objetivo) if propio else del_negocio
        con_atributos = [v for v in filas if v.atributos is not None]
        for v in filas:
            suyas = [x for x in lineas
                     if x.item_id == item_id and x.item_variante_id in (None, v.variante_id)]
            costo = (sum((x.cantidad * x.factor * x.costo_promedio_base for x in suyas), CERO)
                     .quantize(CENTAVOS, ROUND_HALF_UP)) if suyas else None
            completo = not any(x.costo_promedio_base == 0 and x.insumo_archivado is None
                               for x in suyas)
            por_variante[v.variante_id] = _info(costo, completo, Decimal(v.precio_venta),
                                                margen_obj, propio, trat)
        if not con_atributos:
            por_item[item_id] = por_variante[filas[0].variante_id]
            continue
        infos = [por_variante[v.variante_id] for v in con_atributos]
        avisos = [i.aviso for i in infos if i.aviso is not None]
        costos = [i.costo for i in infos if i.costo is not None]
        por_item[item_id] = InfoPrecio(
            costo=min(costos) if costos else None,
            costo_completo=all(i.costo_completo for i in infos), margen_objetivo=margen_obj,
            margen_propio=propio, precio_sugerido=None, margen_actual=None,
            aviso=min(avisos, key=_GRAVEDAD.get) if avisos else None)
    return por_item, por_variante


def para_items(con: Connection, ctx: ais.ContextoNegocio,
               item_ids: list[uuid.UUID]) -> dict[uuid.UUID, InfoPrecio]:
    """Costo, sugerido y aviso de varios ítems (para la lista del catálogo y la ficha)."""
    return calcular(con, ctx, item_ids)[0]
