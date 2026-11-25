"""Importaciones con la plantilla de factura (docs/PLAN_IMPORTACION.md).

1. Vista previa: lee la plantilla y sugiere nombre corto, categoría, coincidencias y variantes.
2. Confirmar: la importación queda EN CAMINO; su costo en Q va a "Mercadería en camino".
3. Recibir: crea los productos y sus variantes (como mercadería), reparte courier y envío local por
   valor, suma el inventario de cada variante al costo puesto en Guatemala y da por perdido lo que
   no llegó. Todo acceso a tablas de negocio pasa por db.aislamiento.
"""

import re
import uuid
from collections import OrderedDict
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from types import SimpleNamespace

import sqlalchemy as sa
from sqlalchemy.engine import Connection, Engine

from integrat import idempotencia, precios
from integrat.contabilidad import motor
from integrat.contabilidad.motor import ROL_POR_MEDIO, centavos
from integrat.db import aislamiento as ais
from integrat.db.tablas import (
    cat_moneda,
    ops_categoria,
    ops_importacion,
    ops_importacion_linea,
    ops_importacion_recepcion,
    ops_importacion_recepcion_linea,
    ops_insumo,
    ops_item,
    ops_item_variante,
)
from integrat.db.tipos import ahora_utc, uuid7
from integrat.importaciones.esquemas import (
    AnularIn,
    Cuadre,
    EncabezadoPrevio,
    EntregaOut,
    ImportacionIn,
    ImportacionOut,
    LineaOut,
    LineaPrevia,
    ListaImportacionesOut,
    ProductoPrevio,
    RecibirIn,
    VistaPreviaOut,
)
from integrat.importaciones.plantilla import Plantilla, limpiar, nombre_sugerido, sin_tildes
from integrat.insumos import mercaderia
from integrat.insumos import servicio as inventario
from integrat.items import servicio as items
from integrat.items.esquemas import CategoriaIn, ItemIn
from integrat.tiempo import hoy_del_negocio
from integrat.variantes import servicio as variantes
from integrat.variantes.esquemas import AtributoIn, VarianteIn, VariantesIn

ORIGEN = "importacion"
OPERACION_CONFIRMAR = "confirmar_importacion"
OPERACION_RECIBIR = "recibir_importacion"
CUATRO = Decimal("0.0001")
OCHO = Decimal("0.00000001")
CERO = Decimal("0")
TOLERANCIA_CUADRE = Decimal("0.01")
ATRIBUTOS_PLANTILLA = ("Talla", "Color")


class NoEncontrado(Exception):
    pass


class MonedaInvalida(Exception):
    pass


class FaltaCambio(Exception):
    """Sin cobro en Q ni tipo de cambio: no hay cómo pasar la factura a quetzales."""


class EstadoInvalido(Exception):
    """La importación ya no está en camino."""


class LineaInvalida(Exception):
    pass


class SinPeso(Exception):
    """Se pidió repartir por peso, pero alguna línea que llegó no tiene peso."""


class NadaQueRecibir(Exception):
    """La entrega no trae nada y no cierra la importación."""


class ProductoConReceta(Exception):
    """Un producto que ya existe tiene receta hecha a mano: no se recibe como mercadería."""


def _texto(valor: Decimal | None, decimales: int = 2) -> str | None:
    return None if valor is None else f"{valor:.{decimales}f}"


def repartir(
    pesos: list[Decimal], total: Decimal, paso: Decimal = Decimal("0.01")
) -> list[Decimal]:
    """Reparte `total` en proporción a `pesos`; el último renglón absorbe el redondeo."""
    if not pesos:
        return []
    suma = sum(pesos, CERO)
    if suma <= 0:
        partes = [CERO] * len(pesos)
        partes[-1] = total
        return partes
    partes, resto = [], total
    for peso in pesos[:-1]:
        parte = (total * peso / suma).quantize(paso, ROUND_HALF_UP)
        partes.append(parte)
        resto -= parte
    partes.append(resto)
    return partes


# ------------------------------------------------------------------ vista previa


def _categorias(con: Connection, ctx: ais.ContextoNegocio) -> list[dict]:
    """Las del negocio (con sus palabras clave) y, detrás, las sugeridas que aún no tiene."""
    propias = con.execute(
        ais.seleccionar(
            ctx,
            ops_categoria,
            ops_categoria.c.id,
            ops_categoria.c.nombre,
            ops_categoria.c.palabras_clave,
        ).order_by(ops_categoria.c.orden)
    ).all()
    atributos = variantes.atributos_de_categorias(con, ctx, [c.id for c in propias])
    lista = [
        {"nombre": c.nombre, "palabras": list(c.palabras_clave or []), "atributos": atributos[c.id]}
        for c in propias
    ]
    tengo = {sin_tildes(c["nombre"]) for c in lista}
    for s in variantes.categorias_sugeridas(con, ctx):
        if sin_tildes(s.nombre) not in tengo:
            lista.append(
                {"nombre": s.nombre, "palabras": s.palabras_clave, "atributos": s.atributos}
            )
    return lista


