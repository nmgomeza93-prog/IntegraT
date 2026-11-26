"""/v1/clientes: a quién le vendes. El negocio sale siempre del token.

El cajero busca, crea y corrige clientes al vender; archivar y definir los campos propios es del
dueño o el administrador. No hay exportación de la base (docs/ANALISIS_INVENTARIO_Y_CLIENTES.md).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.engine import Engine

from integrat import validaciones as val
from integrat.auth.dependencias import AccesoNegocio, acceso_negocio
from integrat.clientes import servicio
from integrat.clientes.esquemas import (
    CampoOut,
    CamposIn,
    ClienteCambios,
    ClienteIn,
    ClienteOut,
    ClienteResumen,
)
from integrat.dependencias import obtener_engine

router = APIRouter(tags=["clientes"])
Motor = Annotated[Engine, Depends(obtener_engine)]
Acceso = Annotated[AccesoNegocio, Depends(acceso_negocio)]

ROLES_QUE_VEN = {"dueno", "administrador", "cajero", "contador"}
ROLES_QUE_ANOTAN = {"dueno", "administrador", "cajero"}
ROLES_QUE_CONFIGURAN = {"dueno", "administrador"}

_NO_ENCONTRADO = HTTPException(status.HTTP_404_NOT_FOUND, "No encontramos ese cliente.")
_DESFASADO = HTTPException(status.HTTP_409_CONFLICT,
                           "Alguien más cambió este cliente. Ábrelo de nuevo e inténtalo otra vez.")


def _exigir(acceso: AccesoNegocio, roles: set[str]) -> None:
    if acceso.rol not in roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No tienes permiso para hacer esto.")


def _invalido(e: Exception) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e))


# ------------------------------------------------------------------ campos propios (antes de /{id})

@router.get("/clientes/campos", response_model=list[CampoOut],
            summary="Los campos de cliente que definió el negocio")
def campos(acceso: Acceso, engine: Motor) -> list[CampoOut]:
    _exigir(acceso, ROLES_QUE_VEN)
    with engine.connect() as con:
        return servicio.listar_campos(con, acceso.contexto)


@router.put("/clientes/campos", response_model=list[CampoOut],
            summary="Fijar los campos de cliente (los que no vienen se archivan)")
def fijar_campos(datos: CamposIn, acceso: Acceso, engine: Motor) -> list[CampoOut]:
    _exigir(acceso, ROLES_QUE_CONFIGURAN)
    try:
        with engine.begin() as con:
            return servicio.fijar_campos(con, acceso.contexto, datos)
    except servicio.CampoInvalido as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, e.mensaje) from None


# ------------------------------------------------------------------ clientes

@router.get("/clientes", response_model=list[ClienteResumen],
            summary="Buscar clientes por nombre, teléfono o NIT (máximo 50)")
def buscar(acceso: Acceso, engine: Motor,
           q: Annotated[str | None, Query(max_length=60)] = None,
           archivados: bool = False) -> list[ClienteResumen]:
    _exigir(acceso, ROLES_QUE_VEN)
    with engine.connect() as con:
        return servicio.buscar(con, acceso.contexto, q, archivados)


@router.post("/clientes", response_model=ClienteOut, status_code=status.HTTP_201_CREATED,
             summary="Agregar un cliente")
def crear(datos: ClienteIn, acceso: Acceso, engine: Motor) -> ClienteOut:
    _exigir(acceso, ROLES_QUE_ANOTAN)
    try:
        with engine.begin() as con:
            return servicio.crear(con, acceso.contexto, datos)
    except val.DatoInvalido as e:
        raise _invalido(e) from None
    except servicio.Duplicado as e:
        raise HTTPException(status.HTTP_409_CONFLICT, e.mensaje()) from None


@router.get("/clientes/{cliente_id}", response_model=ClienteOut,
            summary="La ficha del cliente con lo que ha comprado")
def ver(cliente_id: uuid.UUID, acceso: Acceso, engine: Motor) -> ClienteOut:
    _exigir(acceso, ROLES_QUE_VEN)
    try:
        with engine.connect() as con:
            return servicio.obtener(con, acceso.contexto, cliente_id)
    except servicio.NoEncontrado:
        raise _NO_ENCONTRADO from None


@router.patch("/clientes/{cliente_id}", response_model=ClienteOut, summary="Cambiar un cliente")
def cambiar(cliente_id: uuid.UUID, cambios: ClienteCambios, acceso: Acceso,
            engine: Motor) -> ClienteOut:
    _exigir(acceso, ROLES_QUE_ANOTAN)
    try:
        with engine.begin() as con:
            return servicio.actualizar(con, acceso.contexto, cliente_id, cambios)
    except servicio.NoEncontrado:
        raise _NO_ENCONTRADO from None
    except servicio.VersionDesfasada:
        raise _DESFASADO from None
    except val.DatoInvalido as e:
        raise _invalido(e) from None
    except servicio.Duplicado as e:
        raise HTTPException(status.HTTP_409_CONFLICT, e.mensaje()) from None


@router.delete("/clientes/{cliente_id}", status_code=status.HTTP_204_NO_CONTENT,
               summary="Archivar un cliente (sus ventas no se tocan)")
def archivar(cliente_id: uuid.UUID, acceso: Acceso, engine: Motor) -> Response:
    _exigir(acceso, ROLES_QUE_CONFIGURAN)
    try:
        with engine.begin() as con:
            servicio.archivar(con, acceso.contexto, cliente_id)
    except servicio.NoEncontrado:
        raise _NO_ENCONTRADO from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/clientes/{cliente_id}/recuperar", response_model=ClienteOut,
             summary="Volver a la lista a un cliente archivado")
def recuperar(cliente_id: uuid.UUID, acceso: Acceso, engine: Motor) -> ClienteOut:
    _exigir(acceso, ROLES_QUE_CONFIGURAN)
    try:
        with engine.begin() as con:
            return servicio.recuperar(con, acceso.contexto, cliente_id)
    except servicio.NoEncontrado:
        raise _NO_ENCONTRADO from None
