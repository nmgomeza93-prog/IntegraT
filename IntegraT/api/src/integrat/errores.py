"""Errores de validación en palabras de la persona: qué dato revisar y por qué.

FastAPI responde por defecto con una lista técnica (loc, type, msg) que la app no puede mostrar.
Aquí se convierte en un texto como "Revisa el nombre: escribe al menos 2 letras."
"""

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

# Nombre de cada campo tal como lo ve la persona. Lo que no está aquí se nombra genérico.
CAMPOS = {
    "nombre": "el nombre", "telefono": "el teléfono", "correo": "el correo",
    "direccion": "la dirección", "tipo_id_fiscal": "el tipo de factura",
    "id_fiscal": "el NIT o CUI", "nombre_fiscal": "el nombre en la factura", "notas": "las notas",
    "datos": "los datos propios", "campos": "los datos que pides", "tipo": "el tipo",
    "precio_venta": "el precio", "cantidad": "la cantidad", "monto": "el monto",
    "costo_total": "el costo", "medio_pago": "cómo paga", "fecha": "la fecha",
    "motivo": "el motivo", "descripcion": "la descripción", "clave": "la contraseña",
    "version": "la versión", "lineas": "lo que agregaste", "unidad_codigo": "la unidad",
    "stock_minimo": "el mínimo", "minimo_defecto": "el mínimo", "margen_objetivo": "el margen",
}


def _campo(loc: tuple) -> str:
    for parte in reversed(loc):
        if isinstance(parte, str) and parte not in ("body", "query", "path", "header"):
            return CAMPOS.get(parte, "un dato")
    return "los datos"


def _por_que(error: dict) -> str:
    tipo, ctx = error.get("type", ""), error.get("ctx") or {}
    if tipo == "missing":
        return "falta"
    if tipo == "string_too_short":
        minimo = ctx.get("min_length", 1)
        return "está vacío" if minimo <= 1 else f"escribe al menos {minimo} letras"
    if tipo == "string_too_long":
        return f"máximo {ctx.get('max_length')} letras"
    if tipo in ("too_short", "too_long"):
        return "revisa cuántos agregaste"
    if tipo in ("greater_than", "greater_than_equal"):
        return "debe ser mayor" + (" que 0" if str(ctx.get("gt", ctx.get("ge"))) == "0" else "")
    if tipo in ("less_than", "less_than_equal", "decimal_max_digits", "decimal_whole_digits"):
        return "es demasiado grande"
    if tipo == "decimal_max_places":
        return f"usa máximo {ctx.get('decimal_places')} decimales"
    if tipo in ("decimal_parsing", "float_parsing", "int_parsing", "decimal_type", "int_type"):
        return "debe ser un número"
    if tipo in ("date_parsing", "date_from_datetime_parsing", "date_type"):
        return "debe ser una fecha"
    if tipo in ("literal_error", "enum"):
        return "elige una de las opciones"
    if tipo == "uuid_parsing":
        return "ya no existe; abre la pantalla de nuevo"
    return "no es válido"


def mensaje_validacion(errores: list[dict]) -> str:
    if not errores:
        return "Revisa los datos e intenta de nuevo."
    primero = errores[0]
    return f"Revisa {_campo(tuple(primero.get('loc', ())))}: {_por_que(primero)}."


async def manejar_validacion(_: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                        content={"detail": mensaje_validacion(list(exc.errors()))})
