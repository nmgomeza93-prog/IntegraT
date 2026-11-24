"""Núcleo: usuario, titular (NIT), negocio, membresías y configuración por tipo de negocio.

Revisión: 0002
Anterior: 0001
Creada: 2026-11-23

REGLA: una migración aplicada NUNCA se edita. Para corregir, crea otra.
MySQL no tiene DDL transaccional: si falla a mitad, revisa y limpia antes de reintentar.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

OPC = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_0900_ai_ci"}
DT = mysql.DATETIME(fsp=6)
BOOL = sa.Boolean(create_constraint=False)
UUID = sa.BINARY(16)
AHORA = sa.text("CURRENT_TIMESTAMP(6)")
AHORA_UPD = sa.text("CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)")


def _id():
    return sa.Column("id", UUID, primary_key=True, comment="UUIDv7 generado por la API")


def _tiempo():
    return [
        sa.Column("creado_en", DT, nullable=False, server_default=AHORA),
        sa.Column("actualizado_en", DT, nullable=False, server_default=AHORA_UPD),
    ]


def _auditoria():
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


def _uq(tabla, *columnas):
    return sa.UniqueConstraint(*columnas, name=op.f(f"uq_{tabla}_{'_'.join(columnas)}"))


def _ck(tabla, nombre, expresion):
    return sa.CheckConstraint(expresion, name=op.f(f"ck_{tabla}_{nombre}"))


def _ix(tabla, *columnas):
    op.create_index(op.f(f"ix_{tabla}_{'_'.join(columnas)}"), tabla, list(columnas))


def upgrade() -> None:
    op.create_table(
        "core_usuario",
        _id(),
        sa.Column("correo", sa.String(254), nullable=False),
        sa.Column("telefono", sa.String(20), nullable=True),
        sa.Column("nombre", sa.String(120), nullable=False),
        sa.Column("clave_hash", sa.String(255), nullable=False, comment="argon2id"),
        sa.Column("verificado_en", DT, nullable=True),
        sa.Column("ultimo_acceso_en", DT, nullable=True),
        sa.Column("tamano_texto", sa.String(12), nullable=False, server_default="normal"),
        *_auditoria(),
        _uq("core_usuario", "correo"),
        _ck("core_usuario", "tamano_texto", "tamano_texto IN ('normal','grande','muy_grande')"),
        comment="Personas que usan IntegraT", **OPC,
    )

    op.create_table(
        "core_titular",
        _id(),
        sa.Column("pais_codigo", sa.CHAR(2), nullable=False),
        sa.Column("nit", sa.String(20), nullable=True),
        sa.Column("nombre_fiscal", sa.String(200), nullable=True),
        sa.Column("tipo_persona", sa.String(12), nullable=True),
        sa.Column("regimen_iva_codigo", sa.String(40), nullable=True),
        sa.Column("regimen_isr_codigo", sa.String(40), nullable=True),
        sa.Column("afiliacion_iva", sa.String(5), nullable=True, comment="FEL: GEN, PEQ, ..."),
        sa.Column("frases", sa.JSON(), nullable=True, comment="FEL: frases y escenarios"),
        sa.Column("politica_costo_ia", sa.String(12), nullable=False,
                  server_default="capitalizar"),
        sa.Column("estado", sa.String(12), nullable=False, server_default="pendiente"),
        *_auditoria(),
        _fk("core_titular", "pais_codigo", "cat_pais.codigo"),
        _fk("core_titular", "regimen_iva_codigo", "fiscal_cfg_regimen.codigo"),
        _fk("core_titular", "regimen_isr_codigo", "fiscal_cfg_regimen.codigo"),
        _uq("core_titular", "pais_codigo", "nit"),
        _ck("core_titular", "tipo_persona", "tipo_persona IN ('individual','juridica')"),
        _ck("core_titular", "politica_costo_ia", "politica_costo_ia IN ('capitalizar','gasto')"),
        _ck("core_titular", "estado", "estado IN ('pendiente','activo')"),
        comment="Contribuyente (NIT): agrupa negocios solo para lo fiscal consolidado", **OPC,
    )
    _ix("core_titular", "regimen_iva_codigo")
    _ix("core_titular", "regimen_isr_codigo")

    op.create_table(
        "core_negocio",
        _id(),
        sa.Column("titular_id", UUID, nullable=True),
        sa.Column("nombre", sa.String(120), nullable=False),
        sa.Column("nombre_comercial", sa.String(120), nullable=True),
        sa.Column("tipo_negocio_codigo", sa.String(40), nullable=False),
        sa.Column("pais_codigo", sa.CHAR(2), nullable=False),
        sa.Column("zona_horaria", sa.String(40), nullable=False),
        sa.Column("moneda_codigo", sa.CHAR(3), nullable=False),
        sa.Column("codigo_establecimiento_sat", sa.Integer(), nullable=True),
        sa.Column("direccion", sa.String(255), nullable=True),
        sa.Column("division_territorial_codigo", sa.String(12), nullable=True),
        sa.Column("codigo_postal", sa.String(10), nullable=True),
        sa.Column("correo", sa.String(254), nullable=True),
        sa.Column("telefono", sa.String(20), nullable=True),
        sa.Column("logo_imagen_id", UUID, nullable=True),
        sa.Column("margen_objetivo_defecto", sa.Numeric(5, 4), nullable=False,
                  server_default=sa.text("0.3500")),
        sa.Column("estado_onboarding", sa.JSON(), nullable=True),
        *_auditoria(),
        _fk("core_negocio", "titular_id", "core_titular.id"),
        _fk("core_negocio", "tipo_negocio_codigo", "cat_tipo_negocio.codigo"),
        _fk("core_negocio", "pais_codigo", "cat_pais.codigo"),
        _fk("core_negocio", "moneda_codigo", "cat_moneda.codigo"),
        _fk("core_negocio", "division_territorial_codigo", "cat_division_territorial.codigo"),
        comment="Unidad de aislamiento: libros, catálogo, inventario y caja propios", **OPC,
    )
    for col in ("titular_id", "tipo_negocio_codigo", "pais_codigo", "moneda_codigo",
                "division_territorial_codigo"):
        _ix("core_negocio", col)

    op.create_table(
        "core_membresia",
        _id(),
        sa.Column("usuario_id", UUID, nullable=False),
        sa.Column("negocio_id", UUID, nullable=False),
        sa.Column("rol", sa.String(20), nullable=False),
        *_auditoria(),
        _fk("core_membresia", "usuario_id", "core_usuario.id"),
        _fk("core_membresia", "negocio_id", "core_negocio.id"),
        _uq("core_membresia", "usuario_id", "negocio_id"),
        _ck("core_membresia", "rol", "rol IN ('dueno','administrador','cajero','cocina','contador')"),
        comment="Acceso de un usuario a un negocio", **OPC,
    )
    _ix("core_membresia", "negocio_id")

    op.create_table(
        "core_membresia_titular",
        _id(),
        sa.Column("usuario_id", UUID, nullable=False),
        sa.Column("titular_id", UUID, nullable=False),
        sa.Column("rol", sa.String(20), nullable=False),
        *_auditoria(),
        _fk("core_membresia_titular", "usuario_id", "core_usuario.id"),
        _fk("core_membresia_titular", "titular_id", "core_titular.id"),
        _uq("core_membresia_titular", "usuario_id", "titular_id"),
        _ck("core_membresia_titular", "rol", "rol IN ('titular_admin','contador')"),
        comment="Acceso a los reportes fiscales consolidados de un titular", **OPC,
    )
    _ix("core_membresia_titular", "titular_id")

    op.create_table(
        "core_cfg_tipo_negocio_capacidad",
        sa.Column("tipo_negocio_codigo", sa.String(40), primary_key=True),
        sa.Column("capacidad", sa.String(40), primary_key=True),
        sa.Column("activa_por_defecto", BOOL, nullable=False),
        *_tiempo(),
        _fk("core_cfg_tipo_negocio_capacidad", "tipo_negocio_codigo", "cat_tipo_negocio.codigo"),
        comment="Capacidades que activa cada tipo de negocio", **OPC,
    )

    op.create_table(
        "core_cfg_tipo_negocio_vocabulario",
        sa.Column("tipo_negocio_codigo", sa.String(40), primary_key=True),
        sa.Column("clave", sa.String(40), primary_key=True),
        sa.Column("texto", sa.String(120), nullable=False),
        *_tiempo(),
        _fk("core_cfg_tipo_negocio_vocabulario", "tipo_negocio_codigo",
            "cat_tipo_negocio.codigo"),
        comment="Palabras de la interfaz según el tipo de negocio", **OPC,
    )

    op.create_table(
        "core_cfg_tipo_negocio_plantilla",
        sa.Column("tipo_negocio_codigo", sa.String(40), primary_key=True),
        sa.Column("tipo_plantilla", sa.String(40), primary_key=True),
        sa.Column("contenido", sa.JSON(), nullable=False),
        sa.Column("version_plantilla", sa.Integer(), nullable=False, server_default=sa.text("1")),
        *_tiempo(),
        _fk("core_cfg_tipo_negocio_plantilla", "tipo_negocio_codigo", "cat_tipo_negocio.codigo"),
        comment="Plantillas por tipo de negocio (onboarding, categorías, KPIs)", **OPC,
    )

    op.create_table(
        "core_negocio_capacidad",
        _id(),
        sa.Column("negocio_id", UUID, nullable=False),
        sa.Column("capacidad", sa.String(40), nullable=False),
        sa.Column("activa", BOOL, nullable=False),
        *_auditoria(),
        _fk("core_negocio_capacidad", "negocio_id", "core_negocio.id"),
        _uq("core_negocio_capacidad", "negocio_id", "capacidad"),
        comment="Capacidades activas de cada negocio (revelación progresiva)", **OPC,
    )


def downgrade() -> None:
    for tabla in (
        "core_negocio_capacidad", "core_cfg_tipo_negocio_plantilla",
        "core_cfg_tipo_negocio_vocabulario", "core_cfg_tipo_negocio_capacidad",
        "core_membresia_titular", "core_membresia", "core_negocio", "core_titular",
        "core_usuario",
    ):
        op.drop_table(tabla)
