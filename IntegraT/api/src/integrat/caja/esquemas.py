"""Formas de entrada y salida de /v1/caja y /v1/dueno. El dinero viaja como texto decimal."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

Dinero = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]
Monto = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]
Nota = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
TipoDueno = Literal["aporte", "retiro"]
MedioDueno = Literal["efectivo", "banco"]


# ------------------------------------------------------------------ caja

class AbrirCajaIn(BaseModel):
    monto_apertura: Dinero


class CerrarCajaIn(BaseModel):
    efectivo_contado: Dinero
    nota: Nota | None = None


class ResumenCajaOut(BaseModel):
    """Cómo se movió el efectivo (entradas +, salidas -) y lo vendido que no pasó por caja."""

    ventas: str
    gastos: str
    compras: str
    inventario: str
    dueno: str
    otros: str
    cantidad_ventas: int
    ventas_tarjeta: str
    ventas_transferencia: str


class SesionCajaOut(BaseModel):
    id: uuid.UUID
    fecha: date
    abierta_en: datetime
    monto_apertura: str
    estado: str
    efectivo_esperado: str  # en vivo mientras está abierta; congelado al cerrar
    efectivo_contado: str | None
    diferencia: str | None  # contado - esperado: negativo = faltó, positivo = sobró
    cerrada_en: datetime | None
    nota: str | None
    resumen: ResumenCajaOut


class CajaOut(BaseModel):
    abierta: SesionCajaOut | None
    ultimo_cierre: SesionCajaOut | None


class ListaCierresOut(BaseModel):
    mes: str
    cierres: list[SesionCajaOut]


# ------------------------------------------------------------------ dueño

class MovimientoDuenoIn(BaseModel):
    tipo: TipoDueno
    monto: Monto
    medio: MedioDueno
    fecha: date | None = Field(default=None, description="Por defecto, hoy en la zona del negocio.")
    nota: Nota | None = None


class MovimientoDuenoOut(BaseModel):
    id: uuid.UUID
    tipo: str
    monto: str
    medio: str
    fecha: date
    nota: str | None


class ListaDuenoOut(BaseModel):
    mes: str
    total_aportes: str
    total_retiros: str
    movimientos: list[MovimientoDuenoOut]
