"""Gastos y sus categorías. Todo acceso a tablas de negocio pasa por db.aislamiento."""

import hashlib
import json
import uuid
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.engine import Connection, Engine

from integrat.contabilidad import eventos as contabilidad
from integrat.db import aislamiento as ais
from integrat.db.tablas import (
    core_cfg_tipo_negocio_plantilla,
    core_idempotencia,
    core_negocio,
    ops_categoria_gasto,
    ops_gasto,
)
from integrat.db.tipos import ahora_utc, uuid7
from integrat.gastos.esquemas import (
    CategoriaGastoCambios,
    CategoriaGastoIn,
    CategoriaGastoOut,
    GastoCambios,
    GastoIn,
    GastoOut,
    ListaGastosOut,
    ResumenCategoria,
    ResumenGastos,
)
from integrat.tiempo import hoy_del_negocio

OPERACION_CREAR_GASTO = "crear_gasto"
VIGENCIA_IDEMPOTENCIA = timedelta(hours=24)
MAX_GASTOS_POR_MES = 500
# Cambiar alguno de estos campos cambia el asiento del gasto (la nota no).
CAMPOS_CONTABLES = {"monto", "medio_pago", "fecha", "categoria_gasto_id", "con_factura"}
CERO = Decimal("0.00")


class NoEncontrado(Exception):
    pass


class VersionDesfasada(Exception):
    """Alguien más cambió el registro después de que la persona lo vio."""


class CategoriaInvalida(Exception):
    pass


class NombreRepetido(Exception):
    pass


class FechaFutura(Exception):
    pass


class MesInvalido(Exception):
    pass


class ClaveReutilizada(Exception):
    """La misma Idempotency-Key llegó con datos distintos."""


# ------------------------------------------------------------------ categorías

def _categoria_out(fila) -> CategoriaGastoOut:
    return CategoriaGastoOut(id=fila.id, nombre=fila.nombre, icono=fila.icono,
                             es_fijo=bool(fila.es_fijo), orden=fila.orden, version=fila.version)


def _consulta_categorias(ctx: ais.ContextoNegocio) -> sa.Select:
    return ais.seleccionar(
        ctx, ops_categoria_gasto, ops_categoria_gasto.c.id, ops_categoria_gasto.c.nombre,
        ops_categoria_gasto.c.icono, ops_categoria_gasto.c.es_fijo, ops_categoria_gasto.c.orden,
        ops_categoria_gasto.c.version,
    )


def listar_categorias(con: Connection, ctx: ais.ContextoNegocio) -> list[CategoriaGastoOut]:
    filas = con.execute(
        _consulta_categorias(ctx).order_by(ops_categoria_gasto.c.orden,
                                           ops_categoria_gasto.c.nombre)
    ).all()
    return [_categoria_out(f) for f in filas]


def _nombre_repetido(con, ctx, nombre: str, excepto: uuid.UUID | None) -> bool:
    consulta = ais.seleccionar(ctx, ops_categoria_gasto, ops_categoria_gasto.c.id).where(
        ops_categoria_gasto.c.nombre == nombre
    )
    if excepto is not None:
        consulta = consulta.where(ops_categoria_gasto.c.id != excepto)
    return con.execute(consulta).first() is not None


def crear_categoria(con: Connection, ctx: ais.ContextoNegocio,
                    datos: CategoriaGastoIn) -> CategoriaGastoOut:
    if _nombre_repetido(con, ctx, datos.nombre, None):
        raise NombreRepetido
    ultimo = con.execute(
        ais.seleccionar(ctx, ops_categoria_gasto, sa.func.max(ops_categoria_gasto.c.orden))
    ).scalar()
    categoria_id = uuid7()
    con.execute(ais.insertar(ctx, ops_categoria_gasto, {
        "id": categoria_id, "nombre": datos.nombre, "icono": datos.icono,
        "es_fijo": datos.es_fijo, "orden": 0 if ultimo is None else ultimo + 1,
    }))
    return _categoria_out(con.execute(
        _consulta_categorias(ctx).where(ops_categoria_gasto.c.id == categoria_id)
    ).one())


