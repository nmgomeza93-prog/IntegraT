"""Lógica de cuentas. Todas las funciones reciben una conexión con transacción abierta."""

import uuid
from dataclasses import dataclass
from datetime import timedelta

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from integrat.auth import seguridad
from integrat.config import config_app
from integrat.db.tablas import core_membresia, core_negocio, core_token_refresco, core_usuario
from integrat.db.tipos import ahora_utc, uuid7


class CorreoYaRegistrado(Exception):
    pass


@dataclass(frozen=True)
class Sesion:
    usuario_id: uuid.UUID
    nombre: str
    correo: str
    access_token: str
    expira_en: int
    refresh_token: str
    negocio_id: uuid.UUID | None


def negocio_por_defecto(con: Connection, usuario_id: uuid.UUID) -> uuid.UUID | None:
    """Negocio al que se ata el token. MVP: el primero del usuario (el más antiguo)."""
    return con.execute(
        sa.select(core_membresia.c.negocio_id)
        .join(core_negocio, core_negocio.c.id == core_membresia.c.negocio_id)
        .where(
            core_membresia.c.usuario_id == usuario_id,
            core_membresia.c.eliminado_en.is_(None),
            core_negocio.c.eliminado_en.is_(None),
        )
        .order_by(core_membresia.c.creado_en, core_membresia.c.id)
        .limit(1)
    ).scalar_one_or_none()


def _guardar_refresco(con: Connection, usuario_id: uuid.UUID) -> str:
    plano, hash_ = seguridad.nuevo_token_refresco()
    con.execute(sa.insert(core_token_refresco).values(
        id=uuid7(), usuario_id=usuario_id, token_hash=hash_, creado_por=usuario_id,
        expira_en=ahora_utc() + timedelta(days=config_app().api_jwt_refresco_dias),
    ))
    return plano


def emitir_sesion(con: Connection, usuario_id: uuid.UUID, nombre: str, correo: str) -> Sesion:
    negocio_id = negocio_por_defecto(con, usuario_id)
    acceso, segundos = seguridad.crear_token_acceso(usuario_id, negocio_id)
    return Sesion(usuario_id, nombre, correo, acceso, segundos,
                  _guardar_refresco(con, usuario_id), negocio_id)


def registrar(con: Connection, *, nombre: str, correo: str, clave: str,
              telefono: str | None) -> Sesion:
    existe = con.execute(
        sa.select(core_usuario.c.id).where(core_usuario.c.correo == correo)
    ).first()
    if existe:
        raise CorreoYaRegistrado
    usuario_id = uuid7()
    try:
        with con.begin_nested():
            con.execute(sa.insert(core_usuario).values(
                id=usuario_id, correo=correo, nombre=nombre, telefono=telefono or None,
                clave_hash=seguridad.hashear_clave(clave), creado_por=usuario_id,
            ))
    except sa.exc.IntegrityError as e:  # carrera: dos registros simultáneos con el mismo correo
        raise CorreoYaRegistrado from e
    return emitir_sesion(con, usuario_id, nombre, correo)


def iniciar_sesion(con: Connection, *, correo: str, clave: str) -> Sesion | None:
    fila = con.execute(
        sa.select(core_usuario.c.id, core_usuario.c.nombre, core_usuario.c.clave_hash)
        .where(core_usuario.c.correo == correo, core_usuario.c.eliminado_en.is_(None))
    ).first()
    valida = seguridad.verificar_clave(clave, fila.clave_hash if fila else None)
    if not fila or not valida:
        return None
    con.execute(sa.update(core_usuario).where(core_usuario.c.id == fila.id)
                .values(ultimo_acceso_en=ahora_utc()))
    return emitir_sesion(con, fila.id, fila.nombre, correo)


def refrescar(con: Connection, token_plano: str) -> Sesion | None:
    """Rota el token de refresco.

    Si se reutiliza uno ya usado, se cierran TODAS las sesiones del usuario (posible robo
    del token). Devuelve None si no es válido; quien llama debe confirmar la transacción
    para que la revocación persista.
    """
    fila = con.execute(
        sa.select(core_token_refresco.c.id, core_token_refresco.c.usuario_id,
                  core_token_refresco.c.expira_en, core_token_refresco.c.revocado_en)
        .where(core_token_refresco.c.token_hash == seguridad.hash_token_refresco(token_plano),
               core_token_refresco.c.eliminado_en.is_(None))
    ).first()
    if fila is None:
        return None
    ahora = ahora_utc()
    if fila.revocado_en is not None:
        con.execute(sa.update(core_token_refresco)
                    .where(core_token_refresco.c.usuario_id == fila.usuario_id,
                           core_token_refresco.c.revocado_en.is_(None))
                    .values(revocado_en=ahora))
        return None
    if fila.expira_en <= ahora:
        return None
    usuario = con.execute(
        sa.select(core_usuario.c.id, core_usuario.c.nombre, core_usuario.c.correo)
        .where(core_usuario.c.id == fila.usuario_id, core_usuario.c.eliminado_en.is_(None))
    ).first()
    if usuario is None:
        return None
    con.execute(sa.update(core_token_refresco)
                .where(core_token_refresco.c.id == fila.id).values(revocado_en=ahora))
    return emitir_sesion(con, usuario.id, usuario.nombre, usuario.correo)
