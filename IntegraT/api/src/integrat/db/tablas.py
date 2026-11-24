"""Metadata de ejecución (SQLAlchemy Core) de la base `integrat`.

Fuente de verdad del ESQUEMA = las migraciones de `api/migrations/versions/`.
Esta metadata debe coincidir con ellas; `tests/test_migraciones.py` lo verifica
comparando contra la base migrada. Para cambiar el esquema: nueva migración + actualizar aquí.

Convención (docs/CONVENCIONES_BD.md): MySQL no tiene esquemas, así que el "esquema lógico"
es el prefijo de la tabla: cat_, core_, fiscal_, ops_, cont_, ia_, integ_, dw_, rpt_, audit_.
"""

import sqlalchemy as sa

from integrat.db.tipos import (
    OPCIONES_TABLA,
    Booleano,
    FechaHora,
    UUIDBinario,
    col_id,
    cols_auditoria,
    cols_tiempo,
)

CONVENCION_NOMBRES = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = sa.MetaData(naming_convention=CONVENCION_NOMBRES)


def _fk(columna: str, tipo, destino: str, nullable: bool = False, **kw) -> sa.Column:
    return sa.Column(columna, tipo, sa.ForeignKey(destino), nullable=nullable, **kw)


# ---------------------------------------------------------------- cat_ (catálogos globales)

cat_moneda = sa.Table(
    "cat_moneda", metadata,
    sa.Column("codigo", sa.CHAR(3), primary_key=True, comment="ISO-4217"),
    sa.Column("nombre", sa.String(60), nullable=False),
    sa.Column("simbolo", sa.String(5), nullable=False),
    sa.Column("decimales", sa.SmallInteger(), nullable=False, server_default=sa.text("2")),
    *cols_tiempo(),
    comment="Monedas (catálogo global)",
    **OPCIONES_TABLA,
)

cat_pais = sa.Table(
    "cat_pais", metadata,
    sa.Column("codigo", sa.CHAR(2), primary_key=True, comment="ISO-3166-1 alfa-2"),
    sa.Column("nombre", sa.String(80), nullable=False),
    _fk("moneda_codigo", sa.CHAR(3), "cat_moneda.codigo"),
    sa.Column("zona_horaria_defecto", sa.String(40), nullable=False),
    sa.Column("nombre_id_fiscal", sa.String(10), nullable=False, comment="Ej. NIT"),
    sa.Column("activo", Booleano, nullable=False, server_default=sa.text("1")),
    *cols_tiempo(),
    sa.Index(None, "moneda_codigo"),
    comment="Países (catálogo global)",
    **OPCIONES_TABLA,
)

cat_unidad_medida = sa.Table(
    "cat_unidad_medida", metadata,
    sa.Column("codigo", sa.String(10), primary_key=True),
    sa.Column("nombre", sa.String(40), nullable=False),
    sa.Column("tipo", sa.String(10), nullable=False),
    _fk("unidad_base_codigo", sa.String(10), "cat_unidad_medida.codigo", nullable=True),
    sa.Column("factor_a_base", sa.Numeric(20, 10), nullable=True,
              comment="Nulo = depende del producto (ej. CAJA)"),
    sa.Column("codigo_fel", sa.String(10), nullable=True, comment="Pendiente: catálogo SAT"),
    *cols_tiempo(),
    sa.CheckConstraint("tipo IN ('unidad','masa','volumen')", name="tipo"),
    sa.Index(None, "unidad_base_codigo"),
    comment="Unidades de medida y su conversión a la unidad base",
    **OPCIONES_TABLA,
)

cat_division_territorial = sa.Table(
    "cat_division_territorial", metadata,
    sa.Column("codigo", sa.String(12), primary_key=True, comment="Ej. GT-01 (depto), GT-0101"),
    _fk("pais_codigo", sa.CHAR(2), "cat_pais.codigo"),
    sa.Column("nivel", sa.SmallInteger(), nullable=False, comment="1=departamento, 2=municipio"),
    sa.Column("nombre", sa.String(80), nullable=False),
    _fk("padre_codigo", sa.String(12), "cat_division_territorial.codigo", nullable=True),
    *cols_tiempo(),
    sa.CheckConstraint("nivel IN (1,2)", name="nivel"),
    sa.Index(None, "pais_codigo"),
    sa.Index(None, "padre_codigo"),
    comment="Divisiones territoriales por país",
    **OPCIONES_TABLA,
)

