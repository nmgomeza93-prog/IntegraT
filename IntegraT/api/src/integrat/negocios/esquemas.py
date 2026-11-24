"""Formas de entrada y salida de /v1/negocios."""

import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

NombreNegocio = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=2, max_length=120)
]
# "¿Das factura?": sí / no / todavía no sé
DaFactura = Literal["si", "no", "no_se"]


class NegocioIn(BaseModel):
    nombre: NombreNegocio
    tipo_negocio_codigo: Annotated[str, Field(min_length=1, max_length=40)]
    da_factura: DaFactura = "no_se"


class PrimerPaso(BaseModel):
    clave: str
    texto: str
    icono: str
    hecho: bool = False


class NegocioOut(BaseModel):
    id: uuid.UUID
    nombre: str
    tipo_negocio_codigo: str
    pais_codigo: str
    moneda_codigo: str
    zona_horaria: str
    da_factura: DaFactura
    capacidades: list[str]  # solo las activas
    vocabulario: dict[str, str]  # palabras de la interfaz según el tipo
    primeros_pasos: list[PrimerPaso]


class AccesoOut(BaseModel):
    token_type: str = "bearer"  # noqa: S105 - es el tipo de esquema, no un secreto
    access_token: str
    expira_en: int
    negocio_id: uuid.UUID


class NegocioCreadoOut(NegocioOut):
    """Al crear el negocio se entrega un access_token ya atado a él."""

    acceso: AccesoOut
