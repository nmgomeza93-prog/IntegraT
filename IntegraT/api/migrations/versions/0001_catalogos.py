"""Catálogos globales (cat_) y regímenes fiscales (fiscal_cfg_regimen).

Revisión: 0001
Anterior: ninguna
Creada: 2026-11-23

REGLA: una migración aplicada NUNCA se edita. Para corregir, crea otra.
MySQL no tiene DDL transaccional: si falla a mitad, revisa y limpia antes de reintentar.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

OPC = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_0900_ai_ci"}
DT = mysql.DATETIME(fsp=6)
BOOL = sa.Boolean(create_constraint=False)


def _tiempo():
    return [
        sa.Column("creado_en", DT, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(6)")),
        sa.Column("actualizado_en", DT, nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)")),
    ]


def _fk(tabla, columna, destino):
    t, c = destino.split(".")
    return sa.ForeignKeyConstraint([columna], [destino], name=op.f(f"fk_{tabla}_{columna}"))


def _ix(tabla, *columnas):
    op.create_index(op.f(f"ix_{tabla}_{'_'.join(columnas)}"), tabla, list(columnas))


def upgrade() -> None:
    op.create_table(
        "cat_moneda",
        sa.Column("codigo", sa.CHAR(3), primary_key=True, comment="ISO-4217"),
        sa.Column("nombre", sa.String(60), nullable=False),
        sa.Column("simbolo", sa.String(5), nullable=False),
        sa.Column("decimales", sa.SmallInteger(), nullable=False, server_default=sa.text("2")),
        *_tiempo(),
        comment="Monedas (catálogo global)", **OPC,
    )

    op.create_table(
        "cat_pais",
        sa.Column("codigo", sa.CHAR(2), primary_key=True, comment="ISO-3166-1 alfa-2"),
        sa.Column("nombre", sa.String(80), nullable=False),
        sa.Column("moneda_codigo", sa.CHAR(3), nullable=False),
        sa.Column("zona_horaria_defecto", sa.String(40), nullable=False),
        sa.Column("nombre_id_fiscal", sa.String(10), nullable=False, comment="Ej. NIT"),
        sa.Column("activo", BOOL, nullable=False, server_default=sa.text("1")),
        *_tiempo(),
        _fk("cat_pais", "moneda_codigo", "cat_moneda.codigo"),
        comment="Países (catálogo global)", **OPC,
    )
    _ix("cat_pais", "moneda_codigo")

    op.create_table(
        "cat_unidad_medida",
        sa.Column("codigo", sa.String(10), primary_key=True),
        sa.Column("nombre", sa.String(40), nullable=False),
        sa.Column("tipo", sa.String(10), nullable=False),
        sa.Column("unidad_base_codigo", sa.String(10), nullable=True),
        sa.Column("factor_a_base", sa.Numeric(20, 10), nullable=True,
                  comment="Nulo = depende del producto (ej. CAJA)"),
        sa.Column("codigo_fel", sa.String(10), nullable=True, comment="Pendiente: catálogo SAT"),
        *_tiempo(),
        _fk("cat_unidad_medida", "unidad_base_codigo", "cat_unidad_medida.codigo"),
        sa.CheckConstraint("tipo IN ('unidad','masa','volumen')",
                           name=op.f("ck_cat_unidad_medida_tipo")),
        comment="Unidades de medida y su conversión a la unidad base", **OPC,
    )
    _ix("cat_unidad_medida", "unidad_base_codigo")

    op.create_table(
        "cat_division_territorial",
        sa.Column("codigo", sa.String(12), primary_key=True,
                  comment="Ej. GT-01 (depto), GT-0101"),
        sa.Column("pais_codigo", sa.CHAR(2), nullable=False),
        sa.Column("nivel", sa.SmallInteger(), nullable=False,
                  comment="1=departamento, 2=municipio"),
        sa.Column("nombre", sa.String(80), nullable=False),
        sa.Column("padre_codigo", sa.String(12), nullable=True),
        *_tiempo(),
        _fk("cat_division_territorial", "pais_codigo", "cat_pais.codigo"),
        _fk("cat_division_territorial", "padre_codigo", "cat_division_territorial.codigo"),
        sa.CheckConstraint("nivel IN (1,2)", name=op.f("ck_cat_division_territorial_nivel")),
        comment="Divisiones territoriales por país", **OPC,
    )
    _ix("cat_division_territorial", "pais_codigo")
    _ix("cat_division_territorial", "padre_codigo")

    op.create_table(
        "cat_tipo_negocio",
        sa.Column("codigo", sa.String(40), primary_key=True),
        sa.Column("nombre", sa.String(80), nullable=False),
        sa.Column("descripcion", sa.String(255), nullable=False),
        sa.Column("icono", sa.String(40), nullable=False),
        sa.Column("orden", sa.SmallInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("activo", BOOL, nullable=False, server_default=sa.text("1")),
        *_tiempo(),
        comment="Tipos de negocio (perfiles de configuración)", **OPC,
    )

    op.create_table(
        "cat_canal_venta_base",
        sa.Column("codigo", sa.String(40), primary_key=True),
        sa.Column("nombre", sa.String(60), nullable=False),
        sa.Column("icono", sa.String(40), nullable=False),
        sa.Column("orden", sa.SmallInteger(), nullable=False, server_default=sa.text("0")),
        *_tiempo(),
        comment="Canales y modalidades de venta base", **OPC,
    )

    op.create_table(
        "fiscal_cfg_regimen",
        sa.Column("codigo", sa.String(40), primary_key=True),
        sa.Column("pais_codigo", sa.CHAR(2), nullable=False),
        sa.Column("impuesto", sa.String(10), nullable=False),
        sa.Column("nombre", sa.String(120), nullable=False),
        sa.Column("nombre_simple", sa.String(120), nullable=False),
        sa.Column("usa_credito_fiscal", BOOL, nullable=False, server_default=sa.text("0")),
        sa.Column("parametros", sa.JSON(), nullable=True),
        sa.Column("validado_por_contador", BOOL, nullable=False, server_default=sa.text("0"),
                  comment="Ver docs/REVISION_CONTADOR.md"),
        sa.Column("vigente_desde", sa.Date(), nullable=False),
        *_tiempo(),
        _fk("fiscal_cfg_regimen", "pais_codigo", "cat_pais.codigo"),
        sa.CheckConstraint("impuesto IN ('IVA','ISR','NINGUNO')",
                           name=op.f("ck_fiscal_cfg_regimen_impuesto")),
        comment="Regímenes fiscales por país (parámetros a validar por el contador)", **OPC,
    )
    _ix("fiscal_cfg_regimen", "pais_codigo")


def downgrade() -> None:
    for tabla in (
        "fiscal_cfg_regimen", "cat_canal_venta_base", "cat_tipo_negocio",
        "cat_division_territorial", "cat_unidad_medida", "cat_pais", "cat_moneda",
    ):
        op.drop_table(tabla)
