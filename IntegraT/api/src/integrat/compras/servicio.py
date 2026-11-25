"""Proveedores y compras a mano. Todo acceso a tablas de negocio pasa por db.aislamiento.

Reglas (docs/PLAN_COMPRAS.md): cada línea es una entrada de inventario (sube la existencia y
recalcula el costo promedio); la compra no se edita, se anula con motivo y se revierte; el total lo
suma la API.
"""

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

import sqlalchemy as sa
from sqlalchemy.engine import Connection, Engine

from integrat.compras.esquemas import (
    CompraIn,
    CompraLineaOut,
    CompraOut,
    ListaComprasOut,
    ProveedorCambios,
    ProveedorIn,
    ProveedorOut,
    ResumenCompras,
)
from integrat.contabilidad import eventos as contabilidad
from integrat.contabilidad import motor
from integrat.db import aislamiento as ais
from integrat.db.tablas import (
    core_idempotencia,
    core_negocio,
    ops_compra,
    ops_compra_linea,
    ops_insumo,
    ops_movimiento_inventario,
    ops_proveedor,
)
from integrat.db.tipos import ahora_utc, uuid7
from integrat.gastos.servicio import MesInvalido, _rango_del_mes
from integrat.insumos import servicio as inventario
from integrat.tiempo import hoy_del_negocio

OPERACION_CREAR_COMPRA = "crear_compra"
ORIGEN_COMPRA = "compra"
VIGENCIA_IDEMPOTENCIA = timedelta(hours=24)
MAX_COMPRAS_POR_MES = 500
CERO = Decimal("0.00")
CENTAVOS = Decimal("0.01")
OCHO = Decimal("0.00000001")

__all__ = ["MesInvalido"]  # se re-exporta para el router


class NoEncontrado(Exception):
    pass


class VersionDesfasada(Exception):
    """Alguien más cambió el registro después de que la persona lo vio."""


class NombreRepetido(Exception):
    pass


class ProveedorInvalido(Exception):
    """El proveedor no existe en este negocio o está archivado."""


class InsumoInvalido(Exception):
    """Un insumo de la compra no existe en este negocio o está archivado."""


class FechaFutura(Exception):
    pass


class YaAnulada(Exception):
    pass


class ClaveReutilizada(Exception):
    """La misma Idempotency-Key llegó con datos distintos."""


def _utc(valor: datetime | None) -> datetime | None:
    return None if valor is None else valor.replace(tzinfo=UTC)


# ------------------------------------------------------------------ proveedores

def _proveedor_out(f) -> ProveedorOut:
    return ProveedorOut(id=f.id, nombre=f.nombre, telefono=f.telefono, version=f.version)


def _consulta_proveedores(ctx: ais.ContextoNegocio) -> sa.Select:
    return ais.seleccionar(ctx, ops_proveedor, ops_proveedor.c.id, ops_proveedor.c.nombre,
                           ops_proveedor.c.telefono, ops_proveedor.c.version)


def listar_proveedores(con: Connection, ctx: ais.ContextoNegocio) -> list[ProveedorOut]:
    filas = con.execute(_consulta_proveedores(ctx).order_by(ops_proveedor.c.nombre,
                                                            ops_proveedor.c.id)).all()
    return [_proveedor_out(f) for f in filas]


def _proveedor_por_nombre(con, ctx, nombre: str, excepto: uuid.UUID | None = None):
    consulta = _consulta_proveedores(ctx).where(ops_proveedor.c.nombre == nombre)
    if excepto is not None:
        consulta = consulta.where(ops_proveedor.c.id != excepto)
    return con.execute(consulta).first()


def crear_proveedor(con: Connection, ctx: ais.ContextoNegocio, datos: ProveedorIn) -> ProveedorOut:
    if _proveedor_por_nombre(con, ctx, datos.nombre) is not None:
        raise NombreRepetido
    proveedor_id = uuid7()
    con.execute(ais.insertar(ctx, ops_proveedor, {
        "id": proveedor_id, "nombre": datos.nombre, "telefono": datos.telefono,
    }))
    return _proveedor_out(con.execute(
        _consulta_proveedores(ctx).where(ops_proveedor.c.id == proveedor_id)).one())