def sugerir_categoria(descripcion: str, categorias: list[dict]) -> dict | None:
    """La categoría de la palabra clave que aparece PRIMERO en la descripción (suele ser lo que
    es el producto: "pijama con top de camiseta" es un pijama); a la par, la más larga."""
    texto = f" {sin_tildes(descripcion)} "
    mejor, posicion, largo = None, len(texto) + 1, 0
    for c in categorias:
        for palabra in c["palabras"]:
            clave = sin_tildes(str(palabra))
            hallado = re.search(rf"\b{re.escape(clave)}\b", texto)
            if hallado and (
                hallado.start() < posicion or (hallado.start() == posicion and len(clave) > largo)
            ):
                mejor, posicion, largo = c, hallado.start(), len(clave)
    return mejor


def _atributos_de_linea(linea, categoria: dict | None) -> dict[str, str]:
    """Talla y color de la plantilla, solo si la categoría los usa (no la talla de una cámara)."""
    usa = set(categoria["atributos"]) if categoria else set(ATRIBUTOS_PLANTILLA)
    valores = {"Talla": linea.talla, "Color": linea.color}
    return {k: v for k, v in valores.items() if v and k in usa}


def _iguales(a: dict | None, b: dict | None) -> bool:
    norm = lambda d: {sin_tildes(k): sin_tildes(str(v)) for k, v in (d or {}).items()}  # noqa: E731
    return norm(a) == norm(b)


def _existente(con, ctx, codigo: str | None, nombre: str):
    """El producto que ya existe: por el código de alguna de sus variantes o por su nombre."""
    if codigo:
        fila = con.execute(
            ais.seleccionar(ctx, ops_item_variante, ops_item_variante.c.item_id)
            .select_from(
                ops_item_variante.join(
                    ops_item,
                    sa.and_(
                        ops_item.c.id == ops_item_variante.c.item_id,
                        ops_item.c.eliminado_en.is_(None),
                    ),
                )
            )
            .where(ops_item_variante.c.codigo == codigo)
            .limit(1)
        ).first()
        if fila is not None:
            return fila.item_id
    fila = con.execute(
        ais.seleccionar(ctx, ops_item, ops_item.c.id).where(ops_item.c.nombre == nombre).limit(1)
    ).first()
    return None if fila is None else fila.id


def _variante_existente(con, ctx, item_id, atributos: dict) -> uuid.UUID | None:
    for v in con.execute(
        ais.seleccionar(
            ctx, ops_item_variante, ops_item_variante.c.id, ops_item_variante.c.atributos
        ).where(ops_item_variante.c.item_id == item_id)
    ):
        if (v.atributos is None and not atributos) or (
            v.atributos and _iguales(v.atributos, atributos)
        ):
            return v.id
    return None


