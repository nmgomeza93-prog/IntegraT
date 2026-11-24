"""Idempotencia de comandos (cabecera Idempotency-Key).

Revisión: 0005
Anterior: 0004
Creada: 2026-11-24

Una misma clave del mismo usuario devuelve el mismo resultado en lugar de repetir la operación.
REGLA: una migración aplicada NUNCA se edita. Para corregir, crea otra.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

OPC = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_0900_ai_ci"}
DT = mysql.DATETIME(fsp=6)
UUID = sa.BINARY(16)
AHORA = sa.text("CURRENT_TIMESTAMP(6)")
AHORA_UPD = sa.text("CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)")


def upgrade() -> None:
    op.create_table(
        "core_idempotencia",
        sa.Column("id", UUID, primary_key=True, comment="UUIDv7 generado por la API"),
        sa.Column("usuario_id", UUID, nullable=False),
        sa.Column("operacion", sa.String(40), nullable=False, comment="Ej. crear_negocio"),
        sa.Column("clave", sa.String(100), nullable=False, comment="Idempotency-Key del cliente"),
        sa.Column("huella", sa.CHAR(64), nullable=False, comment="SHA-256 de los datos enviados"),
        sa.Column("recurso_id", UUID, nullable=False, comment="Lo que se creó (ej. el negocio)"),
        sa.Column("creado_en", DT, nullable=False, server_default=AHORA),
        sa.Column("creado_por", UUID, nullable=True),
        sa.Column("actualizado_en", DT, nullable=False, server_default=AHORA_UPD),
        sa.Column("actualizado_por", UUID, nullable=True),
        sa.Column("eliminado_en", DT, nullable=True, comment="Borrado lógico"),
        sa.Column("eliminado_por", UUID, nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.ForeignKeyConstraint(
            ["usuario_id"], ["core_usuario.id"], name=op.f("fk_core_idempotencia_usuario_id")
        ),
        sa.UniqueConstraint("usuario_id", "operacion", "clave",
                            name=op.f("uq_core_idempotencia_usuario_id_operacion_clave")),
        comment="Claves de idempotencia de comandos (vigencia 24 horas)", **OPC,
    )


def downgrade() -> None:
    op.drop_table("core_idempotencia")
