"""Insumos y sus movimientos. Todo acceso a tablas de negocio pasa por db.aislamiento.

Existencia y costo viven en la unidad base (UN, G o ML); aquí se convierte de y hacia la unidad de
uso del insumo. Los movimientos son inmutables: lo que ya pasó no se edita, se corrige con otro.
"""

import hashlib
import json
import uuid
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

import sqlalchemy as sa
from sqlalchemy.engine import Connection, Engine

from integrat.contabilidad import eventos as contabilidad
from integrat.db import aislamiento as ais
from integrat.db.tablas import (
    cat_unidad_medida,
    core_idempotencia,
    ops_insumo,
    ops_movimiento_inventario,
)
from integrat.db.tipos import ahora_utc, uuid7
from integrat.insumos.esquemas import (
    InsumoCambios,
    InsumoIn,
    InsumoOut,
    ListaInsumosOut,
    ListaMovimientosOut,
    MovimientoIn,
    MovimientoOut,
    UnidadOut,
)

OPERACION_MOVIMIENTO = "crear_movimiento_inventario"
VIGENCIA_IDEMPOTENCIA = timedelta(hours=24)
MAX_INSUMOS = 500
MAX_MOVIMIENTOS = 100
CERO = Decimal("0")
CUATRO = Decimal("0.0001")
OCHO = Decimal("0.00000001")
CENTAVOS = Decimal("0.01")


class NoEncontrado(Exception):
    pass


class VersionDesfasada(Exception):
    """Alguien más cambió el registro después de que la persona lo vio."""


class NombreRepetido(Exception):
    pass


class UnidadInvalida(Exception):
    """La unidad no existe o no se puede usar para este insumo."""


class SinCambio(Exception):
    """El ajuste pide la cantidad que ya hay."""


class ClaveReutilizada(Exception):
    """La misma Idempotency-Key llegó con datos distintos."""


# ------------------------------------------------------------------ unidades

def listar_unidades(con: Connection) -> list[UnidadOut]:
    """Las unidades que se pueden usar: las que tienen conversión fija (sin CAJA ni PAQ)."""
    filas = con.execute(
        sa.select(cat_unidad_medida.c.codigo, cat_unidad_medida.c.nombre, cat_unidad_medida.c.tipo)
        .where(cat_unidad_medida.c.factor_a_base.is_not(None))
        .order_by(cat_unidad_medida.c.tipo, cat_unidad_medida.c.factor_a_base)
    ).all()
    return [UnidadOut(codigo=f.codigo, nombre=f.nombre, tipo=f.tipo) for f in filas]


def buscar_unidad(con: Connection, codigo: str):
    fila = con.execute(
        sa.select(cat_unidad_medida.c.codigo, cat_unidad_medida.c.tipo,
                  cat_unidad_medida.c.factor_a_base.label("factor"))
        .where(cat_unidad_medida.c.codigo == codigo.upper(),
               cat_unidad_medida.c.factor_a_base.is_not(None))
    ).first()
    if fila is None:
        raise UnidadInvalida
    return fila


# ------------------------------------------------------------------ formato

def cantidad_texto(valor: Decimal) -> str:
    q = valor.quantize(CUATRO, ROUND_HALF_UP)
    if q == 0:
        return "0"
    texto = f"{q:f}"
    return texto.rstrip("0").rstrip(".") if "." in texto else texto


def _costo_texto(valor: Decimal) -> str:
    """Costo por unidad: 4 decimales como máximo, 2 como mínimo ("15.00", "0.0331")."""
    entero, decimales = f"{valor.quantize(CUATRO, ROUND_HALF_UP):f}".split(".")
    return f"{entero}.{decimales.rstrip('0').ljust(2, '0')}"


def _estado(existencia_base: Decimal, minimo_base: Decimal) -> str:
    if existencia_base <= 0:
        return "falta"
    if minimo_base > 0 and existencia_base <= minimo_base:
        return "poco"
    return "ok"


# ------------------------------------------------------------------ insumos

def _consulta(ctx: ais.ContextoNegocio) -> sa.Select:
    return ais.seleccionar(
        ctx, ops_insumo,
        ops_insumo.c.id, ops_insumo.c.nombre, ops_insumo.c.unidad_codigo,
        ops_insumo.c.existencia_base, ops_insumo.c.costo_promedio_base,
        ops_insumo.c.stock_minimo_base, ops_insumo.c.version, ops_insumo.c.item_id,
        cat_unidad_medida.c.nombre.label("unidad_nombre"),
        cat_unidad_medida.c.factor_a_base.label("factor"),
    ).select_from(ops_insumo.join(
        cat_unidad_medida, cat_unidad_medida.c.codigo == ops_insumo.c.unidad_codigo))


