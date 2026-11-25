"""Margen objetivo propio de un platillo o producto (para el precio sugerido).

Revisión: 0015
Anterior: 0014
Creada: 2026-11-25

Nulo = usa el margen objetivo del negocio (`core_negocio.margen_objetivo_defecto`).
docs/PLAN_PRECIO_SUGERIDO.md. REGLA: una migración aplicada NUNCA se edita.
"""
import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ops_item", sa.Column(
        "margen_objetivo", sa.Numeric(5, 4), nullable=True,
        comment="Margen objetivo propio (nulo = el del negocio)"))
    op.create_check_constraint(op.f("ck_ops_item_margen_objetivo"), "ops_item",
                               "margen_objetivo IS NULL OR "
                               "(margen_objetivo >= 0 AND margen_objetivo <= 0.9)")


def downgrade() -> None:
    op.drop_constraint(op.f("ck_ops_item_margen_objetivo"), "ops_item", type_="check")
    op.drop_column("ops_item", "margen_objetivo")
