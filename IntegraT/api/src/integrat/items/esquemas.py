"""Formas de entrada y salida de /v1/items y /v1/categorias.

El dinero viaja como texto decimal con 2 decimales ("45.00"), nunca como float.
"""

import uuid
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints, field_serializer

from integrat.variantes.esquemas import VarianteOut

NombreItem = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=120)]
NombreCategoria = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=2, max_length=80)
]
Descripcion = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]
Precio = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]
Icono = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
# Margen objetivo entre 0 y 0.9 (90 %), con 4 decimales ("0.3500").
Margen = Annotated[Decimal, Field(ge=0, le=Decimal("0.9"), max_digits=5, decimal_places=4)]


# ------------------------------------------------------------------ categorías

class CategoriaIn(BaseModel):
    nombre: NombreCategoria
    icono: Icono | None = None


class CategoriaCambios(BaseModel):
    version: int = Field(ge=1, description="La versión que viste; evita pisar cambios ajenos.")
    nombre: NombreCategoria | None = None
    icono: Icono | None = None


class CategoriaOut(BaseModel):
    id: uuid.UUID
    nombre: str
    orden: int
    icono: str | None
    cantidad_items: int
    version: int
    atributos: list[str] = []  # qué atributos usan sus productos (ej. Talla, Color)


# ------------------------------------------------------------------ ítems

class ItemIn(BaseModel):
    nombre: NombreItem
    precio_venta: Precio
    categoria_id: uuid.UUID | None = None
    descripcion: Descripcion | None = None


class ItemCambios(BaseModel):
    """Solo se cambia lo que se envía. `categoria_id: null` lo deja sin categoría."""

    version: int = Field(ge=1, description="La versión que viste; evita pisar cambios ajenos.")
    nombre: NombreItem | None = None
    precio_venta: Precio | None = None
    categoria_id: uuid.UUID | None = None
    descripcion: Descripcion | None = None
    margen_objetivo: Margen | None = Field(
        default=None, description="Margen propio para el precio sugerido; null = el del negocio.")


class ItemOut(BaseModel):
    id: uuid.UUID
    tipo_item: str
    nombre: str
    descripcion: str | None
    categoria_id: uuid.UUID | None
    categoria_nombre: str | None
    precio_venta: Decimal
    se_vende: bool
    archivado: bool
    version: int
    aviso: str | None = None  # ej. "Ya tienes un platillo con ese nombre."
    # Precio sugerido (lo calcula la API: integrat.precios). Sin receta con costo: nulos.
    precio_sugerido: str | None = None
    aviso_precio: str | None = None   # "pierde", "bajo", "ok"
    margen_objetivo: str = "0.3500"   # el que se usa (propio o del negocio)
    margen_propio: bool = False
    # Variantes de verdad (talla, color…). Sin variantes: lista vacía y el precio es el del ítem;
    # con variantes, `precio_venta` es el más bajo ("desde").
    tiene_variantes: bool = False
    variantes: list[VarianteOut] = []
    # Inventario: cuánto queda (sumando sus variantes); None = no controla inventario.
    controla_inventario: bool = False
    disponible: int | None = None

    @field_serializer("precio_venta")
    def _precio_como_texto(self, valor: Decimal) -> str:
        return f"{valor:.2f}"


class ListaItemsOut(BaseModel):
    total: int
    items: list[ItemOut]