def actualizar_categoria(con: Connection, ctx: ais.ContextoNegocio, categoria_id: uuid.UUID,
                         cambios: CategoriaGastoCambios) -> CategoriaGastoOut:
    actual = con.execute(
        ais.seleccionar(ctx, ops_categoria_gasto, ops_categoria_gasto.c.version)
        .where(ops_categoria_gasto.c.id == categoria_id)
    ).first()
    if actual is None:
        raise NoEncontrado
    if actual.version != cambios.version:
        raise VersionDesfasada
    enviados = cambios.model_fields_set
    valores: dict = {}
    if "nombre" in enviados and cambios.nombre is not None:
        if _nombre_repetido(con, ctx, cambios.nombre, categoria_id):
            raise NombreRepetido
        valores["nombre"] = cambios.nombre
    if "icono" in enviados:
        valores["icono"] = cambios.icono
    if "es_fijo" in enviados and cambios.es_fijo is not None:
        valores["es_fijo"] = cambios.es_fijo  # los gastos ya anotados conservan el suyo
    resultado = con.execute(
        ais.actualizar(ctx, ops_categoria_gasto, ops_categoria_gasto.c.id == categoria_id,
                       ops_categoria_gasto.c.version == cambios.version)
        .values(**valores, version=ops_categoria_gasto.c.version + 1,
                actualizado_por=ctx.usuario_id)
    )
    if resultado.rowcount == 0:
        raise VersionDesfasada
    return _categoria_out(con.execute(
        _consulta_categorias(ctx).where(ops_categoria_gasto.c.id == categoria_id)
    ).one())


def archivar_categoria(con: Connection, ctx: ais.ContextoNegocio, categoria_id: uuid.UUID) -> None:
    """Deja de ofrecerse para gastos nuevos; los gastos que ya la usan no se tocan."""
    resultado = con.execute(
        ais.actualizar(ctx, ops_categoria_gasto, ops_categoria_gasto.c.id == categoria_id)
        .values(eliminado_en=ahora_utc(), eliminado_por=ctx.usuario_id)
    )
    if resultado.rowcount == 0:
        raise NoEncontrado


def asegurar_categorias_de_ejemplo(con: Connection, ctx: ais.ContextoNegocio) -> None:
    """Negocios creados antes de los gastos: la primera vez reciben las categorías de ejemplo.

    Solo si nunca tuvieron una (ni siquiera archivada). Se bloquea la fila del negocio para que
    dos peticiones a la vez no las siembren dos veces.
    """
    con.execute(sa.select(core_negocio.c.id).where(core_negocio.c.id == ctx.negocio_id)
                .with_for_update())
    hay = con.execute(
        ais.seleccionar(ctx, ops_categoria_gasto, ops_categoria_gasto.c.id,
                        incluir_eliminados=True).limit(1).with_for_update()
    ).first()
    if hay is not None:
        return
    tipo = con.execute(
        sa.select(core_negocio.c.tipo_negocio_codigo).where(core_negocio.c.id == ctx.negocio_id)
    ).scalar_one()
    sembrar_categorias(con, ctx, tipo)


def sembrar_categorias(con: Connection, ctx: ais.ContextoNegocio, tipo_negocio: str) -> None:
    """Copia al negocio nuevo las categorías de gasto de ejemplo de su tipo de negocio."""
    plantilla = con.execute(
        sa.select(core_cfg_tipo_negocio_plantilla.c.contenido).where(
            core_cfg_tipo_negocio_plantilla.c.tipo_negocio_codigo == tipo_negocio,
            core_cfg_tipo_negocio_plantilla.c.tipo_plantilla == "categorias_gasto",
        )
    ).scalar_one_or_none() or {}
    for orden, categoria in enumerate(plantilla.get("categorias", [])):
        con.execute(ais.insertar(ctx, ops_categoria_gasto, {
            "id": uuid7(), "nombre": categoria["nombre"], "icono": categoria.get("icono"),
            "es_fijo": bool(categoria.get("es_fijo", False)),
            "rol_cuenta_codigo": categoria.get("rol_cuenta"), "orden": orden,
        }))


# ------------------------------------------------------------------ gastos

def _consulta_gastos(ctx: ais.ContextoNegocio) -> sa.Select:
    # Une con la categoría aunque esté archivada: el gasto conserva el nombre que tenía.
    categoria = sa.and_(
        ops_categoria_gasto.c.id == ops_gasto.c.categoria_gasto_id,
        ops_categoria_gasto.c.negocio_id == ctx.negocio_id,
    )
    return ais.seleccionar(
        ctx, ops_gasto,
        ops_gasto.c.id, ops_gasto.c.fecha, ops_gasto.c.monto,
        ops_gasto.c.categoria_gasto_id.label("categoria_id"),
        ops_categoria_gasto.c.nombre.label("categoria_nombre"),
        ops_gasto.c.medio_pago, ops_gasto.c.descripcion, ops_gasto.c.es_fijo,
        ops_gasto.c.con_factura, ops_gasto.c.version,
    ).select_from(ops_gasto.join(ops_categoria_gasto, categoria))


