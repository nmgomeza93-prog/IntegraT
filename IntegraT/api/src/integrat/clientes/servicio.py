"""Clientes y sus campos propios. Todo acceso a tablas de negocio pasa por db.aislamiento.

docs/ANALISIS_INVENTARIO_Y_CLIENTES.md (C1): datos fijos + campos que define el negocio,
validaciones en validaciones.py, aviso de duplicados por teléfono o NIT/CUI y la ficha con lo
que ha comprado.
"""

import re
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from integrat.clientes import validaciones as val
from integrat.clientes.esquemas import (
    CampoOut,
    CamposIn,
    ClienteCambios,
    ClienteIn,
    ClienteOut,
    ClienteResumen,
    CompraDelCliente,
    ComprasDelCliente,
)
from integrat.db import aislamiento as ais
from integrat.db.tablas import ops_campo_cliente, ops_cliente, ops_venta
from integrat.db.tipos import ahora_utc, uuid7

MAX_RESULTADOS = 50
ULTIMAS_COMPRAS = 10


class NoEncontrado(Exception):
    pass


class VersionDesfasada(Exception):
    pass


class Duplicado(Exception):
    def __init__(self, nombre: str, por: str):
        super().__init__(nombre)
        self.nombre, self.por = nombre, por

    def mensaje(self) -> str:
        return (f"Ya tienes a {self.nombre} con ese {self.por}. Búscalo en tus clientes "
                "o guárdalo de todos modos.")


class CampoInvalido(Exception):
    def __init__(self, mensaje: str):
        super().__init__(mensaje)
        self.mensaje = mensaje


def _utc(valor: datetime | None) -> datetime | None:
    return None if valor is None else valor.replace(tzinfo=UTC)


# ------------------------------------------------------------------ campos propios

def _campos_vivos(con: Connection, ctx: ais.ContextoNegocio) -> list:
    return con.execute(
        ais.seleccionar(ctx, ops_campo_cliente, ops_campo_cliente.c.id, ops_campo_cliente.c.nombre,
                        ops_campo_cliente.c.tipo, ops_campo_cliente.c.orden)
        .order_by(ops_campo_cliente.c.orden, ops_campo_cliente.c.id)
    ).all()


def listar_campos(con: Connection, ctx: ais.ContextoNegocio) -> list[CampoOut]:
    return [CampoOut(id=c.id, nombre=c.nombre, tipo=c.tipo, orden=c.orden)
            for c in _campos_vivos(con, ctx)]


def fijar_campos(con: Connection, ctx: ais.ContextoNegocio, datos: CamposIn) -> list[CampoOut]:
    """Deja exactamente esta lista: los que no vienen se archivan (sus valores no se borran)."""
    nombres = [c.nombre.casefold() for c in datos.campos]
    if len(set(nombres)) != len(nombres):
        raise CampoInvalido("Hay dos campos con el mismo nombre.")
    actuales = {c.id: c for c in _campos_vivos(con, ctx)}
    for orden, campo in enumerate(datos.campos):
        if campo.id is None:
            con.execute(ais.insertar(ctx, ops_campo_cliente, {
                "id": uuid7(), "nombre": campo.nombre, "tipo": campo.tipo, "orden": orden}))
            continue
        previo = actuales.pop(campo.id, None)
        if previo is None:
            raise CampoInvalido("Uno de los campos ya no existe. Abre la lista de nuevo.")
        if previo.tipo != campo.tipo:
            raise CampoInvalido(f"{previo.nombre}: no se puede cambiar el tipo; crea otro campo.")
        con.execute(ais.actualizar(ctx, ops_campo_cliente, ops_campo_cliente.c.id == campo.id)
                    .values(nombre=campo.nombre, orden=orden, actualizado_por=ctx.usuario_id))
    for campo_id in actuales:
        con.execute(ais.actualizar(ctx, ops_campo_cliente, ops_campo_cliente.c.id == campo_id)
                    .values(eliminado_en=ahora_utc(), eliminado_por=ctx.usuario_id))
    return listar_campos(con, ctx)


def _validar_datos(campos: list, nuevos: dict, previos: dict | None = None) -> dict:
    """Mezcla `nuevos` sobre `previos`, valida cada valor según su campo y quita los vacíos."""
    por_id = {str(c.id): c for c in campos}
    resultado = dict(previos or {})
    for clave, valor in nuevos.items():
        campo = por_id.get(clave)
        if campo is None:
            raise val.DatoInvalido("Uno de los campos ya no existe. Abre la ficha de nuevo.")
        limpio = val.valor_de_campo(campo.nombre, campo.tipo, valor)
        if limpio is None:
            resultado.pop(clave, None)
        else:
            resultado[clave] = limpio
    return resultado


# ------------------------------------------------------------------ clientes

_COLUMNAS = (ops_cliente.c.id, ops_cliente.c.nombre, ops_cliente.c.telefono, ops_cliente.c.correo,
             ops_cliente.c.direccion, ops_cliente.c.tipo_id_fiscal, ops_cliente.c.id_fiscal,
             ops_cliente.c.nombre_fiscal, ops_cliente.c.notas, ops_cliente.c.datos,
             ops_cliente.c.creado_en, ops_cliente.c.version, ops_cliente.c.eliminado_en)