def vista_previa(con: Connection, ctx: ais.ContextoNegocio, plantilla: Plantilla) -> VistaPreviaOut:
    enc = plantilla.encabezado
    avisos = list(plantilla.avisos)
    conocida = (
        con.execute(
            sa.select(cat_moneda.c.codigo).where(cat_moneda.c.codigo == enc.moneda_codigo)
        ).first()
        is not None
    )
    if not conocida:
        avisos.append(f"No reconocemos la moneda {enc.moneda_codigo}. Revísala antes de confirmar.")
    categorias = _categorias(con, ctx)

    grupos: OrderedDict[str, dict] = OrderedDict()
    for linea in plantilla.lineas:
        nombre = linea.nombre or nombre_sugerido(linea.descripcion)
        clave = sin_tildes(linea.codigo) if linea.codigo else f"nombre:{sin_tildes(nombre)}"
        if clave not in grupos:
            categoria = sugerir_categoria(linea.descripcion or nombre, categorias)
            grupos[clave] = {
                "nombre": nombre,
                "codigo": linea.codigo,
                "categoria": categoria,
                "lineas": [],
            }
        grupos[clave]["lineas"].append(linea)

    # Nombres repetidos entre productos distintos: se distinguen con el color (o un número).
    vistos: dict[str, int] = {}
    for g in grupos.values():
        base = g["nombre"]
        if sin_tildes(base) in vistos:
            color = g["lineas"][0].color
            g["nombre"] = f"{base} {color}" if color else f"{base} {vistos[sin_tildes(base)] + 1}"
        vistos[sin_tildes(base)] = vistos.get(sin_tildes(base), 0) + 1

    productos: list[ProductoPrevio] = []
    for g in grupos.values():
        item_id = _existente(con, ctx, g["codigo"], g["nombre"])
        lineas = []
        for linea in g["lineas"]:
            atributos = _atributos_de_linea(linea, g["categoria"])
            lineas.append(
                LineaPrevia(
                    fila=linea.fila,
                    codigo=linea.codigo,
                    descripcion=linea.descripcion,
                    atributos=atributos,
                    cantidad=linea.cantidad,
                    precio_unitario=_texto(linea.precio_unitario, 4),
                    peso=_texto(linea.peso, 3),
                    item_variante_id=None
                    if item_id is None
                    else _variante_existente(con, ctx, item_id, atributos),
                )
            )
        productos.append(
            ProductoPrevio(
                nombre=g["nombre"],
                categoria=g["categoria"]["nombre"] if g["categoria"] else None,
                item_id=item_id,
                existente=item_id is not None,
                lineas=lineas,
            )
        )

    suma_lineas = sum((x.precio_unitario * x.cantidad for x in plantilla.lineas), CERO)
    cargos = enc.garantia_envio + enc.costo_importacion + enc.otros_cobros
    calculado = suma_lineas + cargos
    diferencia = None if enc.total_factura is None else enc.total_factura - calculado
    cuadra = diferencia is None or abs(diferencia) <= TOLERANCIA_CUADRE
    if not cuadra:
        avisos.append(
            f"La suma de la factura no cuadra con el total: difiere en "
            f"{diferencia:.2f} {enc.moneda_codigo}."
        )
    return VistaPreviaOut(
        encabezado=EncabezadoPrevio(
            plataforma=enc.plataforma,
            numero_factura=enc.numero_factura,
            numero_orden=enc.numero_orden,
            fecha_factura=enc.fecha_factura,
            moneda_codigo=enc.moneda_codigo,
            moneda_conocida=conocida,
            tipo_cambio=_texto(enc.tipo_cambio, 8),
            total_factura=_texto(enc.total_factura),
            garantia_envio=_texto(enc.garantia_envio),
            costo_importacion=_texto(enc.costo_importacion),
            otros_cobros=_texto(enc.otros_cobros),
        ),
        cuadre=Cuadre(
            lineas=_texto(suma_lineas),
            cargos=_texto(cargos),
            total_calculado=_texto(calculado),
            total_factura=_texto(enc.total_factura),
            diferencia=_texto(diferencia),
            cuadra=cuadra,
        ),
        productos=productos,
        unidades=sum(x.cantidad for x in plantilla.lineas),
        avisos=avisos,
    )


# ------------------------------------------------------------------ confirmar (en camino)


