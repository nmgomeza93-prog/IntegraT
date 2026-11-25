"""Aislamiento por negocio (reemplaza el RLS que MySQL no tiene; decisión D-19).

REGLA: toda lectura o escritura de una tabla con columna `negocio_id` se construye
con estas funciones, que SIEMPRE agregan el filtro del negocio del contexto.
El `negocio_id` del contexto sale del token del usuario (nunca de parámetros del cliente).
"""

import uuid
from dataclasses import dataclass

import sqlalchemy as sa


class ErrorAislamiento(Exception):
    """Intento de operar fuera del negocio del contexto."""


@dataclass(frozen=True)
class ContextoNegocio:
    negocio_id: uuid.UUID
    usuario_id: uuid.UUID | None = None


def es_tabla_de_negocio(tabla: sa.Table) -> bool:
    return "negocio_id" in tabla.c


def _exigir_tabla_de_negocio(tabla: sa.Table) -> None:
    if not es_tabla_de_negocio(tabla):
        raise ErrorAislamiento(f"La tabla {tabla.name} no tiene negocio_id.")


def _filtros(ctx: ContextoNegocio, tabla: sa.Table, incluir_eliminados: bool):
    filtros = [tabla.c.negocio_id == ctx.negocio_id]
    if not incluir_eliminados and "eliminado_en" in tabla.c:
        filtros.append(tabla.c.eliminado_en.is_(None))
    return filtros


def seleccionar(
    ctx: ContextoNegocio, tabla: sa.Table, *columnas, incluir_eliminados: bool = False
) -> sa.Select:
    _exigir_tabla_de_negocio(tabla)
    consulta = sa.select(*(columnas or (tabla,)))
    return consulta.where(*_filtros(ctx, tabla, incluir_eliminados))


def insertar(ctx: ContextoNegocio, tabla: sa.Table, valores: dict) -> sa.Insert:
    _exigir_tabla_de_negocio(tabla)
    otro = valores.get("negocio_id")
    if otro is not None and otro != ctx.negocio_id:
        raise ErrorAislamiento("No se puede insertar en otro negocio.")
    datos = {**valores, "negocio_id": ctx.negocio_id}
    if "creado_por" in tabla.c and ctx.usuario_id is not None:
        datos.setdefault("creado_por", ctx.usuario_id)
    return sa.insert(tabla).values(**datos)


def actualizar(ctx: ContextoNegocio, tabla: sa.Table, *condiciones,
               incluir_eliminados: bool = False) -> sa.Update:
    """UPDATE limitado al negocio del contexto. Agregar `.values(...)` al resultado.

    `incluir_eliminados=True` solo para recuperar algo archivado.
    """
    _exigir_tabla_de_negocio(tabla)
    return sa.update(tabla).where(*_filtros(ctx, tabla, incluir_eliminados), *condiciones)