cat_tipo_negocio = sa.Table(
    "cat_tipo_negocio", metadata,
    sa.Column("codigo", sa.String(40), primary_key=True),
    sa.Column("nombre", sa.String(80), nullable=False),
    sa.Column("descripcion", sa.String(255), nullable=False),
    sa.Column("icono", sa.String(40), nullable=False),
    sa.Column("orden", sa.SmallInteger(), nullable=False, server_default=sa.text("0")),
    sa.Column("activo", Booleano, nullable=False, server_default=sa.text("1")),
    *cols_tiempo(),
    comment="Tipos de negocio (perfiles de configuración)",
    **OPCIONES_TABLA,
)

cat_canal_venta_base = sa.Table(
    "cat_canal_venta_base", metadata,
    sa.Column("codigo", sa.String(40), primary_key=True),
    sa.Column("nombre", sa.String(60), nullable=False),
    sa.Column("icono", sa.String(40), nullable=False),
    sa.Column("orden", sa.SmallInteger(), nullable=False, server_default=sa.text("0")),
    *cols_tiempo(),
    comment="Canales y modalidades de venta base",
    **OPCIONES_TABLA,
)

# ---------------------------------------------------------------- fiscal_

fiscal_cfg_regimen = sa.Table(
    "fiscal_cfg_regimen", metadata,
    sa.Column("codigo", sa.String(40), primary_key=True),
    _fk("pais_codigo", sa.CHAR(2), "cat_pais.codigo"),
    sa.Column("impuesto", sa.String(10), nullable=False),
    sa.Column("nombre", sa.String(120), nullable=False),
    sa.Column("nombre_simple", sa.String(120), nullable=False),
    sa.Column("usa_credito_fiscal", Booleano, nullable=False, server_default=sa.text("0")),
    sa.Column("parametros", sa.JSON(), nullable=True),
    sa.Column("validado_por_contador", Booleano, nullable=False, server_default=sa.text("0"),
              comment="Ver docs/REVISION_CONTADOR.md"),
    sa.Column("vigente_desde", sa.Date(), nullable=False),
    *cols_tiempo(),
    sa.CheckConstraint("impuesto IN ('IVA','ISR','NINGUNO')", name="impuesto"),
    sa.Index(None, "pais_codigo"),
    comment="Regímenes fiscales por país (parámetros a validar por el contador)",
    **OPCIONES_TABLA,
)

# ---------------------------------------------------------------- core_

core_usuario = sa.Table(
    "core_usuario", metadata,
    col_id(),
    sa.Column("correo", sa.String(254), nullable=False),
    sa.Column("telefono", sa.String(20), nullable=True),
    sa.Column("nombre", sa.String(120), nullable=False),
    sa.Column("clave_hash", sa.String(255), nullable=False, comment="argon2id"),
    sa.Column("verificado_en", FechaHora, nullable=True),
    sa.Column("ultimo_acceso_en", FechaHora, nullable=True),
    sa.Column("tamano_texto", sa.String(12), nullable=False, server_default="normal"),
    *cols_auditoria(),
    sa.UniqueConstraint("correo"),
    sa.CheckConstraint("tamano_texto IN ('normal','grande','muy_grande')", name="tamano_texto"),
    comment="Personas que usan IntegraT",
    **OPCIONES_TABLA,
)

