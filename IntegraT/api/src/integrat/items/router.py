"""/v1/items y /v1/categorias: catálogo de productos y platillos del negocio del token."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy.engine import Engine

from integrat.auth.dependencias import AccesoNegocio, acceso_negocio
from integrat.dependencias import obtener_engine
from integrat.items import servicio
from integrat.items.esquemas import (
    CategoriaCambios,
    CategoriaIn,
    CategoriaOut,
    ItemCambios,
    ItemIn,
    ItemOut,
    ListaItemsOut,
)

router = APIRouter(tags=["catálogo"])
Motor = Annotated[Engine, Depends(obtener_engine)]
Acceso = Annotated[AccesoNegocio, Depends(acceso_negocio)]

ROLES_QUE_EDITAN = {"dueno", "administrador"}


def _puede_editar(acceso: AccesoNegocio) -> None:
    if acceso.rol not in ROLES_QUE_EDITAN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No tienes permiso para cambiar esto.")


def _no_encontrado(que: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"No encontramos {que}.")


_DESFASADA = HTTPException(
    status.HTTP_409_CONFLICT,
    "Alguien más cambió esto. Ábrelo de nuevo e inténtalo otra vez.",
)


# ------------------------------------------------------------------ categorías

@router.get("/categorias", response_model=list[CategoriaOut], summary="Mis categorías")
def listar_categorias(acceso: Acceso, engine: Motor) -> list[CategoriaOut]:
    with engine.begin() as con:
        servicio.asegurar_categorias_de_ejemplo(con, acceso.contexto)
        return servicio.listar_categorias(con, acceso.contexto)


@router.post("/categorias", response_model=CategoriaOut, status_code=status.HTTP_201_CREATED,
             summary="Crear una categoría")
def crear_categoria(datos: CategoriaIn, acceso: Acceso, engine: Motor) -> CategoriaOut:
    _puede_editar(acceso)
    try:
        with engine.begin() as con:
            return servicio.crear_categoria(con, acceso.contexto, datos)
    except servicio.NombreRepetido:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Ya tienes una categoría con ese nombre.") from None


@router.patch("/categorias/{categoria_id}", response_model=CategoriaOut,
              summary="Cambiar una categoría")
def cambiar_categoria(categoria_id: uuid.UUID, cambios: CategoriaCambios, acceso: Acceso,
                      engine: Motor) -> CategoriaOut:
    _puede_editar(acceso)
    try:
        with engine.begin() as con:
            return servicio.actualizar_categoria(con, acceso.contexto, categoria_id, cambios)
    except servicio.NoEncontrado:
        raise _no_encontrado("esa categoría") from None
    except servicio.VersionDesfasada:
        raise _DESFASADA from None
    except servicio.NombreRepetido:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Ya tienes una categoría con ese nombre.") from None


@router.delete("/categorias/{categoria_id}", status_code=status.HTTP_204_NO_CONTENT,
               summary="Archivar una categoría (sus ítems quedan sin categoría)")
def archivar_categoria(categoria_id: uuid.UUID, acceso: Acceso, engine: Motor) -> Response:
    _puede_editar(acceso)
    try:
        with engine.begin() as con:
            servicio.archivar_categoria(con, acceso.contexto, categoria_id)
    except servicio.NoEncontrado:
        raise _no_encontrado("esa categoría") from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------------------------ ítems

@router.get("/items", response_model=ListaItemsOut, summary="Mis productos o platillos")
def listar_items(
    acceso: Acceso, engine: Motor,
    categoria_id: uuid.UUID | None = None,
    buscar: Annotated[str | None, Query(max_length=120)] = None,
    archivados: bool = False,
    limite: Annotated[int, Query(ge=1, le=200)] = 50,
    desplazar: Annotated[int, Query(ge=0)] = 0,
) -> ListaItemsOut:
    with engine.connect() as con:
        return servicio.listar_items(
            con, acceso.contexto, categoria_id=categoria_id, buscar=buscar,
            archivados=archivados, limite=limite, desplazar=desplazar,
        )


@router.post("/items", response_model=ItemOut, status_code=status.HTTP_201_CREATED,
             summary="Agregar un producto o platillo (nombre y precio)")
def crear_item(
    datos: ItemIn, acceso: Acceso, engine: Motor,
    idempotency_key: Annotated[
        str | None,
        Header(
            min_length=8, max_length=100, pattern=r"^[A-Za-z0-9_.:-]+$",
            description="Clave única por intento (ej. un UUID). Repetirla con los mismos datos "
                        "devuelve el mismo ítem en lugar de crear otro.",
        ),
    ] = None,
) -> ItemOut:
    _puede_editar(acceso)
    try:
        return servicio.crear_item_idempotente(engine, acceso.contexto, datos, idempotency_key)
    except servicio.CategoriaInvalida:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "Esa categoría no existe.") from None
    except servicio.ClaveReutilizada:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "Esa clave ya se usó con otros datos.") from None


@router.get("/items/{item_id}", response_model=ItemOut, summary="Ver un producto o platillo")
def ver_item(item_id: uuid.UUID, acceso: Acceso, engine: Motor) -> ItemOut:
    try:
        with engine.connect() as con:
            return servicio.obtener_item(con, acceso.contexto, item_id)
    except servicio.NoEncontrado:
        raise _no_encontrado("eso") from None


@router.patch("/items/{item_id}", response_model=ItemOut,
              summary="Cambiar nombre, precio, categoría o descripción")
def cambiar_item(item_id: uuid.UUID, cambios: ItemCambios, acceso: Acceso,
                 engine: Motor) -> ItemOut:
    _puede_editar(acceso)
    try:
        with engine.begin() as con:
            return servicio.actualizar_item(con, acceso.contexto, item_id, cambios)
    except servicio.NoEncontrado:
        raise _no_encontrado("eso") from None
    except servicio.VersionDesfasada:
        raise _DESFASADA from None
    except servicio.CategoriaInvalida:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "Esa categoría no existe.") from None


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT,
               summary="Archivar un producto o platillo (no se borra)")
def archivar_item(item_id: uuid.UUID, acceso: Acceso, engine: Motor) -> Response:
    _puede_editar(acceso)
    try:
        with engine.begin() as con:
            servicio.archivar_item(con, acceso.contexto, item_id)
    except servicio.NoEncontrado:
        raise _no_encontrado("eso") from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
