"""Dependencias de autenticación. El negocio SIEMPRE sale del token, jamás del cliente."""

import uuid
from dataclasses import dataclass
from typing import Annotated

import sqlalchemy as sa
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.engine import Engine

from integrat.auth import seguridad
from integrat.db.aislamiento import ContextoNegocio
from integrat.db.tablas import core_membresia, core_negocio, core_usuario
from integrat.dependencias import obtener_engine

_bearer = HTTPBearer(auto_error=False, description="Token de acceso (Authorization: Bearer ...)")


def _no_autenticado() -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED, "Tu sesión venció. Inicia sesión otra vez.",
        headers={"WWW-Authenticate": "Bearer"},
    )


@dataclass(frozen=True)
class UsuarioActual:
    id: uuid.UUID
    nombre: str
    correo: str
    negocio_id: uuid.UUID | None  # el del token


def usuario_actual(
    credenciales: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    engine: Annotated[Engine, Depends(obtener_engine)],
) -> UsuarioActual:
    if credenciales is None:
        raise _no_autenticado()
    try:
        claims = seguridad.leer_token_acceso(credenciales.credentials)
    except seguridad.ErrorToken:
        raise _no_autenticado() from None
    with engine.connect() as con:
        fila = con.execute(
            sa.select(core_usuario.c.nombre, core_usuario.c.correo)
            .where(core_usuario.c.id == claims.usuario_id, core_usuario.c.eliminado_en.is_(None))
        ).first()
    if fila is None:
        raise _no_autenticado()
    return UsuarioActual(claims.usuario_id, fila.nombre, fila.correo, claims.negocio_id)


@dataclass(frozen=True)
class AccesoNegocio:
    contexto: ContextoNegocio
    rol: str


def acceso_negocio(
    usuario: Annotated[UsuarioActual, Depends(usuario_actual)],
    engine: Annotated[Engine, Depends(obtener_engine)],
) -> AccesoNegocio:
    """Exige un token atado a un negocio y que la membresía siga vigente."""
    if usuario.negocio_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Primero crea tu negocio.")
    with engine.connect() as con:
        rol = con.execute(
            sa.select(core_membresia.c.rol)
            .join(core_negocio, core_negocio.c.id == core_membresia.c.negocio_id)
            .where(
                core_membresia.c.usuario_id == usuario.id,
                core_membresia.c.negocio_id == usuario.negocio_id,
                core_membresia.c.eliminado_en.is_(None),
                core_negocio.c.eliminado_en.is_(None),
            )
        ).scalar_one_or_none()
    if rol is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Ya no tienes acceso a este negocio.")
    return AccesoNegocio(ContextoNegocio(usuario.negocio_id, usuario.id), rol)
