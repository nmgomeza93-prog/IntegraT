"""Formas de entrada y salida de /v1/compras y /v1/proveedores.

La app NO envía totales: solo qué se compró, cuánto costó cada línea y cómo se pagó. La API suma el
total. El dinero viaja como texto con 2 decimales y las cantidades como texto decimal.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints, model_validator

MedioPago = Literal["efectivo", "tarjeta", "transferencia"]
Nombre = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=120)]
Telefono = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=30)]
Nota = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
Factura = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
Codigo = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10)]
CantidadPositiva = Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=4)]
Dinero = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]


# ------------------------------------------------------------------ proveedores

class ProveedorIn(BaseModel):
    nombre: Nombre
    telefono: Telefono | None = None


class ProveedorCambios(BaseModel):
    """Solo se cambia lo que se envía. `telefono: null` borra el teléfono."""

    version: int = Field(ge=1, description="La versión que viste; evita pisar cambios ajenos.")
    nombre: Nombre | None = None
    telefono: Telefono | None = None


class ProveedorOut(BaseModel):
    id: uuid.UUID
    nombre: str
    telefono: str | None
    version: int


# ------------------------------------------------------------------ compras

class CompraLineaIn(BaseModel):
    insumo_id: uuid.UUID
    cantidad: CantidadPositiva
    unidad_codigo: Codigo | None = Field(
        default=None, description="Por defecto, la unidad del insumo; otra del mismo tipo sirve.")
    costo_total: Dinero = Field(description="Lo que costó TODA esta línea, no por unidad.")


class CompraIn(BaseModel):
    lineas: Annotated[list[CompraLineaIn], Field(min_length=1, max_length=50)]
    medio_pago: MedioPago
    fecha: date | None = Field(default=None, description="Por defecto, hoy en la zona del negocio.")
    proveedor_id: uuid.UUID | None = None
    proveedor_nuevo: ProveedorIn | None = Field(
        default=None,
        description="Crea el proveedor al registrar la compra (o usa el que ya exista).")
    numero_factura: Factura | None = None
    nota: Nota | None = None

    @model_validator(mode="after")
    def _un_solo_proveedor(self):
        if self.proveedor_id is not None and self.proveedor_nuevo is not None:
            raise ValueError("Elige un proveedor existente o crea uno nuevo, no los dos.")
        return self


class AnularIn(BaseModel):
    motivo: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=200)]


class CompraLineaOut(BaseModel):
    insumo_id: uuid.UUID
    nombre: str
    cantidad: str
    unidad_codigo: str
    costo_total: str


class CompraOut(BaseModel):
    id: uuid.UUID
    fecha: date
    proveedor_id: uuid.UUID | None
    proveedor_nombre: str | None
    numero_factura: str | None
    medio_pago: str
    total: str
    estado: str
    nota: str | None
    lineas: list[CompraLineaOut]
    anulada_en: datetime | None = None
    motivo_anulacion: str | None = None


class ResumenCompras(BaseModel):
    cantidad: int       # compras vigentes (sin anuladas)
    total: str


class ListaComprasOut(BaseModel):
    mes: str            # AAAA-MM
    resumen: ResumenCompras
    compras: list[CompraOut]