def _insumo_out(f) -> InsumoOut:
    factor = f.factor
    valor = max(CERO, f.existencia_base * f.costo_promedio_base).quantize(CENTAVOS, ROUND_HALF_UP)
    return InsumoOut(
        id=f.id, nombre=f.nombre, unidad_codigo=f.unidad_codigo, unidad_nombre=f.unidad_nombre,
        existencia=cantidad_texto(f.existencia_base / factor),
        costo_unitario=_costo_texto(f.costo_promedio_base * factor), valor=f"{valor:.2f}",
        stock_minimo=cantidad_texto(f.stock_minimo_base / factor),
        estado=_estado(f.existencia_base, f.stock_minimo_base), item_id=f.item_id,
        version=f.version,
    )


def obtener_insumo(con: Connection, ctx: ais.ContextoNegocio, insumo_id: uuid.UUID) -> InsumoOut:
    fila = con.execute(_consulta(ctx).where(ops_insumo.c.id == insumo_id)).first()
    if fila is None:
        raise NoEncontrado
    return _insumo_out(fila)


def _escapar_like(texto: str) -> str:
    return texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def listar_insumos(con: Connection, ctx: ais.ContextoNegocio,
                   buscar: str | None) -> ListaInsumosOut:
    consulta = _consulta(ctx)
    if buscar and buscar.strip():
        consulta = consulta.where(
            ops_insumo.c.nombre.like(f"%{_escapar_like(buscar.strip())}%", escape="\\"))
    filas = con.execute(consulta.order_by(ops_insumo.c.nombre, ops_insumo.c.id)
                        .limit(MAX_INSUMOS)).all()
    insumos = [_insumo_out(f) for f in filas]
    valor = sum((Decimal(i.valor) for i in insumos), CERO)
    return ListaInsumosOut(
        total=len(insumos), valor_inventario=f"{valor:.2f}",
        por_reponer=sum(1 for i in insumos if i.estado != "ok"), insumos=insumos,
    )


def nombre_repetido(con, ctx, nombre: str, excepto: uuid.UUID | None) -> bool:
    consulta = ais.seleccionar(ctx, ops_insumo, ops_insumo.c.id).where(
        ops_insumo.c.nombre == nombre)
    if excepto is not None:
        consulta = consulta.where(ops_insumo.c.id != excepto)
    return con.execute(consulta).first() is not None


def crear_insumo(con: Connection, ctx: ais.ContextoNegocio, datos: InsumoIn) -> InsumoOut:
    unidad = buscar_unidad(con, datos.unidad_codigo)
    if nombre_repetido(con, ctx, datos.nombre, None):
        raise NombreRepetido
    minimo = (datos.stock_minimo or CERO) * unidad.factor
    insumo_id = uuid7()
    con.execute(ais.insertar(ctx, ops_insumo, {
        "id": insumo_id, "nombre": datos.nombre, "unidad_codigo": unidad.codigo,
        "stock_minimo_base": minimo.quantize(CUATRO, ROUND_HALF_UP),
    }))
    if datos.existencia_inicial is not None:
        fila = bloquear(con, ctx, insumo_id)
        movimiento_id = aplicar(con, ctx, fila, "inicial",
                                (datos.existencia_inicial * unidad.factor),
                                datos.costo_total_inicial)
        contabilidad.asentar_movimiento(con, ctx, movimiento_id, valor=datos.costo_total_inicial)
    return obtener_insumo(con, ctx, insumo_id)


def actualizar_insumo(con: Connection, ctx: ais.ContextoNegocio, insumo_id: uuid.UUID,
                      cambios: InsumoCambios) -> InsumoOut:
    actual = con.execute(_consulta(ctx).where(ops_insumo.c.id == insumo_id)).first()
    if actual is None:
        raise NoEncontrado
    if actual.version != cambios.version:
        raise VersionDesfasada
    enviados = cambios.model_fields_set
    valores: dict = {}
    if "nombre" in enviados and cambios.nombre is not None:
        if nombre_repetido(con, ctx, cambios.nombre, insumo_id):
            raise NombreRepetido
        valores["nombre"] = cambios.nombre
    if "stock_minimo" in enviados and cambios.stock_minimo is not None:
        valores["stock_minimo_base"] = (cambios.stock_minimo * actual.factor).quantize(
            CUATRO, ROUND_HALF_UP)
    resultado = con.execute(
        ais.actualizar(ctx, ops_insumo, ops_insumo.c.id == insumo_id,
                       ops_insumo.c.version == cambios.version)
        .values(**valores, version=ops_insumo.c.version + 1, actualizado_por=ctx.usuario_id)
    )
    if resultado.rowcount == 0:
        raise VersionDesfasada
    return obtener_insumo(con, ctx, insumo_id)


