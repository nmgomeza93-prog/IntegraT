"""Formas de entrada y salida de /v1/negocios."""

import uuid
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

NombreNegocio = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=2, max_length=120)
]
# "¿Das factura?": sí / no / todavía no sé
DaFactura = Literal["si", "no", "no_se"]
# Régimen de IVA en palabras simples (docs/PLAN_CONTABILIDAD.md). [verificar con el contador]
RegimenIva = Literal["general", "pequeno", "no_se"]


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
    regimen_iva: RegimenIva = "no_se"
    margen_objetivo: str = "0.3500"  # margen objetivo del negocio (precio sugerido y meta)
    vender_sin_existencia: Literal["bloquear", "avisar"] = "avisar"
    minimo_defecto: str = "0.00"  # unidades con que la mercadería nueva avisa "por agotarse"
    telefono: str | None = None   # normalizado: +50255551234
    correo: str | None = None
    direccion: str | None = None
    nit: str | None = None        # del titular, sin guion
    nombre_fiscal: str | None = None
    capacidades: list[str]  # solo las activas
    vocabulario: dict[str, str]  # palabras de la interfaz según el tipo
    primeros_pasos: list[PrimerPaso]


class DatosNegocioIn(BaseModel):
    """Mi negocio. Solo cambia lo que se envía; null lo borra. NIT y nombre fiscal: el dueño."""

    nombre: NombreNegocio | None = None
    telefono: Annotated[str, StringConstraints(strip_whitespace=True, max_length=30)] | None = None
    correo: Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)] | None = None
    direccion: Annotated[str, StringConstraints(strip_whitespace=True,
                                                max_length=255)] | None = None
    nit: Annotated[str, StringConstraints(strip_whitespace=True, max_length=20)] | None = None
    nombre_fiscal: Annotated[str, StringConstraints(strip_whitespace=True,
                                                    max_length=200)] | None = None


class ReglasVentaIn(BaseModel):
    vender_sin_existencia: Literal["bloquear", "avisar"]
    minimo_defecto: Annotated[Decimal, Field(ge=0, max_digits=10, decimal_places=2)] | None = None
    aplicar_a_todos: bool = Field(
        default=False, description="Poner ese mínimo también a la mercadería que ya existe.")


class PreciosIn(BaseModel):
    margen_objetivo: Annotated[Decimal, Field(ge=0, le=Decimal("0.9"), max_digits=5,
                                              decimal_places=4)]


class ImpuestosIn(BaseModel):
    regimen_iva: RegimenIva


class AccesoOut(BaseModel):
    token_type: str = "bearer"  # noqa: S105 - es el tipo de esquema, no un secreto
    access_token: str
    expira_en: int
    negocio_id: uuid.UUID


class NegocioCreadoOut(NegocioOut):
    """Al crear el negocio se entrega un access_token ya atado a él."""

    acceso: AccesoOut
