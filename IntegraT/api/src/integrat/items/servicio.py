"""Catálogo de productos y platillos. Todo acceso a tablas de negocio pasa por db.aislamiento.

Cada ítem tiene una variante implícita ("Única") que guarda el precio de venta, o variantes de
verdad con talla, color… (docs/PLAN_VARIANTES.md); su precio de lista es el más bajo.
"""

import hashlib
import json
import uuid
from datetime import timedelta

import sqlalchemy as sa
from sqlalchemy.engine import Connection, Engine

from integrat import existencias, precios
from integrat.db import aislamiento as ais
from integrat.db.tablas import (
    core_cfg_tipo_negocio_plantilla,
    core_idempotencia,
    core_negocio,
    ops_categoria,
    ops_item,
    ops_item_variante,
    ops_receta_linea,
)
from integrat.db.tipos import ahora_utc, uuid7
from integrat.insumos import mercaderia
from integrat.items.esquemas import (
    CategoriaCambios,
    CategoriaIn,
    CategoriaOut,
    ItemCambios,
    ItemIn,
    ItemOut,
    ListaItemsOut,
)
from integrat.variantes import servicio as variantes

OPERACION_CREAR_ITEM = "crear_item"
VIGENCIA_IDEMPOTENCIA = timedelta(hours=24)
NOMBRE_VARIANTE_IMPLICITA = "Única"


class NoEncontrado(Exception):
    pass


class VersionDesfasada(Exception):
    """Alguien más cambió el registro después de que la persona lo vio."""


class CategoriaInvalida(Exception):
    pass


class NombreRepetido(Exception):
    pass


class ClaveReutilizada(Exception):
    """La misma Idempotency-Key llegó con datos distintos."""


def _escapar_like(texto: str) -> str:
    return texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# ------------------------------------------------------------------ categorías

def _categoria_out(fila, atributos: list[str] | None = None) -> CategoriaOut:
    return CategoriaOut(id=fila.id, nombre=fila.nombre, orden=fila.orden, icono=fila.icono,
                        cantidad_items=fila.cantidad_items, version=fila.version,
                        atributos=atributos or [])


def _consulta_categorias(ctx: ais.ContextoNegocio) -> sa.Select:
    cantidad = (
        sa.select(sa.func.count())
        .where(ops_item.c.categoria_id == ops_categoria.c.id,
               ops_item.c.negocio_id == ctx.negocio_id,
               ops_item.c.eliminado_en.is_(None))
        .scalar_subquery()
    )
    return ais.seleccionar(
        ctx, ops_categoria, ops_categoria.c.id, ops_categoria.c.nombre, ops_categoria.c.orden,
        ops_categoria.c.icono, ops_categoria.c.version, cantidad.label("cantidad_items"),
    )


def listar_categorias(con: Connection, ctx: ais.ContextoNegocio) -> list[CategoriaOut]:
    filas = con.execute(
        _consulta_categorias(ctx).order_by(ops_categoria.c.orden, ops_categoria.c.nombre)
    ).all()
    atributos = variantes.atributos_de_categorias(con, ctx, [f.id for f in filas])
    return [_categoria_out(f, atributos[f.id]) for f in filas]


def _categoria_existe(con: Connection, ctx: ais.ContextoNegocio, categoria_id: uuid.UUID) -> bool:
    return con.execute(
        ais.seleccionar(ctx, ops_categoria, ops_categoria.c.id)
        .where(ops_categoria.c.id == categoria_id)
    ).first() is not None


def _nombre_de_categoria_repetido(con, ctx, nombre: str, excepto: uuid.UUID | None) -> bool:
    consulta = ais.seleccionar(ctx, ops_categoria, ops_categoria.c.id).where(
        ops_categoria.c.nombre == nombre
    )
    if excepto is not None:
        consulta = consulta.where(ops_categoria.c.id != excepto)
    return con.execute(consulta).first() is not None


def crear_categoria(con: Connection, ctx: ais.ContextoNegocio, datos: CategoriaIn) -> CategoriaOut:
    if _nombre_de_categoria_repetido(con, ctx, datos.nombre, None):
        raise NombreRepetido
    ultimo = con.execute(
        ais.seleccionar(ctx, ops_categoria, sa.func.max(ops_categoria.c.orden))
    ).scalar()
    categoria_id = uuid7()
    con.execute(ais.insertar(ctx, ops_categoria, {
        "id": categoria_id, "nombre": datos.nombre, "icono": datos.icono,
        "orden": 0 if ultimo is None else ultimo + 1,
    }))
    variantes.aplicar_sugerencia(con, ctx, categoria_id, datos.nombre)  # Ropa -> talla y color
    return _categoria_out(con.execute(
        _consulta_categorias(ctx).where(ops_categoria.c.id == categoria_id)
    ).one(), variantes.atributos_de_categorias(con, ctx, [categoria_id])[categoria_id])