def archivar_insumo(con: Connection, ctx: ais.ContextoNegocio, insumo_id: uuid.UUID) -> None:
    """Sus movimientos se conservan; deja de ofrecerse."""
    resultado = con.execute(
        ais.actualizar(ctx, ops_insumo, ops_insumo.c.id == insumo_id)
        .values(eliminado_en=ahora_utc(), eliminado_por=ctx.usuario_id)
    )
    if resultado.rowcount == 0:
        raise NoEncontrado


# ------------------------------------------------------------------ movimientos

def bloquear(con: Connection, ctx: ais.ContextoNegocio, insumo_id: uuid.UUID):
    """Lee el insumo bloqueándolo: dos movimientos a la vez se hacen uno tras otro.

    La lectura con bloqueo ve lo último confirmado aunque la transacción ya tenga su "foto"
    (REPEATABLE READ), así que la existencia que se suma nunca es una vieja.
    """
    fila = con.execute(
        _consulta(ctx).where(ops_insumo.c.id == insumo_id).with_for_update(of=ops_insumo)
    ).first()
    if fila is None:
        raise NoEncontrado
    return fila


def aplicar(con: Connection, ctx: ais.ContextoNegocio, fila, tipo: str, cantidad_base: Decimal,
             costo_total: Decimal | None, *, origen_tipo: str | None = None,
             origen_id: uuid.UUID | None = None, nota: str | None = None,
             costo_movimiento: Decimal | None = None,
             costo_promedio_nuevo: Decimal | None = None) -> uuid.UUID:
    """Registra un movimiento y deja al día la existencia y el costo promedio.

    `cantidad_base` lleva signo, salvo en entradas e iniciales (siempre positiva). Solo las
    entradas cambian el costo promedio; lo demás sale o entra al costo vigente (o a
    `costo_movimiento`, para devolver al costo con que salió).
    """
    existencia, costo = fila.existencia_base, fila.costo_promedio_base
    cantidad_base = cantidad_base.quantize(CUATRO, ROUND_HALF_UP)
    if tipo in ("entrada", "inicial"):
        costo_mov = (costo_total / cantidad_base).quantize(OCHO, ROUND_HALF_UP)
        if existencia <= 0:
            nuevo_costo = costo_mov
        else:
            nuevo_costo = ((existencia * costo + costo_total)
                           / (existencia + cantidad_base)).quantize(OCHO, ROUND_HALF_UP)
    else:
        costo_mov = costo if costo_movimiento is None else costo_movimiento
        # lo que sale o se devuelve no cambia el promedio, salvo que se pida (anular una compra)
        nuevo_costo = costo if costo_promedio_nuevo is None else costo_promedio_nuevo
    movimiento_id = uuid7()
    con.execute(ais.insertar(ctx, ops_movimiento_inventario, {
        "id": movimiento_id, "insumo_id": fila.id, "fecha_hora": ahora_utc(), "tipo": tipo,
        "cantidad_base": cantidad_base, "costo_unitario_base": costo_mov,
        "origen_tipo": origen_tipo, "origen_id": origen_id, "nota": nota,
    }))
    con.execute(
        ais.actualizar(ctx, ops_insumo, ops_insumo.c.id == fila.id).values(
            existencia_base=existencia + cantidad_base, costo_promedio_base=nuevo_costo,
            actualizado_por=ctx.usuario_id,  # sin cambiar `version`: no pisa ediciones
        )
    )
    return movimiento_id


def _movimiento_out(f, factor: Decimal, insumo: InsumoOut | None = None) -> MovimientoOut:
    return MovimientoOut(
        id=f.id, tipo=f.tipo, cantidad=cantidad_texto(f.cantidad_base / factor),
        costo_unitario=_costo_texto(f.costo_unitario_base * factor), fecha_hora=f.fecha_hora,
        nota=f.nota, insumo=insumo,
    )


def _consulta_movimientos(ctx: ais.ContextoNegocio) -> sa.Select:
    return ais.seleccionar(
        ctx, ops_movimiento_inventario, ops_movimiento_inventario.c.id,
        ops_movimiento_inventario.c.tipo, ops_movimiento_inventario.c.cantidad_base,
        ops_movimiento_inventario.c.costo_unitario_base, ops_movimiento_inventario.c.fecha_hora,
        ops_movimiento_inventario.c.nota, cat_unidad_medida.c.factor_a_base.label("factor"),
    ).select_from(
        ops_movimiento_inventario
        .join(ops_insumo, ops_insumo.c.id == ops_movimiento_inventario.c.insumo_id)
        .join(cat_unidad_medida, cat_unidad_medida.c.codigo == ops_insumo.c.unidad_codigo)
    )