def _out(f, campos: list, compras: ComprasDelCliente | None = None) -> ClienteOut:
    vivos = {str(c.id) for c in campos}
    return ClienteOut(
        id=f.id, nombre=f.nombre, telefono=f.telefono, tipo_id_fiscal=f.tipo_id_fiscal,
        id_fiscal=f.id_fiscal, correo=f.correo, direccion=f.direccion,
        nombre_fiscal=f.nombre_fiscal, notas=f.notas,
        datos={k: v for k, v in (f.datos or {}).items() if k in vivos},
        cliente_desde=_utc(f.creado_en), version=f.version, compras=compras,
        archivado=f.eliminado_en is not None,
    )


def _buscar_duplicado(con: Connection, ctx: ais.ContextoNegocio, telefono: str | None,
                      id_fiscal: str | None, excepto: uuid.UUID | None = None) -> None:
    for columna, valor, por in ((ops_cliente.c.telefono, telefono, "teléfono"),
                                (ops_cliente.c.id_fiscal, id_fiscal, "NIT o CUI")):
        if valor is None:
            continue
        consulta = ais.seleccionar(ctx, ops_cliente, ops_cliente.c.nombre).where(columna == valor)
        if excepto is not None:
            consulta = consulta.where(ops_cliente.c.id != excepto)
        otro = con.execute(consulta.limit(1)).scalar()
        if otro is not None:
            raise Duplicado(otro, por)


def _limpio(valor: str | None) -> str | None:
    return valor if valor else None


def crear(con: Connection, ctx: ais.ContextoNegocio, datos: ClienteIn) -> ClienteOut:
    telefono = val.telefono(datos.telefono) if datos.telefono else None
    correo = val.correo(datos.correo) if datos.correo else None
    id_fiscal = val.id_fiscal(datos.tipo_id_fiscal, datos.id_fiscal)
    campos = _campos_vivos(con, ctx)
    valores = _validar_datos(campos, datos.datos)
    if not datos.aunque_se_repita:
        _buscar_duplicado(con, ctx, telefono, id_fiscal)
    cliente_id = uuid7()
    con.execute(ais.insertar(ctx, ops_cliente, {
        "id": cliente_id, "nombre": datos.nombre, "telefono": telefono, "correo": correo,
        "direccion": _limpio(datos.direccion), "tipo_id_fiscal": datos.tipo_id_fiscal,
        "id_fiscal": id_fiscal, "nombre_fiscal": _limpio(datos.nombre_fiscal),
        "notas": _limpio(datos.notas), "datos": valores or None,
    }))
    fila = con.execute(ais.seleccionar(ctx, ops_cliente, *_COLUMNAS)
                       .where(ops_cliente.c.id == cliente_id)).one()
    return _out(fila, campos)


def buscar(con: Connection, ctx: ais.ContextoNegocio, q: str | None,
           archivados: bool = False) -> list[ClienteResumen]:
    """Por nombre (sin tildes ni mayúsculas), teléfono o NIT/CUI. `archivados`: solo esos."""
    consulta = ais.seleccionar(ctx, ops_cliente, ops_cliente.c.id, ops_cliente.c.nombre,
                               ops_cliente.c.telefono, ops_cliente.c.tipo_id_fiscal,
                               ops_cliente.c.id_fiscal, incluir_eliminados=archivados)
    if archivados:
        consulta = consulta.where(ops_cliente.c.eliminado_en.is_not(None))
    texto = (q or "").strip()
    if texto:
        patron = "%" + texto.replace("\\", "").replace("%", "").replace("_", "") + "%"
        condiciones = [ops_cliente.c.nombre.like(patron)]
        digitos = re.sub(r"\D", "", texto)
        if len(digitos) >= 3:
            condiciones.append(ops_cliente.c.telefono.like(f"%{digitos}%"))
            condiciones.append(ops_cliente.c.id_fiscal.like(f"%{digitos}%"))
        consulta = consulta.where(sa.or_(*condiciones))
    filas = con.execute(consulta.order_by(ops_cliente.c.nombre, ops_cliente.c.id)
                        .limit(MAX_RESULTADOS)).all()
    return [ClienteResumen(id=f.id, nombre=f.nombre, telefono=f.telefono,
                           tipo_id_fiscal=f.tipo_id_fiscal, id_fiscal=f.id_fiscal) for f in filas]


def _compras(con: Connection, ctx: ais.ContextoNegocio, cliente_id: uuid.UUID) -> ComprasDelCliente:
    vigentes = ais.seleccionar(ctx, ops_venta).where(
        ops_venta.c.cliente_id == cliente_id, ops_venta.c.estado == "pagada").subquery()
    resumen = con.execute(sa.select(
        sa.func.count(), sa.func.coalesce(sa.func.sum(vigentes.c.total), 0),
        sa.func.max(vigentes.c.fecha_hora))).one()
    ultimas = con.execute(
        sa.select(vigentes.c.id, vigentes.c.numero, vigentes.c.fecha_hora, vigentes.c.total)
        .order_by(vigentes.c.fecha_hora.desc(), vigentes.c.numero.desc()).limit(ULTIMAS_COMPRAS)
    ).all()
    return ComprasDelCliente(
        cantidad=resumen[0], total=Decimal(resumen[1]), ultima=_utc(resumen[2]),
        ultimas=[CompraDelCliente(venta_id=u.id, numero=u.numero, fecha_hora=_utc(u.fecha_hora),
                                  total=u.total) for u in ultimas],
    )


