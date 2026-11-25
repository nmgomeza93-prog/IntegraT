"""Importaciones: varias entregas por importación y reparto del courier por peso.

Revisión: 0018
Anterior: 0017
Creada: 2026-11-25

Cada "Me llegó el paquete" es una entrega (`ops_importacion_recepcion`) con lo que llegó de cada
línea; la importación queda "llegando" mientras falte algo (docs/PLAN_IMPORTACION.md).
REGLA: una migración aplicada NUNCA se edita. Para corregir, crea otra.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None

OPC = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_0900_ai_ci"}
DT = mysql.DATETIME(fsp=6)
UUID = sa.BINARY(16)
AHORA = sa.text("CURRENT_TIMESTAMP(6)")
AHORA_UPD = sa.text("CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)")
DINERO = sa.Numeric(14, 2)
CK_ESTADO = op.f("ck_ops_importacion_estado")
ESTADOS_ANTES = "('en_camino','recibida','recibida_parcial','anulada')"
ESTADOS_AHORA = "('en_camino','llegando','recibida','recibida_parcial','anulada')"


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
    op.drop_constraint(CK_ESTADO, "ops_importacion", type_="check")
    op.create_check_constraint(CK_ESTADO, "ops_importacion", f"estado IN {ESTADOS_AHORA}")
    op.add_column("ops_importacion_linea", sa.Column(
        "peso", sa.Numeric(12, 3), nullable=True,
        comment="Peso de la línea (cualquier unidad; solo importa la proporción)"))
    op.add_column("ops_importacion_linea", sa.Column(
        "cantidad_perdida", sa.Integer(), nullable=True, comment="Lo que ya no va a llegar"))

    op.create_table(
        "ops_importacion_recepcion",
        sa.Column("id", UUID, primary_key=True, comment="UUIDv7 generado por la API"),
        sa.Column("negocio_id", UUID, nullable=False),
        sa.Column("importacion_id", UUID, nullable=False),
        sa.Column("numero", sa.SmallInteger(), nullable=False, comment="1, 2, 3… por importación"),
        sa.Column("recibida_en", DT, nullable=False),
        sa.Column("guia", sa.String(60), nullable=True),
        sa.Column("courier_q", DINERO, nullable=False, server_default=sa.text("0")),
        sa.Column("envio_local_q", DINERO, nullable=False, server_default=sa.text("0")),
        sa.Column("medio_pago", sa.String(20), nullable=False),
        sa.Column("reparto", sa.String(10), nullable=False, server_default="valor"),
        sa.Column("cierra", sa.Boolean(create_constraint=False), nullable=False,
                  server_default=sa.text("0"), comment="Lo que faltaba se dio por perdido"),
        *_auditoria(),
        _fk("ops_importacion_recepcion", "negocio_id", "core_negocio.id"),
        _fk("ops_importacion_recepcion", "importacion_id", "ops_importacion.id"),
        sa.CheckConstraint("reparto IN ('valor','peso')",
                           name=op.f("ck_ops_importacion_recepcion_reparto")),
        comment="Entregas de una importación (cada paquete que llega)", **OPC,
    )
    op.create_index(op.f("ix_ops_importacion_recepcion_negocio_id"), "ops_importacion_recepcion",
                    ["negocio_id"])
    op.create_index(op.f("ix_ops_importacion_recepcion_importacion_id"),
                    "ops_importacion_recepcion", ["importacion_id"])

    op.create_table(
        "ops_importacion_recepcion_linea",
        sa.Column("id", UUID, primary_key=True, comment="UUIDv7 generado por la API"),
        sa.Column("negocio_id", UUID, nullable=False),
        sa.Column("recepcion_id", UUID, nullable=False),
        sa.Column("linea_id", UUID, nullable=False),
        sa.Column("cantidad", sa.Integer(), nullable=False),
        sa.Column("costo_q", DINERO, nullable=False, comment="Su parte de lo pagado en Q"),
        sa.Column("courier_q", DINERO, nullable=False, server_default=sa.text("0")),
        sa.Column("costo_unitario_q", sa.Numeric(18, 8), nullable=False),
        *_auditoria(),
        _fk("ops_importacion_recepcion_linea", "negocio_id", "core_negocio.id"),
        _fk("ops_importacion_recepcion_linea", "recepcion_id", "ops_importacion_recepcion.id"),
        _fk("ops_importacion_recepcion_linea", "linea_id", "ops_importacion_linea.id"),
        sa.CheckConstraint("cantidad > 0", name=op.f("ck_ops_importacion_recepcion_linea_cantidad")),
        comment="Lo que llegó de cada línea en una entrega", **OPC,
    )
    op.create_index(op.f("ix_ops_importacion_recepcion_linea_negocio_id"),
                    "ops_importacion_recepcion_linea", ["negocio_id"])
    op.create_index(op.f("ix_ops_importacion_recepcion_linea_recepcion_id"),
                    "ops_importacion_recepcion_linea", ["recepcion_id"])
    op.create_index(op.f("ix_ops_importacion_recepcion_linea_linea_id"),
                    "ops_importacion_recepcion_linea", ["linea_id"])


def downgrade() -> None:
    op.drop_table("ops_importacion_recepcion_linea")
    op.drop_table("ops_importacion_recepcion")
    op.drop_column("ops_importacion_linea", "cantidad_perdida")
    op.drop_column("ops_importacion_linea", "peso")
    op.execute("UPDATE ops_importacion SET estado = 'en_camino' WHERE estado = 'llegando'")
    op.drop_constraint(CK_ESTADO, "ops_importacion", type_="check")
    op.create_check_constraint(CK_ESTADO, "ops_importacion", f"estado IN {ESTADOS_ANTES}")
