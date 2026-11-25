"""POST /v1/negocios y GET /v1/negocios/{id}."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy.engine import Engine

from integrat.auth import seguridad
from integrat.auth.dependencias import AccesoNegocio, UsuarioActual, acceso_negocio, usuario_actual
from integrat.dependencias import obtener_engine
from integrat.negocios import servicio
from integrat.negocios.esquemas import (
    AccesoOut,
    ImpuestosIn,
    NegocioCreadoOut,
    NegocioIn,
    NegocioOut,
    PreciosIn,
    ReglasVentaIn,
)

router = APIRouter(tags=["negocios"])
Motor = Annotated[Engine, Depends(obtener_engine)]


@router.post("/negocios", response_model=NegocioCreadoOut, status_code=status.HTTP_201_CREATED,
             summary="Crear mi negocio (queda como dueño)")
def crear(
    datos: NegocioIn,
    usuario: Annotated[UsuarioActual, Depends(usuario_actual)],
    engine: Motor,
    idempotency_key: Annotated[
        str | None,
        Header(
            min_length=8, max_length=100, pattern=r"^[A-Za-z0-9_.:-]+$",
            description="Clave única por intento (ej. un UUID). Repetirla con los mismos datos "
                        "devuelve el mismo negocio en lugar de crear otro.",
        ),
    ] = None,
) -> NegocioCreadoOut:
    try:
        negocio, negocio_id = servicio.crear_negocio_idempotente(
            engine, usuario.id, datos, idempotency_key
        )
    except servicio.TipoNegocioInvalido:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "Ese tipo de negocio no existe.") from None
    except servicio.ClaveReutilizada:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "Esa clave ya se usó con otros datos.") from None
    token, segundos = seguridad.crear_token_acceso(usuario.id, negocio_id)
    return NegocioCreadoOut(
        **negocio.model_dump(),
        acceso=AccesoOut(access_token=token, expira_en=segundos, negocio_id=negocio_id),
    )


@router.get("/negocios/{negocio_id}", response_model=NegocioOut, summary="Ver mi negocio")
def ver(negocio_id: uuid.UUID, acceso: Annotated[AccesoNegocio, Depends(acceso_negocio)],
        engine: Motor) -> NegocioOut:
    # El negocio sale del token. Si el id de la ruta es otro: 404 (no se revela que existe).
    if negocio_id != acceso.contexto.negocio_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontramos ese negocio.")
    with engine.connect() as con:
        negocio = servicio.leer_negocio(con, acceso.contexto)
    if negocio is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontramos ese negocio.")
    return negocio


@router.put("/negocios/{negocio_id}/impuestos", status_code=status.HTTP_204_NO_CONTENT,
            summary="Cómo pagas impuestos (régimen de IVA)")
def fijar_impuestos(negocio_id: uuid.UUID, datos: ImpuestosIn,
                    acceso: Annotated[AccesoNegocio, Depends(acceso_negocio)],
                    engine: Motor) -> Response:
    if negocio_id != acceso.contexto.negocio_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontramos ese negocio.")
    if acceso.rol != "dueno":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo el dueño puede cambiar esto.")
    with engine.begin() as con:
        servicio.fijar_impuestos(con, acceso.contexto, datos)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/negocios/{negocio_id}/precios", status_code=status.HTTP_204_NO_CONTENT,
            summary="Tu margen objetivo (para el precio sugerido y la meta)")
def fijar_precios(negocio_id: uuid.UUID, datos: PreciosIn,
                  acceso: Annotated[AccesoNegocio, Depends(acceso_negocio)],
                  engine: Motor) -> Response:
    if negocio_id != acceso.contexto.negocio_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontramos ese negocio.")
    if acceso.rol not in {"dueno", "administrador"}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No tienes permiso para cambiar esto.")
    with engine.begin() as con:
        servicio.fijar_precios(con, acceso.contexto, datos)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/negocios/{negocio_id}/ventas", status_code=status.HTTP_204_NO_CONTENT,
            summary="Si se puede vender lo que no hay en inventario (bloquear o avisar)")
def fijar_reglas_venta(negocio_id: uuid.UUID, datos: ReglasVentaIn,
                       acceso: Annotated[AccesoNegocio, Depends(acceso_negocio)],
                       engine: Motor) -> Response:
    if negocio_id != acceso.contexto.negocio_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontramos ese negocio.")
    if acceso.rol not in {"dueno", "administrador"}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No tienes permiso para cambiar esto.")
    with engine.begin() as con:
        servicio.fijar_reglas_venta(con, acceso.contexto, datos)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
