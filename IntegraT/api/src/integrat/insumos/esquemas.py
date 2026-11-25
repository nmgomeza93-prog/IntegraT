"""Formas de entrada y salida de /v1/insumos.

Las cantidades y los costos viajan como texto decimal, nunca como float. La API guarda todo en la
unidad base (UN, G o ML) y devuelve las cantidades en la unidad de uso del insumo.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints, model_validator

Nombre = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=80)]
Nota = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
Codigo = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10)]
CantidadPositiva = Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=4)]
CantidadNoNegativa = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=4)]
Dinero = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]


class UnidadOut(BaseModel):
    codigo: str
    nombre: str
    tipo: str  # unidad, masa o volumen: solo se convierte dentro del mismo tipo


# ------------------------------------------------------------------ insumos

class InsumoIn(BaseModel):
    nombre: Nombre
    unidad_codigo: Codigo
    stock_minimo: CantidadNoNegativa | None = Field(
        default=None, description="Debajo de esta cantidad avisamos 'te queda poco'.")
    existencia_inicial: CantidadPositiva | None = Field(
        default=None, description="Lo que ya tienes hoy, en la unidad del insumo.")
    costo_total_inicial: Dinero | None = Field(
        default=None, description="Lo que te costó lo que ya tienes (total, no por unidad).")

    @model_validator(mode="after")
    def _costo_si_hay_existencia(self):
        if self.existencia_inicial is not None and self.costo_total_inicial is None:
            raise ValueError("Dinos cuánto te costó lo que ya tienes.")
        if self.existencia_inicial is None and self.costo_total_inicial is not None:
            raise ValueError("Dinos cuánto tienes para guardar su costo.")
        return self


class InsumoCambios(BaseModel):
    """Solo se cambia lo que se envía. La unidad no se cambia: rompería los costos."""

    version: int = Field(ge=1, description="La versión que viste; evita pisar cambios ajenos.")
    nombre: Nombre | None = None
    stock_minimo: CantidadNoNegativa | None = None


class InsumoOut(BaseModel):
    id: uuid.UUID
    nombre: str
    unidad_codigo: str
    unidad_nombre: str
    existencia: str          # en la unidad de uso, puede ser negativa
    costo_unitario: str      # costo promedio por unidad de uso
    valor: str               # existencia × costo promedio, 2 decimales
    stock_minimo: str
    estado: Literal["ok", "poco", "falta"]
    item_id: uuid.UUID | None = None   # si es la mercadería de un producto, cuál
    version: int


class ListaInsumosOut(BaseModel):
    total: int
    valor_inventario: str
    por_reponer: int         # los que están en "poco" o "falta"
    insumos: list[InsumoOut]


# ------------------------------------------------------------------ movimientos

class MovimientoIn(BaseModel):
    """Entrada = compraste o recibiste · merma = se perdió · ajuste = cuántos hay de verdad."""

    tipo: Literal["entrada", "merma", "ajuste"]
    cantidad: CantidadNoNegativa = Field(
        description="Entrada y merma: cuánto. Ajuste: cuánto hay realmente ahora.")
    unidad_codigo: Codigo | None = Field(
        default=None, description="Por defecto, la unidad del insumo; otra del mismo tipo sirve.")
    costo_total: Dinero | None = Field(
        default=None, description="Solo en entradas: lo que costó todo lo que entró.")
    nota: Nota | None = None

    @model_validator(mode="after")
    def _coherente(self):
        if self.tipo != "ajuste" and self.cantidad <= 0:
            raise ValueError("La cantidad debe ser mayor que 0.")
        if self.tipo == "entrada" and self.costo_total is None:
            raise ValueError("Dinos cuánto costó lo que entró.")
        if self.tipo != "entrada" and self.costo_total is not None:
            raise ValueError("El costo solo se indica en las entradas.")
        return self


class MovimientoOut(BaseModel):
    id: uuid.UUID
    tipo: str
    cantidad: str            # con signo, en la unidad del insumo
    costo_unitario: str
    fecha_hora: datetime     # UTC
    nota: str | None
    insumo: InsumoOut | None = None   # cómo quedó el insumo (solo al registrar)


class ListaMovimientosOut(BaseModel):
    movimientos: list[MovimientoOut]


# ------------------------------------------------------------------ recetas

class RecetaLineaIn(BaseModel):
    insumo_id: uuid.UUID
    cantidad: CantidadPositiva = Field(description="Lo que lleva UNA unidad vendida.")
    unidad_codigo: Codigo | None = Field(
        default=None, description="Por defecto, la unidad del insumo; otra del mismo tipo sirve.")


class RecetaIn(BaseModel):
    """La receta completa: reemplaza a la anterior. Una lista vacía la quita."""

    lineas: Annotated[list[RecetaLineaIn], Field(max_length=30)]


class RecetaLineaOut(BaseModel):
    insumo_id: uuid.UUID
    insumo_nombre: str
    archivado: bool          # el insumo se archivó: ya no se descuenta
    cantidad: str
    unidad_codigo: str
    unidad_nombre: str
    costo: str               # lo que cuesta esta línea por unidad vendida, 2 decimales
    sin_costo: bool          # el insumo aún no tiene costo (nunca entró con precio)


class RecetaOut(BaseModel):
    item_id: uuid.UUID
    item_nombre: str
    tiene_receta: bool
    lineas: list[RecetaLineaOut]
    costo_total: str         # por unidad vendida
    costo_completo: bool     # falso si a algún insumo le falta costo: el total se queda corto
    precio_venta: str | None
    margen: str | None       # precio − costo
    margen_porcentaje: int | None   # del precio, redondeado


# ------------------------------------------------------------------ mercadería para revender

class MercaderiaIn(BaseModel):
    activa: bool = Field(description="Lo compro ya hecho para revenderlo.")


class MercaderiaOut(BaseModel):
    activa: bool
    insumo: InsumoOut | None   # el insumo ligado al producto (existencia y costo)
