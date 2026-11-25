"""Atributos (talla, color…), atributos por categoría y variantes de los productos.

Reglas (docs/PLAN_VARIANTES.md):
- Cada negocio recibe los atributos de su tipo de negocio (plantilla `variantes`) la primera vez.
- Los valores nuevos de una variante se agregan solos al atributo; los atributos se crean aparte.
- Las variantes de un producto se guardan completas (como la receta): las que no vienen se
  archivan. Al darle variantes, la implícita ("Única", sin atributos) se archiva; sin variantes,
  vuelve a existir.
"""

import uuid
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from integrat.db import aislamiento as ais
from integrat.db.tablas import (
    core_cfg_tipo_negocio_plantilla,
    core_negocio,
    ops_atributo,
    ops_atributo_valor,
    ops_categoria,
    ops_categoria_atributo,
    ops_item,
    ops_item_variante,
)
from integrat.db.tipos import ahora_utc, uuid7
from integrat.variantes.esquemas import (
    AtributoIn,
    AtributoOut,
    CategoriaSugeridaOut,
    ValorOut,
    VarianteOut,
    VariantesIn,
)

SEPARADOR = " · "


class NoEncontrado(Exception):
    pass


class NombreRepetido(Exception):
    pass


class AtributoDesconocido(Exception):
    def __init__(self, nombre: str):
        super().__init__(nombre)
        self.nombre = nombre


class VarianteRepetida(Exception):
    pass


class VarianteInvalida(Exception):
    """Un id de variante que no es de este producto (o ya está archivada)."""


def _clave(texto: str) -> str:
    return " ".join(texto.split()).casefold()


# ------------------------------------------------------------------ plantilla del tipo de negocio

def _plantilla(con: Connection, ctx: ais.ContextoNegocio) -> dict:
    tipo = con.execute(
        sa.select(core_negocio.c.tipo_negocio_codigo).where(core_negocio.c.id == ctx.negocio_id)
    ).scalar_one()
    return con.execute(
        sa.select(core_cfg_tipo_negocio_plantilla.c.contenido).where(
            core_cfg_tipo_negocio_plantilla.c.tipo_negocio_codigo == tipo,
            core_cfg_tipo_negocio_plantilla.c.tipo_plantilla == "variantes")
    ).scalar_one_or_none() or {}


def asegurar_atributos(con: Connection, ctx: ais.ContextoNegocio) -> None:
    """La primera vez, el negocio recibe los atributos de su tipo (serializado por el negocio)."""
    hay = ais.seleccionar(ctx, ops_atributo, ops_atributo.c.id, incluir_eliminados=True).limit(1)
    if con.execute(hay).first() is not None:
        return
    con.execute(sa.select(core_negocio.c.id).where(core_negocio.c.id == ctx.negocio_id)
                .with_for_update())
    if con.execute(hay).first() is not None:
        return
    for orden, atributo in enumerate(_plantilla(con, ctx).get("atributos", [])):
        _insertar_atributo(con, ctx, atributo["nombre"], atributo.get("valores", []), orden)


def _insertar_atributo(con, ctx, nombre: str, valores: list[str], orden: int) -> uuid.UUID:
    atributo_id = uuid7()
    con.execute(ais.insertar(ctx, ops_atributo, {"id": atributo_id, "nombre": nombre,
                                                 "orden": orden}))
    vistos: set[str] = set()
    for i, valor in enumerate(valores):
        if _clave(str(valor)) in vistos:
            continue
        vistos.add(_clave(str(valor)))
        con.execute(ais.insertar(ctx, ops_atributo_valor, {
            "id": uuid7(), "atributo_id": atributo_id, "valor": str(valor), "orden": i}))
    return atributo_id


# ------------------------------------------------------------------ atributos

