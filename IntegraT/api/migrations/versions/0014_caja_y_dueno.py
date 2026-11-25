"""Caja del día y dinero del dueño.

Revisión: 0014
Anterior: 0013
Creada: 2026-11-25

`ops_sesion_caja`: una apertura y su cierre (efectivo esperado, contado y diferencia).
`ops_movimiento_dueno`: aportes y retiros del dueño (docs/PLAN_CAJA.md).
REGLA: una migración aplicada NUNCA se edita. Para corregir, crea otra.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

OPC = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_0900_ai_ci"}
DT = mysql.DATETIME(fsp=6)
UUID = sa.BINARY(16)
AHORA = sa.text("CURRENT_TIMESTAMP(6)")
AHORA_UPD = sa.text("CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)")
DINERO = sa.Numeric(14, 2)


def _auditoria() -> list[sa.Column]:
    return [
        sa.Column("creado_en", DT, nullable=False, server_default=AHORA),
        sa.Column("creado_por", UUID, nullable=True),
        sa.Column("actualizado_en", DT, nullable=False, server_default=AHORA_UPD),
        sa.Column("actualizado_por", UUID, nullable=True),
        sa.Column("eliminado_en", DT, nullable=True, comment="Borrado lógico"),
        sa.Column("eliminado_por", UUID, nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
    ]


def upgrade() -> None:
    op.create_table(
        "ops_sesion_caja",
        sa.Column("id", UUID, primary_key=True, comment="UUIDv7 generado por la API"),
        sa.Column("negocio_id", UUID, nullable=False),
        sa.Column("fecha", sa.Date(), nullable=False, comment="Día de la apertura (calendario local)"),
        sa.Column("abierta_en", DT, nullable=False, comment="UTC"),
        sa.Column("monto_apertura", DINERO, nullable=False),
        sa.Column("estado", sa.String(10), nullable=False, server_default="abierta"),
        sa.Column("cerrada_en", DT, nullable=True),
        sa.Column("cerrada_por", UUID, nullable=True),
        sa.Column("efectivo_esperado", DINERO, nullable=True),
        sa.Column("efectivo_contado", DINERO, nullable=True),
        sa.Column("diferencia", DINERO, nullable=True, comment="contado - esperado"),
        sa.Column("nota", sa.String(200), nullable=True),
        *_auditoria(),
        sa.ForeignKeyConstraint(["negocio_id"], ["core_negocio.id"],
                                name=op.f("fk_ops_sesion_caja_negocio_id")),
        sa.CheckConstraint("estado IN ('abierta','cerrada')", name=op.f("ck_ops_sesion_caja_estado")),
        sa.CheckConstraint("monto_apertura >= 0", name=op.f("ck_ops_sesion_caja_monto_apertura")),
        sa.CheckConstraint("efectivo_contado IS NULL OR efectivo_contado >= 0",
                           name=op.f("ck_ops_sesion_caja_efectivo_contado")),
        comment="Caja del día: apertura y cierre", **OPC,
    )
    op.create_index(op.f("ix_ops_sesion_caja_negocio_id_estado"), "ops_sesion_caja",
                    ["negocio_id", "estado"])
    op.create_index(op.f("ix_ops_sesion_caja_negocio_id_fecha"), "ops_sesion_caja",
                    ["negocio_id", "fecha"])

    op.create_table(
        "ops_movimiento_dueno",
        sa.Column("id", UUID, primary_key=True, comment="UUIDv7 generado por la API"),
        sa.Column("negocio_id", UUID, nullable=False),
        sa.Column("tipo", sa.String(10), nullable=False),
        sa.Column("monto", DINERO, nullable=False),
        sa.Column("medio", sa.String(10), nullable=False),
        sa.Column("fecha", sa.Date(), nullable=False, comment="Calendario local"),
        sa.Column("nota", sa.String(200), nullable=True),
        *_auditoria(),
        sa.ForeignKeyConstraint(["negocio_id"], ["core_negocio.id"],
                                name=op.f("fk_ops_movimiento_dueno_negocio_id")),
        sa.CheckConstraint("tipo IN ('aporte','retiro')", name=op.f("ck_ops_movimiento_dueno_tipo")),
        sa.CheckConstraint("medio IN ('efectivo','banco')", name=op.f("ck_ops_movimiento_dueno_medio")),
        sa.CheckConstraint("monto > 0", name=op.f("ck_ops_movimiento_dueno_monto")),
        comment="Dinero que el dueño pone o saca del negocio", **OPC,
    )
    op.create_index(op.f("ix_ops_movimiento_dueno_negocio_id_fecha"), "ops_movimiento_dueno",
                    ["negocio_id", "fecha"])


def downgrade() -> None:
    op.drop_table("ops_movimiento_dueno")
    op.drop_table("ops_sesion_caja")