def actualizar_categoria(con: Connection, ctx: ais.ContextoNegocio, categoria_id: uuid.UUID,
                         cambios: CategoriaCambios) -> CategoriaOut:
    actual = con.execute(
        ais.seleccionar(ctx, ops_categoria, ops_categoria.c.version)
        .where(ops_categoria.c.id == categoria_id)
    ).first()
    if actual is None:
        raise NoEncontrado
    if actual.version != cambios.version:
        raise VersionDesfasada
    enviados = cambios.model_fields_set
    valores: dict = {}
    if "nombre" in enviados and cambios.nombre is not None:
        if _nombre_de_categoria_repetido(con, ctx, cambios.nombre, categoria_id):
            raise NombreRepetido
        valores["nombre"] = cambios.nombre
    if "icono" in enviados:
        valores["icono"] = cambios.icono
    resultado = con.execute(
        ais.actualizar(ctx, ops_categoria, ops_categoria.c.id == categoria_id,
                       ops_categoria.c.version == cambios.version)
        .values(**valores, version=ops_categoria.c.version + 1, actualizado_por=ctx.usuario_id)
    )
    if resultado.rowcount == 0:
        raise VersionDesfasada
    return _categoria_out(con.execute(
        _consulta_categorias(ctx).where(ops_categoria.c.id == categoria_id)
    ).one())


def archivar_categoria(con: Connection, ctx: ais.ContextoNegocio, categoria_id: uuid.UUID) -> None:
    """Archiva la categoría; sus ítems siguen existiendo, sin categoría."""
    resultado = con.execute(
        ais.actualizar(ctx, ops_categoria, ops_categoria.c.id == categoria_id)
        .values(eliminado_en=ahora_utc(), eliminado_por=ctx.usuario_id)
    )
    if resultado.rowcount == 0:
        raise NoEncontrado
    con.execute(
        ais.actualizar(ctx, ops_item, ops_item.c.categoria_id == categoria_id)
        .values(categoria_id=None, actualizado_por=ctx.usuario_id,
                version=ops_item.c.version + 1)
    )


def asegurar_categorias_de_ejemplo(con: Connection, ctx: ais.ContextoNegocio) -> None:
    """Negocios creados antes del catálogo: la primera vez reciben las categorías de ejemplo.

    Solo si nunca tuvieron una (ni siquiera archivada). Se bloquea la fila del negocio para que
    dos peticiones a la vez no las siembren dos veces.
    """
    con.execute(sa.select(core_negocio.c.id).where(core_negocio.c.id == ctx.negocio_id)
                .with_for_update())
    hay = con.execute(
        ais.seleccionar(ctx, ops_categoria, ops_categoria.c.id, incluir_eliminados=True)
        .limit(1).with_for_update()
    ).first()
    if hay is not None:
        return
    tipo = con.execute(
        sa.select(core_negocio.c.tipo_negocio_codigo).where(core_negocio.c.id == ctx.negocio_id)
    ).scalar_one()
    sembrar_catalogo(con, ctx, tipo)


def sembrar_catalogo(con: Connection, ctx: ais.ContextoNegocio, tipo_negocio: str) -> None:
    """Copia al negocio nuevo las categorías de ejemplo de su tipo de negocio."""
    plantilla = con.execute(
        sa.select(core_cfg_tipo_negocio_plantilla.c.contenido).where(
            core_cfg_tipo_negocio_plantilla.c.tipo_negocio_codigo == tipo_negocio,
            core_cfg_tipo_negocio_plantilla.c.tipo_plantilla == "catalogo",
        )
    ).scalar_one_or_none() or {}
    for orden, categoria in enumerate(plantilla.get("categorias", [])):
        con.execute(ais.insertar(ctx, ops_categoria, {
            "id": uuid7(), "nombre": categoria["nombre"], "icono": categoria.get("icono"),
            "orden": orden,
        }))


# ------------------------------------------------------------------ ítems

