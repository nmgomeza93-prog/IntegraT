"""/v1/importaciones: vista previa de la plantilla, confirmar, recibir, anular y ver el rastreo.

El negocio sale siempre del token (docs/PLAN_IMPORTACION.md).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile, status
from sqlalchemy.engine import Engine

from integrat import idempotencia
from integrat.auth.dependencias import AccesoNegocio, acceso_negocio
from integrat.dependencias import obtener_engine
from integrat.importaciones import plantilla, servicio
from integrat.importaciones.esquemas import (
    AnularIn,
    ImportacionIn,
    ImportacionOut,
    ListaImportacionesOut,
    RecibirIn,
    VistaPreviaOut,
)

router = APIRouter(tags=["importaciones"])
Motor = Annotated[Engine, Depends(obtener_engine)]
Acceso = Annotated[AccesoNegocio, Depends(acceso_negocio)]
Clave = Annotated[
    str | None,
    Header(
        alias="Idempotency-Key",
        min_length=8,
        max_length=100,
        pattern=r"^[A-Za-z0-9_.:-]+$",
        description="Clave única por intento; repetirla no lo hace dos veces.",
    ),
]

# Como las compras: dueño y administrador registran; el contador también ve.
ROLES_QUE_VEN = {"dueno", "administrador", "contador"}
ROLES_QUE_ESCRIBEN = {"dueno", "administrador"}


def _exigir(acceso: AccesoNegocio, roles: set[str]) -> None:
    if acceso.rol not in roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No tienes permiso para hacer esto.")


def _no_encontrada() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "No encontramos esa importación.")


@router.post(
    "/importaciones/vista-previa",
    response_model=VistaPreviaOut,
    summary="Leer la plantilla de la factura (no guarda nada)",
)
async def vista_previa(
    acceso: Acceso,
    engine: Motor,
    archivo: Annotated[UploadFile, File(description="Plantilla .xlsx o .csv")],
) -> VistaPreviaOut:
    _exigir(acceso, ROLES_QUE_ESCRIBEN)
    contenido = await archivo.read(plantilla.MAX_BYTES + 1)
    try:
        leida = plantilla.leer(contenido, archivo.filename or "")
    except plantilla.PlantillaInvalida as e:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, " ".join(e.errores[:5])
        ) from None
    with engine.begin() as con:
        return servicio.vista_previa(con, acceso.contexto, leida)


@router.post(
    "/importaciones",
    response_model=ImportacionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Confirmar la importación: queda en camino",
)
def confirmar(
    datos: ImportacionIn, acceso: Acceso, engine: Motor, idempotency_key: Clave = None
) -> ImportacionOut:
    _exigir(acceso, ROLES_QUE_ESCRIBEN)
    try:
        return servicio.confirmar(engine, acceso.contexto, datos, idempotency_key)
    except servicio.MonedaInvalida:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "No reconocemos esa moneda."
        ) from None
    except servicio.FaltaCambio:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Dinos cuánto te cobró la tarjeta en quetzales."
        ) from None
    except servicio.LineaInvalida:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Revisa los productos de la importación."
        ) from None
    except idempotencia.ClaveReutilizada:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Esa clave ya se usó con otros datos."
        ) from None


@router.get(
    "/importaciones",
    response_model=ListaImportacionesOut,
    summary="Importaciones en camino y recibidas",
)
def listar(acceso: Acceso, engine: Motor) -> ListaImportacionesOut:
    _exigir(acceso, ROLES_QUE_VEN)
    with engine.connect() as con:
        return servicio.listar(con, acceso.contexto)


@router.get(
    "/importaciones/{importacion_id}",
    response_model=ImportacionOut,
    summary="Una importación con su rastreo y el costo de cada línea",
)
def ver(importacion_id: uuid.UUID, acceso: Acceso, engine: Motor) -> ImportacionOut:
    _exigir(acceso, ROLES_QUE_VEN)
    try:
        with engine.connect() as con:
            return servicio.obtener(con, acceso.contexto, importacion_id)
    except servicio.NoEncontrado:
        raise _no_encontrada() from None


@router.post(
    "/importaciones/{importacion_id}/recibir",
    response_model=ImportacionOut,
    summary="Me llegó el paquete",
)
def recibir(
    importacion_id: uuid.UUID,
    datos: RecibirIn,
    acceso: Acceso,
    engine: Motor,
    idempotency_key: Clave = None,
) -> ImportacionOut:
    _exigir(acceso, ROLES_QUE_ESCRIBEN)
    try:
        return servicio.recibir(engine, acceso.contexto, importacion_id, datos, idempotency_key)
    except servicio.NoEncontrado:
        raise _no_encontrada() from None
    except servicio.EstadoInvalido:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Esta importación ya no está en camino."
        ) from None
    except servicio.LineaInvalida:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Revisa lo que llegó de cada línea."
        ) from None
    except servicio.SinPeso:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Para repartir por peso, todo lo que llegó debe tener peso.",
        ) from None
    except servicio.NadaQueRecibir:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Dinos qué llegó en este paquete."
        ) from None
    except servicio.ProductoConReceta:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Uno de los productos tiene receta. Quítasela para recibirlo."
        ) from None
    except idempotencia.ClaveReutilizada:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Esa clave ya se usó con otros datos."
        ) from None


@router.post(
    "/importaciones/{importacion_id}/anular",
    response_model=ImportacionOut,
    summary="Anular una importación en camino",
)
def anular(
    importacion_id: uuid.UUID, datos: AnularIn, acceso: Acceso, engine: Motor
) -> ImportacionOut:
    _exigir(acceso, ROLES_QUE_ESCRIBEN)
    try:
        with engine.begin() as con:
            return servicio.anular(con, acceso.contexto, importacion_id, datos)
    except servicio.NoEncontrado:
        raise _no_encontrada() from None
    except servicio.EstadoInvalido:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Solo se anula una importación que sigue en camino."
        ) from None