def _confirmar(con: Connection, ctx: ais.ContextoNegocio, datos: ImportacionIn):
    if (
        con.execute(
            sa.select(cat_moneda.c.codigo).where(cat_moneda.c.codigo == datos.moneda_codigo)
        ).first()
        is None
    ):
        raise MonedaInvalida
    lineas = [(p, linea) for p in datos.productos for linea in p.lineas]
    valores = [linea.precio_unitario * linea.cantidad for _, linea in lineas]
    cargos_total = datos.garantia_envio + datos.costo_importacion + datos.otros_cobros
    total_origen = (sum(valores, CERO) + cargos_total).quantize(CUATRO, ROUND_HALF_UP)
    if total_origen <= 0:
        raise LineaInvalida
    if datos.moneda_codigo == "GTQ":
        tipo_cambio = Decimal("1")
        total_q = centavos(datos.cobro_q if datos.cobro_q is not None else total_origen)
    elif datos.cobro_q is not None:
        total_q = centavos(datos.cobro_q)
        tipo_cambio = (total_q / total_origen).quantize(OCHO, ROUND_HALF_UP)
    elif datos.tipo_cambio is not None:
        tipo_cambio = datos.tipo_cambio
        total_q = centavos(total_origen * tipo_cambio)
    else:
        raise FaltaCambio

    # Cada línea: su valor + su parte de los cargos; y su parte de lo pagado en Q.
    cargos = repartir(valores, cargos_total, CUATRO)
    en_q = repartir([v + c for v, c in zip(valores, cargos, strict=True)], total_q)
    for producto, _ in lineas:
        if (
            producto.item_id is not None
            and con.execute(
                ais.seleccionar(ctx, ops_item, ops_item.c.id).where(
                    ops_item.c.id == producto.item_id
                )
            ).first()
            is None
        ):
            raise LineaInvalida

    importacion_id = uuid7()
    con.execute(
        ais.insertar(
            ctx,
            ops_importacion,
            {
                "id": importacion_id,
                "plataforma": datos.plataforma.lower(),
                "numero_factura": datos.numero_factura,
                "numero_orden": datos.numero_orden,
                "fecha_factura": datos.fecha_factura,
                "moneda_codigo": datos.moneda_codigo,
                "garantia_envio": datos.garantia_envio,
                "costo_importacion": datos.costo_importacion,
                "otros_cobros": datos.otros_cobros,
                "total_origen": total_origen,
                "tipo_cambio": tipo_cambio,
                "total_q": total_q,
                "medio_pago": datos.medio_pago,
                "estado": "en_camino",
                "nota": datos.nota or None,
            },
        )
    )
    for orden, ((producto, linea), cargo, q) in enumerate(zip(lineas, cargos, en_q, strict=True)):
        con.execute(
            ais.insertar(
                ctx,
                ops_importacion_linea,
                {
                    "id": uuid7(),
                    "importacion_id": importacion_id,
                    "producto_nombre": producto.nombre,
                    "categoria_nombre": producto.categoria,
                    "codigo": linea.codigo,
                    "descripcion": linea.descripcion,
                    "atributos": linea.atributos or None,
                    "item_id": producto.item_id,
                    "item_variante_id": linea.item_variante_id,
                    "cantidad": linea.cantidad,
                    "precio_unitario": linea.precio_unitario,
                    "cargos_origen": cargo,
                    "costo_pedido_q": q,
                    "peso": linea.peso,
                    "orden": orden,
                },
            )
        )
    motor.registrar(
        con,
        ctx,
        evento="IMPORTACION_PEDIDO",
        fecha=datos.fecha_factura or hoy_del_negocio(con, ctx),
        descripcion=f"Importación {datos.plataforma} {datos.numero_orden or ''}".strip(),
        importes={"total": total_q},
        comodines={"@pago": ROL_POR_MEDIO[datos.medio_pago]},
        origen_tipo=ORIGEN,
        origen_id=importacion_id,
    )
    return importacion_id, obtener(con, ctx, importacion_id)


def confirmar(
    engine: Engine, ctx: ais.ContextoNegocio, datos: ImportacionIn, clave: str | None
) -> ImportacionOut:
    return idempotencia.ejecutar(
        engine,
        ctx,
        OPERACION_CONFIRMAR,
        clave,
        idempotencia.huella(datos),
        crear=lambda con: _confirmar(con, ctx, datos),
        leer=lambda con, i: _leer_o_no_existe(con, ctx, i),
    )


# ------------------------------------------------------------------ recibir


def _categoria_id(con, ctx, nombre: str | None) -> uuid.UUID | None:
    if not nombre:
        return None
    for c in con.execute(
        ais.seleccionar(ctx, ops_categoria, ops_categoria.c.id, ops_categoria.c.nombre)
    ):
        if sin_tildes(c.nombre) == sin_tildes(nombre):
            return c.id
    return items.crear_categoria(con, ctx, CategoriaIn(nombre=nombre[:80])).id  # hereda atributos


def _asegurar_atributos(con, ctx, nombres: set[str]) -> None:
    variantes.asegurar_atributos(con, ctx)
    existentes = {sin_tildes(a.nombre) for a in variantes.listar_atributos(con, ctx)}
    for nombre in sorted(nombres):
        if sin_tildes(nombre) not in existentes:
            variantes.crear_atributo(con, ctx, AtributoIn(nombre=nombre))


def _preparar_producto(con, ctx, nombre: str, categoria: str | None, item_id, filas) -> uuid.UUID:
    """Crea (o completa) el producto con las variantes de sus líneas y lo deja como mercadería.

    Devuelve el id del producto y deja en cada fila su `item_variante_id`.
    """
    if item_id is None:
        item_id = items.crear_item(
            con,
            ctx,
            ItemIn(
                nombre=nombre[:120],
                precio_venta=Decimal("0"),
                categoria_id=_categoria_id(con, ctx, categoria),
            ),
        ).id
    con_atributos = [f for f in filas if f.atributos]
    if con_atributos:
        _asegurar_atributos(con, ctx, {k for f in con_atributos for k in f.atributos})
        actuales = variantes.variantes_de(con, ctx, [item_id])[item_id]
        lista = [
            VarianteIn(
                id=v.id, atributos=dict(v.atributos), codigo=v.codigo, precio_venta=v.precio_venta
            )
            for v in actuales
        ]
        for f in con_atributos:
            if not any(_iguales(v.atributos, f.atributos) for v in lista):
                lista.append(
                    VarianteIn(
                        atributos=dict(f.atributos), codigo=f.codigo, precio_venta=Decimal("0")
                    )
                )
        variantes.guardar_variantes(con, ctx, item_id, VariantesIn(variantes=lista))
    try:
        mercaderia.activar(con, ctx, item_id)  # también sincroniza un insumo por variante
    except mercaderia.ConReceta:
        raise ProductoConReceta from None
    for f in filas:
        f.item_variante_id_final = _variante_existente(con, ctx, item_id, f.atributos or {})
    return item_id


