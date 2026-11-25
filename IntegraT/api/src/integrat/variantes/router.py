"""Atributos, categorías sugeridas, atributos por categoría y variantes de un producto.

/v1/atributos, /v1/categorias/sugeridas, /v1/categorias/{id}/atributos, /v1/items/{id}/variantes.
El negocio sale siempre del token.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.engine import Engine

from integrat.auth.dependencias import AccesoNegocio, acceso_negocio
from integrat.dependencias import obtener_engine
from integrat.items import servicio as items
from integrat.items.esquemas import ItemOut
from integrat.variantes import servicio
from integrat.variantes.esquemas import (
    AtributoIn,
    AtributoOut,
    AtributosCategoriaIn,
    CategoriaSugeridaOut,
    ValorIn,
    VariantesIn,
)

router = APIRouter(tags=["variantes"])
Motor = Annotated[Engine, Depends(obtener_engine)]
Acceso = Annotated[AccesoNegocio, Depends(acceso_negocio)]

# Como el catálogo: todos ven; dueño y administrador cambian.
ROLES_QUE_ESCRIBEN = {"dueno", "administrador"}


def _exigir_escritura(acceso: AccesoNegocio) -> None:
    if acceso.rol not in ROLES_QUE_ESCRIBEN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No tienes permiso para hacer esto.")


@router.get("/atributos", response_model=list[AtributoOut],
            summary="Atributos de variante (talla, color…) y sus valores")
def listar(acceso: Acceso, engine: Motor) -> list[AtributoOut]:
    with engine.begin() as con:
        servicio.asegurar_atributos(con, acceso.contexto)
        return servicio.listar_atributos(con, acceso.contexto)


@router.post("/atributos", response_model=AtributoOut, status_code=status.HTTP_201_CREATED,
             summary="Crear un atributo (ej. Material)")
def crear(datos: AtributoIn, acceso: Acceso, engine: Motor) -> AtributoOut:
    _exigir_escritura(acceso)
    try:
        with engine.begin() as con:
            return servicio.crear_atributo(con, acceso.contexto, datos)
    except servicio.NombreRepetido:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Ya tienes un atributo con ese nombre.") from None


@router.post("/atributos/{atributo_id}/valores", response_model=AtributoOut,
             summary="Agregar un valor a un atributo (ej. talla XXL)")
def agregar_valor(atributo_id: uuid.UUID, datos: ValorIn, acceso: Acceso,
                  engine: Motor) -> AtributoOut:
    _exigir_escritura(acceso)
    try:
        with engine.begin() as con:
            return servicio.agregar_valor(con, acceso.contexto, atributo_id, datos.valor)
    except servicio.NoEncontrado:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontramos ese atributo.") from None


@router.get("/categorias/sugeridas", response_model=list[CategoriaSugeridaOut],
            summary="Categorías sugeridas para tu tipo de negocio, con sus atributos")
def sugeridas(acceso: Acceso, engine: Motor) -> list[CategoriaSugeridaOut]:
    with engine.connect() as con:
        return servicio.categorias_sugeridas(con, acceso.contexto)


@router.put("/categorias/{categoria_id}/atributos", response_model=list[str],
            summary="Qué atributos usan los productos de una categoría")
def atributos_de_categoria(categoria_id: uuid.UUID, datos: AtributosCategoriaIn, acceso: Acceso,
                           engine: Motor) -> list[str]:
    _exigir_escritura(acceso)
    try:
        with engine.begin() as con:
            return servicio.fijar_atributos_categoria(con, acceso.contexto, categoria_id,
                                                      datos.atributo_ids)
    except servicio.NoEncontrado:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontramos esa categoría.") from None
    except servicio.AtributoDesconocido:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "Alguno de esos atributos no existe.") from None


@router.put("/items/{item_id}/variantes", response_model=ItemOut,
            summary="Guardar las variantes (tallas, colores…) de un producto")
def guardar_variantes(item_id: uuid.UUID, datos: VariantesIn, acceso: Acceso,
                      engine: Motor) -> ItemOut:
    _exigir_escritura(acceso)
    try:
        with engine.begin() as con:
            servicio.guardar_variantes(con, acceso.contexto, item_id, datos)
            return items.obtener_item(con, acceso.contexto, item_id)
    except servicio.NoEncontrado:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontramos eso.") from None
    except servicio.AtributoDesconocido as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            f"No tienes el atributo «{e.nombre}». Créalo primero.") from None
    except servicio.VarianteRepetida:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "Hay dos variantes iguales.") from None
    except servicio.VarianteInvalida:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "Alguna de esas variantes no es de este producto.") from None
