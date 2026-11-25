"""Formas de salida de /v1/resultados, /v1/asientos y /v1/cuentas. El dinero viaja como texto."""

import uuid
from datetime import date

from pydantic import BaseModel


class ResultadosOut(BaseModel):
    """El mes en palabras simples, calculado desde los asientos."""

    mes: str                 # AAAA-MM
    vendiste: str            # ventas (sin IVA en el régimen general)
    costo_de_lo_vendido: str
    se_perdio: str           # mermas y faltantes de inventario
    gastaste: str
    otros_ingresos: str
    te_queda: str            # puede ser negativo
    sin_iva: bool            # las cifras de este mes excluyen el IVA (régimen general)


class LineaAsientoOut(BaseModel):
    cuenta_codigo: str
    cuenta_nombre: str
    debe: str
    haber: str


class AsientoOut(BaseModel):
    id: uuid.UUID
    numero: int
    fecha: date
    descripcion: str
    tipo_evento: str
    reverso_de_asiento_id: uuid.UUID | None
    lineas: list[LineaAsientoOut]


class LibroDiarioOut(BaseModel):
    mes: str
    total_debe: str
    total_haber: str
    asientos: list[AsientoOut]


class CuentaOut(BaseModel):
    codigo: str
    nombre: str
    nombre_simple: str | None
    tipo: str
    naturaleza: str
    acepta_movimientos: bool
    rol: str | None
    saldo: str  # según su naturaleza; solo en las cuentas de movimiento


class PlanCuentasOut(BaseModel):
    al: date
    cuentas: list[CuentaOut]
