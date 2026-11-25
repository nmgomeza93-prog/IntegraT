"""/v1/gastos: anotar, ver por mes, corregir y archivar. El negocio sale siempre del token."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy.engine import Engine

from integrat.auth.dependencias import AccesoNegocio, acceso_negocio
from integrat.dependencias import obtener_engine
from integrat.gastos import servicio
from integrat.gastos.esquemas import (
    CategoriaGastoCambios,
    CategoriaGastoIn,
    CategoriaGastoOut,
    GastoCambios,
    GastoIn,
    GastoOut,
    ListaGastosOut,
)

router = APIRouter(tags=["gastos"])
Motor = Annotated[Engine, Depends(obtener_engine)]
Acceso = Annotated[AccesoNegocio, Depends(acceso_negocio)]

# Los gastos (sueldos, renta) no son para todos: el cajero no los ve.
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


def _categoria_no_existe() -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Esa categoría no existe.")


def _fecha_futura() -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                         "La fecha no puede ser de mañana en adelante.")


# ------------------------------------------------------------------ categorías

@router.get("/gastos/categorias", response_model=list[CategoriaGastoOut],
            summary="Mis categorías de gasto")
def listar_categorias(acceso: Acceso, engine: Motor) -> list[CategoriaGastoOut]:
    _exigir(acceso, ROLES_QUE_VEN)
    with engine.begin() as con:
        servicio.asegurar_categorias_de_ejemplo(con, acceso.contexto)
        return servicio.listar_categorias(con, acceso.contexto)


@router.post("/gastos/categorias", response_model=CategoriaGastoOut,
             status_code=status.HTTP_201_CREATED, summary="Crear una categoría de gasto")
def crear_categoria(datos: CategoriaGastoIn, acceso: Acceso, engine: Motor) -> CategoriaGastoOut:
    _exigir(acceso, ROLES_QUE_ESCRIBEN)
    try:
        with engine.begin() as con:
            return servicio.crear_categoria(con, acceso.contexto, datos)
    except servicio.NombreRepetido:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Ya tienes una categoría con ese nombre.") from None


@router.patch("/gastos/categorias/{categoria_id}", response_model=CategoriaGastoOut,
              summary="Cambiar una categoría de gasto")
def cambiar_categoria(categoria_id: uuid.UUID, cambios: CategoriaGastoCambios, acceso: Acceso,
                      engine: Motor) -> CategoriaGastoOut:
    _exigir(acceso, ROLES_QUE_ESCRIBEN)
    try:
        with engine.begin() as con:
            return servicio.actualizar_categoria(con, acceso.contexto, categoria_id, cambios)
    except servicio.NoEncontrado:
        raise _no_encontrado("esa categoría") from None
    except servicio.VersionDesfasada:
        raise _DESFASADO from None
    except servicio.NombreRepetido:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Ya tienes una categoría con ese nombre.") from None


@router.delete("/gastos/categorias/{categoria_id}", status_code=status.HTTP_204_NO_CONTENT,
               summary="Archivar una categoría (sus gastos no se tocan)")
def archivar_categoria(categoria_id: uuid.UUID, acceso: Acceso, engine: Motor) -> Response:
    _exigir(acceso, ROLES_QUE_ESCRIBEN)
    try:
        with engine.begin() as con:
            servicio.archivar_categoria(con, acceso.contexto, categoria_id)
    except servicio.NoEncontrado:
        raise _no_encontrado("esa categoría") from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------------------------ gastos

@router.post("/gastos", response_model=GastoOut, status_code=status.HTTP_201_CREATED,
             summary="Anotar un gasto")
def anotar(
    datos: GastoIn, acceso: Acceso, engine: Motor,
    idempotency_key: Annotated[
        str | None,
        Header(
            min_length=8, max_length=100, pattern=r"^[A-Za-z0-9_.:-]+$",
            description="Clave única por intento (ej. un UUID). Repetirla con los mismos datos "
                        "devuelve el mismo gasto en lugar de anotarlo otra vez.",
        ),
    ] = None,
) -> GastoOut:
    _exigir(acceso, ROLES_QUE_ESCRIBEN)
    try:
        return servicio.crear_gasto_idempotente(engine, acceso.contexto, datos, idempotency_key)
    except servicio.CategoriaInvalida:
        raise _categoria_no_existe() from None
    except servicio.FechaFutura:
        raise _fecha_futura() from None
    except servicio.ClaveReutilizada:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "Esa clave ya se usó con otros datos.") from None


@router.get("/gastos", response_model=ListaGastosOut,
            summary="Gastos de un mes (por defecto, el actual) con su resumen")
def del_mes(acceso: Acceso, engine: Motor, mes: str | None = None) -> ListaGastosOut:
    _exigir(acceso, ROLES_QUE_VEN)
    try:
        with engine.connect() as con:
            return servicio.listar_del_mes(con, acceso.contexto, mes)
    except servicio.MesInvalido:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "El mes debe ser como 2026-11.") from None


@router.get("/gastos/{gasto_id}", response_model=GastoOut, summary="Ver un gasto")
def ver(gasto_id: uuid.UUID, acceso: Acceso, engine: Motor) -> GastoOut:
    _exigir(acceso, ROLES_QUE_VEN)
    try:
        with engine.connect() as con:
            return servicio.obtener_gasto(con, acceso.contexto, gasto_id)
    except servicio.NoEncontrado:
        raise _no_encontrado("ese gasto") from None


@router.patch("/gastos/{gasto_id}", response_model=GastoOut,
              summary="Corregir un gasto (monto, categoría, fecha, medio de pago o nota)")
def corregir(gasto_id: uuid.UUID, cambios: GastoCambios, acceso: Acceso,
             engine: Motor) -> GastoOut:
    _exigir(acceso, ROLES_QUE_ESCRIBEN)
    try:
        with engine.begin() as con:
            return servicio.actualizar_gasto(con, acceso.contexto, gasto_id, cambios)
    except servicio.NoEncontrado:
        raise _no_encontrado("ese gasto") from None
    except servicio.VersionDesfasada:
        raise _DESFASADO from None
    except servicio.CategoriaInvalida:
        raise _categoria_no_existe() from None
    except servicio.FechaFutura:
        raise _fecha_futura() from None


@router.delete("/gastos/{gasto_id}", status_code=status.HTTP_204_NO_CONTENT,
               summary="Archivar un gasto (no se borra)")
def archivar(gasto_id: uuid.UUID, acceso: Acceso, engine: Motor) -> Response:
    _exigir(acceso, ROLES_QUE_ESCRIBEN)
    try:
        with engine.begin() as con:
            servicio.archivar_gasto(con, acceso.contexto, gasto_id)
    except servicio.NoEncontrado:
        raise _no_encontrado("ese gasto") from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
