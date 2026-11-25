"""Regla del negocio para vender sin existencia: bloquear o solo avisar.

Revisión: 0019
Anterior: 0018
Creada: 2026-11-25

docs/ANALISIS_INVENTARIO_Y_CLIENTES.md: las tiendas en línea bloquean por defecto; los restaurantes avisan.
REGLA: una migración aplicada NUNCA se edita. Para corregir, crea otra.
"""
import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("core_negocio", sa.Column(
        "vender_sin_existencia", sa.String(10), nullable=False, server_default="avisar",
        comment="bloquear: no se cobra lo que no hay; avisar: se cobra y se avisa"))
    op.create_check_constraint(op.f("ck_core_negocio_vender_sin_existencia"), "core_negocio",
                               "vender_sin_existencia IN ('bloquear','avisar')")
    op.execute("UPDATE core_negocio SET vender_sin_existencia = 'bloquear' "
               "WHERE tipo_negocio_codigo = 'ventas_en_linea'")


def downgrade() -> None:
    op.drop_constraint(op.f("ck_core_negocio_vender_sin_existencia"), "core_negocio", type_="check")
    op.drop_column("core_negocio", "vender_sin_existencia")
