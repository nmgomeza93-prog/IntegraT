"""/v1/insumos y /v1/unidades: lo que el negocio compra y consume. El negocio sale del token."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy.engine import Engine

from integrat.auth.dependencias import AccesoNegocio, acceso_negocio
from integrat.dependencias import obtener_engine
from integrat.insumos import mercaderia, recetas, servicio
from integrat.insumos.esquemas import (
    InsumoCambios,
    InsumoIn,
    InsumoOut,
    ListaInsumosOut,
    ListaMovimientosOut,
    MercaderiaIn,
    MercaderiaOut,
    MovimientoIn,
    MovimientoOut,
    RecetaIn,
    RecetaOut,
    UnidadOut,
)

router = APIRouter(tags=["inventario"])
Motor = Annotated[Engine, Depends(obtener_engine)]
Acceso = Annotated[AccesoNegocio, Depends(acceso_negocio)]

# Existencias y costos no son para todos: el cajero vende, pero no los ve.
ROLES_QUE_VEN = {"dueno", "administrador", "contador"}
ROLES_QUE_ESCRIBEN = {"dueno", "administrador"}

_DESFASADO = HTTPException(
    status.HTTP_409_CONFLICT,
    "Alguien más cambió esto. Ábrelo de nuevo e inténtalo otra vez.",
)


def _exigir(acceso: AccesoNegocio, roles: set[str]) -> None:
    if acceso.rol not in roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No tienes permiso para hacer esto.")


def _no_encontrado() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "No encontramos ese insumo.")


def _unidad_invalida() -> HTTPException:
    return HTTPException(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "Esa unidad no sirve aquí. Usa una del mismo tipo (peso con peso, líquido con líquido).")


def _nombre_repetido() -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, "Ya tienes un insumo con ese nombre.")


@router.get("/unidades", response_model=list[UnidadOut], summary="Unidades de medida disponibles")
def unidades(acceso: Acceso, engine: Motor) -> list[UnidadOut]:
    _exigir(acceso, ROLES_QUE_VEN)
    with engine.connect() as con:
        return servicio.listar_unidades(con)


@router.get("/insumos", response_model=ListaInsumosOut, summary="Mis insumos con su existencia")
def listar(acceso: Acceso, engine: Motor,
           buscar: Annotated[str | None, Query(max_length=80)] = None) -> ListaInsumosOut:
    _exigir(acceso, ROLES_QUE_VEN)
    with engine.connect() as con:
        return servicio.listar_insumos(con, acceso.contexto, buscar)


@router.post("/insumos", response_model=InsumoOut, status_code=status.HTTP_201_CREATED,
             summary="Agregar un insumo (con lo que ya tienes, si quieres)")
def crear(datos: InsumoIn, acceso: Acceso, engine: Motor) -> InsumoOut:
    _exigir(acceso, ROLES_QUE_ESCRIBEN)
    try:
        with engine.begin() as con:
            return servicio.crear_insumo(con, acceso.contexto, datos)
    except servicio.UnidadInvalida:
        raise _unidad_invalida() from None
    except servicio.NombreRepetido:
        raise _nombre_repetido() from None


@router.get("/insumos/{insumo_id}", response_model=InsumoOut, summary="Ver un insumo")
def ver(insumo_id: uuid.UUID, acceso: Acceso, engine: Motor) -> InsumoOut:
    _exigir(acceso, ROLES_QUE_VEN)
    try:
        with engine.connect() as con:
            return servicio.obtener_insumo(con, acceso.contexto, insumo_id)
    except servicio.NoEncontrado:
        raise _no_encontrado() from None


@router.patch("/insumos/{insumo_id}", response_model=InsumoOut,
              summary="Cambiar el nombre o el mínimo de un insumo")
def cambiar(insumo_id: uuid.UUID, cambios: InsumoCambios, acceso: Acceso,
            engine: Motor) -> InsumoOut:
    _exigir(acceso, ROLES_QUE_ESCRIBEN)
    try:
        with engine.begin() as con:
            return servicio.actualizar_insumo(con, acceso.contexto, insumo_id, cambios)
    except servicio.NoEncontrado:
        raise _no_encontrado() from None
    except servicio.VersionDesfasada:
        raise _DESFASADO from None
    except servicio.NombreRepetido:
        raise _nombre_repetido() from None


@router.delete("/insumos/{insumo_id}", status_code=status.HTTP_204_NO_CONTENT,
               summary="Archivar un insumo (sus movimientos se conservan)")
def archivar(insumo_id: uuid.UUID, acceso: Acceso, engine: Motor) -> Response:
    _exigir(acceso, ROLES_QUE_ESCRIBEN)
    try:
        with engine.begin() as con:
            servicio.archivar_insumo(con, acceso.contexto, insumo_id)
    except servicio.NoEncontrado:
        raise _no_encontrado() from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/insumos/{insumo_id}/movimientos", response_model=MovimientoOut,
             status_code=status.HTTP_201_CREATED,
             summary="Anotar una entrada, una merma o corregir la cantidad")
def anotar_movimiento(
    insumo_id: uuid.UUID, datos: MovimientoIn, acceso: Acceso, engine: Motor,
    idempotency_key: Annotated[
        str | None,
        Header(
            min_length=8, max_length=100, pattern=r"^[A-Za-z0-9_.:-]+$",
            description="Clave única por intento (ej. un UUID). Repetirla con los mismos datos "
                        "devuelve el mismo movimiento en lugar de anotarlo otra vez.",
        ),
    ] = None,
) -> MovimientoOut:
    _exigir(acceso, ROLES_QUE_ESCRIBEN)
    try:
        return servicio.registrar_movimiento_idempotente(
            engine, acceso.contexto, insumo_id, datos, idempotency_key)
    except servicio.NoEncontrado:
        raise _no_encontrado() from None
    except servicio.UnidadInvalida:
        raise _unidad_invalida() from None
    except servicio.SinCambio:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "Ya tienes esa cantidad; no hay nada que corregir.") from None
    except servicio.ClaveReutilizada:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "Esa clave ya se usó con otros datos.") from None


@router.get("/insumos/{insumo_id}/movimientos", response_model=ListaMovimientosOut,
            summary="Historial de un insumo (lo más reciente primero)")
def historial(insumo_id: uuid.UUID, acceso: Acceso, engine: Motor) -> ListaMovimientosOut:
    _exigir(acceso, ROLES_QUE_VEN)
    try:
        with engine.connect() as con:
            return servicio.listar_movimientos(con, acceso.contexto, insumo_id)
    except servicio.NoEncontrado:
        raise _no_encontrado() from None


# ------------------------------------------------------------------ recetas

@router.get("/items/{item_id}/receta", response_model=RecetaOut,
            summary="Receta de un producto o platillo, con su costo y margen")
def ver_receta(item_id: uuid.UUID, acceso: Acceso, engine: Motor) -> RecetaOut:
    _exigir(acceso, ROLES_QUE_VEN)
    try:
        with engine.connect() as con:
            return recetas.obtener_receta(con, acceso.contexto, item_id)
    except recetas.ItemNoEncontrado:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontramos eso.") from None


@router.put("/items/{item_id}/receta", response_model=RecetaOut,
            summary="Guardar la receta completa (reemplaza la anterior; vacía la quita)")
def guardar_receta(item_id: uuid.UUID, datos: RecetaIn, acceso: Acceso,
                   engine: Motor) -> RecetaOut:
    _exigir(acceso, ROLES_QUE_ESCRIBEN)
    try:
        with engine.begin() as con:
            return recetas.reemplazar_receta(con, acceso.contexto, item_id, datos)
    except recetas.ItemNoEncontrado:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontramos eso.") from None
    except recetas.InsumoInvalido:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "Uno de los insumos no existe.") from None
    except recetas.InsumoRepetido:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "Un insumo aparece dos veces en la receta.") from None
    except recetas.MercaderiaActiva:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Este producto se compra hecho: su receta se maneja sola. "
            "Quita la mercadería para armar una receta.") from None
    except servicio.UnidadInvalida:
        raise _unidad_invalida() from None


# ------------------------------------------------------------------ mercadería para revender

@router.get("/items/{item_id}/mercaderia", response_model=MercaderiaOut,
            summary="¿Este producto se compra hecho para revenderlo?")
def ver_mercaderia(item_id: uuid.UUID, acceso: Acceso, engine: Motor) -> MercaderiaOut:
    _exigir(acceso, ROLES_QUE_VEN)
    try:
        with engine.connect() as con:
            return mercaderia.obtener(con, acceso.contexto, item_id)
    except mercaderia.ItemNoEncontrado:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontramos eso.") from None


@router.put("/items/{item_id}/mercaderia", response_model=MercaderiaOut,
            summary="Activar o quitar la mercadería de un producto (insumo + receta de 1 unidad)")
def guardar_mercaderia(item_id: uuid.UUID, datos: MercaderiaIn, acceso: Acceso,
                       engine: Motor) -> MercaderiaOut:
    _exigir(acceso, ROLES_QUE_ESCRIBEN)
    try:
        with engine.begin() as con:
            if datos.activa:
                return mercaderia.activar(con, acceso.contexto, item_id)
            return mercaderia.desactivar(con, acceso.contexto, item_id)
    except mercaderia.ItemNoEncontrado:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontramos eso.") from None
    except mercaderia.ConReceta:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Este producto ya tiene una receta. Quítala primero para comprarlo hecho.") from None
