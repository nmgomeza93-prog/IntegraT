"""POST /v1/negocios y GET /v1/negocios/{id}."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.engine import Engine

from integrat.auth import seguridad
from integrat.auth.dependencias import AccesoNegocio, UsuarioActual, acceso_negocio, usuario_actual
from integrat.dependencias import obtener_engine
from integrat.negocios import servicio
from integrat.negocios.esquemas import AccesoOut, NegocioCreadoOut, NegocioIn, NegocioOut

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