def _insumo_de(con, ctx, item_id: uuid.UUID, variante_id: uuid.UUID) -> uuid.UUID:
    """El insumo (mercadería) de esa variante; la implícita usa el insumo sin variante."""
    explicita = con.execute(
        ais.seleccionar(ctx, ops_item_variante, ops_item_variante.c.atributos).where(
            ops_item_variante.c.id == variante_id
        )
    ).scalar()
    condicion = (
        ops_insumo.c.item_variante_id == variante_id
        if explicita is not None
        else ops_insumo.c.item_variante_id.is_(None)
    )
    return con.execute(
        ais.seleccionar(ctx, ops_insumo, ops_insumo.c.id).where(
            ops_insumo.c.item_id == item_id, condicion
        )
    ).scalar_one()


def _recibir(
    con: Connection, ctx: ais.ContextoNegocio, importacion_id: uuid.UUID, datos: RecibirIn
):
    imp = con.execute(
        ais.seleccionar(ctx, ops_importacion)
        .where(ops_importacion.c.id == importacion_id)
        .with_for_update()
    ).first()
    if imp is None:
        raise NoEncontrado
    if imp.estado not in ("en_camino", "llegando"):
        raise EstadoInvalido
    filas = [
        SimpleNamespace(**f._mapping)
        for f in con.execute(
            ais.seleccionar(ctx, ops_importacion_linea)
            .where(ops_importacion_linea.c.importacion_id == importacion_id)
            .order_by(ops_importacion_linea.c.orden)
        )
    ]
    por_id = {f.id: f for f in filas}
    pendiente = {
        f.id: f.cantidad - (f.cantidad_recibida or 0) - (f.cantidad_perdida or 0) for f in filas
    }
    if datos.lineas is None:  # llegó todo lo que faltaba
        llegan = {i: n for i, n in pendiente.items() if n > 0}
    else:
        llegan = {}
        for r in datos.lineas:
            if r.linea_id not in por_id or r.cantidad > pendiente[r.linea_id]:
                raise LineaInvalida
            if r.cantidad:
                llegan[r.linea_id] = llegan.get(r.linea_id, 0) + r.cantidad
        if any(llegan[i] > pendiente[i] for i in llegan):
            raise LineaInvalida
    if not llegan and not datos.cerrar:
        raise NadaQueRecibir
    asignado = {f.id: CERO for f in filas}  # lo que ya se pasó a inventario en otras entregas
    for r in con.execute(
        ais.seleccionar(
            ctx,
            ops_importacion_recepcion_linea,
            ops_importacion_recepcion_linea.c.linea_id,
            sa.func.sum(ops_importacion_recepcion_linea.c.costo_q).label("q"),
        )
        .where(ops_importacion_recepcion_linea.c.linea_id.in_(list(por_id)))
        .group_by(ops_importacion_recepcion_linea.c.linea_id)
    ):
        asignado[r.linea_id] = Decimal(r.q or 0)

    # Productos y variantes de lo que llega (los nuevos se crean ahora, cuando de verdad llegan).
    grupos: OrderedDict[tuple, list] = OrderedDict()
    for f in filas:
        if f.id not in llegan:
            continue
        clave = (f.item_id,) if f.item_id else ("nuevo", sin_tildes(f.producto_nombre))
        grupos.setdefault(clave, []).append(f)
    for grupo in grupos.values():
        primera = grupo[0]
        if primera.item_id is None:  # una entrega anterior ya pudo crear el producto
            primera.item_id = next(
                (
                    f.item_id
                    for f in filas
                    if f.item_id
                    and sin_tildes(f.producto_nombre) == sin_tildes(primera.producto_nombre)
                ),
                None,
            )
        item_id = _preparar_producto(
            con, ctx, primera.producto_nombre, primera.categoria_nombre, primera.item_id, grupo
        )
        for f in grupo:
            f.item_id = item_id
            for otra in filas:  # las demás líneas del mismo producto ya lo tienen
                if otra.item_id is None and sin_tildes(otra.producto_nombre) == sin_tildes(
                    f.producto_nombre
                ):
                    otra.item_id = item_id

    # Lo que pasa a inventario de cada línea: su parte de lo pagado; si con esta entrega la línea
    # se completa, lo que le falte (así la suma cuadra al centavo).
    llegando = [f for f in filas if f.id in llegan]
    costo_q: dict = {}
    for f in llegando:
        recibira = (f.cantidad_recibida or 0) + llegan[f.id]
        if recibira + (f.cantidad_perdida or 0) == f.cantidad:
            costo_q[f.id] = centavos(f.costo_pedido_q) - asignado[f.id]
        else:
            costo_q[f.id] = centavos(f.costo_pedido_q * llegan[f.id] / f.cantidad)
    adicional = centavos((datos.courier_q or CERO) + (datos.envio_local_q or CERO))
    if datos.reparto == "peso":
        if any(f.peso is None or f.peso <= 0 for f in llegando):
            raise SinPeso
        pesos = [Decimal(f.peso) * llegan[f.id] / f.cantidad for f in llegando]
    else:
        pesos = [costo_q[f.id] for f in llegando]
    courier = dict(zip([f.id for f in llegando], repartir(pesos, adicional), strict=True))

    # Lo que ya no va a llegar (si se cierra): su parte de lo pagado se da por perdida.
    perdido = CERO
    perdidas: dict = {}
    if datos.cerrar:
        for f in filas:
            falta = pendiente[f.id] - llegan.get(f.id, 0)
            if falta > 0:
                perdidas[f.id] = falta
                perdido += centavos(f.costo_pedido_q) - asignado[f.id] - costo_q.get(f.id, CERO)

    numero = (
        con.execute(
            ais.seleccionar(
                ctx, ops_importacion_recepcion, sa.func.max(ops_importacion_recepcion.c.numero)
            ).where(ops_importacion_recepcion.c.importacion_id == importacion_id)
        ).scalar()
        or 0
    ) + 1
    recepcion_id = uuid7()
    ahora = ahora_utc()
    con.execute(
        ais.insertar(
            ctx,
            ops_importacion_recepcion,
            {
                "id": recepcion_id,
                "importacion_id": importacion_id,
                "numero": numero,
                "recibida_en": ahora,
                "guia": datos.guia or None,
                "courier_q": datos.courier_q,
                "envio_local_q": datos.envio_local_q,
                "medio_pago": datos.medio_pago,
                "reparto": datos.reparto,
                "cierra": datos.cerrar,
            },
        )
    )
    total_inventario = CERO
    entradas = []
    for f in llegando:
        n = llegan[f.id]
        costo = costo_q[f.id] + courier[f.id]
        total_inventario += costo
        con.execute(
            ais.insertar(
                ctx,
                ops_importacion_recepcion_linea,
                {
                    "id": uuid7(),
                    "recepcion_id": recepcion_id,
                    "linea_id": f.id,
                    "cantidad": n,
                    "costo_q": costo_q[f.id],
                    "courier_q": courier[f.id],
                    "costo_unitario_q": (costo / n).quantize(OCHO, ROUND_HALF_UP),
                },
            )
        )
        entradas.append((_insumo_de(con, ctx, f.item_id, f.item_variante_id_final), n, costo))
    for insumo_id, n, costo in sorted(entradas, key=lambda e: e[0]):
        fila = inventario.bloquear(con, ctx, insumo_id)
        inventario.aplicar(
            con,
            ctx,
            fila,
            "entrada",
            Decimal(n),
            costo,
            origen_tipo=ORIGEN,
            origen_id=importacion_id,
        )

    # Cada línea, al día: recibido, perdido, courier y costo puesto en Guatemala (promedio).
    for f in filas:
        if f.id not in llegan and f.id not in perdidas:
            continue
        cambios = {"actualizado_por": ctx.usuario_id}
        if f.id in llegan:
            n_total = (f.cantidad_recibida or 0) + llegan[f.id]
            landed = asignado[f.id] + (f.courier_q or CERO) + costo_q[f.id] + courier[f.id]
            cambios |= {
                "cantidad_recibida": n_total,
                "courier_q": (f.courier_q or CERO) + courier[f.id],
                "costo_unitario_q": (landed / n_total).quantize(OCHO, ROUND_HALF_UP),
                "item_id": f.item_id,
                "item_variante_id": f.item_variante_id_final,
            }
        if f.id in perdidas:
            cambios["cantidad_perdida"] = (f.cantidad_perdida or 0) + perdidas[f.id]
        con.execute(
            ais.actualizar(ctx, ops_importacion_linea, ops_importacion_linea.c.id == f.id).values(
                **cambios
            )
        )

    falta_total = sum(pendiente.values()) - sum(llegan.values()) - sum(perdidas.values())
    if falta_total > 0:
        estado = "llegando"
    else:
        hubo_perdidas = bool(perdidas) or any(f.cantidad_perdida for f in filas)
        estado = "recibida_parcial" if hubo_perdidas else "recibida"
    con.execute(
        ais.actualizar(ctx, ops_importacion, ops_importacion.c.id == importacion_id).values(
            estado=estado,
            recibida_en=ahora,
            guia=datos.guia or imp.guia,
            courier_q=(imp.courier_q or CERO) + (datos.courier_q or CERO),
            envio_local_q=(imp.envio_local_q or CERO) + (datos.envio_local_q or CERO),
            medio_pago_courier=datos.medio_pago,
            version=ops_importacion.c.version + 1,
            actualizado_por=ctx.usuario_id,
        )
    )
    motor.registrar(
        con,
        ctx,
        evento="IMPORTACION_RECEPCION",
        fecha=hoy_del_negocio(con, ctx),
        descripcion=f"Entrega {numero} de la importación {imp.plataforma} "
        f"{imp.numero_orden or ''}".strip(),
        importes={
            "inventario": centavos(total_inventario),
            "perdido": centavos(perdido),
            "transito": centavos(sum(costo_q.values(), CERO) + perdido),
            "courier": adicional,
        },
        comodines={"@pago": ROL_POR_MEDIO[datos.medio_pago]},
        origen_tipo=ORIGEN,
        origen_id=importacion_id,
    )

    # Los productos nuevos quedan listos para vender: su precio es el sugerido.
    item_ids = list({f.item_id for f in llegando})
    if item_ids:
        _, por_variante = precios.calcular(con, ctx, item_ids)
        for variante_id, info in por_variante.items():
            if info.precio_sugerido is not None:
                con.execute(
                    ais.actualizar(
                        ctx,
                        ops_item_variante,
                        ops_item_variante.c.id == variante_id,
                        ops_item_variante.c.precio_venta == 0,
                    ).values(precio_venta=info.precio_sugerido, actualizado_por=ctx.usuario_id)
                )
    return importacion_id, obtener(con, ctx, importacion_id)


