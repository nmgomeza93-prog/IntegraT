"""Caja del día y dinero del dueño. Todo acceso a tablas de negocio pasa por db.aislamiento.

Reglas (docs/PLAN_CAJA.md): el efectivo esperado sale de los libros (cuenta de Caja) desde que se
abrió la caja; la diferencia al cerrar queda como faltante o sobrante con su asiento.

Las horas de apertura y cierre se toman del reloj de la BASE (CURRENT_TIMESTAMP), el mismo que
marca `creado_en` de los asientos: así la ventana de la caja y los asientos nunca se desfasan
aunque el reloj del servidor de la API difiera unos segundos.
"""

import uuid
from collections import defaultdict
from datetime import UTC, date, datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.engine import Connection, Engine

from integrat import idempotencia
from integrat.caja.esquemas import (
    AbrirCajaIn,
    CajaOut,
    CerrarCajaIn,
    ListaCierresOut,
    ListaDuenoOut,
    MovimientoDuenoIn,
    MovimientoDuenoOut,
    ResumenCajaOut,
    SesionCajaOut,
)
from integrat.contabilidad import eventos as contabilidad
from integrat.contabilidad.motor import cuenta_de_rol
from integrat.db import aislamiento as ais
from integrat.db.tablas import (
    cont_asiento,
    cont_asiento_linea,
    core_negocio,
    ops_movimiento_dueno,
    ops_pago,
    ops_sesion_caja,
    ops_venta,
)
from integrat.db.tipos import ahora_utc, uuid7
from integrat.gastos.servicio import MesInvalido, _rango_del_mes
from integrat.tiempo import hoy_del_negocio

CERO = Decimal("0.00")
OPERACION_CERRAR = "cerrar_caja"
OPERACION_DUENO = "movimiento_dueno"
MAX_POR_MES = 500
# Origen del asiento -> renglón del resumen de la caja.
RENGLON_POR_ORIGEN = {"venta": "ventas", "gasto": "gastos", "compra": "compras",
                      "movimiento": "inventario", "dueno": "dueno"}

__all__ = ["MesInvalido"]  # se re-exporta para el router


class YaAbierta(Exception):
    pass


class NoHayAbierta(Exception):
    pass


class NoEncontrado(Exception):
    pass


class FechaFutura(Exception):
    pass


def _dinero(valor: Decimal) -> str:
    return f"{valor:.2f}"


def _utc(valor: datetime | None) -> datetime | None:
    return None if valor is None else valor.replace(tzinfo=UTC)


def _ahora_bd(con: Connection) -> datetime:
    return con.execute(sa.text("SELECT CURRENT_TIMESTAMP(6)")).scalar_one()


# ------------------------------------------------------------------ resumen

def _resumen(con: Connection, ctx: ais.ContextoNegocio, desde: datetime,
             hasta: datetime | None) -> tuple[Decimal, ResumenCajaOut]:
    """Movimiento neto de Caja en la ventana (sin el asiento del propio cierre) y su desglose."""
    caja = cuenta_de_rol(con, ctx, "CAJA")
    asiento = sa.and_(cont_asiento.c.id == cont_asiento_linea.c.asiento_id,
                      cont_asiento.c.negocio_id == ctx.negocio_id)
    consulta = (
        ais.seleccionar(ctx, cont_asiento_linea, cont_asiento.c.origen_tipo,
                        sa.func.sum(cont_asiento_linea.c.debe - cont_asiento_linea.c.haber)
                        .label("neto"))
        .select_from(cont_asiento_linea.join(cont_asiento, asiento))
        .where(cont_asiento_linea.c.cuenta_contable_id == caja,
               cont_asiento.c.creado_en >= desde,
               sa.or_(cont_asiento.c.origen_tipo.is_(None),
                      cont_asiento.c.origen_tipo != contabilidad.ORIGEN_CAJA))
        .group_by(cont_asiento.c.origen_tipo)
    )
    if hasta is not None:
        consulta = consulta.where(cont_asiento.c.creado_en <= hasta)
    renglones: dict[str, Decimal] = defaultdict(lambda: CERO)
    for f in con.execute(consulta):
        renglones[RENGLON_POR_ORIGEN.get(f.origen_tipo, "otros")] += Decimal(f.neto or 0)

    ventas = (
        ais.seleccionar(ctx, ops_venta, ops_pago.c.medio_pago,
                        sa.func.count().label("cantidad"), sa.func.sum(ops_pago.c.monto)
                        .label("total"))
        .select_from(ops_venta.join(ops_pago, sa.and_(ops_pago.c.venta_id == ops_venta.c.id,
                                                      ops_pago.c.negocio_id == ctx.negocio_id)))
        .where(ops_venta.c.estado == "pagada", ops_venta.c.creado_en >= desde)
        .group_by(ops_pago.c.medio_pago)
    )
    if hasta is not None:
        ventas = ventas.where(ops_venta.c.creado_en <= hasta)
    por_medio = {f.medio_pago: (f.cantidad, Decimal(f.total or 0)) for f in con.execute(ventas)}
    neto = sum(renglones.values(), CERO)
    return neto, ResumenCajaOut(
        ventas=_dinero(renglones["ventas"]), gastos=_dinero(renglones["gastos"]),
        compras=_dinero(renglones["compras"]), inventario=_dinero(renglones["inventario"]),
        dueno=_dinero(renglones["dueno"]), otros=_dinero(renglones["otros"]),
        cantidad_ventas=sum(c for c, _ in por_medio.values()),
        ventas_tarjeta=_dinero(por_medio.get("tarjeta", (0, CERO))[1]),
        ventas_transferencia=_dinero(por_medio.get("transferencia", (0, CERO))[1]),
    )


