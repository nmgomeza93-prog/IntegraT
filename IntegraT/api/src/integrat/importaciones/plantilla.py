"""Lector de la plantilla de factura en camino (la de la v1, que el dueño sigue usando).

Hoja `Factura_camino` (o la primera): una fila `ENCABEZADO` con los datos de la factura y una fila
`PRODUCTO` por artículo. Acepta .xlsx y .csv, y los mismos alias de columnas que la v1.
No toca la base de datos: solo convierte el archivo en datos limpios (docs/PLAN_IMPORTACION.md).
"""

import csv
import io
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

MAX_LINEAS = 500
MAX_BYTES = 2 * 1024 * 1024

COLUMNAS = (
    "tipo_registro",
    "proveedor_id",
    "numero_factura",
    "numero_orden_plataforma",
    "plataforma",
    "fecha_factura",
    "moneda_codigo",
    "tipo_cambio",
    "total_factura",
    "garantia_envio",
    "costo_importacion",
    "otros_cobros",
    "skc",
    "cantidad",
    "precio_unitario_fob",
    "descripcion_proveedor",
    "nombre_operativo",
    "talla",
    "color",
    "precio_venta_ref",
)
ALIAS = {
    "tiporegistro": "tipo_registro",
    "tipo": "tipo_registro",
    "proveedor": "proveedor_id",
    "id_proveedor": "proveedor_id",
    "invoice": "numero_factura",
    "invoice_no": "numero_factura",
    "orden": "numero_orden_plataforma",
    "order_number": "numero_orden_plataforma",
    "numero_orden": "numero_orden_plataforma",
    "plataforma_origen": "plataforma",
    "fecha": "fecha_factura",
    "moneda": "moneda_codigo",
    "tc": "tipo_cambio",
    "tipo_de_cambio": "tipo_cambio",
    "grand_total": "total_factura",
    "total": "total_factura",
    "garantia": "garantia_envio",
    "importacion": "costo_importacion",
    "otros": "otros_cobros",
    "precio_fob": "precio_unitario_fob",
    "precio_unitario": "precio_unitario_fob",
    "precio": "precio_unitario_fob",
    "descripcion": "descripcion_proveedor",
    "nombre": "nombre_operativo",
    "nombre_bodega": "nombre_operativo",
    "precio_venta": "precio_venta_ref",
    "peso_kg": "peso",
    "peso_lb": "peso",
    "weight": "peso",
}
# Donde se corta la descripción larga de la plataforma para sugerir un nombre corto.
CORTES = re.compile(r"\s+(con|para|en\s+forma|y\s+pantal)\s+|,|\s-\s", re.IGNORECASE)
MAX_NOMBRE = 60
CONECTORES = {"y", "de", "del", "con", "para", "en", "la", "el", "los", "las", "a", "e"}


class PlantillaInvalida(Exception):
    def __init__(self, errores: list[str]):
        super().__init__("; ".join(errores))
        self.errores = errores


@dataclass
class Encabezado:
    plataforma: str
    numero_factura: str | None
    numero_orden: str | None
    fecha_factura: date | None
    moneda_codigo: str
    tipo_cambio: Decimal | None
    total_factura: Decimal | None
    garantia_envio: Decimal
    costo_importacion: Decimal
    otros_cobros: Decimal


@dataclass
class LineaPlantilla:
    fila: int
    codigo: str | None
    cantidad: int
    precio_unitario: Decimal
    descripcion: str
    nombre: str | None
    talla: str | None
    color: str | None
    precio_venta_ref: Decimal | None
    peso: Decimal | None = None


@dataclass
class Plantilla:
    encabezado: Encabezado
    lineas: list[LineaPlantilla]
    avisos: list[str] = field(default_factory=list)


# ------------------------------------------------------------------ texto y números


def limpiar(valor) -> str | None:
    """Texto sin espacios raros (NBSP de Excel) ni bordes; None si queda vacío."""
    if valor is None:
        return None
    texto = unicodedata.normalize("NFC", str(valor)).replace("\xa0", " ")
    texto = " ".join(texto.split())
    return texto or None


def sin_tildes(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    ).casefold()


