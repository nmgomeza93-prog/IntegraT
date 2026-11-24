"""Catálogo básico: categorías, ítems (producto/platillo) y su variante implícita.

Revisión: 0006
Anterior: 0005
Creada: 2026-11-24

Todo ítem tiene al menos una variante (la implícita "Única") que guarda el precio de venta;
así las variantes visibles, ventas e inventario no obligan a migrar datos después.
REGLA: una migración aplicada NUNCA se edita. Para corregir, crea otra.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "0006"
down_revision = "0005"
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
        "ops_categoria",
        sa.Column("id", UUID, primary_key=True, comment="UUIDv7 generado por la API"),
        sa.Column("negocio_id", UUID, nullable=False),
        sa.Column("nombre", sa.String(80), nullable=False),
        sa.Column("orden", sa.SmallInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("icono", sa.String(40), nullable=True),
        *_auditoria(),
        sa.ForeignKeyConstraint(["negocio_id"], ["core_negocio.id"],
                                name=op.f("fk_ops_categoria_negocio_id")),
        comment="Categorías del catálogo de cada negocio", **OPC,
    )
    op.create_index(op.f("ix_ops_categoria_negocio_id"), "ops_categoria", ["negocio_id"])

    op.create_table(
        "ops_item",
        sa.Column("id", UUID, primary_key=True, comment="UUIDv7 generado por la API"),
        sa.Column("negocio_id", UUID, nullable=False),
        sa.Column("categoria_id", UUID, nullable=True),
        sa.Column("tipo_item", sa.String(20), nullable=False,
                  comment="producto o platillo (lo define el tipo de negocio)"),
        sa.Column("nombre", sa.String(120), nullable=False),
        sa.Column("descripcion", sa.String(500), nullable=True),
        sa.Column("se_vende", sa.Boolean(create_constraint=False), nullable=False,
                  server_default=sa.text("1")),
        *_auditoria(),
        sa.ForeignKeyConstraint(["negocio_id"], ["core_negocio.id"],
                                name=op.f("fk_ops_item_negocio_id")),
        sa.ForeignKeyConstraint(["categoria_id"], ["ops_categoria.id"],
                                name=op.f("fk_ops_item_categoria_id")),
        sa.CheckConstraint("tipo_item IN ('producto','platillo')",
                           name=op.f("ck_ops_item_tipo_item")),
        comment="Productos y platillos que vende el negocio", **OPC,
    )
    op.create_index(op.f("ix_ops_item_negocio_id"), "ops_item", ["negocio_id"])
    op.create_index(op.f("ix_ops_item_categoria_id"), "ops_item", ["categoria_id"])

    op.create_table(
        "ops_item_variante",
        sa.Column("id", UUID, primary_key=True, comment="UUIDv7 generado por la API"),
        sa.Column("negocio_id", UUID, nullable=False),
        sa.Column("item_id", UUID, nullable=False),
        sa.Column("nombre", sa.String(80), nullable=False, server_default="Única"),
        sa.Column("precio_venta", sa.Numeric(14, 2), nullable=False),
        *_auditoria(),
        sa.ForeignKeyConstraint(["negocio_id"], ["core_negocio.id"],
                                name=op.f("fk_ops_item_variante_negocio_id")),
        sa.ForeignKeyConstraint(["item_id"], ["ops_item.id"],
                                name=op.f("fk_ops_item_variante_item_id")),
        sa.CheckConstraint("precio_venta >= 0", name=op.f("ck_ops_item_variante_precio_venta")),
        comment="Presentaciones de un ítem; la implícita 'Única' guarda el precio", **OPC,
    )
    op.create_index(op.f("ix_ops_item_variante_negocio_id"), "ops_item_variante", ["negocio_id"])
    op.create_index(op.f("ix_ops_item_variante_item_id"), "ops_item_variante", ["item_id"])


def downgrade() -> None:
    op.drop_table("ops_item_variante")
    op.drop_table("ops_item")
    op.drop_table("ops_categoria")
