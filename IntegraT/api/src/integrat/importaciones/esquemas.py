"""Formas de /v1/importaciones. El dinero viaja como texto decimal; las monedas, como su código."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

Texto = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Corto = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
Nota = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
Monto = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=4)]
Dinero = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]
MedioPago = Literal["efectivo", "tarjeta", "transferencia"]


# ------------------------------------------------------------------ vista previa (no guarda nada)


class LineaPrevia(BaseModel):
    fila: int
    codigo: str | None
    descripcion: str
    atributos: dict[str, str]  # solo los que usa la categoría (ej. Talla y Color)
    cantidad: int
    precio_unitario: str  # en la moneda de la factura
    peso: str | None = None  # de la plantilla (para repartir el courier por peso)
    item_variante_id: uuid.UUID | None = None  # si esa variante ya existe


class ProductoPrevio(BaseModel):
    nombre: str  # sugerido (editable)
    categoria: str | None  # sugerida (editable)
    item_id: uuid.UUID | None = None  # si el producto ya existe
    existente: bool = False
    lineas: list[LineaPrevia]


class Cuadre(BaseModel):
    lineas: str
    cargos: str
    total_calculado: str
    total_factura: str | None
    diferencia: str | None
    cuadra: bool


class EncabezadoPrevio(BaseModel):
    plataforma: str
    numero_factura: str | None
    numero_orden: str | None
    fecha_factura: date | None
    moneda_codigo: str
    moneda_conocida: bool
    tipo_cambio: str | None
    total_factura: str | None
    garantia_envio: str
    costo_importacion: str
    otros_cobros: str


class VistaPreviaOut(BaseModel):
    encabezado: EncabezadoPrevio
    cuadre: Cuadre
    productos: list[ProductoPrevio]
    unidades: int
    avisos: list[str]


# ------------------------------------------------------------------ confirmar (queda en camino)


class LineaIn(BaseModel):
    codigo: Annotated[str, StringConstraints(strip_whitespace=True, max_length=60)] | None = None
    descripcion: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = (
        None
    )
    atributos: Annotated[dict[Corto, Corto], Field(max_length=5)] = {}
    cantidad: Annotated[int, Field(ge=1, le=9999)]
    precio_unitario: Monto
    item_variante_id: uuid.UUID | None = None
    peso: Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=3)] | None = None


class ProductoIn(BaseModel):
    nombre: Texto
    categoria: Corto | None = None
    item_id: uuid.UUID | None = None
    lineas: Annotated[list[LineaIn], Field(min_length=1, max_length=200)]


class ImportacionIn(BaseModel):
    plataforma: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30)
    ]
    numero_factura: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=60)] | None
    ) = None
    numero_orden: Annotated[str, StringConstraints(strip_whitespace=True, max_length=60)] | None = (
        None
    )
    fecha_factura: date | None = None
    moneda_codigo: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=3, max_length=3, to_upper=True)
    ]
    garantia_envio: Monto = Decimal("0")
    costo_importacion: Monto = Decimal("0")
    otros_cobros: Monto = Decimal("0")
    cobro_q: Dinero | None = Field(default=None, description="Lo que te cobró la tarjeta en Q.")
    tipo_cambio: Annotated[Decimal, Field(gt=0, max_digits=18, decimal_places=8)] | None = None
    medio_pago: MedioPago = "tarjeta"
    nota: Nota | None = None
    productos: Annotated[list[ProductoIn], Field(min_length=1, max_length=500)]


class RecibirLineaIn(BaseModel):
    linea_id: uuid.UUID
    cantidad: Annotated[int, Field(ge=0, le=9999)] = Field(
        description="Lo que llegó en esta entrega."
    )


class RecibirIn(BaseModel):
    """Una entrega. Sin `lineas`, llegó todo lo que faltaba."""

    courier_q: Dinero = Decimal("0")
    envio_local_q: Dinero = Decimal("0")
    medio_pago: MedioPago = "efectivo"
    guia: Annotated[str, StringConstraints(strip_whitespace=True, max_length=60)] | None = None
    lineas: Annotated[list[RecibirLineaIn], Field(max_length=500)] | None = Field(
        default=None, description="Lo que llegó de cada línea; sin esto, todo lo pendiente."
    )
    cerrar: bool = Field(
        default=False, description="Lo que todavía falta ya no va a llegar: se da por perdido."
    )
    reparto: Literal["valor", "peso"] = "valor"


class AnularIn(BaseModel):
    motivo: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=200)]


# ------------------------------------------------------------------ salida


class LineaOut(BaseModel):
    id: uuid.UUID
    nombre: str  # "Producto · M · Rosa"
    codigo: str | None
    atributos: dict[str, str]
    item_id: uuid.UUID | None
    item_variante_id: uuid.UUID | None
    cantidad: int
    precio_unitario: str  # moneda de la factura
    costo_pedido_q: str  # su parte de la factura en Q
    cantidad_recibida: int | None
    cantidad_perdida: int | None = None
    pendiente: int = 0
    peso: str | None = None
    courier_q: str | None
    costo_unitario_q: str | None  # puesto en Guatemala
    precio_sugerido: str | None = None


class EntregaOut(BaseModel):
    numero: int
    recibida_en: datetime
    guia: str | None
    courier_q: str
    envio_local_q: str
    reparto: str
    cierra: bool
    unidades: int


class ImportacionOut(BaseModel):
    id: uuid.UUID
    plataforma: str
    numero_factura: str | None
    numero_orden: str | None
    fecha_factura: date | None
    moneda_codigo: str
    total_factura: str  # moneda de la factura (líneas + cargos)
    tipo_cambio: str
    total_q: str
    medio_pago: str
    estado: str
    creada_en: datetime
    recibida_en: datetime | None
    guia: str | None
    courier_q: str | None
    envio_local_q: str | None
    nota: str | None
    motivo_anulacion: str | None
    unidades: int
    dias_en_camino: int
    pendientes: int = 0
    entregas: list[EntregaOut] = []
    lineas: list[LineaOut] = []


class ListaImportacionesOut(BaseModel):
    en_camino: list[ImportacionOut]
    recibidas: list[ImportacionOut]
