"""/v1/compras y /v1/proveedores: compras a mano. El negocio sale siempre del token."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy.engine import Engine

from integrat.auth.dependencias import AccesoNegocio, acceso_negocio
from integrat.compras import servicio
from integrat.compras.esquemas import (
    AnularIn,
    CompraIn,
    CompraOut,
    ListaComprasOut,
    ProveedorCambios,
    ProveedorIn,
    ProveedorOut,
)
from integrat.dependencias import obtener_engine
from integrat.insumos import servicio as inventario

router = APIRouter(tags=["compras"])
Motor = Annotated[Engine, Depends(obtener_engine)]
Acceso = Annotated[AccesoNegocio, Depends(acceso_negocio)]

# Lo que se compra y a quién no es para todos: el cajero no lo ve.
ROLES_QUE_VEN = {"dueno", "administrador", "contador"}
ROLES_QUE_ESCRIBEN = {"dueno", "administrador"}

_DESFASADO = HTTPException(
    status.HTTP_409_CONFLICT,
    "Alguien más cambió esto. Ábrelo de nuevo e inténtalo otra vez.",
)


def _exigir(acceso: AccesoNegocio, roles: set[str]) -> None:
    if acceso.rol not in roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No tienes permiso para hacer esto.")


def _no_encontrado(que: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"No encontramos {que}.")


def _nombre_repetido() -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, "Ya tienes un proveedor con ese nombre.")


# ------------------------------------------------------------------ proveedores

@router.get("/proveedores", response_model=list[ProveedorOut], summary="Mis proveedores")
def listar_proveedores(acceso: Acceso, engine: Motor) -> list[ProveedorOut]:
    _exigir(acceso, ROLES_QUE_VEN)
    with engine.connect() as con:
        return servicio.listar_proveedores(con, acceso.contexto)


@router.post("/proveedores", response_model=ProveedorOut, status_code=status.HTTP_201_CREATED,
             summary="Agregar un proveedor")
def crear_proveedor(datos: ProveedorIn, acceso: Acceso, engine: Motor) -> ProveedorOut:
    _exigir(acceso, ROLES_QUE_ESCRIBEN)
    try:
        with engine.begin() as con:
            return servicio.crear_proveedor(con, acceso.contexto, datos)
    except servicio.NombreRepetido:
        raise _nombre_repetido() from None


@router.patch("/proveedores/{proveedor_id}", response_model=ProveedorOut,
              summary="Cambiar un proveedor")
def cambiar_proveedor(proveedor_id: uuid.UUID, cambios: ProveedorCambios, acceso: Acceso,
                      engine: Motor) -> ProveedorOut:
    _exigir(acceso, ROLES_QUE_ESCRIBEN)
    try:
        with engine.begin() as con:
            return servicio.actualizar_proveedor(con, acceso.contexto, proveedor_id, cambios)
    except servicio.NoEncontrado:
        raise _no_encontrado("ese proveedor") from None
    except servicio.VersionDesfasada:
        raise _DESFASADO from None
    except servicio.NombreRepetido:
        raise _nombre_repetido() from None


@router.delete("/proveedores/{proveedor_id}", status_code=status.HTTP_204_NO_CONTENT,
               summary="Archivar un proveedor (sus compras no se tocan)")
def archivar_proveedor(proveedor_id: uuid.UUID, acceso: Acceso, engine: Motor) -> Response:
    _exigir(acceso, ROLES_QUE_ESCRIBEN)
    try:
        with engine.begin() as con:
            servicio.archivar_proveedor(con, acceso.contexto, proveedor_id)
    except servicio.NoEncontrado:
        raise _no_encontrado("ese proveedor") from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------------------------ compras

@router.post("/compras", response_model=CompraOut, status_code=status.HTTP_201_CREATED,
             summary="Registrar una compra (sube el inventario y recalcula el costo)")
def registrar(
    datos: CompraIn, acceso: Acceso, engine: Motor,
    idempotency_key: Annotated[
        str | None,
        Header(
            min_length=8, max_length=100, pattern=r"^[A-Za-z0-9_.:-]+$",
            description="Clave única por intento (ej. un UUID). Repetirla con los mismos datos "
                        "devuelve la misma compra en lugar de registrarla otra vez.",
        ),
    ] = None,
) -> CompraOut:
    _exigir(acceso, ROLES_QUE_ESCRIBEN)
    try:
        return servicio.crear_compra_idempotente(engine, acceso.contexto, datos, idempotency_key)
    except servicio.ProveedorInvalido:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "Ese proveedor no existe.") from None
    except servicio.InsumoInvalido:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "Uno de los insumos no existe.") from None
    except inventario.UnidadInvalida:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Esa unidad no sirve aquí. Usa una del mismo tipo (peso con peso, líquido con líquido)."
        ) from None
    except servicio.FechaFutura:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "La fecha no puede ser de mañana en adelante.") from None
    except servicio.ClaveReutilizada:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "Esa clave ya se usó con otros datos.") from None


@router.get("/compras", response_model=ListaComprasOut,
            summary="Compras de un mes (por defecto, el actual) con su total")
def del_mes(acceso: Acceso, engine: Motor, mes: str | None = None) -> ListaComprasOut:
    _exigir(acceso, ROLES_QUE_VEN)
    try:
        with engine.connect() as con:
            return servicio.listar_del_mes(con, acceso.contexto, mes)
    except servicio.MesInvalido:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "El mes debe ser como 2026-11.") from None


@router.get("/compras/{compra_id}", response_model=CompraOut, summary="Ver una compra")
def ver(compra_id: uuid.UUID, acceso: Acceso, engine: Motor) -> CompraOut:
    _exigir(acceso, ROLES_QUE_VEN)
    try:
        with engine.connect() as con:
            return servicio.obtener_compra(con, acceso.contexto, compra_id)
    except servicio.NoEncontrado:
        raise _no_encontrado("esa compra") from None


@router.post("/compras/{compra_id}/anular", response_model=CompraOut,
             summary="Anular una compra con motivo (se revierte el inventario)")
def anular(compra_id: uuid.UUID, datos: AnularIn, acceso: Acceso, engine: Motor) -> CompraOut:
    _exigir(acceso, ROLES_QUE_ESCRIBEN)
    try:
        with engine.begin() as con:
            return servicio.anular_compra(con, acceso.contexto, compra_id, datos.motivo)
    except servicio.NoEncontrado:
        raise _no_encontrado("esa compra") from None
    except servicio.YaAnulada:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Esa compra ya estaba anulada.") from None