def obtener_movimiento(con: Connection, ctx: ais.ContextoNegocio, movimiento_id: uuid.UUID,
                       insumo_id: uuid.UUID) -> MovimientoOut:
    fila = con.execute(
        _consulta_movimientos(ctx).where(
            ops_movimiento_inventario.c.id == movimiento_id,
            ops_movimiento_inventario.c.insumo_id == insumo_id)
    ).first()
    if fila is None:
        raise NoEncontrado
    return _movimiento_out(fila, fila.factor, obtener_insumo(con, ctx, insumo_id))


def registrar_movimiento(con: Connection, ctx: ais.ContextoNegocio, insumo_id: uuid.UUID,
                         datos: MovimientoIn) -> MovimientoOut:
    fila = bloquear(con, ctx, insumo_id)
    propia = buscar_unidad(con, fila.unidad_codigo)
    usada = buscar_unidad(con, datos.unidad_codigo) if datos.unidad_codigo else propia
    if usada.tipo != propia.tipo:
        raise UnidadInvalida  # no se convierte peso a volumen
    cantidad_base = datos.cantidad * usada.factor

    if datos.tipo == "entrada":
        movimiento_id = aplicar(con, ctx, fila, "entrada", cantidad_base, datos.costo_total,
                                 nota=datos.nota)
    elif datos.tipo == "merma":
        movimiento_id = aplicar(con, ctx, fila, "merma", -cantidad_base, None, nota=datos.nota)
    else:
        diferencia = cantidad_base.quantize(CUATRO, ROUND_HALF_UP) - fila.existencia_base
        if diferencia == 0:
            raise SinCambio
        movimiento_id = aplicar(con, ctx, fila, "ajuste", diferencia, None, nota=datos.nota)
    contabilidad.asentar_movimiento(con, ctx, movimiento_id, valor=datos.costo_total)
    return obtener_movimiento(con, ctx, movimiento_id, insumo_id)


def listar_movimientos(con: Connection, ctx: ais.ContextoNegocio,
                       insumo_id: uuid.UUID) -> ListaMovimientosOut:
    obtener_insumo(con, ctx, insumo_id)  # 404 si no es de este negocio
    filas = con.execute(
        _consulta_movimientos(ctx)
        .where(ops_movimiento_inventario.c.insumo_id == insumo_id)
        .order_by(ops_movimiento_inventario.c.fecha_hora.desc(),
                  ops_movimiento_inventario.c.id.desc())
        .limit(MAX_MOVIMIENTOS)
    ).all()
    return ListaMovimientosOut(movimientos=[_movimiento_out(f, f.factor) for f in filas])


def _huella(insumo_id: uuid.UUID, datos: MovimientoIn) -> str:
    cuerpo = {"insumo": str(insumo_id), **datos.model_dump(mode="json")}
    return hashlib.sha256(json.dumps(cuerpo, sort_keys=True).encode()).hexdigest()


def registrar_movimiento_idempotente(engine: Engine, ctx: ais.ContextoNegocio,
                                     insumo_id: uuid.UUID, datos: MovimientoIn,
                                     clave: str | None) -> MovimientoOut:
    """Registra el movimiento una sola vez por (usuario, Idempotency-Key); sin clave, siempre."""
    if clave is None:
        with engine.begin() as con:
            return registrar_movimiento(con, ctx, insumo_id, datos)

    huella = _huella(insumo_id, datos)
    filtro = sa.and_(
        core_idempotencia.c.usuario_id == ctx.usuario_id,
        core_idempotencia.c.operacion == OPERACION_MOVIMIENTO,
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
                        return obtener_movimiento(con, ctx, previo["recurso_id"], insumo_id)
                    except NoEncontrado:
                        con.execute(sa.delete(core_idempotencia).where(filtro))
                movimiento = registrar_movimiento(con, ctx, insumo_id, datos)
                con.execute(sa.insert(core_idempotencia).values(
                    id=uuid7(), usuario_id=ctx.usuario_id, operacion=OPERACION_MOVIMIENTO,
                    clave=clave, huella=huella, recurso_id=movimiento.id,
                    creado_por=ctx.usuario_id,
                ))
                return movimiento
        except sa.exc.IntegrityError:
            # Carrera: otra petición con la misma clave se confirmó primero; se reintenta una vez.
            if intento == 2:
                raise
    raise AssertionError("inalcanzable")
