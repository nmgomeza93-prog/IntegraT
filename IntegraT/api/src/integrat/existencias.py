"""Cuánto queda de cada producto y si se puede vender (docs/ANALISIS_INVENTARIO_Y_CLIENTES.md).

- Un producto CONTROLA inventario si su receta tiene líneas con insumos vivos: la mercadería para
  revender (un insumo por producto o por variante) o un platillo con receta.
- Disponible de una variante = el mínimo, entre los insumos que consume, de
  `existencia ÷ lo que lleva una unidad`, redondeado hacia abajo (nunca negativo).
- Regla del negocio (`core_negocio.vender_sin_existencia`):
  - `bloquear`: no se cobra lo que no alcanza, ni lo que no controla inventario.
  - `avisar`: se cobra y se avisa (como antes).
"""

import uuid
from collections import defaultdict
from decimal import ROUND_FLOOR, Decimal

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from integrat.db import aislamiento as ais
from integrat.db.tablas import (
    cat_unidad_medida,
    core_cfg_tipo_negocio_plantilla,
    core_negocio,
    ops_insumo,
    ops_item_variante,
    ops_receta_linea,
)

BLOQUEAR = "bloquear"
AVISAR = "avisar"
AGOTADO = "agotado"
POCO = "poco"  # por agotarse: algún insumo llegó a su mínimo
_GRAVEDAD = {AGOTADO: 0, POCO: 1}


class SinExistencia(Exception):
    """Alguna línea pide más de lo que hay (o algo que no controla inventario) en modo bloquear."""

    def __init__(self, faltantes: list[tuple[str, int | None]]):
        super().__init__(faltantes)
        self.faltantes = faltantes  # (nombre, disponible; None = no controla inventario)

    def mensaje(self) -> str:
        partes = []
        for nombre, disponible in self.faltantes:
            if disponible is None:
                partes.append(f"{nombre} (aún no tiene inventario: cómpralo o impórtalo primero)")
            elif disponible == 0:
                partes.append(f"{nombre} (agotado)")
            else:
                partes.append(f"{nombre} (solo quedan {disponible})")
        return "No te alcanza para vender: " + "; ".join(partes) + "."


# ------------------------------------------------------------------ reglas del negocio

def operacion(con: Connection, negocio_id: uuid.UUID) -> dict:
    """La plantilla `operacion` del tipo de negocio (regla inicial y mercadería por defecto)."""
    tipo = con.execute(sa.select(core_negocio.c.tipo_negocio_codigo)
                       .where(core_negocio.c.id == negocio_id)).scalar_one()
    return con.execute(
        sa.select(core_cfg_tipo_negocio_plantilla.c.contenido).where(
            core_cfg_tipo_negocio_plantilla.c.tipo_negocio_codigo == tipo,
            core_cfg_tipo_negocio_plantilla.c.tipo_plantilla == "operacion")
    ).scalar_one_or_none() or {}


def regla(con: Connection, ctx: ais.ContextoNegocio) -> str:
    return con.execute(sa.select(core_negocio.c.vender_sin_existencia)
                       .where(core_negocio.c.id == ctx.negocio_id)).scalar_one()


# ------------------------------------------------------------------ cuánto queda

def _lineas(con: Connection, ctx: ais.ContextoNegocio, item_ids: list[uuid.UUID]):
    return con.execute(
        ais.seleccionar(ctx, ops_receta_linea, ops_receta_linea.c.item_id,
                        ops_receta_linea.c.item_variante_id, ops_receta_linea.c.insumo_id,
                        ops_receta_linea.c.cantidad,
                        cat_unidad_medida.c.factor_a_base.label("factor"),
                        ops_insumo.c.existencia_base, ops_insumo.c.stock_minimo_base)
        .select_from(
            ops_receta_linea
            .join(ops_insumo, sa.and_(ops_insumo.c.id == ops_receta_linea.c.insumo_id,
                                      ops_insumo.c.negocio_id == ctx.negocio_id,
                                      ops_insumo.c.eliminado_en.is_(None)))
            .join(cat_unidad_medida,
                  cat_unidad_medida.c.codigo == ops_receta_linea.c.unidad_codigo))
        .where(ops_receta_linea.c.item_id.in_(item_ids))
    ).all()