def _gasto_out(fila) -> GastoOut:
    return GastoOut(
        id=fila.id, fecha=fila.fecha, monto=fila.monto, categoria_id=fila.categoria_id,
        categoria_nombre=fila.categoria_nombre, medio_pago=fila.medio_pago,
        descripcion=fila.descripcion, es_fijo=bool(fila.es_fijo),
        con_factura=bool(fila.con_factura), version=fila.version,
    )


def obtener_gasto(con: Connection, ctx: ais.ContextoNegocio, gasto_id: uuid.UUID) -> GastoOut:
    fila = con.execute(_consulta_gastos(ctx).where(ops_gasto.c.id == gasto_id)).first()
    if fila is None:
        raise NoEncontrado
    return _gasto_out(fila)


def _categoria_vigente(con: Connection, ctx: ais.ContextoNegocio, categoria_id: uuid.UUID):
    fila = con.execute(
        ais.seleccionar(ctx, ops_categoria_gasto, ops_categoria_gasto.c.id,
                        ops_categoria_gasto.c.es_fijo)
        .where(ops_categoria_gasto.c.id == categoria_id)
    ).first()
    if fila is None:
        raise CategoriaInvalida
    return fila


def _validar_fecha(con: Connection, ctx: ais.ContextoNegocio, fecha: date) -> None:
    if fecha > hoy_del_negocio(con, ctx):
        raise FechaFutura


def crear_gasto(con: Connection, ctx: ais.ContextoNegocio, datos: GastoIn) -> GastoOut:
    categoria = _categoria_vigente(con, ctx, datos.categoria_id)
    fecha = datos.fecha or hoy_del_negocio(con, ctx)
    _validar_fecha(con, ctx, fecha)
    gasto_id = uuid7()
    con.execute(ais.insertar(ctx, ops_gasto, {
        "id": gasto_id, "categoria_gasto_id": categoria.id, "fecha": fecha, "monto": datos.monto,
        "medio_pago": datos.medio_pago, "descripcion": datos.descripcion or None,
        "es_fijo": bool(categoria.es_fijo), "con_factura": datos.con_factura,
    }))
    contabilidad.asentar_gasto(con, ctx, gasto_id)
    return obtener_gasto(con, ctx, gasto_id)


def _huella(datos: GastoIn) -> str:
    return hashlib.sha256(
        json.dumps(datos.model_dump(mode="json"), sort_keys=True).encode()
    ).hexdigest()


