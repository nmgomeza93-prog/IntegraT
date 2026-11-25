"""Ventas rápidas: venta, líneas y pago.

Revisión: 0007
Anterior: 0006
Creada: 2026-11-24

Las ventas son inmutables: se corrigen anulando (estado + quién/cuándo/por qué), nunca editando.
Cada línea congela el nombre y el precio con que se vendió.
REGLA: una migración aplicada NUNCA se edita. Para corregir, crea otra.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "0007"
down_revision = "0006"
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
        "ops_venta",
        sa.Column("id", UUID, primary_key=True, comment="UUIDv7 generado por la API"),
        sa.Column("negocio_id", UUID, nullable=False),
        sa.Column("numero", sa.Integer(), nullable=False, comment="Consecutivo por negocio"),
        sa.Column("fecha_hora", DT, nullable=False, comment="UTC"),
        sa.Column("estado", sa.String(12), nullable=False, server_default="pagada"),
        sa.Column("total", sa.Numeric(14, 2), nullable=False),
        sa.Column("moneda_codigo", sa.CHAR(3), nullable=False),
        sa.Column("anulada_en", DT, nullable=True),
        sa.Column("anulada_por", UUID, nullable=True),
        sa.Column("motivo_anulacion", sa.String(200), nullable=True),
        *_auditoria(),
        sa.ForeignKeyConstraint(["negocio_id"], ["core_negocio.id"],
                                name=op.f("fk_ops_venta_negocio_id")),
        sa.ForeignKeyConstraint(["moneda_codigo"], ["cat_moneda.codigo"],
                                name=op.f("fk_ops_venta_moneda_codigo")),
        sa.UniqueConstraint("negocio_id", "numero", name=op.f("uq_ops_venta_negocio_id_numero")),
        sa.CheckConstraint("estado IN ('pagada','anulada')", name=op.f("ck_ops_venta_estado")),
        sa.CheckConstraint("total >= 0", name=op.f("ck_ops_venta_total")),
        comment="Ventas (inmutables; se corrigen anulando)", **OPC,
    )
    op.create_index(op.f("ix_ops_venta_negocio_id_fecha_hora"), "ops_venta",
                    ["negocio_id", "fecha_hora"])
    op.create_index(op.f("ix_ops_venta_moneda_codigo"), "ops_venta", ["moneda_codigo"])

    op.create_table(
        "ops_venta_linea",
        sa.Column("id", UUID, primary_key=True, comment="UUIDv7 generado por la API"),
        sa.Column("negocio_id", UUID, nullable=False),
        sa.Column("venta_id", UUID, nullable=False),
        sa.Column("item_id", UUID, nullable=False),
        sa.Column("item_variante_id", UUID, nullable=False),
        sa.Column("nombre", sa.String(120), nullable=False, comment="Congelado al vender"),
        sa.Column("cantidad", sa.Numeric(14, 4), nullable=False),
        sa.Column("precio_unitario", sa.Numeric(14, 2), nullable=False,
                  comment="Congelado al vender"),
        sa.Column("total", sa.Numeric(14, 2), nullable=False),
        *_auditoria(),
        sa.ForeignKeyConstraint(["negocio_id"], ["core_negocio.id"],
                                name=op.f("fk_ops_venta_linea_negocio_id")),
        sa.ForeignKeyConstraint(["venta_id"], ["ops_venta.id"],
                                name=op.f("fk_ops_venta_linea_venta_id")),
        sa.ForeignKeyConstraint(["item_id"], ["ops_item.id"],
                                name=op.f("fk_ops_venta_linea_item_id")),
        sa.ForeignKeyConstraint(["item_variante_id"], ["ops_item_variante.id"],
                                name=op.f("fk_ops_venta_linea_item_variante_id")),
        sa.CheckConstraint("cantidad > 0", name=op.f("ck_ops_venta_linea_cantidad")),
        sa.CheckConstraint("precio_unitario >= 0", name=op.f("ck_ops_venta_linea_precio_unitario")),
        comment="Líneas de una venta, con nombre y precio congelados", **OPC,
    )
    op.create_index(op.f("ix_ops_venta_linea_negocio_id"), "ops_venta_linea", ["negocio_id"])
    op.create_index(op.f("ix_ops_venta_linea_venta_id"), "ops_venta_linea", ["venta_id"])
    op.create_index(op.f("ix_ops_venta_linea_item_id"), "ops_venta_linea", ["item_id"])
    op.create_index(op.f("ix_ops_venta_linea_item_variante_id"), "ops_venta_linea",
                    ["item_variante_id"])

    op.create_table(
        "ops_pago",
        sa.Column("id", UUID, primary_key=True, comment="UUIDv7 generado por la API"),
        sa.Column("negocio_id", UUID, nullable=False),
        sa.Column("venta_id", UUID, nullable=False),
        sa.Column("medio_pago", sa.String(20), nullable=False),
        sa.Column("monto", sa.Numeric(14, 2), nullable=False),
        *_auditoria(),
        sa.ForeignKeyConstraint(["negocio_id"], ["core_negocio.id"],
                                name=op.f("fk_ops_pago_negocio_id")),
        sa.ForeignKeyConstraint(["venta_id"], ["ops_venta.id"],
                                name=op.f("fk_ops_pago_venta_id")),
        sa.CheckConstraint("medio_pago IN ('efectivo','tarjeta','transferencia')",
                           name=op.f("ck_ops_pago_medio_pago")),
        sa.CheckConstraint("monto >= 0", name=op.f("ck_ops_pago_monto")),
        comment="Pagos de una venta (hoy uno por venta; el pago dividido llegará después)", **OPC,
    )
    op.create_index(op.f("ix_ops_pago_negocio_id"), "ops_pago", ["negocio_id"])
    op.create_index(op.f("ix_ops_pago_venta_id"), "ops_pago", ["venta_id"])


def downgrade() -> None:
    op.drop_table("ops_pago")
    op.drop_table("ops_venta_linea")
    op.drop_table("ops_venta")