def _tipo_item_del_negocio(con: Connection, ctx: ais.ContextoNegocio) -> str:
    """'platillo' o 'producto', según el tipo de negocio (plantilla `catalogo`)."""
    plantilla = con.execute(
        sa.select(core_cfg_tipo_negocio_plantilla.c.contenido)
        .select_from(core_negocio.join(
            core_cfg_tipo_negocio_plantilla,
            core_cfg_tipo_negocio_plantilla.c.tipo_negocio_codigo
            == core_negocio.c.tipo_negocio_codigo))
        .where(core_negocio.c.id == ctx.negocio_id,
               core_cfg_tipo_negocio_plantilla.c.tipo_plantilla == "catalogo")
    ).scalar_one_or_none() or {}
    return plantilla.get("tipo_item", "producto")


def _consulta_items(ctx: ais.ContextoNegocio, incluir_eliminados: bool = False) -> sa.Select:
    # Un renglón por ítem: el precio de lista es el más bajo de sus variantes vivas.
    precios_vivos = (
        sa.select(ops_item_variante.c.item_id,
                  sa.func.min(ops_item_variante.c.precio_venta).label("precio_venta"))
        .where(ops_item_variante.c.negocio_id == ctx.negocio_id,
               sa.true() if incluir_eliminados else ops_item_variante.c.eliminado_en.is_(None))
        .group_by(ops_item_variante.c.item_id)
        .subquery("precio_item")
    )
    variante = precios_vivos.c.item_id == ops_item.c.id
    categoria = sa.and_(
        ops_categoria.c.id == ops_item.c.categoria_id,
        ops_categoria.c.negocio_id == ctx.negocio_id,
    )
    return ais.seleccionar(
        ctx, ops_item,
        ops_item.c.id, ops_item.c.tipo_item, ops_item.c.nombre, ops_item.c.descripcion,
        ops_item.c.categoria_id, ops_categoria.c.nombre.label("categoria_nombre"),
        precios_vivos.c.precio_venta, ops_item.c.se_vende, ops_item.c.version,
        ops_item.c.eliminado_en,
        incluir_eliminados=incluir_eliminados,
    ).select_from(
        ops_item.join(precios_vivos, variante).outerjoin(ops_categoria, categoria)
    )


def _item_out(fila, aviso: str | None = None, precio: precios.InfoPrecio | None = None,
              de_variantes: list | None = None, por_variante: dict | None = None,
              stock: tuple[dict, dict] | None = None,
              alertas: tuple[dict, dict] | None = None) -> ItemOut:
    stock_item, stock_var = stock or ({}, {})
    alerta_item, alerta_var = alertas or ({}, {})
    extra = {}
    if precio is not None:
        extra = {
            "precio_sugerido": None if precio.precio_sugerido is None
            else f"{precio.precio_sugerido:.2f}",
            "aviso_precio": precio.aviso, "margen_objetivo": f"{precio.margen_objetivo:.4f}",
            "margen_propio": precio.margen_propio,
        }
    return ItemOut(
        id=fila.id, tipo_item=fila.tipo_item, nombre=fila.nombre, descripcion=fila.descripcion,
        categoria_id=fila.categoria_id, categoria_nombre=fila.categoria_nombre,
        precio_venta=fila.precio_venta, se_vende=bool(fila.se_vende),
        archivado=fila.eliminado_en is not None, version=fila.version, aviso=aviso,
        tiene_variantes=bool(de_variantes),
        variantes=[variantes.variante_out(v, (por_variante or {}).get(v.id), stock_var.get(v.id),
                                          alerta_var.get(v.id))
                   for v in de_variantes or []],
        alerta_existencia=alerta_item.get(fila.id),
        controla_inventario=stock_item.get(fila.id) is not None,
        disponible=stock_item.get(fila.id), **extra,
    )


def obtener_item(con: Connection, ctx: ais.ContextoNegocio, item_id: uuid.UUID,
                 aviso: str | None = None) -> ItemOut:
    fila = con.execute(_consulta_items(ctx).where(ops_item.c.id == item_id)).first()
    if fila is None:
        raise NoEncontrado
    por_item, por_variante = precios.calcular(con, ctx, [item_id])
    return _item_out(fila, aviso, por_item.get(item_id),
                     variantes.variantes_de(con, ctx, [item_id])[item_id], por_variante,
                     existencias.disponibles(con, ctx, [item_id]),
                     existencias.estados(con, ctx, [item_id]))


