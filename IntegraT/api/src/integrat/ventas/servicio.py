"""Ventas rápidas. Todo acceso a tablas de negocio pasa por db.aislamiento.

Reglas (docs/PLAN_VENTAS.md): la API calcula el total con el precio vigente y lo congela en cada
línea; las ventas no se editan ni se borran, se anulan; el número es consecutivo por negocio.
"""

import hashlib
import json
import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.engine import Connection, Engine

from integrat import existencias
from integrat.contabilidad import eventos as contabilidad
from integrat.db import aislamiento as ais
from integrat.db.tablas import (
    core_idempotencia,
    core_negocio,
    ops_item,
    ops_item_variante,
    ops_pago,
    ops_venta,
    ops_venta_linea,
)
from integrat.db.tipos import ahora_utc, uuid7
from integrat.insumos import recetas
from integrat.tiempo import zona_del_negocio
from integrat.ventas.esquemas import (
    MEDIOS_PAGO,
    LineaOut,
    ListaVentasOut,
    ResumenOut,
    VentaIn,
    VentaOut,
)

OPERACION_CREAR_VENTA = "crear_venta"
VIGENCIA_IDEMPOTENCIA = timedelta(hours=24)
CENTAVO = Decimal("0.01")
MAX_VENTAS_POR_DIA = 500


class NoEncontrado(Exception):
    pass


class ItemNoVendible(Exception):
    """Un ítem no existe en este negocio, está archivado o no está a la venta."""


class FaltaVariante(Exception):
    """El producto tiene variantes (talla, color…) y la línea no dice cuál."""


class YaAnulada(Exception):
    pass


class ClaveReutilizada(Exception):
    """La misma Idempotency-Key llegó con datos distintos."""


def _utc(valor: datetime | None) -> datetime | None:
    return None if valor is None else valor.replace(tzinfo=UTC)


# ------------------------------------------------------------------ crear

Clave = tuple[uuid.UUID, uuid.UUID | None]  # (ítem, variante pedida)


def _cantidades_por_item(datos: VentaIn) -> dict[Clave, int]:
    """El mismo ítem (y la misma variante) repetido se suma."""
    cantidades: dict[Clave, int] = defaultdict(int)
    for linea in datos.lineas:
        cantidades[(linea.item_id, linea.item_variante_id)] += linea.cantidad
    return dict(cantidades)


def _cargar_variantes(con: Connection, ctx: ais.ContextoNegocio, ids: list[uuid.UUID]):
    """Variantes vivas de los ítems vendibles del negocio, con su precio vigente."""
    variante = sa.and_(
        ops_item_variante.c.item_id == ops_item.c.id,
        ops_item_variante.c.negocio_id == ctx.negocio_id,
        ops_item_variante.c.eliminado_en.is_(None),
    )
    filas = con.execute(
        ais.seleccionar(
            ctx, ops_item, ops_item.c.id, ops_item.c.nombre,
            ops_item_variante.c.id.label("variante_id"), ops_item_variante.c.precio_venta,
            ops_item_variante.c.nombre.label("variante_nombre"),
            ops_item_variante.c.atributos,
        )
        .select_from(ops_item.join(ops_item_variante, variante))
        .where(ops_item.c.id.in_(ids), ops_item.c.se_vende.is_(True))
    ).all()
    por_item: dict[uuid.UUID, list] = defaultdict(list)
    for f in filas:
        por_item[f.id].append(f)
    return por_item


def _resolver(por_item: dict, item_id: uuid.UUID, variante_id: uuid.UUID | None):
    """La variante que se vende: la pedida o, si el ítem no tiene variantes, su implícita."""
    opciones = por_item.get(item_id)
    if not opciones:
        raise ItemNoVendible
    if variante_id is not None:
        elegida = next((f for f in opciones if f.variante_id == variante_id), None)
        if elegida is None:
            raise ItemNoVendible
        return elegida
    if any(f.atributos is not None for f in opciones):
        raise FaltaVariante
    return opciones[0]


def _siguiente_numero(con: Connection, ctx: ais.ContextoNegocio) -> int:
    """Siguiente número consecutivo del negocio.

    Se bloquea la fila del negocio: las ventas de un mismo negocio se numeran de una en una
    (las de negocios distintos no se estorban). La lectura del último número es "con bloqueo"
    para ver lo ya confirmado por las ventas que acaban de terminar.
    """
    con.execute(
        sa.select(core_negocio.c.id).where(core_negocio.c.id == ctx.negocio_id).with_for_update()
    )
    ultimo = con.execute(
        ais.seleccionar(ctx, ops_venta, ops_venta.c.numero, incluir_eliminados=True)
        .order_by(ops_venta.c.numero.desc()).limit(1).with_for_update()
    ).scalar()
    return (ultimo or 0) + 1