def _sesion_out(con: Connection, ctx: ais.ContextoNegocio, f) -> SesionCajaOut:
    neto, resumen = _resumen(con, ctx, f.abierta_en, f.cerrada_en)
    esperado = f.efectivo_esperado if f.estado == "cerrada" else f.monto_apertura + neto
    return SesionCajaOut(
        id=f.id, fecha=f.fecha, abierta_en=_utc(f.abierta_en),
        monto_apertura=_dinero(f.monto_apertura), estado=f.estado,
        efectivo_esperado=_dinero(esperado),
        efectivo_contado=None if f.efectivo_contado is None else _dinero(f.efectivo_contado),
        diferencia=None if f.diferencia is None else _dinero(f.diferencia),
        cerrada_en=_utc(f.cerrada_en), nota=f.nota, resumen=resumen,
    )


def _abierta(con: Connection, ctx: ais.ContextoNegocio, *, bloquear: bool = False):
    consulta = ais.seleccionar(ctx, ops_sesion_caja).where(ops_sesion_caja.c.estado == "abierta")
    return con.execute(consulta.with_for_update() if bloquear else consulta).first()


def _obtener(con: Connection, ctx: ais.ContextoNegocio, sesion_id: uuid.UUID) -> SesionCajaOut:
    fila = con.execute(
        ais.seleccionar(ctx, ops_sesion_caja).where(ops_sesion_caja.c.id == sesion_id)).first()
    if fila is None:
        raise idempotencia.YaNoExiste
    return _sesion_out(con, ctx, fila)


# ------------------------------------------------------------------ caja

def estado_caja(con: Connection, ctx: ais.ContextoNegocio) -> CajaOut:
    abierta = _abierta(con, ctx)
    ultimo = con.execute(
        ais.seleccionar(ctx, ops_sesion_caja).where(ops_sesion_caja.c.estado == "cerrada")
        .order_by(ops_sesion_caja.c.cerrada_en.desc()).limit(1)
    ).first()
    return CajaOut(
        abierta=None if abierta is None else _sesion_out(con, ctx, abierta),
        ultimo_cierre=None if ultimo is None else _sesion_out(con, ctx, ultimo),
    )


def abrir_caja(con: Connection, ctx: ais.ContextoNegocio, datos: AbrirCajaIn) -> SesionCajaOut:
    # Se serializa por negocio: dos aperturas a la vez no dejan dos cajas abiertas.
    con.execute(sa.select(core_negocio.c.id).where(core_negocio.c.id == ctx.negocio_id)
                .with_for_update())
    if _abierta(con, ctx, bloquear=True) is not None:
        raise YaAbierta
    sesion_id = uuid7()
    con.execute(ais.insertar(ctx, ops_sesion_caja, {
        "id": sesion_id, "fecha": hoy_del_negocio(con, ctx), "abierta_en": _ahora_bd(con),
        "monto_apertura": datos.monto_apertura, "estado": "abierta",
    }))
    return _obtener(con, ctx, sesion_id)


def _cerrar(con: Connection, ctx: ais.ContextoNegocio, datos: CerrarCajaIn):
    sesion = _abierta(con, ctx, bloquear=True)
    if sesion is None:
        raise NoHayAbierta
    ahora = _ahora_bd(con)
    neto, _ = _resumen(con, ctx, sesion.abierta_en, ahora)
    esperado = sesion.monto_apertura + neto
    diferencia = datos.efectivo_contado - esperado
    con.execute(
        ais.actualizar(ctx, ops_sesion_caja, ops_sesion_caja.c.id == sesion.id).values(
            estado="cerrada", cerrada_en=ahora, cerrada_por=ctx.usuario_id,
            efectivo_esperado=esperado, efectivo_contado=datos.efectivo_contado,
            diferencia=diferencia, nota=datos.nota or None, version=ops_sesion_caja.c.version + 1,
            actualizado_por=ctx.usuario_id,
        )
    )
    contabilidad.asentar_diferencia_caja(con, ctx, sesion.id, diferencia)
    return sesion.id, _obtener(con, ctx, sesion.id)


