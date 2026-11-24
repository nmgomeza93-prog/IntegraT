"""POST /v1/auth/registro, /login, /refrescar y GET /v1/yo."""

import logging
from typing import Annotated

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.engine import Engine

from integrat.auth import limitador, servicio
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


def ip_cliente(request: Request) -> str:
    """IP de quien llama. Detrás del proxy de Railway, uvicorn (--proxy-headers) la toma de
    X-Forwarded-For si FORWARDED_ALLOW_IPS lo permite (docs/PLAN_CIERRE_FASE1.md, paso 4)."""
    return request.client.host if request.client else "desconocida"


def _demasiados(segundos: int) -> HTTPException:
    return HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, limitador.MENSAJE,
                         headers={"Retry-After": str(segundos)})


@router.post("/auth/registro", response_model=SesionOut, status_code=status.HTTP_201_CREATED,
             summary="Crear una cuenta")
def registro(datos: RegistroIn, engine: Motor, request: Request) -> SesionOut:
    ip = ip_cliente(request)
    try:
        # El intento se anota ANTES y en su propia transacción: cuenta aunque el registro falle.
        with engine.begin() as con:
            espera = limitador.segundos_de_espera(con, "registro", ip=ip)
            if espera is None:
                limitador.registrar(con, "registro", ip=ip)
        if espera is not None:
            log.warning("Acceso: bloqueo de registro ip=%s", ip)
            raise _demasiados(espera)
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
def login(datos: LoginIn, engine: Motor, request: Request) -> SesionOut:
    ip = ip_cliente(request)
    sesion = None
    try:
        # La transacción se confirma aunque el login falle: así se guarda el intento fallido.
        with engine.begin() as con:
            espera = limitador.segundos_de_espera(con, "login", ip=ip, correo=datos.correo)
            if espera is None:
                sesion = servicio.iniciar_sesion(con, correo=datos.correo, clave=datos.clave)
                if sesion is None:
                    limitador.registrar(con, "login", ip=ip, correo=datos.correo)
                else:
                    limitador.olvidar_correo(con, "login", datos.correo)
    except ErrorConfiguracion as e:
        raise _sin_configuracion(e) from None
    if espera is not None:
        log.warning("Acceso: bloqueo de login ip=%s correo#%s", ip,
                    limitador.correo_corto(datos.correo))
        raise _demasiados(espera)
    if sesion is None:  # mismo mensaje exista o no el correo
        log.warning("Acceso: login fallido ip=%s correo#%s", ip,
                    limitador.correo_corto(datos.correo))
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Correo o contraseña incorrectos.")
    return _a_salida(sesion)


@router.post("/auth/refrescar", response_model=SesionOut,
             summary="Renovar la sesión con el token de refresco")
def refrescar(datos: RefrescarIn, engine: Motor, request: Request) -> SesionOut:
    ip = ip_cliente(request)
    sesion = None
    try:
        # La transacción se confirma aunque el resultado sea None: así persiste la revocación
        # por reutilización de un token ya usado y el intento fallido.
        with engine.begin() as con:
            espera = limitador.segundos_de_espera(con, "refrescar", ip=ip)
            if espera is None:
                sesion = servicio.refrescar(con, datos.refresh_token)
                if sesion is None:
                    limitador.registrar(con, "refrescar", ip=ip)
    except ErrorConfiguracion as e:
        raise _sin_configuracion(e) from None
    if espera is not None:
        log.warning("Acceso: bloqueo de refresco ip=%s", ip)
        raise _demasiados(espera)
    if sesion is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            "Tu sesión venció. Inicia sesión otra vez.")
    return _a_salida(sesion)


@router.post("/auth/salir", status_code=status.HTTP_204_NO_CONTENT,
             summary="Cerrar sesión (revoca el token de refresco)")
def salir(datos: RefrescarIn, engine: Motor) -> Response:
    # No exige token de acceso (puede estar vencido): el token de refresco es la credencial.
    # Responde 204 exista o no el token, para no revelar cuáles existen.
    with engine.begin() as con:
        servicio.cerrar_sesion(con, datos.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/yo",response_model=YoOut, summary="Quién soy y a qué negocios tengo acceso")
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
