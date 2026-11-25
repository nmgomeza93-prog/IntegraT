"""Mínimo de existencia por defecto del negocio (alerta "por agotarse").

Revisión: 0020
Anterior: 0019
Creada: 2026-11-25

La mercadería nueva nace con este mínimo (en unidades); cada insumo puede tener el suyo
(docs/ANALISIS_INVENTARIO_Y_CLIENTES.md, paso V2).
REGLA: una migración aplicada NUNCA se edita. Para corregir, crea otra.
"""
import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("core_negocio", sa.Column(
        "minimo_defecto", sa.Numeric(10, 2), nullable=False, server_default=sa.text("0"),
        comment="Unidades con que la mercadería nueva avisa 'por agotarse'"))
    op.create_check_constraint(op.f("ck_core_negocio_minimo_defecto"), "core_negocio",
                               "minimo_defecto >= 0")
    op.execute("UPDATE core_negocio SET minimo_defecto = 2 "
               "WHERE tipo_negocio_codigo = 'ventas_en_linea'")


def downgrade() -> None:
    op.drop_constraint(op.f("ck_core_negocio_minimo_defecto"), "core_negocio", type_="check")
    op.drop_column("core_negocio", "minimo_defecto")