def _disponible(lineas, existencia: dict | None = None) -> int | None:
    """Unidades que alcanzan con esas líneas; None si no hay ninguna (no controla inventario)."""
    if not lineas:
        return None
    unidades = None
    for x in lineas:
        por_unidad = x.cantidad * x.factor
        if por_unidad <= 0:
            continue
        hay = existencia[x.insumo_id] if existencia is not None else x.existencia_base
        alcanza = max(0, int((Decimal(hay) / por_unidad).to_integral_value(rounding=ROUND_FLOOR)))
        unidades = alcanza if unidades is None else min(unidades, alcanza)
    return unidades


def disponibles(con: Connection, ctx: ais.ContextoNegocio, item_ids: list[uuid.UUID]
                ) -> tuple[dict[uuid.UUID, int | None], dict[uuid.UUID, int | None]]:
    """(por ítem, por variante). Un ítem con variantes suma lo de sus variantes."""
    if not item_ids:
        return {}, {}
    variantes = con.execute(
        ais.seleccionar(ctx, ops_item_variante, ops_item_variante.c.id,
                        ops_item_variante.c.item_id, ops_item_variante.c.atributos)
        .where(ops_item_variante.c.item_id.in_(item_ids))
    ).all()
    lineas = _lineas(con, ctx, item_ids)
    por_variante: dict[uuid.UUID, int | None] = {}
    por_item: dict[uuid.UUID, int | None] = {}
    agrupadas: dict[uuid.UUID, list] = defaultdict(list)
    for v in variantes:
        agrupadas[v.item_id].append(v)
    for item_id, filas in agrupadas.items():
        for v in filas:
            suyas = [x for x in lineas
                     if x.item_id == item_id and x.item_variante_id in (None, v.id)]
            por_variante[v.id] = _disponible(suyas)
        explicitas = [v for v in filas if v.atributos is not None] or filas
        valores = [por_variante[v.id] for v in explicitas if por_variante[v.id] is not None]
        por_item[item_id] = sum(valores) if valores else None
    return por_item, por_variante


def _estado(lineas, disponible: int | None) -> str | None:
    if disponible is None:
        return None
    if disponible <= 0:
        return AGOTADO
    if any(x.stock_minimo_base > 0 and x.existencia_base <= x.stock_minimo_base for x in lineas):
        return POCO
    return None


def _peor(estados: list[str | None]) -> str | None:
    presentes = [e for e in estados if e is not None]
    return min(presentes, key=_GRAVEDAD.get) if presentes else None


def estados(con: Connection, ctx: ais.ContextoNegocio, item_ids: list[uuid.UUID]
            ) -> tuple[dict[uuid.UUID, str | None], dict[uuid.UUID, str | None]]:
    """"agotado", "poco" o None por ítem y por variante (el ítem toma el peor de sus variantes)."""
    if not item_ids:
        return {}, {}
    variantes = con.execute(
        ais.seleccionar(ctx, ops_item_variante, ops_item_variante.c.id,
                        ops_item_variante.c.item_id, ops_item_variante.c.atributos)
        .where(ops_item_variante.c.item_id.in_(item_ids))
    ).all()
    lineas = _lineas(con, ctx, item_ids)
    por_variante: dict[uuid.UUID, str | None] = {}
    por_item: dict[uuid.UUID, str | None] = {}
    agrupadas: dict[uuid.UUID, list] = defaultdict(list)
    for v in variantes:
        agrupadas[v.item_id].append(v)
    for item_id, filas in agrupadas.items():
        for v in filas:
            suyas = [x for x in lineas
                     if x.item_id == item_id and x.item_variante_id in (None, v.id)]
            por_variante[v.id] = _estado(suyas, _disponible(suyas))
        explicitas = [v for v in filas if v.atributos is not None] or filas
        por_item[item_id] = _peor([por_variante[v.id] for v in explicitas])
    return por_item, por_variante


