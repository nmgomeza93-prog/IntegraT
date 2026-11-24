"""Límite de intentos de acceso (contra la fuerza bruta y el registro masivo).

Vive en la base de datos (no en memoria) para que funcione con varias réplicas y sobreviva
a los reinicios. Guarda solo huellas del correo y de la IP (ver `seguridad.huella`).

Reglas (docs/PLAN_CIERRE_FASE1.md, paso 2):
- login:     5 fallos por correo y 20 fallos por IP en 15 minutos. Un login correcto borra los
             fallos de ese correo.
- registro:  10 intentos por IP en 1 hora (cuentan todos, salgan bien o mal).
- refrescar: 30 fallos por IP en 15 minutos.
El correo protege cada cuenta aunque alguien falsee su IP; la IP frena el recorrido de muchos
correos y el registro masivo.
"""

import math
import random
from dataclasses import dataclass
from datetime import timedelta

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from integrat.auth import seguridad
from integrat.db.tablas import core_intento_acceso as tabla
from integrat.db.tipos import ahora_utc, uuid7

MENSAJE = "Demasiados intentos. Espera unos minutos e inténtalo de nuevo."
RETENCION = timedelta(days=1)  # lo más viejo se borra


@dataclass(frozen=True)
class Regla:
    tipo: str  # "ip" | "correo"
    maximo: int
    ventana: timedelta


REGLAS: dict[str, tuple[Regla, ...]] = {
    "login": (
        Regla("correo", 5, timedelta(minutes=15)),
        Regla("ip", 20, timedelta(minutes=15)),
    ),
    "registro": (Regla("ip", 10, timedelta(hours=1)),),
    "refrescar": (Regla("ip", 30, timedelta(minutes=15)),),
}


def _ahora():
    """Reloj del limitador (las pruebas lo adelantan para simular que pasa el tiempo)."""
    return ahora_utc()


def _valores(ip: str, correo: str | None) -> dict[str, str]:
    valores = {"ip": ip}
    if correo:
        valores["correo"] = correo
    return valores


def segundos_de_espera(con: Connection, accion: str, *, ip: str, correo: str | None = None
                       ) -> int | None:
    """None si puede intentar; si no, los segundos que debe esperar."""
    ahora = _ahora()
    valores = _valores(ip, correo)
    espera = 0
    for regla in REGLAS[accion]:
        valor = valores.get(regla.tipo)
        if valor is None:
            continue
        cantidad, mas_viejo = con.execute(
            sa.select(sa.func.count(), sa.func.min(tabla.c.creado_en)).where(
                tabla.c.accion == accion,
                tabla.c.clave_tipo == regla.tipo,
                tabla.c.clave_hash == seguridad.huella(valor),
                tabla.c.creado_en > ahora - regla.ventana,
                tabla.c.eliminado_en.is_(None),
            )
        ).one()
        if cantidad >= regla.maximo:
            libre_en = (mas_viejo + regla.ventana - ahora).total_seconds()
            espera = max(espera, math.ceil(libre_en), 1)
    return espera or None


def registrar(con: Connection, accion: str, *, ip: str, correo: str | None = None) -> None:
    """Anota un intento (en login y refresco: solo los fallidos)."""
    ahora = _ahora()
    valores = _valores(ip, correo)
    for regla in REGLAS[accion]:
        valor = valores.get(regla.tipo)
        if valor is None:
            continue
        con.execute(sa.insert(tabla).values(
            id=uuid7(), accion=accion, clave_tipo=regla.tipo,
            clave_hash=seguridad.huella(valor), creado_en=ahora,
        ))
    if random.random() < 0.02:  # limpieza ocasional: no hace falta un proceso aparte  # noqa: S311
        con.execute(sa.delete(tabla).where(tabla.c.creado_en < ahora - RETENCION))


def olvidar_correo(con: Connection, accion: str, correo: str) -> None:
    """Un acceso correcto borra los fallos previos de ese correo."""
    con.execute(sa.delete(tabla).where(
        tabla.c.accion == accion, tabla.c.clave_tipo == "correo",
        tabla.c.clave_hash == seguridad.huella(correo),
    ))


def correo_corto(correo: str) -> str:
    """Identificador para los logs: permite seguir una cuenta sin escribir su correo."""
    return seguridad.huella(correo)[:8]