def _normalizar_columna(nombre) -> str:
    base = re.sub(r"[^a-z0-9_]", "", re.sub(r"\s+", "_", sin_tildes(str(nombre or "")).strip()))
    return ALIAS.get(base, base)


def _decimal(valor, campo: str, errores: list[str], fila: int) -> Decimal | None:
    texto = limpiar(valor)
    if texto is None:
        return None
    texto = texto.replace("$", "").replace("Q", "").replace(" ", "")
    if texto.count(",") and not texto.count("."):
        texto = texto.replace(",", ".")  # 70,30 -> 70.30
    texto = texto.replace(",", "")  # 2,867.49 -> 2867.49
    try:
        numero = Decimal(texto)
    except InvalidOperation:
        errores.append(f"Fila {fila}: «{campo}» no es un número ({valor}).")
        return None
    if numero < 0:
        errores.append(f"Fila {fila}: «{campo}» no puede ser negativo.")
        return None
    return numero


def _fecha(valor) -> date | None:
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    texto = limpiar(valor)
    if texto is None:
        return None
    for formato in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(texto[:10], formato).date()
        except ValueError:
            continue
    return None


def nombre_sugerido(descripcion: str) -> str:
    """Un nombre corto a partir de la descripción larga de la plataforma.

    "SilkySpell Conjunto de pijama con top de camiseta…" -> "SilkySpell Conjunto de pijama".
    """
    texto = limpiar(descripcion) or "Producto"
    corto = CORTES.split(texto, maxsplit=1)[0].strip(" ,.-/")
    if len(corto) < 8:  # el corte quedó muy corto: mejor las primeras palabras
        corto = " ".join(texto.split()[:6])
    if len(corto) > MAX_NOMBRE:
        corto = corto[:MAX_NOMBRE].rsplit(" ", 1)[0]
    palabras = corto.split()
    while len(palabras) > 2 and palabras[-1].casefold() in CONECTORES:  # "…sexy y" -> "…sexy"
        palabras.pop()
    corto = " ".join(palabras)
    return corto[:1].upper() + corto[1:]


# ------------------------------------------------------------------ leer el archivo


def _filas_xlsx(contenido: bytes) -> list[list]:
    from openpyxl import load_workbook  # solo cuando llega un Excel

    try:
        libro = load_workbook(io.BytesIO(contenido), read_only=True, data_only=True)
    except Exception:  # noqa: BLE001 - cualquier archivo dañado es "no se pudo leer"
        raise PlantillaInvalida(["No pudimos leer el archivo de Excel."]) from None
    hoja = libro["Factura_camino"] if "Factura_camino" in libro.sheetnames else libro.worksheets[0]
    return [list(f) for f in hoja.iter_rows(values_only=True)]


def _filas_csv(contenido: bytes) -> list[list]:
    for codificacion in ("utf-8-sig", "latin-1"):
        try:
            texto = contenido.decode(codificacion)
            break
        except UnicodeDecodeError:
            continue
    delimitador = (
        ";" if texto.split("\n", 1)[0].count(";") > texto.split("\n", 1)[0].count(",") else ","
    )
    return [fila for fila in csv.reader(io.StringIO(texto), delimiter=delimitador)]


def leer(contenido: bytes, nombre_archivo: str) -> Plantilla:
    if len(contenido) > MAX_BYTES:
        raise PlantillaInvalida(["El archivo es muy grande (máximo 2 MB)."])
    nombre = (nombre_archivo or "").lower()
    if nombre.endswith((".xlsx", ".xlsm")):
        filas = _filas_xlsx(contenido)
    elif nombre.endswith((".csv", ".txt")):
        filas = _filas_csv(contenido)
    else:
        raise PlantillaInvalida(["Sube la plantilla en Excel (.xlsx) o CSV."])
    filas = [f for f in filas if any(limpiar(c) for c in f)]
    if not filas:
        raise PlantillaInvalida(["La plantilla está vacía."])
    columnas = [_normalizar_columna(c) for c in filas[0]]
    faltan = [c for c in ("tipo_registro", "cantidad", "precio_unitario_fob") if c not in columnas]
    if faltan:
        raise PlantillaInvalida(
            [f"Faltan columnas: {', '.join(faltan)}. Usa la plantilla de factura."]
        )
    registros = [(i + 2, dict(zip(columnas, f, strict=False))) for i, f in enumerate(filas[1:])]
    return interpretar(registros)


