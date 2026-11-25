"""Inventario: insumos y sus movimientos (inmutables).

Revisión: 0009
Anterior: 0008
Creada: 2026-11-24

Existencia y costo se guardan en la unidad base (UN, G o ML); la API convierte a la unidad de uso.
REGLA: una migración aplicada NUNCA se edita. Para corregir, crea otra.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "0009"
down_revision = "0008"
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
        "ops_insumo",
        sa.Column("id", UUID, primary_key=True, comment="UUIDv7 generado por la API"),
        sa.Column("negocio_id", UUID, nullable=False),
        sa.Column("nombre", sa.String(80), nullable=False),
        sa.Column("unidad_codigo", sa.String(10), nullable=False, comment="Unidad de uso"),
        sa.Column("existencia_base", sa.Numeric(18, 4), nullable=False,
                  server_default=sa.text("0"), comment="En unidad base; puede ser negativa"),
        sa.Column("costo_promedio_base", sa.Numeric(18, 8), nullable=False,
                  server_default=sa.text("0"), comment="Costo promedio ponderado por unidad base"),
        sa.Column("stock_minimo_base", sa.Numeric(18, 4), nullable=False,
                  server_default=sa.text("0"), comment="Aviso de 'te queda poco'"),
        *_auditoria(),
        sa.ForeignKeyConstraint(["negocio_id"], ["core_negocio.id"],
                                name=op.f("fk_ops_insumo_negocio_id")),
        sa.ForeignKeyConstraint(["unidad_codigo"], ["cat_unidad_medida.codigo"],
                                name=op.f("fk_ops_insumo_unidad_codigo")),
        sa.CheckConstraint("costo_promedio_base >= 0", name=op.f("ck_ops_insumo_costo_promedio_base")),
        sa.CheckConstraint("stock_minimo_base >= 0", name=op.f("ck_ops_insumo_stock_minimo_base")),
        comment="Insumos que el negocio compra y consume", **OPC,
    )
    op.create_index(op.f("ix_ops_insumo_negocio_id"), "ops_insumo", ["negocio_id"])
    op.create_index(op.f("ix_ops_insumo_unidad_codigo"), "ops_insumo", ["unidad_codigo"])

    op.create_table(
        "ops_movimiento_inventario",
        sa.Column("id", UUID, primary_key=True, comment="UUIDv7 generado por la API"),
        sa.Column("negocio_id", UUID, nullable=False),
        sa.Column("insumo_id", UUID, nullable=False),
        sa.Column("fecha_hora", DT, nullable=False, comment="UTC"),
        sa.Column("tipo", sa.String(20), nullable=False),
        sa.Column("cantidad_base", sa.Numeric(18, 4), nullable=False, comment="Con signo"),
        sa.Column("costo_unitario_base", sa.Numeric(18, 8), nullable=False),
        sa.Column("origen_tipo", sa.String(20), nullable=True),
        sa.Column("origen_id", UUID, nullable=True),
        sa.Column("nota", sa.String(200), nullable=True),
        sa.Column("creado_en", DT, nullable=False, server_default=AHORA),
        sa.Column("creado_por", UUID, nullable=True),
        sa.ForeignKeyConstraint(["negocio_id"], ["core_negocio.id"],
                                name=op.f("fk_ops_movimiento_inventario_negocio_id")),
        sa.ForeignKeyConstraint(["insumo_id"], ["ops_insumo.id"],
                                name=op.f("fk_ops_movimiento_inventario_insumo_id")),
        sa.CheckConstraint(
            "tipo IN ('entrada','merma','ajuste','consumo_venta','reverso_venta','inicial')",
            name=op.f("ck_ops_movimiento_inventario_tipo")),
        sa.CheckConstraint("costo_unitario_base >= 0",
                           name=op.f("ck_ops_movimiento_inventario_costo_unitario_base")),
        comment="Movimientos de inventario (inmutables; se corrigen con otro movimiento)", **OPC,
    )
    op.create_index(op.f("ix_ops_movimiento_inventario_negocio_id_insumo_id_fecha_hora"),
                    "ops_movimiento_inventario", ["negocio_id", "insumo_id", "fecha_hora"])
    op.create_index(op.f("ix_ops_movimiento_inventario_insumo_id"), "ops_movimiento_inventario",
                    ["insumo_id"])


def downgrade() -> None:
    op.drop_table("ops_movimiento_inventario")
    op.drop_table("ops_insumo")
