"""Formas de entrada y salida de /v1/clientes (las validaciones de fondo, en validaciones.py)."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, StringConstraints, field_serializer, field_validator

Nombre = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=120)]
Texto30 = Annotated[str, StringConstraints(strip_whitespace=True, max_length=30)]
Texto120 = Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)]
Texto200 = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
Texto300 = Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)]
TipoFiscal = Literal["CF", "NIT", "CUI"]
TipoCampo = Literal["texto", "numero", "fecha", "si_no"]


class ClienteIn(BaseModel):
    nombre: Nombre
    telefono: Texto30 | None = None
    correo: Texto120 | None = None
    direccion: Texto200 | None = None
    tipo_id_fiscal: TipoFiscal = "CF"
    id_fiscal: Texto30 | None = None
    nombre_fiscal: Texto120 | None = None
    notas: Texto300 | None = None
    datos: dict[str, Any] = Field(default_factory=dict,
                                  description="Campos propios: {campo_id: valor}")
    aunque_se_repita: bool = Field(
        default=False, description="Guardar aunque ya haya un cliente con ese teléfono o NIT.")

    @field_validator("datos", mode="before")
    @classmethod
    def _lista_vacia(cls, v):
        return {} if v == [] else v  # R manda una lista vacía como []


class ClienteCambios(BaseModel):
    """Solo se cambia lo que se envía; `null` borra el dato. `datos` se mezcla con los que había."""

    version: int = Field(ge=1, description="La versión que viste; evita pisar cambios ajenos.")
    nombre: Nombre | None = None
    telefono: Texto30 | None = None
    correo: Texto120 | None = None
    direccion: Texto200 | None = None
    tipo_id_fiscal: TipoFiscal | None = None
    id_fiscal: Texto30 | None = None
    nombre_fiscal: Texto120 | None = None
    notas: Texto300 | None = None
    datos: dict[str, Any] | None = None
    aunque_se_repita: bool = False

    @field_validator("datos", mode="before")
    @classmethod
    def _lista_vacia(cls, v):
        return {} if v == [] else v


class ClienteResumen(BaseModel):
    id: uuid.UUID
    nombre: str
    telefono: str | None
    tipo_id_fiscal: str
    id_fiscal: str | None


class CompraDelCliente(BaseModel):
    venta_id: uuid.UUID
    numero: int
    fecha_hora: datetime  # UTC
    total: Decimal

    @field_serializer("total")
    def _texto(self, v: Decimal) -> str:
        return f"{v:.2f}"


class ComprasDelCliente(BaseModel):
    cantidad: int
    total: Decimal
    ultima: datetime | None
    ultimas: list[CompraDelCliente]

    @field_serializer("total")
    def _texto(self, v: Decimal) -> str:
        return f"{v:.2f}"


class ClienteOut(ClienteResumen):
    correo: str | None
    direccion: str | None
    nombre_fiscal: str | None
    notas: str | None
    datos: dict[str, Any]
    cliente_desde: datetime  # UTC
    version: int
    archivado: bool = False  # sigue con sus ventas; no aparece al vender
    compras: ComprasDelCliente | None = None  # solo en la ficha


class CampoIn(BaseModel):
    id: uuid.UUID | None = Field(default=None, description="Sin id = campo nuevo")
    nombre: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=40)]
    tipo: TipoCampo


class CamposIn(BaseModel):
    campos: Annotated[list[CampoIn], Field(max_length=10)]


class CampoOut(BaseModel):
    id: uuid.UUID
    nombre: str
    tipo: str
    orden: int
