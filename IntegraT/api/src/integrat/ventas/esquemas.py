"""Formas de entrada y salida de /v1/ventas.

La app NO envía precios ni totales: solo qué se vendió y cómo se pagó. La API calcula el total
con el precio vigente y lo congela. El dinero viaja como texto con 2 decimales.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints, field_serializer

MedioPago = Literal["efectivo", "tarjeta", "transferencia"]
MEDIOS_PAGO: tuple[str, ...] = ("efectivo", "tarjeta", "transferencia")


class LineaIn(BaseModel):
    item_id: uuid.UUID
    item_variante_id: uuid.UUID | None = Field(
        default=None, description="Obligatoria si el producto tiene variantes (talla, color…).")
    cantidad: Annotated[int, Field(ge=1, le=999)]


class VentaIn(BaseModel):
    lineas: Annotated[list[LineaIn], Field(min_length=1, max_length=50)]
    medio_pago: MedioPago


class AnularIn(BaseModel):
    motivo: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=200)]


class _Dinero(BaseModel):
    @field_serializer("*", mode="wrap")
    def _dinero_como_texto(self, valor, siguiente, info):
        if isinstance(valor, Decimal):
            return f"{valor:.2f}"
        return siguiente(valor)


class LineaOut(_Dinero):
    item_id: uuid.UUID
    item_variante_id: uuid.UUID | None = None
    nombre: str
    cantidad: int
    precio_unitario: Decimal
    total: Decimal


class VentaOut(_Dinero):
    id: uuid.UUID
    numero: int
    fecha_hora: datetime  # UTC
    estado: str
    total: Decimal
    moneda_codigo: str
    medio_pago: str
    lineas: list[LineaOut]
    anulada_en: datetime | None = None
    motivo_anulacion: str | None = None
    insumos_en_falta: list[str] = []  # solo al cobrar: insumos que se acabaron con esta venta


class ResumenOut(BaseModel):
    cantidad: int  # ventas vigentes (sin anuladas)
    total: str
    por_medio: dict[str, str]


class ListaVentasOut(BaseModel):
    fecha: date  # el día consultado, en la zona horaria del negocio
    resumen: ResumenOut
    ventas: list[VentaOut]