def actualizar_proveedor(con: Connection, ctx: ais.ContextoNegocio, proveedor_id: uuid.UUID,
                         cambios: ProveedorCambios) -> ProveedorOut:
    actual = con.execute(
        _consulta_proveedores(ctx).where(ops_proveedor.c.id == proveedor_id)).first()
    if actual is None:
        raise NoEncontrado
    if actual.version != cambios.version:
        raise VersionDesfasada
    enviados = cambios.model_fields_set
    valores: dict = {}
    if "nombre" in enviados and cambios.nombre is not None:
        if _proveedor_por_nombre(con, ctx, cambios.nombre, excepto=proveedor_id) is not None:
            raise NombreRepetido
        valores["nombre"] = cambios.nombre
    if "telefono" in enviados:
        valores["telefono"] = cambios.telefono
    resultado = con.execute(
        ais.actualizar(ctx, ops_proveedor, ops_proveedor.c.id == proveedor_id,
                       ops_proveedor.c.version == cambios.version)
        .values(**valores, version=ops_proveedor.c.version + 1, actualizado_por=ctx.usuario_id)
    )
    if resultado.rowcount == 0:
        raise VersionDesfasada
    return _proveedor_out(con.execute(
        _consulta_proveedores(ctx).where(ops_proveedor.c.id == proveedor_id)).one())


def archivar_proveedor(con: Connection, ctx: ais.ContextoNegocio, proveedor_id: uuid.UUID) -> None:
    """Deja de ofrecerse; sus compras conservan su nombre."""
    resultado = con.execute(
        ais.actualizar(ctx, ops_proveedor, ops_proveedor.c.id == proveedor_id)
        .values(eliminado_en=ahora_utc(), eliminado_por=ctx.usuario_id)
    )
    if resultado.rowcount == 0:
        raise NoEncontrado


def _resolver_proveedor(con: Connection, ctx: ais.ContextoNegocio,
                        datos: CompraIn) -> uuid.UUID | None:
    if datos.proveedor_id is not None:
        existe = con.execute(
            ais.seleccionar(ctx, ops_proveedor, ops_proveedor.c.id)
            .where(ops_proveedor.c.id == datos.proveedor_id)
        ).first()
        if existe is None:
            raise ProveedorInvalido
        return datos.proveedor_id
    if datos.proveedor_nuevo is None:
        return None
    # Se serializa por negocio para que dos compras a la vez no creen el mismo proveedor dos veces.
    con.execute(sa.select(core_negocio.c.id).where(core_negocio.c.id == ctx.negocio_id)
                .with_for_update())
    previo = con.execute(
        _consulta_proveedores(ctx).where(ops_proveedor.c.nombre == datos.proveedor_nuevo.nombre)
        .with_for_update()
    ).first()
    if previo is not None:
        return previo.id
    return crear_proveedor(con, ctx, datos.proveedor_nuevo).id


# ------------------------------------------------------------------ crear

def _consulta_compras(ctx: ais.ContextoNegocio) -> sa.Select:
    # Une con el proveedor aunque esté archivado: la compra conserva su nombre.
    proveedor = sa.and_(ops_proveedor.c.id == ops_compra.c.proveedor_id,
                        ops_proveedor.c.negocio_id == ctx.negocio_id)
    return ais.seleccionar(
        ctx, ops_compra, ops_compra.c.id, ops_compra.c.fecha, ops_compra.c.proveedor_id,
        ops_proveedor.c.nombre.label("proveedor_nombre"), ops_compra.c.numero_factura,
        ops_compra.c.medio_pago, ops_compra.c.total, ops_compra.c.estado, ops_compra.c.nota,
        ops_compra.c.anulada_en, ops_compra.c.motivo_anulacion,
    ).select_from(ops_compra.outerjoin(ops_proveedor, proveedor))


def _armar(con: Connection, ctx: ais.ContextoNegocio, filas) -> list[CompraOut]:
    ids = [f.id for f in filas]
    if not ids:
        return []
    lineas: dict[uuid.UUID, list[CompraLineaOut]] = {i: [] for i in ids}
    for f in con.execute(
        ais.seleccionar(ctx, ops_compra_linea).where(ops_compra_linea.c.compra_id.in_(ids))
        .order_by(ops_compra_linea.c.creado_en, ops_compra_linea.c.id)
    ):
        lineas[f.compra_id].append(CompraLineaOut(
            insumo_id=f.insumo_id, nombre=f.nombre,
            cantidad=inventario.cantidad_texto(f.cantidad), unidad_codigo=f.unidad_codigo,
            costo_total=f"{f.costo_total:.2f}",
        ))
    return [
        CompraOut(
            id=f.id, fecha=f.fecha, proveedor_id=f.proveedor_id,
            proveedor_nombre=f.proveedor_nombre, numero_factura=f.numero_factura,
            medio_pago=f.medio_pago, total=f"{f.total:.2f}", estado=f.estado, nota=f.nota,
            lineas=lineas[f.id], anulada_en=_utc(f.anulada_en),
            motivo_anulacion=f.motivo_anulacion,
        )
        for f in filas
    ]