def crear_venta(con: Connection, ctx: ais.ContextoNegocio, datos: VentaIn) -> VentaOut:
    pedidas = _cantidades_por_item(datos)
    por_item = _cargar_variantes(con, ctx, list({i for i, _ in pedidas}))

    lineas = []
    vendidas: dict[tuple[uuid.UUID, uuid.UUID], int] = defaultdict(int)  # (ítem, variante real)
    nombres: dict[tuple[uuid.UUID, uuid.UUID], str] = {}
    for (item_id, variante_id), cantidad in pedidas.items():
        fila = _resolver(por_item, item_id, variante_id)
        precio = Decimal(fila.precio_venta).quantize(CENTAVO)
        nombre = fila.nombre
        if fila.atributos is not None:  # "Pijama Luxe · M · Rosa"
            nombre = f"{fila.nombre} · {fila.variante_nombre}"
        lineas.append({
            "item_id": item_id, "item_variante_id": fila.variante_id, "nombre": nombre[:120],
            "cantidad": cantidad, "precio_unitario": precio,
            "total": (precio * cantidad).quantize(CENTAVO),
        })
        vendidas[(item_id, fila.variante_id)] += cantidad
        nombres[(item_id, fila.variante_id)] = nombre
    # Antes de numerar y cobrar: si el negocio no vende sin existencia, que todo alcance.
    existencias.verificar(con, ctx, dict(vendidas), nombres)
    total = sum((linea["total"] for linea in lineas), Decimal("0.00"))
    moneda = con.execute(
        sa.select(core_negocio.c.moneda_codigo).where(core_negocio.c.id == ctx.negocio_id)
    ).scalar_one()

    venta_id = uuid7()
    con.execute(ais.insertar(ctx, ops_venta, {
        "id": venta_id, "numero": _siguiente_numero(con, ctx), "fecha_hora": ahora_utc(),
        "estado": "pagada", "total": total, "moneda_codigo": moneda,
    }))
    for linea in lineas:
        con.execute(ais.insertar(ctx, ops_venta_linea, {
            "id": uuid7(), "venta_id": venta_id, **linea,
        }))
    con.execute(ais.insertar(ctx, ops_pago, {
        "id": uuid7(), "venta_id": venta_id, "medio_pago": datos.medio_pago, "monto": total,
    }))
    faltantes = recetas.consumir_por_venta(con, ctx, venta_id, dict(vendidas))
    contabilidad.asentar_venta(con, ctx, venta_id)  # al final: el libro se bloquea de último
    _, estados = existencias.estados(con, ctx, list({i for i, _ in vendidas}))
    por_agotarse = sorted(nombres[k] for k in vendidas if estados.get(k[1]) is not None)
    return obtener_venta(con, ctx, venta_id).model_copy(
        update={"insumos_en_falta": faltantes, "por_agotarse": por_agotarse})


def _huella(datos: VentaIn) -> str:
    cuerpo = {
        "medio_pago": datos.medio_pago,
        "lineas": sorted((str(i), str(v), c) for (i, v), c in _cantidades_por_item(datos).items()),
    }
    return hashlib.sha256(json.dumps(cuerpo, sort_keys=True).encode()).hexdigest()


