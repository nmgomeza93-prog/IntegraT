"""Tipos y columnas estándar de la base `integrat` (convención en docs/CONVENCIONES_BD.md).

Se usan tanto en las migraciones como en la metadata de ejecución (`tablas.py`).
"""

import secrets
import time
import uuid

import sqlalchemy as sa
from sqlalchemy.dialects import mysql
from sqlalchemy.types import TypeDecorator


def uuid7() -> uuid.UUID:
    """UUID versión 7 (RFC 9562): ordenado por tiempo, ideal como PK en InnoDB."""
    milisegundos = time.time_ns() // 1_000_000
    datos = bytearray(milisegundos.to_bytes(6, "big") + secrets.token_bytes(10))
    datos[6] = (datos[6] & 0x0F) | 0x70  # versión 7
    datos[8] = (datos[8] & 0x3F) | 0x80  # variante RFC
    return uuid.UUID(bytes=bytes(datos))


class UUIDBinario(TypeDecorator):
    """UUID guardado como BINARY(16). En Python se maneja como uuid.UUID."""

    impl = sa.BINARY(16)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if not isinstance(value, uuid.UUID):
            value = uuid.UUID(str(value))
        return value.bytes

    def process_result_value(self, value, dialect):
        return None if value is None else uuid.UUID(bytes=bytes(value))


AHORA = sa.text("CURRENT_TIMESTAMP(6)")
AHORA_ON_UPDATE = sa.text("CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)")

FechaHora = mysql.DATETIME(fsp=6)  # siempre en UTC (la sesión fija time_zone='+00:00')
Dinero = sa.Numeric(14, 2)
Cantidad = sa.Numeric(14, 4)
Booleano = sa.Boolean(create_constraint=False)  # TINYINT(1) en MySQL

OPCIONES_TABLA = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_0900_ai_ci",
}


def col_id() -> sa.Column:
    return sa.Column("id", UUIDBinario(), primary_key=True, comment="UUIDv7 generado por la API")


def cols_tiempo() -> list[sa.Column]:
    """Para catálogos y configuración global: solo marcas de tiempo."""
    return [
        sa.Column("creado_en", FechaHora, nullable=False, server_default=AHORA),
        sa.Column("actualizado_en", FechaHora, nullable=False, server_default=AHORA_ON_UPDATE),
    ]


def cols_auditoria() -> list[sa.Column]:
    """Columnas estándar de toda tabla de negocio (auditoría, borrado lógico, versión)."""
    return [
        sa.Column("creado_en", FechaHora, nullable=False, server_default=AHORA),
        sa.Column("creado_por", UUIDBinario(), nullable=True),
        sa.Column("actualizado_en", FechaHora, nullable=False, server_default=AHORA_ON_UPDATE),
        sa.Column("actualizado_por", UUIDBinario(), nullable=True),
        sa.Column("eliminado_en", FechaHora, nullable=True, comment="Borrado lógico"),
        sa.Column("eliminado_por", UUIDBinario(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
    ]
