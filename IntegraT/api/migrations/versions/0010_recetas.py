"""Recetas: qué insumos lleva cada producto o platillo.

Revisión: 0010
Anterior: 0009
Creada: 2026-11-24

La cantidad se guarda en la unidad que escribió la persona (puede ser distinta a la del insumo,
siempre del mismo tipo). Reemplazar una receta archiva sus líneas anteriores.
REGLA: una migración aplicada NUNCA se edita. Para corregir, crea otra.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "0010"
down_revision = "0009"
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
        "ops_receta_linea",
        sa.Column("id", UUID, primary_key=True, comment="UUIDv7 generado por la API"),
        sa.Column("negocio_id", UUID, nullable=False),
        sa.Column("item_id", UUID, nullable=False),
        sa.Column("insumo_id", UUID, nullable=False),
        sa.Column("cantidad", sa.Numeric(14, 4), nullable=False,
                  comment="Por una unidad vendida, en `unidad_codigo`"),
        sa.Column("unidad_codigo", sa.String(10), nullable=False),
        *_auditoria(),
        sa.ForeignKeyConstraint(["negocio_id"], ["core_negocio.id"],
                                name=op.f("fk_ops_receta_linea_negocio_id")),
        sa.ForeignKeyConstraint(["item_id"], ["ops_item.id"],
                                name=op.f("fk_ops_receta_linea_item_id")),
        sa.ForeignKeyConstraint(["insumo_id"], ["ops_insumo.id"],
                                name=op.f("fk_ops_receta_linea_insumo_id")),
        sa.ForeignKeyConstraint(["unidad_codigo"], ["cat_unidad_medida.codigo"],
                                name=op.f("fk_ops_receta_linea_unidad_codigo")),
        sa.CheckConstraint("cantidad > 0", name=op.f("ck_ops_receta_linea_cantidad")),
        comment="Líneas de receta: insumos que consume cada ítem vendido", **OPC,
    )
    op.create_index(op.f("ix_ops_receta_linea_negocio_id"), "ops_receta_linea", ["negocio_id"])
    op.create_index(op.f("ix_ops_receta_linea_item_id"), "ops_receta_linea", ["item_id"])
    op.create_index(op.f("ix_ops_receta_linea_insumo_id"), "ops_receta_linea", ["insumo_id"])
    op.create_index(op.f("ix_ops_receta_linea_unidad_codigo"), "ops_receta_linea",
                    ["unidad_codigo"])


def downgrade() -> None:
    op.drop_table("ops_receta_linea")