def obtener_compra(con: Connection, ctx: ais.ContextoNegocio, compra_id: uuid.UUID) -> CompraOut:
    fila = con.execute(_consulta_compras(ctx).where(ops_compra.c.id == compra_id)).first()
    if fila is None:
        raise NoEncontrado
    return _armar(con, ctx, [fila])[0]


def crear_compra(con: Connection, ctx: ais.ContextoNegocio, datos: CompraIn) -> CompraOut:
    fecha = datos.fecha or hoy_del_negocio(con, ctx)
    if fecha > hoy_del_negocio(con, ctx):
        raise FechaFutura

    ids = {linea.insumo_id for linea in datos.lineas}
    unidad_de = {
        f.id: (f.unidad_codigo, f.nombre, f.item_id) for f in con.execute(
            ais.seleccionar(ctx, ops_insumo, ops_insumo.c.id, ops_insumo.c.unidad_codigo,
                            ops_insumo.c.nombre, ops_insumo.c.item_id)
            .where(ops_insumo.c.id.in_(ids)))
    }
    if len(unidad_de) != len(ids):
        raise InsumoInvalido

    resueltas = []
    for linea in datos.lineas:
        codigo, nombre, _ = unidad_de[linea.insumo_id]
        propia = inventario.buscar_unidad(con, codigo)
        usada = (inventario.buscar_unidad(con, linea.unidad_codigo) if linea.unidad_codigo
                 else propia)
        if usada.tipo != propia.tipo:
            raise inventario.UnidadInvalida  # no se convierte peso a volumen
        resueltas.append((linea, nombre, usada))

    # Los insumos se bloquean ANTES de insertar las líneas (que los referencian): si no, dos compras
    # del mismo insumo a la vez se traban entre sí. Siempre en el mismo orden.
    for insumo_id in sorted(ids):
        try:
            inventario.bloquear(con, ctx, insumo_id)
        except inventario.NoEncontrado:
            raise InsumoInvalido from None

    proveedor_id = _resolver_proveedor(con, ctx, datos)
    total = sum((linea.costo_total for linea in datos.lineas), CERO).quantize(CENTAVOS)
    compra_id = uuid7()
    con.execute(ais.insertar(ctx, ops_compra, {
        "id": compra_id, "proveedor_id": proveedor_id, "fecha": fecha,
        "numero_factura": datos.numero_factura, "medio_pago": datos.medio_pago, "total": total,
        "estado": "registrada", "nota": datos.nota or None,
    }))
    for linea, nombre, usada in resueltas:
        con.execute(ais.insertar(ctx, ops_compra_linea, {
            "id": uuid7(), "compra_id": compra_id, "insumo_id": linea.insumo_id, "nombre": nombre,
            "cantidad": linea.cantidad, "unidad_codigo": usada.codigo,
            "costo_total": linea.costo_total,
        }))
    # Régimen general con factura: lo que entra al inventario es el costo SIN IVA (el IVA va por
    # cobrar). Así el costo promedio y el costo por platillo quedan netos.
    trat = motor.tratamiento_iva(con, ctx)
    con_iva = trat.separa and bool(datos.numero_factura)
    bases = contabilidad.bases_vacias()
    # Los movimientos se aplican siempre en el mismo orden de insumos: sin bloqueos cruzados.
    for linea, _, usada in sorted(resueltas, key=lambda r: r[0].insumo_id):
        base, _iva = motor.separar_iva(linea.costo_total, trat, aplica=con_iva)
        bases[contabilidad.rol_inventario(unidad_de[linea.insumo_id][2])] += base
        fila = inventario.bloquear(con, ctx, linea.insumo_id)
        inventario.aplicar(con, ctx, fila, "entrada", linea.cantidad * usada.factor,
                           base, origen_tipo=ORIGEN_COMPRA, origen_id=compra_id)
    contabilidad.asentar_compra(con, ctx, compra_id, fecha=fecha, medio_pago=datos.medio_pago,
                                total=total, bases=bases, trat=trat)
    return obtener_compra(con, ctx, compra_id)


def _huella(datos: CompraIn) -> str:
    return hashlib.sha256(
        json.dumps(datos.model_dump(mode="json"), sort_keys=True).encode()
    ).hexdigest()


