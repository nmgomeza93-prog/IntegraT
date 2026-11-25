"""Compras a mano: proveedores, compras y sus líneas.

Revisión: 0011
Anterior: 0010
Creada: 2026-11-24

La fecha de la compra es un día calendario (DATE) que elige la persona. Anular una compra crea
movimientos `reverso_compra`, por eso se amplía el CHECK del tipo de movimiento de inventario.
REGLA: una migración aplicada NUNCA se edita. Para corregir, crea otra.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

OPC = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_0900_ai_ci"}
DT = mysql.DATETIME(fsp=6)
UUID = sa.BINARY(16)
AHORA = sa.text("CURRENT_TIMESTAMP(6)")
AHORA_UPD = sa.text("CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)")
TIPOS_ANTES = "('entrada','merma','ajuste','consumo_venta','reverso_venta','inicial')"
TIPOS_AHORA = "('entrada','merma','ajuste','consumo_venta','reverso_venta','inicial','reverso_compra')"
CK_TIPO = op.f("ck_ops_movimiento_inventario_tipo")


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
        "ops_proveedor",
        sa.Column("id", UUID, primary_key=True, comment="UUIDv7 generado por la API"),
        sa.Column("negocio_id", UUID, nullable=False),
        sa.Column("nombre", sa.String(120), nullable=False),
        sa.Column("telefono", sa.String(30), nullable=True),
        *_auditoria(),
        sa.ForeignKeyConstraint(["negocio_id"], ["core_negocio.id"],
                                name=op.f("fk_ops_proveedor_negocio_id")),
        comment="Proveedores del negocio", **OPC,
    )
    op.create_index(op.f("ix_ops_proveedor_negocio_id"), "ops_proveedor", ["negocio_id"])

    op.create_table(
        "ops_compra",
        sa.Column("id", UUID, primary_key=True, comment="UUIDv7 generado por la API"),
        sa.Column("negocio_id", UUID, nullable=False),
        sa.Column("proveedor_id", UUID, nullable=True),
        sa.Column("fecha", sa.Date(), nullable=False, comment="Día de la compra (calendario local)"),
        sa.Column("numero_factura", sa.String(40), nullable=True),
        sa.Column("medio_pago", sa.String(20), nullable=False),
        sa.Column("total", sa.Numeric(14, 2), nullable=False),
        sa.Column("estado", sa.String(12), nullable=False, server_default="registrada"),
        sa.Column("nota", sa.String(200), nullable=True),
        sa.Column("anulada_en", DT, nullable=True),
        sa.Column("anulada_por", UUID, nullable=True),
        sa.Column("motivo_anulacion", sa.String(200), nullable=True),
        *_auditoria(),
        sa.ForeignKeyConstraint(["negocio_id"], ["core_negocio.id"],
                                name=op.f("fk_ops_compra_negocio_id")),
        sa.ForeignKeyConstraint(["proveedor_id"], ["ops_proveedor.id"],
                                name=op.f("fk_ops_compra_proveedor_id")),
        sa.CheckConstraint("medio_pago IN ('efectivo','tarjeta','transferencia')",
                           name=op.f("ck_ops_compra_medio_pago")),
        sa.CheckConstraint("estado IN ('registrada','anulada')", name=op.f("ck_ops_compra_estado")),
        sa.CheckConstraint("total >= 0", name=op.f("ck_ops_compra_total")),
        comment="Compras (inmutables; se corrigen anulando)", **OPC,
    )
    op.create_index(op.f("ix_ops_compra_negocio_id_fecha"), "ops_compra", ["negocio_id", "fecha"])
    op.create_index(op.f("ix_ops_compra_proveedor_id"), "ops_compra", ["proveedor_id"])

    op.create_table(
        "ops_compra_linea",
        sa.Column("id", UUID, primary_key=True, comment="UUIDv7 generado por la API"),
        sa.Column("negocio_id", UUID, nullable=False),
        sa.Column("compra_id", UUID, nullable=False),
        sa.Column("insumo_id", UUID, nullable=False),
        sa.Column("nombre", sa.String(80), nullable=False, comment="Congelado al comprar"),
        sa.Column("cantidad", sa.Numeric(14, 4), nullable=False, comment="En `unidad_codigo`"),
        sa.Column("unidad_codigo", sa.String(10), nullable=False),
        sa.Column("costo_total", sa.Numeric(14, 2), nullable=False),
        *_auditoria(),
        sa.ForeignKeyConstraint(["negocio_id"], ["core_negocio.id"],
                                name=op.f("fk_ops_compra_linea_negocio_id")),
        sa.ForeignKeyConstraint(["compra_id"], ["ops_compra.id"],
                                name=op.f("fk_ops_compra_linea_compra_id")),
        sa.ForeignKeyConstraint(["insumo_id"], ["ops_insumo.id"],
                                name=op.f("fk_ops_compra_linea_insumo_id")),
        sa.ForeignKeyConstraint(["unidad_codigo"], ["cat_unidad_medida.codigo"],
                                name=op.f("fk_ops_compra_linea_unidad_codigo")),
        sa.CheckConstraint("cantidad > 0", name=op.f("ck_ops_compra_linea_cantidad")),
        sa.CheckConstraint("costo_total >= 0", name=op.f("ck_ops_compra_linea_costo_total")),
        comment="Líneas de una compra", **OPC,
    )
    op.create_index(op.f("ix_ops_compra_linea_negocio_id"), "ops_compra_linea", ["negocio_id"])
    op.create_index(op.f("ix_ops_compra_linea_compra_id"), "ops_compra_linea", ["compra_id"])
    op.create_index(op.f("ix_ops_compra_linea_insumo_id"), "ops_compra_linea", ["insumo_id"])
    op.create_index(op.f("ix_ops_compra_linea_unidad_codigo"), "ops_compra_linea",
                    ["unidad_codigo"])

    op.drop_constraint(CK_TIPO, "ops_movimiento_inventario", type_="check")
    op.create_check_constraint(CK_TIPO, "ops_movimiento_inventario", f"tipo IN {TIPOS_AHORA}")


def downgrade() -> None:
    op.execute("DELETE FROM ops_movimiento_inventario WHERE tipo = 'reverso_compra'")
    op.drop_constraint(CK_TIPO, "ops_movimiento_inventario", type_="check")
    op.create_check_constraint(CK_TIPO, "ops_movimiento_inventario", f"tipo IN {TIPOS_ANTES}")
    op.drop_table("ops_compra_linea")
    op.drop_table("ops_compra")
    op.drop_table("ops_proveedor")
