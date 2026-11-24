"""Tokens de refresco de sesión (se guardan solo como hash SHA-256).

Revisión: 0003
Anterior: 0002
Creada: 2026-11-24

REGLA: una migración aplicada NUNCA se edita. Para corregir, crea otra.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

OPC = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_0900_ai_ci"}
DT = mysql.DATETIME(fsp=6)
UUID = sa.BINARY(16)
AHORA = sa.text("CURRENT_TIMESTAMP(6)")
AHORA_UPD = sa.text("CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)")


def upgrade() -> None:
    op.create_table(
        "core_token_refresco",
        sa.Column("id", UUID, primary_key=True, comment="UUIDv7 generado por la API"),
        sa.Column("usuario_id", UUID, nullable=False),
        sa.Column("token_hash", sa.CHAR(64), nullable=False, comment="SHA-256 del token; nunca el token"),
        sa.Column("expira_en", DT, nullable=False),
        sa.Column("revocado_en", DT, nullable=True),
        sa.Column("creado_en", DT, nullable=False, server_default=AHORA),
        sa.Column("creado_por", UUID, nullable=True),
        sa.Column("actualizado_en", DT, nullable=False, server_default=AHORA_UPD),
        sa.Column("actualizado_por", UUID, nullable=True),
        sa.Column("eliminado_en", DT, nullable=True, comment="Borrado lógico"),
        sa.Column("eliminado_por", UUID, nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.ForeignKeyConstraint(
            ["usuario_id"], ["core_usuario.id"], name=op.f("fk_core_token_refresco_usuario_id")
        ),
        sa.UniqueConstraint("token_hash", name=op.f("uq_core_token_refresco_token_hash")),
        comment="Tokens de refresco de sesión (rotan en cada uso)", **OPC,
    )
    op.create_index(
        op.f("ix_core_token_refresco_usuario_id"), "core_token_refresco", ["usuario_id"]
    )


def downgrade() -> None:
    op.drop_table("core_token_refresco")