def recibir(
    engine: Engine,
    ctx: ais.ContextoNegocio,
    importacion_id: uuid.UUID,
    datos: RecibirIn,
    clave: str | None,
) -> ImportacionOut:
    return idempotencia.ejecutar(
        engine,
        ctx,
        OPERACION_RECIBIR,
        clave,
        idempotencia.huella(datos, {"importacion": str(importacion_id)}),
        crear=lambda con: _recibir(con, ctx, importacion_id, datos),
        leer=lambda con, i: _leer_o_no_existe(con, ctx, i),
    )


# ------------------------------------------------------------------ anular


def anular(
    con: Connection, ctx: ais.ContextoNegocio, importacion_id: uuid.UUID, datos: AnularIn
) -> ImportacionOut:
    resultado = con.execute(
        ais.actualizar(
            ctx,
            ops_importacion,
            ops_importacion.c.id == importacion_id,
            ops_importacion.c.estado == "en_camino",
        ).values(
            estado="anulada",
            anulada_en=ahora_utc(),
            anulada_por=ctx.usuario_id,
            motivo_anulacion=datos.motivo,
            version=ops_importacion.c.version + 1,
            actualizado_por=ctx.usuario_id,
        )
    )
    if resultado.rowcount == 0:
        existe = con.execute(
            ais.seleccionar(ctx, ops_importacion, ops_importacion.c.id).where(
                ops_importacion.c.id == importacion_id
            )
        ).first()
        raise EstadoInvalido if existe else NoEncontrado
    motor.revertir_origen(con, ctx, ORIGEN, importacion_id, "Importación anulada")
    return obtener(con, ctx, importacion_id)