def listar_atributos(con: Connection, ctx: ais.ContextoNegocio) -> list[AtributoOut]:
    atributos = con.execute(
        ais.seleccionar(ctx, ops_atributo, ops_atributo.c.id, ops_atributo.c.nombre)
        .order_by(ops_atributo.c.orden, ops_atributo.c.nombre)
    ).all()
    valores: dict[uuid.UUID, list[ValorOut]] = {a.id: [] for a in atributos}
    for v in con.execute(
        ais.seleccionar(ctx, ops_atributo_valor, ops_atributo_valor.c.id,
                        ops_atributo_valor.c.atributo_id, ops_atributo_valor.c.valor)
        .order_by(ops_atributo_valor.c.orden, ops_atributo_valor.c.valor)
    ):
        if v.atributo_id in valores:
            valores[v.atributo_id].append(ValorOut(id=v.id, valor=v.valor))
    return [AtributoOut(id=a.id, nombre=a.nombre, valores=valores[a.id]) for a in atributos]


def _atributos_por_clave(con: Connection, ctx: ais.ContextoNegocio) -> dict[str, tuple]:
    """clave del nombre -> (id, nombre, orden)."""
    return {
        _clave(f.nombre): (f.id, f.nombre, f.orden) for f in con.execute(
            ais.seleccionar(ctx, ops_atributo, ops_atributo.c.id, ops_atributo.c.nombre,
                            ops_atributo.c.orden))
    }


def crear_atributo(con: Connection, ctx: ais.ContextoNegocio, datos: AtributoIn) -> AtributoOut:
    asegurar_atributos(con, ctx)
    existentes = _atributos_por_clave(con, ctx)
    if _clave(datos.nombre) in existentes:
        raise NombreRepetido
    orden = max((o for _, _, o in existentes.values()), default=-1) + 1
    atributo_id = _insertar_atributo(con, ctx, datos.nombre, datos.valores, orden)
    return next(a for a in listar_atributos(con, ctx) if a.id == atributo_id)


def _valor_canonico(con, ctx, atributo_id: uuid.UUID, valor: str) -> str:
    """El valor tal como ya existe (sin importar mayúsculas) o, si es nuevo, lo agrega."""
    filas = con.execute(
        ais.seleccionar(ctx, ops_atributo_valor, ops_atributo_valor.c.valor,
                        ops_atributo_valor.c.orden)
        .where(ops_atributo_valor.c.atributo_id == atributo_id)
    ).all()
    for f in filas:
        if _clave(f.valor) == _clave(valor):
            return f.valor
    valor = " ".join(valor.split())
    con.execute(ais.insertar(ctx, ops_atributo_valor, {
        "id": uuid7(), "atributo_id": atributo_id, "valor": valor,
        "orden": max((f.orden for f in filas), default=-1) + 1}))
    return valor


def agregar_valor(con: Connection, ctx: ais.ContextoNegocio, atributo_id: uuid.UUID,
                  valor: str) -> AtributoOut:
    existe = con.execute(ais.seleccionar(ctx, ops_atributo, ops_atributo.c.id)
                         .where(ops_atributo.c.id == atributo_id)).first()
    if existe is None:
        raise NoEncontrado
    _valor_canonico(con, ctx, atributo_id, valor)
    return next(a for a in listar_atributos(con, ctx) if a.id == atributo_id)


# ------------------------------------------------------------------ categorías

