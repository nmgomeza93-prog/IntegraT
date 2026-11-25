"""Motor contable: roles, plantillas del plan de cuentas, reglas, plan por negocio y asientos.

Revisión: 0013
Anterior: 0012
Creada: 2026-11-25

Libros por negocio (docs/PLAN_CONTABILIDAD.md). Los asientos y sus líneas son inmutables: se
corrigen con un reverso. MySQL no tiene restricciones diferidas: el cuadre lo valida la API dentro
de la transacción. `ops_gasto.con_factura` decide si el gasto lleva IVA por cobrar (régimen general).
REGLA: una migración aplicada NUNCA se edita. Para corregir, crea otra.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

OPC = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_0900_ai_ci"}
DT = mysql.DATETIME(fsp=6)
UUID = sa.BINARY(16)
AHORA = sa.text("CURRENT_TIMESTAMP(6)")
AHORA_UPD = sa.text("CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)")
DINERO = sa.Numeric(14, 2)


def _tiempo() -> list[sa.Column]:
    return [
        sa.Column("creado_en", DT, nullable=False, server_default=AHORA),
        sa.Column("actualizado_en", DT, nullable=False, server_default=AHORA_UPD),
    ]


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


def _fk(tabla: str, columna: str, destino: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint([columna], [destino], name=op.f(f"fk_{tabla}_{columna}"))


def upgrade() -> None:
    op.create_table(
        "cont_cfg_rol_cuenta",
        sa.Column("codigo", sa.String(40), primary_key=True),
        sa.Column("descripcion_simple", sa.String(120), nullable=False),
        sa.Column("naturaleza", sa.String(10), nullable=False),
        *_tiempo(),
        sa.CheckConstraint("naturaleza IN ('deudora','acreedora')",
                           name=op.f("ck_cont_cfg_rol_cuenta_naturaleza")),
        comment="Roles de cuenta que usa el motor (global)", **OPC,
    )

    op.create_table(
        "cont_cfg_plantilla_plan_cuentas",
        sa.Column("pais_codigo", sa.CHAR(2), primary_key=True),
        sa.Column("tipo_negocio_codigo", sa.String(40), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("contenido", sa.JSON(), nullable=False),
        *_tiempo(),
        _fk("cont_cfg_plantilla_plan_cuentas", "pais_codigo", "cat_pais.codigo"),
        _fk("cont_cfg_plantilla_plan_cuentas", "tipo_negocio_codigo", "cat_tipo_negocio.codigo"),
        comment="Plan de cuentas de ejemplo por país y tipo de negocio", **OPC,
    )
    op.create_index(op.f("ix_cont_cfg_plantilla_plan_cuentas_tipo_negocio_codigo"),
                    "cont_cfg_plantilla_plan_cuentas", ["tipo_negocio_codigo"])

    op.create_table(
        "cont_cfg_regla_contable",
        sa.Column("codigo", sa.String(60), primary_key=True),
        sa.Column("pais_codigo", sa.CHAR(2), nullable=False),
        sa.Column("tipo_evento", sa.String(30), nullable=False),
        sa.Column("tratamiento_iva", sa.String(12), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("vigente_desde", sa.Date(), nullable=False),
        sa.Column("descripcion_simple", sa.String(120), nullable=False),
        sa.Column("lineas", sa.JSON(), nullable=False),
        *_tiempo(),
        _fk("cont_cfg_regla_contable", "pais_codigo", "cat_pais.codigo"),
        sa.CheckConstraint("tratamiento_iva IN ('separado','sin_separar')",
                           name=op.f("ck_cont_cfg_regla_contable_tratamiento_iva")),
        comment="Reglas contables: evento -> líneas por rol de cuenta (a validar por el contador)",
        **OPC,
    )
    op.create_index(op.f("ix_cont_cfg_regla_contable_pais_codigo_tipo_evento_tratamiento_iva"),
                    "cont_cfg_regla_contable", ["pais_codigo", "tipo_evento", "tratamiento_iva"])

    op.create_table(
        "cont_libro",
        sa.Column("id", UUID, primary_key=True, comment="UUIDv7 generado por la API"),
        sa.Column("negocio_id", UUID, nullable=False),
        sa.Column("ultimo_numero", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("plan_version", sa.Integer(), nullable=True,
                  comment="Versión de la plantilla con que se sembró el plan"),
        *_auditoria(),
        _fk("cont_libro", "negocio_id", "core_negocio.id"),
        sa.UniqueConstraint("negocio_id", name=op.f("uq_cont_libro_negocio_id")),
        comment="Libro de cada negocio: numera los asientos", **OPC,
    )

    op.create_table(
        "cont_cuenta_contable",
        sa.Column("id", UUID, primary_key=True, comment="UUIDv7 generado por la API"),
        sa.Column("negocio_id", UUID, nullable=False),
        sa.Column("codigo", sa.String(20), nullable=False),
        sa.Column("nombre", sa.String(120), nullable=False),
        sa.Column("nombre_simple", sa.String(120), nullable=True),
        sa.Column("tipo", sa.String(12), nullable=False),
        sa.Column("naturaleza", sa.String(10), nullable=False),
        sa.Column("padre_id", UUID, nullable=True),
        sa.Column("acepta_movimientos", sa.Boolean(create_constraint=False), nullable=False,
                  server_default=sa.text("1")),
        sa.Column("rol_cuenta_codigo", sa.String(40), nullable=True),
        *_auditoria(),
        _fk("cont_cuenta_contable", "negocio_id", "core_negocio.id"),
        _fk("cont_cuenta_contable", "padre_id", "cont_cuenta_contable.id"),
        _fk("cont_cuenta_contable", "rol_cuenta_codigo", "cont_cfg_rol_cuenta.codigo"),
        sa.UniqueConstraint("negocio_id", "codigo",
                            name=op.f("uq_cont_cuenta_contable_negocio_id_codigo")),
        sa.CheckConstraint(
            "tipo IN ('activo','pasivo','patrimonio','ingreso','costo','gasto')",
            name=op.f("ck_cont_cuenta_contable_tipo")),
        sa.CheckConstraint("naturaleza IN ('deudora','acreedora')",
                           name=op.f("ck_cont_cuenta_contable_naturaleza")),
        comment="Plan de cuentas propio de cada negocio", **OPC,
    )
    op.create_index(op.f("ix_cont_cuenta_contable_padre_id"), "cont_cuenta_contable",
                    ["padre_id"])
    op.create_index(op.f("ix_cont_cuenta_contable_rol_cuenta_codigo"), "cont_cuenta_contable",
                    ["rol_cuenta_codigo"])

    op.create_table(
        "cont_asiento",
        sa.Column("id", UUID, primary_key=True, comment="UUIDv7 generado por la API"),
        sa.Column("negocio_id", UUID, nullable=False),
        sa.Column("numero", sa.Integer(), nullable=False, comment="Consecutivo por negocio"),
        sa.Column("fecha", sa.Date(), nullable=False, comment="Día contable (calendario local)"),
        sa.Column("descripcion_simple", sa.String(200), nullable=False),
        sa.Column("tipo_evento", sa.String(30), nullable=False),
        sa.Column("origen_tipo", sa.String(20), nullable=True),
        sa.Column("origen_id", UUID, nullable=True),
        sa.Column("regla_codigo", sa.String(60), nullable=True),
        sa.Column("regla_version", sa.Integer(), nullable=True),
        sa.Column("tratamiento_iva", sa.String(12), nullable=True),
        sa.Column("reverso_de_asiento_id", UUID, nullable=True),
        sa.Column("creado_en", DT, nullable=False, server_default=AHORA),
        sa.Column("creado_por", UUID, nullable=True),
        _fk("cont_asiento", "negocio_id", "core_negocio.id"),
        _fk("cont_asiento", "reverso_de_asiento_id", "cont_asiento.id"),
        sa.UniqueConstraint("negocio_id", "numero", name=op.f("uq_cont_asiento_negocio_id_numero")),
        comment="Asientos contables (inmutables; se corrigen con un reverso)", **OPC,
    )
    op.create_index(op.f("ix_cont_asiento_negocio_id_fecha"), "cont_asiento",
                    ["negocio_id", "fecha"])
    op.create_index(op.f("ix_cont_asiento_origen_id"), "cont_asiento", ["origen_id"])
    op.create_index(op.f("ix_cont_asiento_reverso_de_asiento_id"), "cont_asiento",
                    ["reverso_de_asiento_id"])

    op.create_table(
        "cont_asiento_linea",
        sa.Column("id", UUID, primary_key=True, comment="UUIDv7 generado por la API"),
        sa.Column("negocio_id", UUID, nullable=False),
        sa.Column("asiento_id", UUID, nullable=False),
        sa.Column("cuenta_contable_id", UUID, nullable=False),
        sa.Column("debe", DINERO, nullable=False, server_default=sa.text("0")),
        sa.Column("haber", DINERO, nullable=False, server_default=sa.text("0")),
        sa.Column("concepto", sa.String(120), nullable=True),
        sa.Column("creado_en", DT, nullable=False, server_default=AHORA),
        sa.Column("creado_por", UUID, nullable=True),
        _fk("cont_asiento_linea", "negocio_id", "core_negocio.id"),
        _fk("cont_asiento_linea", "asiento_id", "cont_asiento.id"),
        _fk("cont_asiento_linea", "cuenta_contable_id", "cont_cuenta_contable.id"),
        sa.CheckConstraint("(debe > 0 AND haber = 0) OR (debe = 0 AND haber > 0)",
                           name=op.f("ck_cont_asiento_linea_debe_o_haber")),
        comment="Líneas de un asiento (inmutables)", **OPC,
    )
    op.create_index(op.f("ix_cont_asiento_linea_negocio_id"), "cont_asiento_linea",
                    ["negocio_id"])
    op.create_index(op.f("ix_cont_asiento_linea_asiento_id"), "cont_asiento_linea",
                    ["asiento_id"])
    op.create_index(op.f("ix_cont_asiento_linea_cuenta_contable_id"), "cont_asiento_linea",
                    ["cuenta_contable_id"])

    op.add_column("ops_gasto", sa.Column(
        "con_factura", sa.Boolean(create_constraint=False), nullable=False,
        server_default=sa.text("0"), comment="Trae factura (IVA por cobrar en el régimen general)"))


def downgrade() -> None:
    op.drop_column("ops_gasto", "con_factura")
    op.drop_table("cont_asiento_linea")
    op.drop_table("cont_asiento")
    op.drop_table("cont_cuenta_contable")
    op.drop_table("cont_libro")
    op.drop_table("cont_cfg_regla_contable")
    op.drop_table("cont_cfg_plantilla_plan_cuentas")
    op.drop_table("cont_cfg_rol_cuenta")