# ------------------------------------------------------------------ leer


def _salida(con, ctx, imp, con_lineas: bool) -> ImportacionOut:
    filas = con.execute(
        ais.seleccionar(ctx, ops_importacion_linea)
        .where(ops_importacion_linea.c.importacion_id == imp.id)
        .order_by(ops_importacion_linea.c.orden)
    ).all()
    lineas = []
    if con_lineas:
        sugeridos = (
            precios.calcular(con, ctx, list({f.item_id for f in filas if f.item_id}))[1]
            if any(f.item_id for f in filas)
            else {}
        )
        for f in filas:
            valores = " · ".join((f.atributos or {}).values())
            info = sugeridos.get(f.item_variante_id)
            lineas.append(
                LineaOut(
                    id=f.id,
                    nombre=f"{f.producto_nombre} · {valores}" if valores else f.producto_nombre,
                    codigo=f.codigo,
                    atributos=dict(f.atributos or {}),
                    item_id=f.item_id,
                    item_variante_id=f.item_variante_id,
                    cantidad=f.cantidad,
                    precio_unitario=_texto(f.precio_unitario, 2),
                    costo_pedido_q=_texto(f.costo_pedido_q),
                    cantidad_recibida=f.cantidad_recibida,
                    cantidad_perdida=f.cantidad_perdida,
                    pendiente=f.cantidad - (f.cantidad_recibida or 0) - (f.cantidad_perdida or 0),
                    peso=_texto(f.peso, 3),
                    courier_q=_texto(f.courier_q),
                    costo_unitario_q=_texto(f.costo_unitario_q),
                    precio_sugerido=None
                    if info is None or info.precio_sugerido is None
                    else _texto(info.precio_sugerido),
                )
            )
    entregas = []
    if con_lineas:
        unidades_por = {
            r.recepcion_id: int(r.n)
            for r in con.execute(
                ais.seleccionar(
                    ctx,
                    ops_importacion_recepcion_linea,
                    ops_importacion_recepcion_linea.c.recepcion_id,
                    sa.func.sum(ops_importacion_recepcion_linea.c.cantidad).label("n"),
                ).group_by(ops_importacion_recepcion_linea.c.recepcion_id)
            )
        }
        for e in con.execute(
            ais.seleccionar(ctx, ops_importacion_recepcion)
            .where(ops_importacion_recepcion.c.importacion_id == imp.id)
            .order_by(ops_importacion_recepcion.c.numero)
        ):
            entregas.append(
                EntregaOut(
                    numero=e.numero,
                    recibida_en=e.recibida_en.replace(tzinfo=UTC),
                    guia=e.guia,
                    courier_q=_texto(e.courier_q),
                    envio_local_q=_texto(e.envio_local_q),
                    reparto=e.reparto,
                    cierra=bool(e.cierra),
                    unidades=unidades_por.get(e.id, 0),
                )
            )
    en_camino = imp.estado in ("en_camino", "llegando")
    hasta = (
        datetime.now(UTC).replace(tzinfo=None)
        if en_camino or imp.recibida_en is None
        else imp.recibida_en
    )
    return ImportacionOut(
        id=imp.id,
        plataforma=imp.plataforma,
        numero_factura=imp.numero_factura,
        numero_orden=imp.numero_orden,
        fecha_factura=imp.fecha_factura,
        moneda_codigo=imp.moneda_codigo,
        total_factura=_texto(imp.total_origen),
        tipo_cambio=_texto(imp.tipo_cambio, 6),
        total_q=_texto(imp.total_q),
        medio_pago=imp.medio_pago,
        estado=imp.estado,
        creada_en=imp.creado_en.replace(tzinfo=UTC),
        recibida_en=None if imp.recibida_en is None else imp.recibida_en.replace(tzinfo=UTC),
        guia=imp.guia,
        courier_q=_texto(imp.courier_q),
        envio_local_q=_texto(imp.envio_local_q),
        nota=imp.nota,
        motivo_anulacion=imp.motivo_anulacion,
        unidades=sum(f.cantidad for f in filas),
        dias_en_camino=(hasta - imp.creado_en).days,
        pendientes=sum(
            f.cantidad - (f.cantidad_recibida or 0) - (f.cantidad_perdida or 0) for f in filas
        )
        if imp.estado != "anulada"
        else 0,
        entregas=entregas,
        lineas=lineas,
    )


def obtener(con: Connection, ctx: ais.ContextoNegocio, importacion_id: uuid.UUID) -> ImportacionOut:
    imp = con.execute(
        ais.seleccionar(ctx, ops_importacion).where(ops_importacion.c.id == importacion_id)
    ).first()
    if imp is None:
        raise NoEncontrado
    return _salida(con, ctx, imp, con_lineas=True)


def _leer_o_no_existe(con, ctx, importacion_id):
    try:
        return obtener(con, ctx, importacion_id)
    except NoEncontrado:
        raise idempotencia.YaNoExiste from None


def listar(con: Connection, ctx: ais.ContextoNegocio) -> ListaImportacionesOut:
    filas = con.execute(
        ais.seleccionar(ctx, ops_importacion)
        .order_by(ops_importacion.c.creado_en.desc())
        .limit(100)
    ).all()
    en_camino = [
        _salida(con, ctx, f, False) for f in filas if f.estado in ("en_camino", "llegando")
    ]
    recibidas = [
        _salida(con, ctx, f, False) for f in filas if f.estado in ("recibida", "recibida_parcial")
    ][:30]
    return ListaImportacionesOut(en_camino=en_camino, recibidas=recibidas)


__all__ = ["limpiar"]