def atributos_de_categorias(con: Connection, ctx: ais.ContextoNegocio,
                            categoria_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
    resultado: dict[uuid.UUID, list[str]] = {c: [] for c in categoria_ids}
    if not categoria_ids:
        return resultado
    for f in con.execute(
        ais.seleccionar(ctx, ops_categoria_atributo, ops_categoria_atributo.c.categoria_id,
                        ops_atributo.c.nombre)
        .select_from(ops_categoria_atributo.join(ops_atributo, sa.and_(
            ops_atributo.c.id == ops_categoria_atributo.c.atributo_id,
            ops_atributo.c.negocio_id == ctx.negocio_id, ops_atributo.c.eliminado_en.is_(None))))
        .where(ops_categoria_atributo.c.categoria_id.in_(categoria_ids))
        .order_by(ops_categoria_atributo.c.orden)
    ):
        resultado[f.categoria_id].append(f.nombre)
    return resultado


def fijar_atributos_categoria(con: Connection, ctx: ais.ContextoNegocio, categoria_id: uuid.UUID,
                              atributo_ids: list[uuid.UUID]) -> list[str]:
    existe = con.execute(ais.seleccionar(ctx, ops_categoria, ops_categoria.c.id)
                         .where(ops_categoria.c.id == categoria_id).with_for_update()).first()
    if existe is None:
        raise NoEncontrado
    validos = {f.id for f in con.execute(
        ais.seleccionar(ctx, ops_atributo, ops_atributo.c.id)
        .where(ops_atributo.c.id.in_(atributo_ids)))} if atributo_ids else set()
    if len(validos) != len(set(atributo_ids)):
        raise AtributoDesconocido("?")
    con.execute(ais.actualizar(ctx, ops_categoria_atributo,
                               ops_categoria_atributo.c.categoria_id == categoria_id)
                .values(eliminado_en=ahora_utc(), eliminado_por=ctx.usuario_id))
    for orden, atributo_id in enumerate(dict.fromkeys(atributo_ids)):
        con.execute(ais.insertar(ctx, ops_categoria_atributo, {
            "id": uuid7(), "categoria_id": categoria_id, "atributo_id": atributo_id,
            "orden": orden}))
    return atributos_de_categorias(con, ctx, [categoria_id])[categoria_id]


def categorias_sugeridas(con: Connection, ctx: ais.ContextoNegocio) -> list[CategoriaSugeridaOut]:
    return [
        CategoriaSugeridaOut(nombre=c["nombre"], icono=c.get("icono"),
                             atributos=list(c.get("atributos", [])),
                             palabras_clave=[str(p) for p in c.get("palabras_clave", [])])
        for c in _plantilla(con, ctx).get("categorias_sugeridas", [])
    ]


def aplicar_sugerencia(con: Connection, ctx: ais.ContextoNegocio, categoria_id: uuid.UUID,
                       nombre: str) -> None:
    """Si la categoría nueva se llama como una sugerida, recibe sus atributos y palabras clave."""
    sugerida = next((c for c in categorias_sugeridas(con, ctx)
                     if _clave(c.nombre) == _clave(nombre)), None)
    if sugerida is None:
        return
    asegurar_atributos(con, ctx)
    por_clave = _atributos_por_clave(con, ctx)
    ids = [por_clave[_clave(a)][0] for a in sugerida.atributos if _clave(a) in por_clave]
    con.execute(ais.actualizar(ctx, ops_categoria, ops_categoria.c.id == categoria_id)
                .values(palabras_clave=sugerida.palabras_clave))
    if ids:
        fijar_atributos_categoria(con, ctx, categoria_id, ids)


# ------------------------------------------------------------------ variantes

def nombre_de_variante(atributos: dict[str, str], orden: list[str]) -> str:
    claves = sorted(atributos, key=lambda k: orden.index(k) if k in orden else len(orden))
    return SEPARADOR.join(atributos[k] for k in claves)[:80]


def variantes_de(con: Connection, ctx: ais.ContextoNegocio,
                 item_ids: list[uuid.UUID]) -> dict[uuid.UUID, list]:
    """Variantes vivas CON atributos (las de verdad) de varios ítems, en orden de creación."""
    resultado: dict[uuid.UUID, list] = {i: [] for i in item_ids}
    if not item_ids:
        return resultado
    for f in con.execute(
        ais.seleccionar(ctx, ops_item_variante, ops_item_variante.c.id,
                        ops_item_variante.c.item_id, ops_item_variante.c.nombre,
                        ops_item_variante.c.atributos, ops_item_variante.c.codigo,
                        ops_item_variante.c.precio_venta)
        .where(ops_item_variante.c.item_id.in_(item_ids),
               ops_item_variante.c.atributos.is_not(None))
        .order_by(ops_item_variante.c.creado_en, ops_item_variante.c.id)
    ):
        resultado[f.item_id].append(f)
    return resultado


def variante_out(f, precio=None) -> VarianteOut:
    return VarianteOut(
        id=f.id, nombre=f.nombre, atributos=dict(f.atributos or {}), codigo=f.codigo,
        precio_venta=f"{Decimal(f.precio_venta):.2f}",
        precio_sugerido=None if precio is None or precio.precio_sugerido is None
        else f"{precio.precio_sugerido:.2f}",
        aviso_precio=None if precio is None else precio.aviso,
    )


def guardar_variantes(con: Connection, ctx: ais.ContextoNegocio, item_id: uuid.UUID,
                      datos: VariantesIn) -> list[uuid.UUID]:
    """Deja el producto con exactamente estas variantes. Devuelve los ids de las vivas."""
    item = con.execute(ais.seleccionar(ctx, ops_item, ops_item.c.id)
                       .where(ops_item.c.id == item_id).with_for_update()).first()
    if item is None:
        raise NoEncontrado
    asegurar_atributos(con, ctx)
    por_clave = _atributos_por_clave(con, ctx)
    orden_atributos = [n for _, n, _ in sorted(por_clave.values(), key=lambda t: t[2])]

    vivas = con.execute(
        ais.seleccionar(ctx, ops_item_variante, ops_item_variante.c.id,
                        ops_item_variante.c.atributos, ops_item_variante.c.precio_venta)
        .where(ops_item_variante.c.item_id == item_id)
        .order_by(ops_item_variante.c.creado_en)
    ).all()
    explicitas = {v.id for v in vivas if v.atributos is not None}

    normalizadas = []
    combinaciones: set[tuple] = set()
    for v in datos.variantes:
        if v.id is not None and v.id not in explicitas:
            raise VarianteInvalida
        atributos: dict[str, str] = {}
        for nombre, valor in v.atributos.items():
            if _clave(nombre) not in por_clave:
                raise AtributoDesconocido(nombre)
            atributo_id, canonico, _ = por_clave[_clave(nombre)]
            atributos[canonico] = _valor_canonico(con, ctx, atributo_id, valor)
        combinacion = tuple(sorted((_clave(k), _clave(x)) for k, x in atributos.items()))
        if combinacion in combinaciones:
            raise VarianteRepetida
        combinaciones.add(combinacion)
        normalizadas.append((v, atributos))

    archivar = ais.actualizar(ctx, ops_item_variante, ops_item_variante.c.item_id == item_id)
    quedan = {v.id for v, _ in normalizadas if v.id is not None}
    for viva in vivas:
        es_implicita = viva.atributos is None
        if (es_implicita and normalizadas) or (not es_implicita and viva.id not in quedan):
            con.execute(archivar.where(ops_item_variante.c.id == viva.id)
                        .values(eliminado_en=ahora_utc(), eliminado_por=ctx.usuario_id))

    ids: list[uuid.UUID] = []
    for v, atributos in normalizadas:
        valores = {"atributos": atributos, "nombre": nombre_de_variante(atributos, orden_atributos),
                   "codigo": v.codigo, "precio_venta": v.precio_venta}
        if v.id is not None:
            con.execute(ais.actualizar(ctx, ops_item_variante, ops_item_variante.c.id == v.id)
                        .values(**valores, version=ops_item_variante.c.version + 1,
                                actualizado_por=ctx.usuario_id))
            ids.append(v.id)
        else:
            nueva = uuid7()
            con.execute(ais.insertar(ctx, ops_item_variante, {"id": nueva, "item_id": item_id,
                                                               **valores}))
            ids.append(nueva)

    if not normalizadas and not any(v.atributos is None for v in vivas):
        # Sin variantes: vuelve la implícita que tenía (con su precio y su inventario).
        anterior = con.execute(
            ais.seleccionar(ctx, ops_item_variante, ops_item_variante.c.id,
                            incluir_eliminados=True)
            .where(ops_item_variante.c.item_id == item_id,
                   ops_item_variante.c.atributos.is_(None))
            .order_by(ops_item_variante.c.creado_en.desc()).limit(1)
        ).first()
        if anterior is not None:
            con.execute(sa.update(ops_item_variante).where(
                ops_item_variante.c.id == anterior.id,
                ops_item_variante.c.negocio_id == ctx.negocio_id).values(
                eliminado_en=None, eliminado_por=None, actualizado_por=ctx.usuario_id))
            ids.append(anterior.id)
        else:
            nueva = uuid7()
            con.execute(ais.insertar(ctx, ops_item_variante, {
                "id": nueva, "item_id": item_id, "nombre": "Única",
                "precio_venta": vivas[0].precio_venta if vivas else Decimal("0")}))
            ids.append(nueva)
    # Si el producto se compra hecho, cada variante tiene su inventario (docs/PLAN_VARIANTES.md).
    from integrat.insumos import mercaderia  # aquí: mercaderia -> recetas -> precios -> ...

    mercaderia.sincronizar(con, ctx, item_id)
    return ids
