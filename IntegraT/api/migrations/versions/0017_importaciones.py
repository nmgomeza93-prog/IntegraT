"""Importaciones (compras SHEIN/TEMU por casillero) con su rastreo.

Revisión: 0017
Anterior: 0016
Creada: 2026-11-25

docs/PLAN_IMPORTACION.md. Una importación se pide (en camino) y se recibe; cada línea guarda lo que
costó en la moneda de la factura, su parte en Q y el costo puesto en Guatemala.
REGLA: una migración aplicada NUNCA se edita. Para corregir, crea otra.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

OPC = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_0900_ai_ci"}
DT = mysql.DATETIME(fsp=6)
UUID = sa.BINARY(16)
AHORA = sa.text("CURRENT_TIMESTAMP(6)")
AHORA_UPD = sa.text("CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)")
ORIGEN = sa.Numeric(14, 4)  # montos en la moneda de la factura
DINERO = sa.Numeric(14, 2)


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
        "ops_importacion",
        sa.Column("id", UUID, primary_key=True, comment="UUIDv7 generado por la API"),
        sa.Column("negocio_id", UUID, nullable=False),
        sa.Column("plataforma", sa.String(30), nullable=False),
        sa.Column("numero_factura", sa.String(60), nullable=True),
        sa.Column("numero_orden", sa.String(60), nullable=True),
        sa.Column("fecha_factura", sa.Date(), nullable=True),
        sa.Column("moneda_codigo", sa.CHAR(3), nullable=False),
        sa.Column("garantia_envio", ORIGEN, nullable=False, server_default=sa.text("0")),
        sa.Column("costo_importacion", ORIGEN, nullable=False, server_default=sa.text("0")),
        sa.Column("otros_cobros", ORIGEN, nullable=False, server_default=sa.text("0")),
        sa.Column("total_origen", ORIGEN, nullable=False, comment="Líneas + cargos, en su moneda"),
        sa.Column("tipo_cambio", sa.Numeric(18, 8), nullable=False, comment="Q por unidad"),
        sa.Column("total_q", DINERO, nullable=False, comment="Lo que se pagó en Q"),
        sa.Column("medio_pago", sa.String(20), nullable=False),
        sa.Column("estado", sa.String(20), nullable=False, server_default="en_camino"),
        sa.Column("recibida_en", DT, nullable=True),
        sa.Column("guia", sa.String(60), nullable=True),
        sa.Column("courier_q", DINERO, nullable=True),
        sa.Column("envio_local_q", DINERO, nullable=True),
        sa.Column("medio_pago_courier", sa.String(20), nullable=True),
        sa.Column("nota", sa.String(200), nullable=True),
        sa.Column("anulada_en", DT, nullable=True),
        sa.Column("anulada_por", UUID, nullable=True),
        sa.Column("motivo_anulacion", sa.String(200), nullable=True),
        *_auditoria(),
        _fk("ops_importacion", "negocio_id", "core_negocio.id"),
        _fk("ops_importacion", "moneda_codigo", "cat_moneda.codigo"),
        sa.CheckConstraint("estado IN ('en_camino','recibida','recibida_parcial','anulada')",
                           name=op.f("ck_ops_importacion_estado")),
        sa.CheckConstraint("medio_pago IN ('efectivo','tarjeta','transferencia')",
                           name=op.f("ck_ops_importacion_medio_pago")),
        sa.CheckConstraint("tipo_cambio > 0", name=op.f("ck_ops_importacion_tipo_cambio")),
        comment="Importaciones (pedido en camino y su recepción) con su rastreo", **OPC,
    )
    op.create_index(op.f("ix_ops_importacion_negocio_id_estado"), "ops_importacion",
                    ["negocio_id", "estado"])
    op.create_index(op.f("ix_ops_importacion_moneda_codigo"), "ops_importacion", ["moneda_codigo"])

    op.create_table(
        "ops_importacion_linea",
        sa.Column("id", UUID, primary_key=True, comment="UUIDv7 generado por la API"),
        sa.Column("negocio_id", UUID, nullable=False),
        sa.Column("importacion_id", UUID, nullable=False),
        sa.Column("producto_nombre", sa.String(120), nullable=False),
        sa.Column("categoria_nombre", sa.String(80), nullable=True),
        sa.Column("codigo", sa.String(60), nullable=True),
        sa.Column("descripcion", sa.String(500), nullable=True),
        sa.Column("atributos", sa.JSON(), nullable=True),
        sa.Column("item_id", UUID, nullable=True),
        sa.Column("item_variante_id", UUID, nullable=True),
        sa.Column("cantidad", sa.Integer(), nullable=False),
        sa.Column("precio_unitario", ORIGEN, nullable=False, comment="En la moneda de la factura"),
        sa.Column("cargos_origen", ORIGEN, nullable=False, server_default=sa.text("0"),
                  comment="Su parte de garantía, importación y otros cobros"),
        sa.Column("costo_pedido_q", DINERO, nullable=False, comment="Su parte de lo pagado en Q"),
        sa.Column("cantidad_recibida", sa.Integer(), nullable=True),
        sa.Column("courier_q", DINERO, nullable=True, comment="Su parte del courier y envío local"),
        sa.Column("costo_unitario_q", sa.Numeric(18, 8), nullable=True,
                  comment="Puesto en Guatemala, por unidad recibida"),
        sa.Column("orden", sa.SmallInteger(), nullable=False, server_default=sa.text("0")),
        *_auditoria(),
        _fk("ops_importacion_linea", "negocio_id", "core_negocio.id"),
        _fk("ops_importacion_linea", "importacion_id", "ops_importacion.id"),
        _fk("ops_importacion_linea", "item_id", "ops_item.id"),
        _fk("ops_importacion_linea", "item_variante_id", "ops_item_variante.id"),
        sa.CheckConstraint("cantidad > 0", name=op.f("ck_ops_importacion_linea_cantidad")),
        comment="Líneas de una importación (una por talla/color)", **OPC,
    )
    op.create_index(op.f("ix_ops_importacion_linea_negocio_id"), "ops_importacion_linea",
                    ["negocio_id"])
    op.create_index(op.f("ix_ops_importacion_linea_importacion_id"), "ops_importacion_linea",
                    ["importacion_id"])
    op.create_index(op.f("ix_ops_importacion_linea_item_id"), "ops_importacion_linea", ["item_id"])
    op.create_index(op.f("ix_ops_importacion_linea_item_variante_id"), "ops_importacion_linea",
                    ["item_variante_id"])


def downgrade() -> None:
    op.drop_table("ops_importacion_linea")
    op.drop_table("ops_importacion")