def listar_items(con: Connection, ctx: ais.ContextoNegocio, *, categoria_id: uuid.UUID | None,
                 buscar: str | None, archivados: bool, limite: int, desplazar: int
                 ) -> ListaItemsOut:
    consulta = _consulta_items(ctx, incluir_eliminados=archivados)
    if archivados:
        consulta = consulta.where(ops_item.c.eliminado_en.is_not(None))
    if categoria_id is not None:
        consulta = consulta.where(ops_item.c.categoria_id == categoria_id)
    if buscar and buscar.strip():
        consulta = consulta.where(
            ops_item.c.nombre.like(f"%{_escapar_like(buscar.strip())}%", escape="\\")
        )
    total = con.execute(sa.select(sa.func.count()).select_from(consulta.subquery())).scalar_one()
    filas = con.execute(
        consulta.order_by(ops_item.c.nombre, ops_item.c.id).limit(limite).offset(desplazar)
    ).all()
    ids = [f.id for f in filas]
    info, por_variante = precios.calcular(con, ctx, ids)
    de_variantes = variantes.variantes_de(con, ctx, ids)
    stock = existencias.disponibles(con, ctx, ids)
    alertas = existencias.estados(con, ctx, ids)
    return ListaItemsOut(total=total, items=[
        _item_out(f, precio=info.get(f.id), de_variantes=de_variantes[f.id],
                  por_variante=por_variante, stock=stock, alertas=alertas) for f in filas])


def asegurar_mercaderia(con: Connection, ctx: ais.ContextoNegocio) -> int:
    """Negocios cuyos productos nacen como mercadería (tiendas): los productos vivos que aún no
    controlan inventario (sin receta ni mercadería) pasan a ser mercadería en 0. Devuelve cuántos.

    Así "primero se carga el inventario": hay que comprarlos o importarlos antes de venderlos.
    """
    if not existencias.operacion(con, ctx.negocio_id).get("mercaderia_por_defecto"):
        return 0
    con_receta = sa.select(ops_receta_linea.c.item_id).where(
        ops_receta_linea.c.negocio_id == ctx.negocio_id, ops_receta_linea.c.eliminado_en.is_(None))
    sin_control = con.execute(
        ais.seleccionar(ctx, ops_item, ops_item.c.id).where(ops_item.c.id.not_in(con_receta))
    ).scalars().all()
    for item_id in sin_control:
        mercaderia.activar(con, ctx, item_id)
    return len(sin_control)


def _aviso_nombre_repetido(con, ctx, nombre: str, tipo_item: str,
                           excepto: uuid.UUID | None) -> str | None:
    consulta = ais.seleccionar(ctx, ops_item, ops_item.c.id).where(ops_item.c.nombre == nombre)
    if excepto is not None:
        consulta = consulta.where(ops_item.c.id != excepto)
    if con.execute(consulta).first() is None:
        return None
    return f"Ya tienes un {tipo_item} con ese nombre."


def crear_item(con: Connection, ctx: ais.ContextoNegocio, datos: ItemIn) -> ItemOut:
    if datos.categoria_id is not None and not _categoria_existe(con, ctx, datos.categoria_id):
        raise CategoriaInvalida
    tipo_item = _tipo_item_del_negocio(con, ctx)
    aviso = _aviso_nombre_repetido(con, ctx, datos.nombre, tipo_item, None)
    item_id = uuid7()
    con.execute(ais.insertar(ctx, ops_item, {
        "id": item_id, "categoria_id": datos.categoria_id, "tipo_item": tipo_item,
        "nombre": datos.nombre, "descripcion": datos.descripcion or None,
    }))
    con.execute(ais.insertar(ctx, ops_item_variante, {
        "id": uuid7(), "item_id": item_id, "nombre": NOMBRE_VARIANTE_IMPLICITA,
        "precio_venta": datos.precio_venta,
    }))
    if existencias.operacion(con, ctx.negocio_id).get("mercaderia_por_defecto"):
        mercaderia.activar(con, ctx, item_id)  # en tiendas: nace como mercadería en 0
    return obtener_item(con, ctx, item_id, aviso)


def _huella(datos: ItemIn) -> str:
    return hashlib.sha256(
        json.dumps(datos.model_dump(mode="json"), sort_keys=True).encode()
    ).hexdigest()