def obtener(con: Connection, ctx: ais.ContextoNegocio, cliente_id: uuid.UUID) -> ClienteOut:
    """La ficha, también de un archivado (sus ventas lo siguen nombrando)."""
    fila = con.execute(ais.seleccionar(ctx, ops_cliente, *_COLUMNAS, incluir_eliminados=True)
                       .where(ops_cliente.c.id == cliente_id)).first()
    if fila is None:
        raise NoEncontrado
    return _out(fila, _campos_vivos(con, ctx), _compras(con, ctx, cliente_id))


def actualizar(con: Connection, ctx: ais.ContextoNegocio, cliente_id: uuid.UUID,
               cambios: ClienteCambios) -> ClienteOut:
    actual = con.execute(ais.seleccionar(ctx, ops_cliente, *_COLUMNAS)
                         .where(ops_cliente.c.id == cliente_id)).first()
    if actual is None:
        raise NoEncontrado
    if actual.version != cambios.version:
        raise VersionDesfasada
    enviados = cambios.model_fields_set
    valores: dict = {}
    if "nombre" in enviados and cambios.nombre is not None:
        valores["nombre"] = cambios.nombre
    if "telefono" in enviados:
        valores["telefono"] = val.telefono(cambios.telefono) if cambios.telefono else None
    if "correo" in enviados:
        valores["correo"] = val.correo(cambios.correo) if cambios.correo else None
    for campo in ("direccion", "nombre_fiscal", "notas"):
        if campo in enviados:
            valores[campo] = _limpio(getattr(cambios, campo))
    if "tipo_id_fiscal" in enviados or "id_fiscal" in enviados:
        tipo = cambios.tipo_id_fiscal or actual.tipo_id_fiscal
        crudo = cambios.id_fiscal if "id_fiscal" in enviados else actual.id_fiscal
        valores["tipo_id_fiscal"] = tipo
        valores["id_fiscal"] = val.id_fiscal(tipo, crudo)
    campos = _campos_vivos(con, ctx)
    if cambios.datos is not None:
        valores["datos"] = _validar_datos(campos, cambios.datos, actual.datos) or None
    if not cambios.aunque_se_repita:
        _buscar_duplicado(con, ctx, valores.get("telefono"), valores.get("id_fiscal"),
                          excepto=cliente_id)
    resultado = con.execute(
        ais.actualizar(ctx, ops_cliente, ops_cliente.c.id == cliente_id,
                       ops_cliente.c.version == cambios.version)
        .values(**valores, version=ops_cliente.c.version + 1, actualizado_por=ctx.usuario_id)
    )
    if resultado.rowcount == 0:
        raise VersionDesfasada
    return obtener(con, ctx, cliente_id)


def archivar(con: Connection, ctx: ais.ContextoNegocio, cliente_id: uuid.UUID) -> None:
    """Deja de ofrecerse; sus ventas conservan a quién se vendió."""
    resultado = con.execute(
        ais.actualizar(ctx, ops_cliente, ops_cliente.c.id == cliente_id)
        .values(eliminado_en=ahora_utc(), eliminado_por=ctx.usuario_id)
    )
    if resultado.rowcount == 0:
        raise NoEncontrado


def recuperar(con: Connection, ctx: ais.ContextoNegocio, cliente_id: uuid.UUID) -> ClienteOut:
    """Vuelve a la lista y a Vender un cliente archivado."""
    resultado = con.execute(
        ais.actualizar(ctx, ops_cliente, ops_cliente.c.id == cliente_id,
                       ops_cliente.c.eliminado_en.is_not(None), incluir_eliminados=True)
        .values(eliminado_en=None, eliminado_por=None, version=ops_cliente.c.version + 1,
                actualizado_por=ctx.usuario_id)
    )
    if resultado.rowcount == 0:
        raise NoEncontrado
    return obtener(con, ctx, cliente_id)


def existe(con: Connection, ctx: ais.ContextoNegocio, cliente_id: uuid.UUID) -> bool:
    return con.execute(ais.seleccionar(ctx, ops_cliente, ops_cliente.c.id)
                       .where(ops_cliente.c.id == cliente_id)).first() is not None


def nombres(con: Connection, ctx: ais.ContextoNegocio, ids: list[uuid.UUID]) -> dict:
    """Nombre de cada cliente (también de los archivados: las ventas viejas lo siguen mostrando)."""
    if not ids:
        return {}
    return {f.id: f.nombre for f in con.execute(
        ais.seleccionar(ctx, ops_cliente, ops_cliente.c.id, ops_cliente.c.nombre,
                        incluir_eliminados=True).where(ops_cliente.c.id.in_(ids)))}
