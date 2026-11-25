"""Clientes: datos fijos, campos propios del negocio y a quién se le vendió.

Revisión: 0021
Anterior: 0020
Creada: 2026-11-25

docs/ANALISIS_INVENTARIO_Y_CLIENTES.md (paso C1). `ops_venta.cliente_id` nulo = Consumidor final.
REGLA: una migración aplicada NUNCA se edita. Para corregir, crea otra.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "0021"
down_revision = "0020"
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


def _fk(tabla, columna, destino):
    return sa.ForeignKeyConstraint([columna], [destino], name=op.f(f"fk_{tabla}_{columna}"))


def upgrade() -> None:
    op.create_table(
        "ops_cliente",
        sa.Column("id", UUID, primary_key=True, comment="UUIDv7 generado por la API"),
        sa.Column("negocio_id", UUID, nullable=False),
        sa.Column("nombre", sa.String(120), nullable=False),
        sa.Column("telefono", sa.String(20), nullable=True, comment="Normalizado: +50255551234"),
        sa.Column("correo", sa.String(120), nullable=True),
        sa.Column("direccion", sa.String(200), nullable=True),
        sa.Column("tipo_id_fiscal", sa.String(3), nullable=False, server_default="CF"),
        sa.Column("id_fiscal", sa.String(20), nullable=True, comment="NIT o CUI sin guiones"),
        sa.Column("nombre_fiscal", sa.String(120), nullable=True),
        sa.Column("notas", sa.String(300), nullable=True),
        sa.Column("datos", sa.JSON(), nullable=True, comment="Campos propios: {campo_id: valor}"),
        *_auditoria(),
        _fk("ops_cliente", "negocio_id", "core_negocio.id"),
        sa.CheckConstraint("tipo_id_fiscal IN ('CF','NIT','CUI')",
                           name=op.f("ck_ops_cliente_tipo_id_fiscal")),
        comment="Clientes del negocio", **OPC,
    )
    op.create_index(op.f("ix_ops_cliente_negocio_id_nombre"), "ops_cliente",
                    ["negocio_id", "nombre"])
    op.create_index(op.f("ix_ops_cliente_negocio_id_telefono"), "ops_cliente",
                    ["negocio_id", "telefono"])
    op.create_index(op.f("ix_ops_cliente_negocio_id_id_fiscal"), "ops_cliente",
                    ["negocio_id", "id_fiscal"])

    op.create_table(
        "ops_campo_cliente",
        sa.Column("id", UUID, primary_key=True, comment="UUIDv7 generado por la API"),
        sa.Column("negocio_id", UUID, nullable=False),
        sa.Column("nombre", sa.String(40), nullable=False),
        sa.Column("tipo", sa.String(8), nullable=False),
        sa.Column("orden", sa.SmallInteger(), nullable=False, server_default=sa.text("0")),
        *_auditoria(),
        _fk("ops_campo_cliente", "negocio_id", "core_negocio.id"),
        sa.CheckConstraint("tipo IN ('texto','numero','fecha','si_no')",
                           name=op.f("ck_ops_campo_cliente_tipo")),
        comment="Campos de cliente que define el negocio (Instagram, Cumpleaños…)", **OPC,
    )
    op.create_index(op.f("ix_ops_campo_cliente_negocio_id"), "ops_campo_cliente", ["negocio_id"])

    op.add_column("ops_venta", sa.Column("cliente_id", UUID, nullable=True,
                                         comment="Nulo = Consumidor final"))
    op.create_foreign_key(op.f("fk_ops_venta_cliente_id"), "ops_venta", "ops_cliente",
                          ["cliente_id"], ["id"])
    op.create_index(op.f("ix_ops_venta_cliente_id"), "ops_venta", ["cliente_id"])


def downgrade() -> None:
    op.drop_constraint(op.f("fk_ops_venta_cliente_id"), "ops_venta", type_="foreignkey")
    op.drop_index(op.f("ix_ops_venta_cliente_id"), table_name="ops_venta")
    op.drop_column("ops_venta", "cliente_id")
    op.drop_table("ops_campo_cliente")
    op.drop_table("ops_cliente")
