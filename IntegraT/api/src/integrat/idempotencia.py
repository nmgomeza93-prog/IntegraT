"""Comandos idempotentes por (usuario, operación, Idempotency-Key).

Repetir la misma clave con los mismos datos devuelve lo que se creó la primera vez (dobles toques,
reintentos por red caída); con otros datos es un error. Sin clave, cada llamada ejecuta el comando.
"""

import hashlib
import json
import uuid
from collections.abc import Callable
from datetime import timedelta

import sqlalchemy as sa
from pydantic import BaseModel
from sqlalchemy.engine import Connection, Engine

from integrat.db.aislamiento import ContextoNegocio
from integrat.db.tablas import core_idempotencia
from integrat.db.tipos import ahora_utc, uuid7

VIGENCIA = timedelta(hours=24)


class ClaveReutilizada(Exception):
    """La misma Idempotency-Key llegó con datos distintos."""


class YaNoExiste(Exception):
    """`leer` lo lanza si lo creado con esa clave ya no existe (se vuelve a crear)."""


def huella(datos: BaseModel, extra: dict | None = None) -> str:
    cuerpo = {**datos.model_dump(mode="json"), **(extra or {})}
    return hashlib.sha256(json.dumps(cuerpo, sort_keys=True).encode()).hexdigest()


def ejecutar[T](engine: Engine, ctx: ContextoNegocio, operacion: str, clave: str | None,
             huella_datos: str, crear: Callable[[Connection], tuple[uuid.UUID, T]],
             leer: Callable[[Connection, uuid.UUID], T]) -> T:
    """`crear(con)` devuelve (id del recurso, respuesta); `leer(con, id)` la reconstruye."""
    if clave is None:
        with engine.begin() as con:
            return crear(con)[1]
    filtro = sa.and_(
        core_idempotencia.c.usuario_id == ctx.usuario_id,
        core_idempotencia.c.operacion == operacion,
        core_idempotencia.c.clave == clave,
    )
    for intento in (1, 2):
        try:
            with engine.begin() as con:
                previo = con.execute(sa.select(core_idempotencia).where(filtro)).mappings().first()
                if previo is not None and previo["creado_en"] < ahora_utc() - VIGENCIA:
                    con.execute(sa.delete(core_idempotencia).where(filtro))  # clave vencida
                    previo = None
                if previo is not None:
                    if previo["huella"] != huella_datos:
                        raise ClaveReutilizada
                    try:
                        return leer(con, previo["recurso_id"])
                    except YaNoExiste:
                        con.execute(sa.delete(core_idempotencia).where(filtro))
                recurso_id, respuesta = crear(con)
                con.execute(sa.insert(core_idempotencia).values(
                    id=uuid7(), usuario_id=ctx.usuario_id, operacion=operacion, clave=clave,
                    huella=huella_datos, recurso_id=recurso_id, creado_por=ctx.usuario_id,
                ))
                return respuesta
        except sa.exc.IntegrityError:
            # Carrera: otra petición con la misma clave se confirmó primero; se reintenta una vez.
            if intento == 2:
                raise
    raise AssertionError("inalcanzable")
