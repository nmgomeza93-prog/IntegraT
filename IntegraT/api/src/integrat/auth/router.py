"""POST /v1/auth/registro, /login, /refrescar y GET /v1/yo."""

import logging
from typing import Annotated

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.engine import Engine

from integrat.auth import servicio
from integrat.auth.dependencias import UsuarioActual, usuario_actual
from integrat.auth.esquemas import (
    LoginIn,
    NegocioResumen,
    RefrescarIn,
    RegistroIn,
    SesionOut,
    UsuarioOut,
    YoOut,
)
from integrat.auth.seguridad import ErrorConfiguracion
from integrat.db.tablas import core_membresia, core_negocio
from integrat.dependencias import obtener_engine

log = logging.getLogger(__name__)
router = APIRouter(tags=["auth"])
Motor = Annotated[Engine, Depends(obtener_engine)]


def _a_salida(s: servicio.Sesion) -> SesionOut:
    return SesionOut(
        access_token=s.access_token, expira_en=s.expira_en, refresh_token=s.refresh_token,
        negocio_id=s.negocio_id,
        usuario=UsuarioOut(id=s.usuario_id, nombre=s.nombre, correo=s.correo),
    )


def _sin_configuracion(e: ErrorConfiguracion) -> HTTPException:
    log.error("Configuración incompleta de tokens: %s", e)
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                         "El servicio no está listo. Intenta más tarde.")


@router.post("/auth/registro", response_model=SesionOut, status_code=status.HTTP_201_CREATED,
             summary="Crear una cuenta")
def registro(datos: RegistroIn, engine: Motor) -> SesionOut:
    try:
        with engine.begin() as con:
            sesion = servicio.registrar(
                con, nombre=datos.nombre, correo=datos.correo, clave=datos.clave,
                telefono=datos.telefono,
            )
    except servicio.CorreoYaRegistrado:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Ese correo ya tiene una cuenta. Prueba iniciar sesión.") from None
    except ErrorConfiguracion as e:
        raise _sin_configuracion(e) from None
    return _a_salida(sesion)


@router.post("/auth/login", response_model=SesionOut, summary="Iniciar sesión")
def login(datos: LoginIn, engine: Motor) -> SesionOut:
    try:
        with engine.begin() as con:
            sesion = servicio.iniciar_sesion(con, correo=datos.correo, clave=datos.clave)
    except ErrorConfiguracion as e:
        raise _sin_configuracion(e) from None
    if sesion is None:  # mismo mensaje exista o no el correo
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Correo o contraseña incorrectos.")
    return _a_salida(sesion)


@router.post("/auth/refrescar", response_model=SesionOut,
             summary="Renovar la sesión con el token de refresco")
def refrescar(datos: RefrescarIn, engine: Motor) -> SesionOut:
    try:
        # La transacción se confirma aunque el resultado sea None: así persiste la revocación
        # por reutilización de un token ya usado.
        with engine.begin() as con:
            sesion = servicio.refrescar(con, datos.refresh_token)
    except ErrorConfiguracion as e:
        raise _sin_configuracion(e) from None
    if sesion is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            "Tu sesión venció. Inicia sesión otra vez.")
    return _a_salida(sesion)


@router.get("/yo", response_model=YoOut, summary="Quién soy y a qué negocios tengo acceso")
def yo(usuario: Annotated[UsuarioActual, Depends(usuario_actual)], engine: Motor) -> YoOut:
    with engine.connect() as con:
        filas = con.execute(
            sa.select(core_negocio.c.id, core_negocio.c.nombre, core_negocio.c.tipo_negocio_codigo,
                      core_membresia.c.rol)
            .join(core_negocio, core_negocio.c.id == core_membresia.c.negocio_id)
            .where(core_membresia.c.usuario_id == usuario.id,
                   core_membresia.c.eliminado_en.is_(None),
                   core_negocio.c.eliminado_en.is_(None))
            .order_by(core_membresia.c.creado_en, core_membresia.c.id)
        ).all()
    return YoOut(
        usuario=UsuarioOut(id=usuario.id, nombre=usuario.nombre, correo=usuario.correo),
        negocio_actual_id=usuario.negocio_id,
        negocios=[NegocioResumen(id=f.id, nombre=f.nombre,
                                 tipo_negocio_codigo=f.tipo_negocio_codigo, rol=f.rol)
                  for f in filas],
    )