def cerrar_caja(engine: Engine, ctx: ais.ContextoNegocio, datos: CerrarCajaIn,
                clave: str | None) -> SesionCajaOut:
    return idempotencia.ejecutar(
        engine, ctx, OPERACION_CERRAR, clave, idempotencia.huella(datos),
        crear=lambda con: _cerrar(con, ctx, datos),
        leer=lambda con, sesion_id: _obtener(con, ctx, sesion_id),
    )


def cierres_del_mes(con: Connection, ctx: ais.ContextoNegocio, mes: str | None) -> ListaCierresOut:
    inicio, siguiente, etiqueta = _rango_del_mes(mes, hoy_del_negocio(con, ctx))
    filas = con.execute(
        ais.seleccionar(ctx, ops_sesion_caja)
        .where(ops_sesion_caja.c.estado == "cerrada", ops_sesion_caja.c.fecha >= inicio,
               ops_sesion_caja.c.fecha < siguiente)
        .order_by(ops_sesion_caja.c.cerrada_en.desc()).limit(MAX_POR_MES)
    ).all()
    return ListaCierresOut(mes=etiqueta, cierres=[_sesion_out(con, ctx, f) for f in filas])


# ------------------------------------------------------------------ dueño

def _dueno_out(f) -> MovimientoDuenoOut:
    return MovimientoDuenoOut(id=f.id, tipo=f.tipo, monto=_dinero(f.monto), medio=f.medio,
                              fecha=f.fecha, nota=f.nota)


def _leer_dueno(con: Connection, ctx: ais.ContextoNegocio,
                movimiento_id: uuid.UUID) -> MovimientoDuenoOut:
    fila = con.execute(ais.seleccionar(ctx, ops_movimiento_dueno)
                       .where(ops_movimiento_dueno.c.id == movimiento_id)).first()
    if fila is None:
        raise idempotencia.YaNoExiste
    return _dueno_out(fila)


def _crear_dueno(con: Connection, ctx: ais.ContextoNegocio, datos: MovimientoDuenoIn):
    hoy = hoy_del_negocio(con, ctx)
    fecha: date = datos.fecha or hoy
    if fecha > hoy:
        raise FechaFutura
    movimiento_id = uuid7()
    con.execute(ais.insertar(ctx, ops_movimiento_dueno, {
        "id": movimiento_id, "tipo": datos.tipo, "monto": datos.monto, "medio": datos.medio,
        "fecha": fecha, "nota": datos.nota or None,
    }))
    contabilidad.asentar_dueno(con, ctx, movimiento_id, tipo=datos.tipo, monto=datos.monto,
                               medio=datos.medio, fecha=fecha)
    return movimiento_id, _leer_dueno(con, ctx, movimiento_id)


def crear_movimiento_dueno(engine: Engine, ctx: ais.ContextoNegocio, datos: MovimientoDuenoIn,
                           clave: str | None) -> MovimientoDuenoOut:
    return idempotencia.ejecutar(
        engine, ctx, OPERACION_DUENO, clave, idempotencia.huella(datos),
        crear=lambda con: _crear_dueno(con, ctx, datos),
        leer=lambda con, movimiento_id: _leer_dueno(con, ctx, movimiento_id),
    )


def borrar_movimiento_dueno(con: Connection, ctx: ais.ContextoNegocio,
                            movimiento_id: uuid.UUID) -> None:
    resultado = con.execute(
        ais.actualizar(ctx, ops_movimiento_dueno, ops_movimiento_dueno.c.id == movimiento_id)
        .values(eliminado_en=ahora_utc(), eliminado_por=ctx.usuario_id)
    )
    if resultado.rowcount == 0:
        raise NoEncontrado
    contabilidad.revertir_dueno(con, ctx, movimiento_id)


def movimientos_dueno_del_mes(con: Connection, ctx: ais.ContextoNegocio,
                              mes: str | None) -> ListaDuenoOut:
    inicio, siguiente, etiqueta = _rango_del_mes(mes, hoy_del_negocio(con, ctx))
    filas = con.execute(
        ais.seleccionar(ctx, ops_movimiento_dueno)
        .where(ops_movimiento_dueno.c.fecha >= inicio, ops_movimiento_dueno.c.fecha < siguiente)
        .order_by(ops_movimiento_dueno.c.fecha.desc(), ops_movimiento_dueno.c.creado_en.desc())
        .limit(MAX_POR_MES)
    ).all()
    movimientos = [_dueno_out(f) for f in filas]
    aportes = sum((f.monto for f in filas if f.tipo == "aporte"), CERO)
    retiros = sum((f.monto for f in filas if f.tipo == "retiro"), CERO)
    return ListaDuenoOut(mes=etiqueta, total_aportes=_dinero(aportes),
                         total_retiros=_dinero(retiros), movimientos=movimientos)