def crear_venta_idempotente(engine: Engine, ctx: ais.ContextoNegocio, datos: VentaIn,
                            clave: str | None) -> VentaOut:
    """Cobra una sola vez por (usuario, Idempotency-Key); sin clave, cada llamada cobra."""
    if clave is None:
        with engine.begin() as con:
            return crear_venta(con, ctx, datos)

    huella = _huella(datos)
    filtro = sa.and_(
        core_idempotencia.c.usuario_id == ctx.usuario_id,
        core_idempotencia.c.operacion == OPERACION_CREAR_VENTA,
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
                        return obtener_venta(con, ctx, previo["recurso_id"])
                    except NoEncontrado:
                        con.execute(sa.delete(core_idempotencia).where(filtro))
                venta = crear_venta(con, ctx, datos)
                con.execute(sa.insert(core_idempotencia).values(
                    id=uuid7(), usuario_id=ctx.usuario_id, operacion=OPERACION_CREAR_VENTA,
                    clave=clave, huella=huella, recurso_id=venta.id, creado_por=ctx.usuario_id,
                ))
                return venta
        except sa.exc.IntegrityError:
            # Carrera: otra petición con la misma clave se confirmó primero; se reintenta una vez.
            if intento == 2:
                raise
    raise AssertionError("inalcanzable")


# ------------------------------------------------------------------ leer

def _armar(con: Connection, ctx: ais.ContextoNegocio, filas_venta) -> list[VentaOut]:
    ids = [f.id for f in filas_venta]
    if not ids:
        return []
    lineas = defaultdict(list)
    for fila in con.execute(
        ais.seleccionar(ctx, ops_venta_linea).where(ops_venta_linea.c.venta_id.in_(ids))
        .order_by(ops_venta_linea.c.creado_en, ops_venta_linea.c.id)
    ):
        lineas[fila.venta_id].append(LineaOut(
            item_id=fila.item_id, item_variante_id=fila.item_variante_id, nombre=fila.nombre,
            cantidad=int(fila.cantidad),
            precio_unitario=fila.precio_unitario, total=fila.total,
        ))
    medios = {
        f.venta_id: f.medio_pago for f in con.execute(
            ais.seleccionar(ctx, ops_pago, ops_pago.c.venta_id, ops_pago.c.medio_pago)
            .where(ops_pago.c.venta_id.in_(ids))
        )
    }
    return [
        VentaOut(
            id=f.id, numero=f.numero, fecha_hora=_utc(f.fecha_hora), estado=f.estado,
            total=f.total, moneda_codigo=f.moneda_codigo, medio_pago=medios.get(f.id, ""),
            lineas=lineas[f.id], anulada_en=_utc(f.anulada_en),
            motivo_anulacion=f.motivo_anulacion,
        )
        for f in filas_venta
    ]


def obtener_venta(con: Connection, ctx: ais.ContextoNegocio, venta_id: uuid.UUID) -> VentaOut:
    fila = con.execute(ais.seleccionar(ctx, ops_venta).where(ops_venta.c.id == venta_id)).first()
    if fila is None:
        raise NoEncontrado
    return _armar(con, ctx, [fila])[0]


def listar_del_dia(con: Connection, ctx: ais.ContextoNegocio, fecha: date | None) -> ListaVentasOut:
    """Las ventas de un día calendario en la zona horaria del negocio (por defecto, hoy)."""
    zona = zona_del_negocio(con, ctx)
    dia = fecha or datetime.now(zona).date()
    inicio = datetime(dia.year, dia.month, dia.day, tzinfo=zona).astimezone(UTC)
    fin = (datetime(dia.year, dia.month, dia.day, tzinfo=zona) + timedelta(days=1)).astimezone(UTC)
    filas = con.execute(
        ais.seleccionar(ctx, ops_venta)
        .where(ops_venta.c.fecha_hora >= inicio.replace(tzinfo=None),
               ops_venta.c.fecha_hora < fin.replace(tzinfo=None))
        .order_by(ops_venta.c.numero.desc()).limit(MAX_VENTAS_POR_DIA)
    ).all()
    ventas = _armar(con, ctx, filas)
    vigentes = [v for v in ventas if v.estado == "pagada"]
    por_medio = {medio: Decimal("0.00") for medio in MEDIOS_PAGO}
    for v in vigentes:
        por_medio[v.medio_pago] += v.total
    resumen = ResumenOut(
        cantidad=len(vigentes),
        total=f"{sum((v.total for v in vigentes), Decimal('0.00')):.2f}",
        por_medio={medio: f"{monto:.2f}" for medio, monto in por_medio.items()},
    )
    return ListaVentasOut(fecha=dia, resumen=resumen, ventas=ventas)


# ------------------------------------------------------------------ anular

def anular_venta(con: Connection, ctx: ais.ContextoNegocio, venta_id: uuid.UUID,
                 motivo: str) -> VentaOut:
    resultado = con.execute(
        ais.actualizar(ctx, ops_venta, ops_venta.c.id == venta_id, ops_venta.c.estado == "pagada")
        .values(estado="anulada", anulada_en=ahora_utc(), anulada_por=ctx.usuario_id,
                motivo_anulacion=motivo, version=ops_venta.c.version + 1,
                actualizado_por=ctx.usuario_id)
    )
    if resultado.rowcount == 0:
        existe = con.execute(
            ais.seleccionar(ctx, ops_venta, ops_venta.c.id).where(ops_venta.c.id == venta_id)
        ).first()
        raise YaAnulada if existe else NoEncontrado
    recetas.devolver_por_anulacion(con, ctx, venta_id)
    venta = obtener_venta(con, ctx, venta_id)
    contabilidad.revertir_venta(con, ctx, venta_id, venta.numero)
    return venta
