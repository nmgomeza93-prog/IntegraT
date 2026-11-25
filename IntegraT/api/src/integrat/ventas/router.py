"""/v1/ventas: cobrar, ver lo vendido y anular. El negocio siempre sale del token."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.engine import Engine

from integrat import existencias
from integrat.auth.dependencias import AccesoNegocio, acceso_negocio
from integrat.dependencias import obtener_engine
from integrat.ventas import servicio
from integrat.ventas.esquemas import AnularIn, ListaVentasOut, VentaIn, VentaOut

router = APIRouter(tags=["ventas"])
Motor = Annotated[Engine, Depends(obtener_engine)]
Acceso = Annotated[AccesoNegocio, Depends(acceso_negocio)]

ROLES_QUE_VENDEN = {"dueno", "administrador", "cajero"}
ROLES_QUE_ANULAN = {"dueno", "administrador"}


def _exigir(acceso: AccesoNegocio, roles: set[str]) -> None:
    if acceso.rol not in roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No tienes permiso para hacer esto.")


@router.post("/ventas", response_model=VentaOut, status_code=status.HTTP_201_CREATED,
             summary="Cobrar una venta (la API calcula el total)")
def cobrar(
    datos: VentaIn, acceso: Acceso, engine: Motor,
    idempotency_key: Annotated[
        str | None,
        Header(
            min_length=8, max_length=100, pattern=r"^[A-Za-z0-9_.:-]+$",
            description="Clave única por intento (ej. un UUID). Repetirla con los mismos datos "
                        "devuelve la misma venta en lugar de cobrar otra vez.",
        ),
    ] = None,
) -> VentaOut:
    _exigir(acceso, ROLES_QUE_VENDEN)
    try:
        return servicio.crear_venta_idempotente(engine, acceso.contexto, datos, idempotency_key)
    except servicio.ItemNoVendible:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Alguno de los productos ya no está disponible. Revisa tu carrito.",
        ) from None
    except existencias.SinExistencia as e:
        raise HTTPException(status.HTTP_409_CONFLICT, e.mensaje()) from None
    except servicio.FaltaVariante:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "Elige la talla o el color de cada producto.") from None
    except servicio.ClaveReutilizada:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "Esa clave ya se usó con otros datos.") from None


@router.get("/ventas", response_model=ListaVentasOut,
            summary="Lo vendido en un día (por defecto, hoy) con su resumen")
def del_dia(acceso: Acceso, engine: Motor, fecha: date | None = None) -> ListaVentasOut:
    with engine.connect() as con:
        return servicio.listar_del_dia(con, acceso.contexto, fecha)


@router.get("/ventas/{venta_id}", response_model=VentaOut, summary="Ver una venta")
def ver(venta_id: uuid.UUID, acceso: Acceso, engine: Motor) -> VentaOut:
    try:
        with engine.connect() as con:
            return servicio.obtener_venta(con, acceso.contexto, venta_id)
    except servicio.NoEncontrado:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontramos esa venta.") from None


@router.post("/ventas/{venta_id}/anular", response_model=VentaOut,
             summary="Anular una venta equivocada (no se borra; queda el motivo)")
def anular(venta_id: uuid.UUID, datos: AnularIn, acceso: Acceso, engine: Motor) -> VentaOut:
    _exigir(acceso, ROLES_QUE_ANULAN)
    try:
        with engine.begin() as con:
            return servicio.anular_venta(con, acceso.contexto, venta_id, datos.motivo)
    except servicio.NoEncontrado:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontramos esa venta.") from None
    except servicio.YaAnulada:
        raise HTTPException(status.HTTP_409_CONFLICT, "Esa venta ya estaba anulada.") from None
