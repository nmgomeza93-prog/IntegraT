"""Mercadería para revender: un insumo puede estar ligado a un producto.

Revisión: 0012
Anterior: 0011
Creada: 2026-11-24

El producto que se compra hecho se maneja con un insumo en unidades más una receta de 1 unidad
(docs/PLAN_COMPRAS.md). `item_id` marca ese insumo como la mercadería de un producto.
REGLA: una migración aplicada NUNCA se edita. Para corregir, crea otra.
"""
import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ops_insumo", sa.Column(
        "item_id", sa.BINARY(16), nullable=True,
        comment="Producto del que este insumo es la mercadería (se compra hecho para revenderlo)"))
    op.create_foreign_key(op.f("fk_ops_insumo_item_id"), "ops_insumo", "ops_item",
                          ["item_id"], ["id"])
    op.create_index(op.f("ix_ops_insumo_item_id"), "ops_insumo", ["item_id"])


def downgrade() -> None:
    op.drop_constraint(op.f("fk_ops_insumo_item_id"), "ops_insumo", type_="foreignkey")
    op.drop_index(op.f("ix_ops_insumo_item_id"), table_name="ops_insumo")
    op.drop_column("ops_insumo", "item_id")