def interpretar(registros: list[tuple[int, dict]]) -> Plantilla:
    errores: list[str] = []
    encabezados = [
        (n, r)
        for n, r in registros
        if (limpiar(r.get("tipo_registro")) or "").upper() == "ENCABEZADO"
    ]
    productos = [
        (n, r)
        for n, r in registros
        if (limpiar(r.get("tipo_registro")) or "").upper() == "PRODUCTO"
    ]
    otros = {limpiar(r.get("tipo_registro")) for _, r in registros} - {
        "ENCABEZADO",
        "PRODUCTO",
        "encabezado",
        "producto",
    }
    if len(encabezados) != 1:
        errores.append(f"Debe haber una sola fila ENCABEZADO (hay {len(encabezados)}).")
    if not productos:
        errores.append("Agrega al menos una fila PRODUCTO.")
    if len(productos) > MAX_LINEAS:
        errores.append(f"Máximo {MAX_LINEAS} productos por plantilla (hay {len(productos)}).")
    if otros - {None}:
        errores.append("tipo_registro solo puede ser ENCABEZADO o PRODUCTO.")
    if errores:
        raise PlantillaInvalida(errores)

    fila_enc, enc = encabezados[0]
    moneda = (limpiar(enc.get("moneda_codigo")) or "USD").upper()
    encabezado = Encabezado(
        plataforma=(limpiar(enc.get("plataforma")) or "otra").lower(),
        numero_factura=limpiar(enc.get("numero_factura")),
        numero_orden=limpiar(enc.get("numero_orden_plataforma")),
        fecha_factura=_fecha(enc.get("fecha_factura")),
        moneda_codigo=moneda,
        tipo_cambio=_decimal(enc.get("tipo_cambio"), "tipo_cambio", errores, fila_enc) or None,
        total_factura=_decimal(enc.get("total_factura"), "total_factura", errores, fila_enc),
        garantia_envio=_decimal(enc.get("garantia_envio"), "garantia_envio", errores, fila_enc)
        or Decimal("0"),
        costo_importacion=_decimal(
            enc.get("costo_importacion"), "costo_importacion", errores, fila_enc
        )
        or Decimal("0"),
        otros_cobros=_decimal(enc.get("otros_cobros"), "otros_cobros", errores, fila_enc)
        or Decimal("0"),
    )
    lineas: list[LineaPlantilla] = []
    for fila, r in productos:
        cantidad = _decimal(r.get("cantidad"), "cantidad", errores, fila)
        precio = _decimal(r.get("precio_unitario_fob"), "precio_unitario_fob", errores, fila)
        descripcion = limpiar(r.get("descripcion_proveedor")) or limpiar(r.get("nombre_operativo"))
        if cantidad is None or cantidad <= 0 or cantidad != int(cantidad):
            errores.append(f"Fila {fila}: la cantidad debe ser un número entero mayor que cero.")
            continue
        if precio is None:
            errores.append(f"Fila {fila}: falta el precio.")
            continue
        if descripcion is None and limpiar(r.get("skc")) is None:
            errores.append(f"Fila {fila}: falta la descripción o el código del producto.")
            continue
        lineas.append(
            LineaPlantilla(
                fila=fila,
                codigo=limpiar(r.get("skc")),
                cantidad=int(cantidad),
                precio_unitario=precio,
                descripcion=descripcion or limpiar(r.get("skc")),
                nombre=limpiar(r.get("nombre_operativo")),
                talla=limpiar(r.get("talla")),
                color=limpiar(r.get("color")),
                precio_venta_ref=_decimal(
                    r.get("precio_venta_ref"), "precio_venta_ref", errores, fila
                ),
                peso=_decimal(r.get("peso"), "peso", errores, fila),
            )
        )
    if errores:
        raise PlantillaInvalida(errores)
    return Plantilla(encabezado=encabezado, lineas=lineas)
