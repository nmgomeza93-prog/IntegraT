"""Formas de /v1/atributos, /v1/categorias/{id}/atributos y /v1/items/{id}/variantes."""

import uuid
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

Nombre = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
Codigo = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
Precio = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]


class ValorOut(BaseModel):
    id: uuid.UUID
    valor: str


class AtributoOut(BaseModel):
    id: uuid.UUID
    nombre: str
    valores: list[ValorOut]


class AtributoIn(BaseModel):
    nombre: Nombre
    valores: Annotated[list[Nombre], Field(max_length=60)] = []


class ValorIn(BaseModel):
    valor: Nombre


class AtributosCategoriaIn(BaseModel):
    """Atributos que usan los productos de la categoría, en orden (reemplaza a los anteriores)."""

    atributo_ids: Annotated[list[uuid.UUID], Field(max_length=5)]


class CategoriaSugeridaOut(BaseModel):
    nombre: str
    icono: str | None
    atributos: list[str]
    palabras_clave: list[str]


class VarianteIn(BaseModel):
    id: uuid.UUID | None = Field(default=None, description="Para cambiar una que ya existe.")
    atributos: Annotated[dict[Nombre, Nombre], Field(min_length=1, max_length=5)] = Field(
        description='Ej. {"Talla": "M", "Color": "Rosa"}')
    codigo: Codigo | None = None
    precio_venta: Precio


class VariantesIn(BaseModel):
    """Todas las variantes del producto (reemplaza a las de antes). Lista vacía = sin variantes."""

    variantes: Annotated[list[VarianteIn], Field(max_length=200)]


class VarianteOut(BaseModel):
    id: uuid.UUID
    nombre: str
    atributos: dict[str, str]
    codigo: str | None
    precio_venta: str
    precio_sugerido: str | None = None
    aviso_precio: str | None = None
    disponible: int | None = None  # cuánto queda; None = no controla inventario
