"""/v1/caja (abrir, ver y cerrar el día) y /v1/dueno (aportes y retiros). Negocio del token."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy.engine import Engine

from integrat import idempotencia
from integrat.auth.dependencias import AccesoNegocio, acceso_negocio
from integrat.caja import servicio
from integrat.caja.esquemas import (
    AbrirCajaIn,
    CajaOut,
    CerrarCajaIn,
    ListaCierresOut,
    ListaDuenoOut,
    MovimientoDuenoIn,
    MovimientoDuenoOut,
    SesionCajaOut,
)
from integrat.dependencias import obtener_engine

router = APIRouter(tags=["caja"])
Motor = Annotated[Engine, Depends(obtener_engine)]
Acceso = Annotated[AccesoNegocio, Depends(acceso_negocio)]
Mes = Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}$",
                                  description="AAAA-MM; por defecto, este mes.")]
Clave = Annotated[
    str | None,
    Header(alias="Idempotency-Key", min_length=8, max_length=100, pattern=r"^[A-Za-z0-9_.:-]+$",
           description="Clave única por intento; repetirla no lo hace dos veces."),
]

ROLES_CAJA = {"dueno", "administrador", "cajero"}
ROLES_VEN_DUENO = {"dueno", "administrador", "contador"}
ROLES_ESCRIBEN_DUENO = {"dueno"}


def _exigir(acceso: AccesoNegocio, roles: set[str]) -> None:
    if acceso.rol not in roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No tienes permiso para hacer esto.")


def _mes_invalido() -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Ese mes no es válido.")


def _clave_reutilizada() -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                         "Esa clave ya se usó con otros datos.")


# ------------------------------------------------------------------ caja

@router.get("/caja", response_model=CajaOut, summary="La caja de hoy y el último cierre")
def ver_caja(acceso: Acceso, engine: Motor) -> CajaOut:
    _exigir(acceso, ROLES_CAJA)
    with engine.begin() as con:
        return servicio.estado_caja(con, acceso.contexto)


@router.post("/caja/abrir", response_model=SesionCajaOut, status_code=status.HTTP_201_CREATED,
             summary="Abrir la caja con el efectivo con que empiezas")
def abrir(datos: AbrirCajaIn, acceso: Acceso, engine: Motor) -> SesionCajaOut:
    _exigir(acceso, ROLES_CAJA)
    try:
        with engine.begin() as con:
            return servicio.abrir_caja(con, acceso.contexto, datos)
    except servicio.YaAbierta:
        raise HTTPException(status.HTTP_409_CONFLICT, "La caja ya está abierta.") from None


@router.post("/caja/cerrar", response_model=SesionCajaOut, summary="Cerrar el día")
def cerrar(datos: CerrarCajaIn, acceso: Acceso, engine: Motor,
           idempotency_key: Clave = None) -> SesionCajaOut:
    _exigir(acceso, ROLES_CAJA)
    try:
        return servicio.cerrar_caja(engine, acceso.contexto, datos, idempotency_key)
    except servicio.NoHayAbierta:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "La caja no está abierta. Ábrela primero.") from None
    except idempotencia.ClaveReutilizada:
        raise _clave_reutilizada() from None


@router.get("/caja/cierres", response_model=ListaCierresOut, summary="Cierres del mes")
def cierres(acceso: Acceso, engine: Motor, mes: Mes = None) -> ListaCierresOut:
    _exigir(acceso, ROLES_CAJA)
    try:
        with engine.begin() as con:
            return servicio.cierres_del_mes(con, acceso.contexto, mes)
    except servicio.MesInvalido:
        raise _mes_invalido() from None


# ------------------------------------------------------------------ dueño

@router.get("/dueno", response_model=ListaDuenoOut, summary="Lo que pusiste y sacaste en el mes")
def dueno_del_mes(acceso: Acceso, engine: Motor, mes: Mes = None) -> ListaDuenoOut:
    _exigir(acceso, ROLES_VEN_DUENO)
    try:
        with engine.connect() as con:
            return servicio.movimientos_dueno_del_mes(con, acceso.contexto, mes)
    except servicio.MesInvalido:
        raise _mes_invalido() from None


@router.post("/dueno", response_model=MovimientoDuenoOut, status_code=status.HTTP_201_CREATED,
             summary="Pusiste o sacaste dinero del negocio")
def anotar_dueno(datos: MovimientoDuenoIn, acceso: Acceso, engine: Motor,
                 idempotency_key: Clave = None) -> MovimientoDuenoOut:
    _exigir(acceso, ROLES_ESCRIBEN_DUENO)
    try:
        return servicio.crear_movimiento_dueno(engine, acceso.contexto, datos, idempotency_key)
    except servicio.FechaFutura:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "La fecha no puede ser de mañana en adelante.") from None
    except idempotencia.ClaveReutilizada:
        raise _clave_reutilizada() from None


@router.delete("/dueno/{movimiento_id}", status_code=status.HTTP_204_NO_CONTENT,
               summary="Borrar un movimiento del dueño (se revierte)")
def borrar_dueno(movimiento_id: uuid.UUID, acceso: Acceso, engine: Motor) -> Response:
    _exigir(acceso, ROLES_ESCRIBEN_DUENO)
    try:
        with engine.begin() as con:
            servicio.borrar_movimiento_dueno(con, acceso.contexto, movimiento_id)
    except servicio.NoEncontrado:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontramos ese movimiento.") from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
