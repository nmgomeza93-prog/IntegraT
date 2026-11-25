"""Variantes de verdad: atributos del negocio (talla, color…), atributos por categoría, y variante,
mercadería y receta por variante.

Revisión: 0016
Anterior: 0015
Creada: 2026-11-25

docs/PLAN_VARIANTES.md. `ops_item_variante.atributos` nulo = la variante implícita ("Única").
REGLA: una migración aplicada NUNCA se edita. Para corregir, crea otra.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "0016"
down_revision = "0015"
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
        "ops_atributo",
        sa.Column("id", UUID, primary_key=True, comment="UUIDv7 generado por la API"),
        sa.Column("negocio_id", UUID, nullable=False),
        sa.Column("nombre", sa.String(40), nullable=False),
        sa.Column("orden", sa.SmallInteger(), nullable=False, server_default=sa.text("0")),
        *_auditoria(),
        _fk("ops_atributo", "negocio_id", "core_negocio.id"),
        comment="Atributos de variante del negocio (talla, color…)", **OPC,
    )
    op.create_index(op.f("ix_ops_atributo_negocio_id"), "ops_atributo", ["negocio_id"])

    op.create_table(
        "ops_atributo_valor",
        sa.Column("id", UUID, primary_key=True, comment="UUIDv7 generado por la API"),
        sa.Column("negocio_id", UUID, nullable=False),
        sa.Column("atributo_id", UUID, nullable=False),
        sa.Column("valor", sa.String(40), nullable=False),
        sa.Column("orden", sa.SmallInteger(), nullable=False, server_default=sa.text("0")),
        *_auditoria(),
        _fk("ops_atributo_valor", "negocio_id", "core_negocio.id"),
        _fk("ops_atributo_valor", "atributo_id", "ops_atributo.id"),
        comment="Valores de un atributo (S, M, L; Negro, Rosa…)", **OPC,
    )
    op.create_index(op.f("ix_ops_atributo_valor_negocio_id"), "ops_atributo_valor", ["negocio_id"])
    op.create_index(op.f("ix_ops_atributo_valor_atributo_id"), "ops_atributo_valor",
                    ["atributo_id"])

    op.create_table(
        "ops_categoria_atributo",
        sa.Column("id", UUID, primary_key=True, comment="UUIDv7 generado por la API"),
        sa.Column("negocio_id", UUID, nullable=False),
        sa.Column("categoria_id", UUID, nullable=False),
        sa.Column("atributo_id", UUID, nullable=False),
        sa.Column("orden", sa.SmallInteger(), nullable=False, server_default=sa.text("0")),
        *_auditoria(),
        _fk("ops_categoria_atributo", "negocio_id", "core_negocio.id"),
        _fk("ops_categoria_atributo", "categoria_id", "ops_categoria.id"),
        _fk("ops_categoria_atributo", "atributo_id", "ops_atributo.id"),
        comment="Qué atributos usan los productos de cada categoría", **OPC,
    )
    op.create_index(op.f("ix_ops_categoria_atributo_negocio_id"), "ops_categoria_atributo",
                    ["negocio_id"])
    op.create_index(op.f("ix_ops_categoria_atributo_categoria_id"), "ops_categoria_atributo",
                    ["categoria_id"])
    op.create_index(op.f("ix_ops_categoria_atributo_atributo_id"), "ops_categoria_atributo",
                    ["atributo_id"])

    op.add_column("ops_categoria", sa.Column(
        "palabras_clave", sa.JSON(), nullable=True,
        comment="Para sugerir la categoría de un producto importado"))
    op.add_column("ops_item_variante", sa.Column(
        "codigo", sa.String(60), nullable=True, comment="Código del proveedor (SKC) o SKU"))
    op.add_column("ops_item_variante", sa.Column(
        "atributos", sa.JSON(), nullable=True, comment="Ej. {Talla: M, Color: Rosa}; nulo = Única"))
    op.add_column("ops_insumo", sa.Column(
        "item_variante_id", UUID, nullable=True,
        comment="Variante de la que este insumo es la mercadería"))
    op.create_foreign_key(op.f("fk_ops_insumo_item_variante_id"), "ops_insumo",
                          "ops_item_variante", ["item_variante_id"], ["id"])
    op.create_index(op.f("ix_ops_insumo_item_variante_id"), "ops_insumo", ["item_variante_id"])
    op.add_column("ops_receta_linea", sa.Column(
        "item_variante_id", UUID, nullable=True, comment="Nulo = la línea es de todas las variantes"))
    op.create_foreign_key(op.f("fk_ops_receta_linea_item_variante_id"), "ops_receta_linea",
                          "ops_item_variante", ["item_variante_id"], ["id"])
    op.create_index(op.f("ix_ops_receta_linea_item_variante_id"), "ops_receta_linea",
                    ["item_variante_id"])


def downgrade() -> None:
    op.drop_constraint(op.f("fk_ops_receta_linea_item_variante_id"), "ops_receta_linea",
                       type_="foreignkey")
    op.drop_index(op.f("ix_ops_receta_linea_item_variante_id"), table_name="ops_receta_linea")
    op.drop_column("ops_receta_linea", "item_variante_id")
    op.drop_constraint(op.f("fk_ops_insumo_item_variante_id"), "ops_insumo", type_="foreignkey")
    op.drop_index(op.f("ix_ops_insumo_item_variante_id"), table_name="ops_insumo")
    op.drop_column("ops_insumo", "item_variante_id")
    op.drop_column("ops_item_variante", "atributos")
    op.drop_column("ops_item_variante", "codigo")
    op.drop_column("ops_categoria", "palabras_clave")
    op.drop_table("ops_categoria_atributo")
    op.drop_table("ops_atributo_valor")
    op.drop_table("ops_atributo")