def alertas(con: Connection, ctx: ais.ContextoNegocio) -> dict:
    """Lo agotado o por agotarse: productos (por variante) e ingredientes, lo agotado primero."""
    from integrat.db.tablas import ops_item  # aquí: evita un ciclo al importar

    items = con.execute(ais.seleccionar(ctx, ops_item, ops_item.c.id, ops_item.c.nombre)).all()
    nombres = {i.id: i.nombre for i in items}
    _, por_variante = estados(con, ctx, list(nombres))
    _, disponibles_var = disponibles(con, ctx, list(nombres))
    variantes = con.execute(
        ais.seleccionar(ctx, ops_item_variante, ops_item_variante.c.id,
                        ops_item_variante.c.item_id, ops_item_variante.c.nombre,
                        ops_item_variante.c.atributos)
        .where(ops_item_variante.c.item_id.in_(list(nombres)))
    ).all() if nombres else []
    con_atributos = {v.item_id for v in variantes if v.atributos is not None}
    productos = []
    for v in variantes:
        if v.atributos is None and v.item_id in con_atributos:
            continue  # la implícita de un producto con tallas no cuenta
        estado = por_variante.get(v.id)
        if estado is None:
            continue
        nombre = nombres[v.item_id] if v.atributos is None else f"{nombres[v.item_id]} · {v.nombre}"
        productos.append({"item_id": v.item_id, "item_variante_id": v.id, "nombre": nombre,
                          "disponible": disponibles_var.get(v.id), "estado": estado})
    ingredientes = []
    for i in con.execute(
        ais.seleccionar(ctx, ops_insumo, ops_insumo.c.id, ops_insumo.c.nombre,
                        ops_insumo.c.existencia_base, ops_insumo.c.stock_minimo_base,
                        ops_insumo.c.unidad_codigo)
        .where(ops_insumo.c.item_id.is_(None))
    ):
        if i.existencia_base <= 0:
            estado = AGOTADO
        elif i.stock_minimo_base > 0 and i.existencia_base <= i.stock_minimo_base:
            estado = POCO
        else:
            continue
        ingredientes.append({"insumo_id": i.id, "nombre": i.nombre, "estado": estado,
                             "unidad_codigo": i.unidad_codigo})
    orden = lambda x: (_GRAVEDAD[x["estado"]], x["nombre"].casefold())  # noqa: E731
    return {"productos": sorted(productos, key=orden),
            "ingredientes": sorted(ingredientes, key=orden)}


# ------------------------------------------------------------------ al vender

def verificar(con: Connection, ctx: ais.ContextoNegocio,
              pedidas: dict[tuple[uuid.UUID, uuid.UUID], int], nombres: dict) -> None:
    """En modo `bloquear`, que todo lo pedido alcance; si no, SinExistencia (no se cobra nada).

    `pedidas`: (ítem, variante) -> unidades; `nombres`: la misma clave -> nombre para el mensaje.
    Los insumos se bloquean (en orden) antes de leer su existencia: dos ventas a la vez no se
    llevan lo mismo.
    """
    if not pedidas or regla(con, ctx) != BLOQUEAR:
        return
    lineas = _lineas(con, ctx, list({i for i, _ in pedidas}))
    insumos = sorted({x.insumo_id for x in lineas})
    existencia: dict[uuid.UUID, Decimal] = {}
    for insumo_id in insumos:
        existencia[insumo_id] = Decimal(con.execute(
            ais.seleccionar(ctx, ops_insumo, ops_insumo.c.existencia_base)
            .where(ops_insumo.c.id == insumo_id).with_for_update()).scalar_one())
    # Lo que se necesita de cada insumo para toda la venta (dos tallas pueden compartir insumo).
    necesita: dict[uuid.UUID, Decimal] = defaultdict(Decimal)
    faltantes: list[tuple[str, int | None]] = []
    for (item_id, variante_id), unidades in pedidas.items():
        suyas = [x for x in lineas
                 if x.item_id == item_id and x.item_variante_id in (None, variante_id)]
        if not suyas:
            faltantes.append((nombres[(item_id, variante_id)], None))
            continue
        for x in suyas:
            necesita[x.insumo_id] += x.cantidad * x.factor * unidades
    for item_id, variante_id in pedidas:
        suyas = [x for x in lineas
                 if x.item_id == item_id and x.item_variante_id in (None, variante_id)]
        if suyas and any(necesita[x.insumo_id] > existencia[x.insumo_id] for x in suyas):
            faltantes.append((nombres[(item_id, variante_id)], _disponible(suyas, existencia)))
    if faltantes:
        raise SinExistencia(faltantes)