def crear_compra_idempotente(engine: Engine, ctx: ais.ContextoNegocio, datos: CompraIn,
                             clave: str | None) -> CompraOut:
    """Registra la compra una sola vez por (usuario, Idempotency-Key); sin clave, siempre."""
    if clave is None:
        with engine.begin() as con:
            return crear_compra(con, ctx, datos)

    huella = _huella(datos)
    filtro = sa.and_(
        core_idempotencia.c.usuario_id == ctx.usuario_id,
        core_idempotencia.c.operacion == OPERACION_CREAR_COMPRA,
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
                        return obtener_compra(con, ctx, previo["recurso_id"])
                    except NoEncontrado:
                        con.execute(sa.delete(core_idempotencia).where(filtro))
                compra = crear_compra(con, ctx, datos)
                con.execute(sa.insert(core_idempotencia).values(
                    id=uuid7(), usuario_id=ctx.usuario_id, operacion=OPERACION_CREAR_COMPRA,
                    clave=clave, huella=huella, recurso_id=compra.id, creado_por=ctx.usuario_id,
                ))
                return compra
        except sa.exc.IntegrityError:
            # Carrera: otra petición con la misma clave se confirmó primero; se reintenta una vez.
            if intento == 2:
                raise
    raise AssertionError("inalcanzable")


# ------------------------------------------------------------------ leer

def listar_del_mes(con: Connection, ctx: ais.ContextoNegocio, mes: str | None) -> ListaComprasOut:
    inicio, siguiente, etiqueta = _rango_del_mes(mes, hoy_del_negocio(con, ctx))
    filas = con.execute(
        _consulta_compras(ctx).where(ops_compra.c.fecha >= inicio, ops_compra.c.fecha < siguiente)
        .order_by(ops_compra.c.fecha.desc(), ops_compra.c.creado_en.desc(), ops_compra.c.id.desc())
        .limit(MAX_COMPRAS_POR_MES)
    ).all()
    compras = _armar(con, ctx, filas)
    vigentes = [c for c in compras if c.estado == "registrada"]
    total = sum((Decimal(c.total) for c in vigentes), CERO)
    return ListaComprasOut(
        mes=etiqueta, resumen=ResumenCompras(cantidad=len(vigentes), total=f"{total:.2f}"),
        compras=compras,
    )


# ------------------------------------------------------------------ anular

def anular_compra(con: Connection, ctx: ais.ContextoNegocio, compra_id: uuid.UUID,
                  motivo: str) -> CompraOut:
    """Anula la compra y revierte cada línea: devuelve la existencia y quita su costo del promedio.

    Si lo comprado ya se gastó en parte (la existencia no alcanza), el promedio se conserva.
    """
    resultado = con.execute(
        ais.actualizar(ctx, ops_compra, ops_compra.c.id == compra_id,
                       ops_compra.c.estado == "registrada")
        .values(estado="anulada", anulada_en=ahora_utc(), anulada_por=ctx.usuario_id,
                motivo_anulacion=motivo, version=ops_compra.c.version + 1,
                actualizado_por=ctx.usuario_id)
    )
    if resultado.rowcount == 0:
        existe = con.execute(
            ais.seleccionar(ctx, ops_compra, ops_compra.c.id).where(ops_compra.c.id == compra_id)
        ).first()
        raise YaAnulada if existe else NoEncontrado

    entradas = con.execute(
        ais.seleccionar(
            ctx, ops_movimiento_inventario, ops_movimiento_inventario.c.insumo_id,
            ops_movimiento_inventario.c.cantidad_base,
            ops_movimiento_inventario.c.costo_unitario_base,
        ).where(ops_movimiento_inventario.c.origen_tipo == ORIGEN_COMPRA,
                ops_movimiento_inventario.c.origen_id == compra_id,
                ops_movimiento_inventario.c.tipo == "entrada")
        .order_by(ops_movimiento_inventario.c.insumo_id, ops_movimiento_inventario.c.id)
    ).all()
    for entrada in entradas:
        try:
            fila = inventario.bloquear(con, ctx, entrada.insumo_id)
        except inventario.NoEncontrado:
            continue  # el insumo se archivó: no hay existencia que devolver
        valor_comprado = entrada.cantidad_base * entrada.costo_unitario_base
        queda = fila.existencia_base - entrada.cantidad_base
        if queda > 0:
            nuevo = ((fila.existencia_base * fila.costo_promedio_base - valor_comprado) / queda)
            nuevo = max(Decimal("0"), nuevo).quantize(OCHO, ROUND_HALF_UP)
        else:
            nuevo = fila.costo_promedio_base
        inventario.aplicar(con, ctx, fila, "reverso_compra", -entrada.cantidad_base, None,
                           origen_tipo=ORIGEN_COMPRA, origen_id=compra_id,
                           costo_movimiento=entrada.costo_unitario_base, costo_promedio_nuevo=nuevo)
    contabilidad.revertir_compra(con, ctx, compra_id)
    return obtener_compra(con, ctx, compra_id)
