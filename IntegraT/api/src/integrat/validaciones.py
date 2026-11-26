"""Validaciones de contacto y fiscales (clientes y negocio); las aplica la API, no la app.

Reglas de NIT y CUI de Guatemala: [verificar con el contador / SAT] (docs/REVISION_CONTADOR.md).
"""

import re
from datetime import date
from decimal import Decimal, InvalidOperation


class DatoInvalido(ValueError):
    """Un dato del cliente no es válido; el mensaje se muestra tal cual al usuario."""


_SEPARADORES = re.compile(r"[\s\-().]")
_CORREO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")

# Municipios por departamento (CUI: dígitos 10-11 departamento, 12-13 municipio). [verificar]
_MUNICIPIOS = [17, 8, 16, 16, 13, 14, 19, 8, 24, 21, 9, 30, 32, 12, 8, 17, 14, 5, 11, 11, 7, 17]


def telefono(valor: str) -> str:
    """8 dígitos de Guatemala (con +502 opcional) u otro país con su prefijo: "+50255551234"."""
    limpio = _SEPARADORES.sub("", valor)
    if limpio.startswith("+"):
        digitos = limpio[1:]
        if not digitos.isdigit() or not 8 <= len(digitos) <= 15:
            raise DatoInvalido("Revisa el teléfono: 8 dígitos, o el + y el código del país.")
        if digitos.startswith("502") and len(digitos) != 11:
            raise DatoInvalido("Un teléfono de Guatemala tiene 8 dígitos.")
        return "+" + digitos
    if not limpio.isdigit():
        raise DatoInvalido("Revisa el teléfono: solo números, por ejemplo 5555 1234.")
    if len(limpio) == 8:
        return "+502" + limpio
    if len(limpio) == 11 and limpio.startswith("502"):
        return "+" + limpio
    raise DatoInvalido("Un teléfono de Guatemala tiene 8 dígitos.")


def correo(valor: str) -> str:
    limpio = valor.strip().lower()
    if len(limpio) > 120 or not _CORREO.match(limpio):
        raise DatoInvalido("Revisa el correo, por ejemplo maria@gmail.com.")
    return limpio


def nit(valor: str) -> str:
    """NIT con su dígito verificador (módulo 11; 10 se escribe K). Se guarda sin guiones."""
    limpio = _SEPARADORES.sub("", valor).upper()
    if not re.fullmatch(r"\d{1,12}[0-9K]", limpio):
        raise DatoInvalido("Revisa el NIT: números y al final un número o K (ej. 1234567-9).")
    cuerpo, verificador = limpio[:-1], limpio[-1]
    suma = sum(int(d) * f for d, f in zip(reversed(cuerpo), range(2, len(cuerpo) + 2), strict=True))
    esperado = (11 - suma % 11) % 11
    if verificador != ("K" if esperado == 10 else str(esperado)):
        raise DatoInvalido("Ese NIT no es válido: revisa el último dígito.")
    return limpio


def cui(valor: str) -> str:
    """CUI del DPI: 13 dígitos (8 + verificador + departamento + municipio)."""
    limpio = _SEPARADORES.sub("", valor)
    if not re.fullmatch(r"\d{13}", limpio):
        raise DatoInvalido("El CUI (DPI) tiene 13 dígitos.")
    numero, verificador = limpio[:8], int(limpio[8])
    depto, muni = int(limpio[9:11]), int(limpio[11:13])
    if not 1 <= depto <= len(_MUNICIPIOS) or not 1 <= muni <= _MUNICIPIOS[depto - 1]:
        raise DatoInvalido("Ese CUI no es válido: revisa los últimos 4 dígitos.")
    if sum(int(d) * (i + 2) for i, d in enumerate(numero)) % 11 != verificador:
        raise DatoInvalido("Ese CUI no es válido: revisa los dígitos.")
    return limpio


def id_fiscal(tipo: str, valor: str | None) -> str | None:
    if tipo == "CF":
        return None
    if not valor or not valor.strip():
        que = "NIT" if tipo == "NIT" else "CUI"
        raise DatoInvalido(f"Escribe el {que} o elige Consumidor final.")
    return nit(valor) if tipo == "NIT" else cui(valor)


def valor_de_campo(nombre: str, tipo: str, valor):
    """El valor de un campo propio, normalizado; None o vacío = sin dato."""
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return None
    if tipo == "texto":
        texto = str(valor).strip()
        if len(texto) > 200:
            raise DatoInvalido(f"{nombre}: máximo 200 letras.")
        return texto
    if tipo == "numero":
        if isinstance(valor, bool):
            raise DatoInvalido(f"{nombre} debe ser un número.")
        try:
            numero = Decimal(str(valor).strip().replace(",", ""))
        except InvalidOperation:
            raise DatoInvalido(f"{nombre} debe ser un número.") from None
        if not numero.is_finite():
            raise DatoInvalido(f"{nombre} debe ser un número.")
        return format(numero.normalize(), "f")
    if tipo == "fecha":
        try:
            return date.fromisoformat(str(valor).strip()).isoformat()
        except ValueError:
            raise DatoInvalido(f"{nombre} debe ser una fecha (año-mes-día).") from None
    if tipo == "si_no":
        if isinstance(valor, bool):
            return valor
        raise DatoInvalido(f"{nombre}: elige sí o no.")
    raise DatoInvalido(f"{nombre}: tipo desconocido.")