def crear_gasto_idempotente(engine: Engine, ctx: ais.ContextoNegocio, datos: GastoIn,
                            clave: str | None) -> GastoOut:
    """Anota el gasto una sola vez por (usuario, Idempotency-Key); sin clave, siempre anota."""
    if clave is None:
        with engine.begin() as con:
            return crear_gasto(con, ctx, datos)

    huella = _huella(datos)
    filtro = sa.and_(
        core_idempotencia.c.usuario_id == ctx.usuario_id,
        core_idempotencia.c.operacion == OPERACION_CREAR_GASTO,
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
                        return obtener_gasto(con, ctx, previo["recurso_id"])
                    except NoEncontrado:
                        con.execute(sa.delete(core_idempotencia).where(filtro))
                gasto = crear_gasto(con, ctx, datos)
                con.execute(sa.insert(core_idempotencia).values(
                    id=uuid7(), usuario_id=ctx.usuario_id, operacion=OPERACION_CREAR_GASTO,
                    clave=clave, huella=huella, recurso_id=gasto.id, creado_por=ctx.usuario_id,
                ))
                return gasto
        except sa.exc.IntegrityError:
            # Carrera: otra petición con la misma clave se confirmó primero; se reintenta una vez.
            if intento == 2:
                raise
    raise AssertionError("inalcanzable")


def actualizar_gasto(con: Connection, ctx: ais.ContextoNegocio, gasto_id: uuid.UUID,
                     cambios: GastoCambios) -> GastoOut:
    actual = con.execute(
        ais.seleccionar(ctx, ops_gasto, ops_gasto.c.version).where(ops_gasto.c.id == gasto_id)
    ).first()
    if actual is None:
        raise NoEncontrado
    if actual.version != cambios.version:
        raise VersionDesfasada

    enviados = cambios.model_fields_set
    valores: dict = {}
    if "monto" in enviados and cambios.monto is not None:
        valores["monto"] = cambios.monto
    if "medio_pago" in enviados and cambios.medio_pago is not None:
        valores["medio_pago"] = cambios.medio_pago
    if "fecha" in enviados and cambios.fecha is not None:
        _validar_fecha(con, ctx, cambios.fecha)
        valores["fecha"] = cambios.fecha
    if "descripcion" in enviados:
        valores["descripcion"] = cambios.descripcion or None
    if "categoria_id" in enviados and cambios.categoria_id is not None:
        categoria = _categoria_vigente(con, ctx, cambios.categoria_id)
        valores["categoria_gasto_id"] = categoria.id
        valores["es_fijo"] = bool(categoria.es_fijo)  # cambia de categoría = cambia de tipo
    if "con_factura" in enviados and cambios.con_factura is not None:
        valores["con_factura"] = cambios.con_factura

    resultado = con.execute(
        ais.actualizar(ctx, ops_gasto, ops_gasto.c.id == gasto_id,
                       ops_gasto.c.version == cambios.version)
        .values(**valores, version=ops_gasto.c.version + 1, actualizado_por=ctx.usuario_id)
    )
    if resultado.rowcount == 0:
        raise VersionDesfasada
    if CAMPOS_CONTABLES & set(valores):
        # El asiento no se edita: se revierte el vigente y se registra el gasto como quedó.
        contabilidad.revertir_gasto(con, ctx, gasto_id, "Corrección de un gasto")
        contabilidad.asentar_gasto(con, ctx, gasto_id)
    return obtener_gasto(con, ctx, gasto_id)


def archivar_gasto(con: Connection, ctx: ais.ContextoNegocio, gasto_id: uuid.UUID) -> None:
    resultado = con.execute(
        ais.actualizar(ctx, ops_gasto, ops_gasto.c.id == gasto_id)
        .values(eliminado_en=ahora_utc(), eliminado_por=ctx.usuario_id)
    )
    if resultado.rowcount == 0:
        raise NoEncontrado
    contabilidad.revertir_gasto(con, ctx, gasto_id, "Gasto borrado")


# ------------------------------------------------------------------ el mes

def _rango_del_mes(mes: str | None, hoy: date) -> tuple[date, date, str]:
    if mes is None:
        inicio = hoy.replace(day=1)
    else:
        try:
            anio, numero = mes.split("-")
            inicio = date(int(anio), int(numero), 1)
        except (ValueError, TypeError):
            raise MesInvalido from None
        if len(anio) != 4 or len(numero) != 2:
            raise MesInvalido
    siguiente = (inicio.replace(day=28) + timedelta(days=4)).replace(day=1)
    return inicio, siguiente, f"{inicio.year:04d}-{inicio.month:02d}"


def listar_del_mes(con: Connection, ctx: ais.ContextoNegocio, mes: str | None) -> ListaGastosOut:
    inicio, siguiente, etiqueta = _rango_del_mes(mes, hoy_del_negocio(con, ctx))
    filas = con.execute(
        _consulta_gastos(ctx)
        .where(ops_gasto.c.fecha >= inicio, ops_gasto.c.fecha < siguiente)
        .order_by(ops_gasto.c.fecha.desc(), ops_gasto.c.creado_en.desc(), ops_gasto.c.id.desc())
        .limit(MAX_GASTOS_POR_MES)
    ).all()
    gastos = [_gasto_out(f) for f in filas]

    total = sum((g.monto for g in gastos), CERO)
    fijos = sum((g.monto for g in gastos if g.es_fijo), CERO)
    por_categoria: dict[uuid.UUID, list] = defaultdict(lambda: [None, CERO])
    for g in gastos:
        entrada = por_categoria[g.categoria_id]
        entrada[0] = g.categoria_nombre
        entrada[1] += g.monto
    resumen_categorias = [
        ResumenCategoria(
            categoria_id=cid, nombre=nombre, total=f"{monto:.2f}",
            porcentaje=int((monto * 100 / total).quantize(Decimal("1"))) if total else 0,
        )
        for cid, (nombre, monto) in sorted(por_categoria.items(), key=lambda kv: -kv[1][1])
    ]
    resumen = ResumenGastos(
        cantidad=len(gastos), total=f"{total:.2f}", total_fijos=f"{fijos:.2f}",
        total_variables=f"{total - fijos:.2f}", por_categoria=resumen_categorias,
    )
    return ListaGastosOut(mes=etiqueta, resumen=resumen, gastos=gastos)