def crear_item_idempotente(engine: Engine, ctx: ais.ContextoNegocio, datos: ItemIn,
                           clave: str | None) -> ItemOut:
    """Crea el ítem una sola vez por (usuario, Idempotency-Key); sin clave, siempre crea."""
    if clave is None:
        with engine.begin() as con:
            return crear_item(con, ctx, datos)

    huella = _huella(datos)
    filtro = sa.and_(
        core_idempotencia.c.usuario_id == ctx.usuario_id,
        core_idempotencia.c.operacion == OPERACION_CREAR_ITEM,
        core_idempotencia.c.clave == clave,
    )
    for intento in (1, 2):
        try:
            with engine.begin() as con:
                previo = con.execute(sa.select(core_idempotencia).where(filtro)).mappings().first()
                if previo is not None and previo["creado_en"] < ahora_utc() - VIGENCIA_IDEMPOTENCIA:
                    con.execute(sa.delete(core_idempotencia).where(filtro))  # clave vencida
                    previo = None
                if previo is not None:
                    if previo["huella"] != huella:
                        raise ClaveReutilizada
                    try:
                        return obtener_item(con, ctx, previo["recurso_id"])
                    except NoEncontrado:
                        con.execute(sa.delete(core_idempotencia).where(filtro))  # ya no existe
                item = crear_item(con, ctx, datos)
                con.execute(sa.insert(core_idempotencia).values(
                    id=uuid7(), usuario_id=ctx.usuario_id, operacion=OPERACION_CREAR_ITEM,
                    clave=clave, huella=huella, recurso_id=item.id, creado_por=ctx.usuario_id,
                ))
                return item
        except sa.exc.IntegrityError:
            # Carrera: otra petición con la misma clave se confirmó primero; se reintenta una vez.
            if intento == 2:
                raise
    raise AssertionError("inalcanzable")


def actualizar_item(con: Connection, ctx: ais.ContextoNegocio, item_id: uuid.UUID,
                    cambios: ItemCambios) -> ItemOut:
    actual = con.execute(
        ais.seleccionar(ctx, ops_item, ops_item.c.version, ops_item.c.tipo_item,
                        ops_item.c.nombre)
        .where(ops_item.c.id == item_id)
    ).first()
    if actual is None:
        raise NoEncontrado
    if actual.version != cambios.version:
        raise VersionDesfasada

    enviados = cambios.model_fields_set
    valores: dict = {}
    aviso = None
    if "nombre" in enviados and cambios.nombre is not None:
        valores["nombre"] = cambios.nombre
        if cambios.nombre != actual.nombre:
            aviso = _aviso_nombre_repetido(con, ctx, cambios.nombre, actual.tipo_item, item_id)
    if "descripcion" in enviados:
        valores["descripcion"] = cambios.descripcion or None
    if "categoria_id" in enviados:
        if cambios.categoria_id is not None and not _categoria_existe(
                con, ctx, cambios.categoria_id):
            raise CategoriaInvalida
        valores["categoria_id"] = cambios.categoria_id
    if "margen_objetivo" in enviados:
        valores["margen_objetivo"] = cambios.margen_objetivo  # null = vuelve al del negocio

    resultado = con.execute(
        ais.actualizar(ctx, ops_item, ops_item.c.id == item_id,
                       ops_item.c.version == cambios.version)
        .values(**valores, version=ops_item.c.version + 1, actualizado_por=ctx.usuario_id)
    )
    if resultado.rowcount == 0:
        raise VersionDesfasada
    if "precio_venta" in enviados and cambios.precio_venta is not None:
        con.execute(
            ais.actualizar(ctx, ops_item_variante, ops_item_variante.c.item_id == item_id)
            .values(precio_venta=cambios.precio_venta, actualizado_por=ctx.usuario_id,
                    version=ops_item_variante.c.version + 1)
        )
    return obtener_item(con, ctx, item_id, aviso)


def archivar_item(con: Connection, ctx: ais.ContextoNegocio, item_id: uuid.UUID) -> None:
    ahora = ahora_utc()
    resultado = con.execute(
        ais.actualizar(ctx, ops_item, ops_item.c.id == item_id)
        .values(eliminado_en=ahora, eliminado_por=ctx.usuario_id)
    )
    if resultado.rowcount == 0:
        raise NoEncontrado
    con.execute(
        ais.actualizar(ctx, ops_item_variante, ops_item_variante.c.item_id == item_id)
        .values(eliminado_en=ahora, eliminado_por=ctx.usuario_id)
    )
    mercaderia.desactivar_en_cascada(con, ctx, item_id)  # su insumo ligado y su receta
