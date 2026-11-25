"""Formas de entrada y salida de /v1/gastos.

El dinero viaja como texto decimal con 2 decimales ("125.50"), nunca como float.
"""

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints, field_serializer

MedioPago = Literal["efectivo", "tarjeta", "transferencia"]
Monto = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]
NombreCategoria = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=2, max_length=80)
]
Nota = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
Icono = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]


# ------------------------------------------------------------------ categorías

class CategoriaGastoIn(BaseModel):
    nombre: NombreCategoria
    icono: Icono | None = None
    es_fijo: bool = False


class CategoriaGastoCambios(BaseModel):
    version: int = Field(ge=1, description="La versión que viste; evita pisar cambios ajenos.")
    nombre: NombreCategoria | None = None
    icono: Icono | None = None
    es_fijo: bool | None = None


class CategoriaGastoOut(BaseModel):
    id: uuid.UUID
    nombre: str
    icono: str | None
    es_fijo: bool
    orden: int
    version: int


# ------------------------------------------------------------------ gastos

class GastoIn(BaseModel):
    monto: Monto
    categoria_id: uuid.UUID
    medio_pago: MedioPago
    fecha: date | None = Field(default=None, description="Por defecto, hoy en la zona del negocio.")
    descripcion: Nota | None = None
    con_factura: bool = Field(
        default=False, description="Te dieron factura (IVA por cobrar en el régimen general).")


class GastoCambios(BaseModel):
    """Solo se cambia lo que se envía. `descripcion: null` borra la nota."""

    version: int = Field(ge=1, description="La versión que viste; evita pisar cambios ajenos.")
    monto: Monto | None = None
    categoria_id: uuid.UUID | None = None
    medio_pago: MedioPago | None = None
    fecha: date | None = None
    descripcion: Nota | None = None
    con_factura: bool | None = None


class GastoOut(BaseModel):
    id: uuid.UUID
    fecha: date
    monto: Decimal
    categoria_id: uuid.UUID
    categoria_nombre: str
    medio_pago: str
    descripcion: str | None
    es_fijo: bool
    con_factura: bool = False
    version: int

    @field_serializer("monto")
    def _monto_como_texto(self, valor: Decimal) -> str:
        return f"{valor:.2f}"


class ResumenCategoria(BaseModel):
    categoria_id: uuid.UUID
    nombre: str
    total: str
    porcentaje: int  # del total del mes, redondeado


class ResumenGastos(BaseModel):
    cantidad: int
    total: str
    total_fijos: str
    total_variables: str
    por_categoria: list[ResumenCategoria]  # de mayor a menor


class ListaGastosOut(BaseModel):
    mes: str  # AAAA-MM
    resumen: ResumenGastos
    gastos: list[GastoOut]
