"""Gastos: categorías de gasto y gastos.

Revisión: 0008
Anterior: 0007
Creada: 2026-11-24

La fecha del gasto es un día calendario (DATE) que elige la persona, no un instante UTC.
REGLA: una migración aplicada NUNCA se edita. Para corregir, crea otra.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

OPC = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_0900_ai_ci"}
DT = mysql.DATETIME(fsp=6)
UUID = sa.BINARY(16)
AHORA = sa.text("CURRENT_TIMESTAMP(6)")
AHORA_UPD = sa.text("CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)")


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
        "ops_categoria_gasto",
        sa.Column("id", UUID, primary_key=True, comment="UUIDv7 generado por la API"),
        sa.Column("negocio_id", UUID, nullable=False),
        sa.Column("nombre", sa.String(80), nullable=False),
        sa.Column("icono", sa.String(40), nullable=True),
        sa.Column("es_fijo", sa.Boolean(create_constraint=False), nullable=False,
                  server_default=sa.text("0"), comment="Gasto fijo (renta, sueldos) o variable"),
        sa.Column("rol_cuenta_codigo", sa.String(40), nullable=True,
                  comment="Rol de cuenta contable (lo usará el motor contable)"),
        sa.Column("orden", sa.SmallInteger(), nullable=False, server_default=sa.text("0")),
        *_auditoria(),
        sa.ForeignKeyConstraint(["negocio_id"], ["core_negocio.id"],
                                name=op.f("fk_ops_categoria_gasto_negocio_id")),
        comment="Categorías de gasto de cada negocio", **OPC,
    )
    op.create_index(op.f("ix_ops_categoria_gasto_negocio_id"), "ops_categoria_gasto",
                    ["negocio_id"])

    op.create_table(
        "ops_gasto",
        sa.Column("id", UUID, primary_key=True, comment="UUIDv7 generado por la API"),
        sa.Column("negocio_id", UUID, nullable=False),
        sa.Column("categoria_gasto_id", UUID, nullable=False),
        sa.Column("fecha", sa.Date(), nullable=False, comment="Día del gasto (calendario local)"),
        sa.Column("monto", sa.Numeric(14, 2), nullable=False),
        sa.Column("medio_pago", sa.String(20), nullable=False),
        sa.Column("descripcion", sa.String(200), nullable=True),
        sa.Column("es_fijo", sa.Boolean(create_constraint=False), nullable=False,
                  server_default=sa.text("0")),
        *_auditoria(),
        sa.ForeignKeyConstraint(["negocio_id"], ["core_negocio.id"],
                                name=op.f("fk_ops_gasto_negocio_id")),
        sa.ForeignKeyConstraint(["categoria_gasto_id"], ["ops_categoria_gasto.id"],
                                name=op.f("fk_ops_gasto_categoria_gasto_id")),
        sa.CheckConstraint("monto > 0", name=op.f("ck_ops_gasto_monto")),
        sa.CheckConstraint("medio_pago IN ('efectivo','tarjeta','transferencia')",
                           name=op.f("ck_ops_gasto_medio_pago")),
        comment="Gastos del negocio", **OPC,
    )
    op.create_index(op.f("ix_ops_gasto_negocio_id_fecha"), "ops_gasto", ["negocio_id", "fecha"])
    op.create_index(op.f("ix_ops_gasto_categoria_gasto_id"), "ops_gasto", ["categoria_gasto_id"])


def downgrade() -> None:
    op.drop_table("ops_gasto")
    op.drop_table("ops_categoria_gasto")