core_titular = sa.Table(
    "core_titular", metadata,
    col_id(),
    _fk("pais_codigo", sa.CHAR(2), "cat_pais.codigo"),
    sa.Column("nit", sa.String(20), nullable=True),
    sa.Column("nombre_fiscal", sa.String(200), nullable=True),
    sa.Column("tipo_persona", sa.String(12), nullable=True),
    _fk("regimen_iva_codigo", sa.String(40), "fiscal_cfg_regimen.codigo", nullable=True),
    _fk("regimen_isr_codigo", sa.String(40), "fiscal_cfg_regimen.codigo", nullable=True),
    sa.Column("afiliacion_iva", sa.String(5), nullable=True, comment="FEL: GEN, PEQ, ..."),
    sa.Column("frases", sa.JSON(), nullable=True, comment="FEL: frases y escenarios"),
    sa.Column("politica_costo_ia", sa.String(12), nullable=False, server_default="capitalizar"),
    sa.Column("estado", sa.String(12), nullable=False, server_default="pendiente"),
    *cols_auditoria(),
    sa.UniqueConstraint("pais_codigo", "nit"),
    sa.CheckConstraint("tipo_persona IN ('individual','juridica')", name="tipo_persona"),
    sa.CheckConstraint("politica_costo_ia IN ('capitalizar','gasto')", name="politica_costo_ia"),
    sa.CheckConstraint("estado IN ('pendiente','activo')", name="estado"),
    sa.Index(None, "regimen_iva_codigo"),
    sa.Index(None, "regimen_isr_codigo"),
    comment="Contribuyente (NIT): agrupa negocios solo para lo fiscal consolidado",
    **OPCIONES_TABLA,
)

core_negocio = sa.Table(
    "core_negocio", metadata,
    col_id(),
    _fk("titular_id", UUIDBinario(), "core_titular.id", nullable=True),
    sa.Column("nombre", sa.String(120), nullable=False),
    sa.Column("nombre_comercial", sa.String(120), nullable=True),
    _fk("tipo_negocio_codigo", sa.String(40), "cat_tipo_negocio.codigo"),
    _fk("pais_codigo", sa.CHAR(2), "cat_pais.codigo"),
    sa.Column("zona_horaria", sa.String(40), nullable=False),
    _fk("moneda_codigo", sa.CHAR(3), "cat_moneda.codigo"),
    sa.Column("codigo_establecimiento_sat", sa.Integer(), nullable=True),
    sa.Column("direccion", sa.String(255), nullable=True),
    _fk("division_territorial_codigo", sa.String(12), "cat_division_territorial.codigo",
        nullable=True),
    sa.Column("codigo_postal", sa.String(10), nullable=True),
    sa.Column("correo", sa.String(254), nullable=True),
    sa.Column("telefono", sa.String(20), nullable=True),
    sa.Column("logo_imagen_id", UUIDBinario(), nullable=True),
    sa.Column("margen_objetivo_defecto", sa.Numeric(5, 4), nullable=False,
              server_default=sa.text("0.3500")),
    sa.Column("estado_onboarding", sa.JSON(), nullable=True),
    *cols_auditoria(),
    sa.Index(None, "titular_id"),
    sa.Index(None, "tipo_negocio_codigo"),
    sa.Index(None, "pais_codigo"),
    sa.Index(None, "moneda_codigo"),
    sa.Index(None, "division_territorial_codigo"),
    comment="Unidad de aislamiento: libros, catálogo, inventario y caja propios",
    **OPCIONES_TABLA,
)

core_membresia = sa.Table(
    "core_membresia", metadata,
    col_id(),
    _fk("usuario_id", UUIDBinario(), "core_usuario.id"),
    _fk("negocio_id", UUIDBinario(), "core_negocio.id"),
    sa.Column("rol", sa.String(20), nullable=False),
    *cols_auditoria(),
    sa.UniqueConstraint("usuario_id", "negocio_id"),
    sa.CheckConstraint(
        "rol IN ('dueno','administrador','cajero','cocina','contador')", name="rol"
    ),
    sa.Index(None, "negocio_id"),
    comment="Acceso de un usuario a un negocio",
    **OPCIONES_TABLA,
)

core_membresia_titular = sa.Table(
    "core_membresia_titular", metadata,
    col_id(),
    _fk("usuario_id", UUIDBinario(), "core_usuario.id"),
    _fk("titular_id", UUIDBinario(), "core_titular.id"),
    sa.Column("rol", sa.String(20), nullable=False),
    *cols_auditoria(),
    sa.UniqueConstraint("usuario_id", "titular_id"),
    sa.CheckConstraint("rol IN ('titular_admin','contador')", name="rol"),
    sa.Index(None, "titular_id"),
    comment="Acceso a los reportes fiscales consolidados de un titular",
    **OPCIONES_TABLA,
)

