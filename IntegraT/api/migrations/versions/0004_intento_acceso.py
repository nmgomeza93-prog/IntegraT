"""Intentos de acceso (límite de intentos de login, registro y refresco).

Revisión: 0004
Anterior: 0003
Creada: 2026-11-24

Guarda solo huellas (HMAC) del correo y de la IP, nunca los valores.
REGLA: una migración aplicada NUNCA se edita. Para corregir, crea otra.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

OPC = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_0900_ai_ci"}
DT = mysql.DATETIME(fsp=6)
UUID = sa.BINARY(16)
AHORA = sa.text("CURRENT_TIMESTAMP(6)")
AHORA_UPD = sa.text("CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)")


def upgrade() -> None:
    op.create_table(
        "core_intento_acceso",
        sa.Column("id", UUID, primary_key=True, comment="UUIDv7 generado por la API"),
        sa.Column("accion", sa.String(20), nullable=False, comment="login, registro, refrescar"),
        sa.Column("clave_tipo", sa.String(10), nullable=False, comment="ip o correo"),
        sa.Column("clave_hash", sa.CHAR(64), nullable=False, comment="HMAC-SHA256; nunca el valor"),
        sa.Column("creado_en", DT, nullable=False, server_default=AHORA),
        sa.Column("creado_por", UUID, nullable=True),
        sa.Column("actualizado_en", DT, nullable=False, server_default=AHORA_UPD),
        sa.Column("actualizado_por", UUID, nullable=True),
        sa.Column("eliminado_en", DT, nullable=True, comment="Borrado lógico"),
        sa.Column("eliminado_por", UUID, nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.CheckConstraint("clave_tipo IN ('ip','correo')",
                           name=op.f("ck_core_intento_acceso_clave_tipo")),
        comment="Intentos de acceso recientes para limitar la fuerza bruta", **OPC,
    )
    op.create_index(
        op.f("ix_core_intento_acceso_accion_clave_tipo_clave_hash_creado_en"),
        "core_intento_acceso", ["accion", "clave_tipo", "clave_hash", "creado_en"],
    )
    op.create_index(op.f("ix_core_intento_acceso_creado_en"), "core_intento_acceso", ["creado_en"])


def downgrade() -> None:
    op.drop_table("core_intento_acceso")