core_cfg_tipo_negocio_capacidad = sa.Table(
    "core_cfg_tipo_negocio_capacidad", metadata,
    sa.Column("tipo_negocio_codigo", sa.String(40), sa.ForeignKey("cat_tipo_negocio.codigo"),
              primary_key=True),
    sa.Column("capacidad", sa.String(40), primary_key=True),
    sa.Column("activa_por_defecto", Booleano, nullable=False),
    *cols_tiempo(),
    comment="Capacidades que activa cada tipo de negocio",
    **OPCIONES_TABLA,
)

core_cfg_tipo_negocio_vocabulario = sa.Table(
    "core_cfg_tipo_negocio_vocabulario", metadata,
    sa.Column("tipo_negocio_codigo", sa.String(40), sa.ForeignKey("cat_tipo_negocio.codigo"),
              primary_key=True),
    sa.Column("clave", sa.String(40), primary_key=True),
    sa.Column("texto", sa.String(120), nullable=False),
    *cols_tiempo(),
    comment="Palabras de la interfaz según el tipo de negocio",
    **OPCIONES_TABLA,
)

core_cfg_tipo_negocio_plantilla = sa.Table(
    "core_cfg_tipo_negocio_plantilla", metadata,
    sa.Column("tipo_negocio_codigo", sa.String(40), sa.ForeignKey("cat_tipo_negocio.codigo"),
              primary_key=True),
    sa.Column("tipo_plantilla", sa.String(40), primary_key=True),
    sa.Column("contenido", sa.JSON(), nullable=False),
    sa.Column("version_plantilla", sa.Integer(), nullable=False, server_default=sa.text("1")),
    *cols_tiempo(),
    comment="Plantillas por tipo de negocio (onboarding, categorías, KPIs)",
    **OPCIONES_TABLA,
)

core_negocio_capacidad = sa.Table(
    "core_negocio_capacidad", metadata,
    col_id(),
    _fk("negocio_id", UUIDBinario(), "core_negocio.id"),
    sa.Column("capacidad", sa.String(40), nullable=False),
    sa.Column("activa", Booleano, nullable=False),
    *cols_auditoria(),
    sa.UniqueConstraint("negocio_id", "capacidad"),
    comment="Capacidades activas de cada negocio (revelación progresiva)",
    **OPCIONES_TABLA,
)

core_token_refresco = sa.Table(
    "core_token_refresco", metadata,
    col_id(),
    _fk("usuario_id", UUIDBinario(), "core_usuario.id"),
    sa.Column("token_hash", sa.CHAR(64), nullable=False,
              comment="SHA-256 del token; nunca el token"),
    sa.Column("expira_en", FechaHora, nullable=False),
    sa.Column("revocado_en", FechaHora, nullable=True),
    *cols_auditoria(),
    sa.UniqueConstraint("token_hash"),
    sa.Index(None, "usuario_id"),
    comment="Tokens de refresco de sesión (rotan en cada uso)",
    **OPCIONES_TABLA,
)

core_intento_acceso = sa.Table(
    "core_intento_acceso", metadata,
    col_id(),
    sa.Column("accion", sa.String(20), nullable=False, comment="login, registro, refrescar"),
    sa.Column("clave_tipo", sa.String(10), nullable=False, comment="ip o correo"),
    sa.Column("clave_hash", sa.CHAR(64), nullable=False, comment="HMAC-SHA256; nunca el valor"),
    *cols_auditoria(),
    sa.CheckConstraint("clave_tipo IN ('ip','correo')", name="clave_tipo"),
    sa.Index(None, "accion", "clave_tipo", "clave_hash", "creado_en"),
    sa.Index(None, "creado_en"),
    comment="Intentos de acceso recientes para limitar la fuerza bruta",
    **OPCIONES_TABLA,
)

PREFIJOS_PERMITIDOS = (
    "cat_", "core_", "fiscal_", "ops_", "cont_", "ia_", "integ_", "dw_", "rpt_", "audit_",
)
