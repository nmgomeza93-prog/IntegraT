"""Metadata de ejecución (SQLAlchemy Core) de la base `integrat`.

Fuente de verdad del ESQUEMA = las migraciones de `api/migrations/versions/`.
Esta metadata debe coincidir con ellas; `tests/test_migraciones.py` lo verifica
comparando contra la base migrada. Para cambiar el esquema: nueva migración + actualizar aquí.

Convención (docs/CONVENCIONES_BD.md): MySQL no tiene esquemas, así que el "esquema lógico"
es el prefijo de la tabla: cat_, core_, fiscal_, ops_, cont_, ia_, integ_, dw_, rpt_, audit_.
"""

import sqlalchemy as sa

from integrat.db.tipos import (
    AHORA,
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

core_idempotencia = sa.Table(
    "core_idempotencia", metadata,
    col_id(),
    _fk("usuario_id", UUIDBinario(), "core_usuario.id"),
    sa.Column("operacion", sa.String(40), nullable=False, comment="Ej. crear_negocio"),
    sa.Column("clave", sa.String(100), nullable=False, comment="Idempotency-Key del cliente"),
    sa.Column("huella", sa.CHAR(64), nullable=False, comment="SHA-256 de los datos enviados"),
    sa.Column("recurso_id", UUIDBinario(), nullable=False,
              comment="Lo que se creó (ej. el negocio)"),
    *cols_auditoria(),
    sa.UniqueConstraint("usuario_id", "operacion", "clave"),
    comment="Claves de idempotencia de comandos (vigencia 24 horas)",
    **OPCIONES_TABLA,
)

# ---------------------------------------------------------------- ops_ (operación diaria)

ops_categoria = sa.Table(
    "ops_categoria", metadata,
    col_id(),
    _fk("negocio_id", UUIDBinario(), "core_negocio.id"),
    sa.Column("nombre", sa.String(80), nullable=False),
    sa.Column("orden", sa.SmallInteger(), nullable=False, server_default=sa.text("0")),
    sa.Column("icono", sa.String(40), nullable=True),
    *cols_auditoria(),
    sa.Column("palabras_clave", sa.JSON(), nullable=True,
              comment="Para sugerir la categoría de un producto importado"),
    sa.Index(None, "negocio_id"),
    comment="Categorías del catálogo de cada negocio",
    **OPCIONES_TABLA,
)

ops_item = sa.Table(
    "ops_item", metadata,
    col_id(),
    _fk("negocio_id", UUIDBinario(), "core_negocio.id"),
    _fk("categoria_id", UUIDBinario(), "ops_categoria.id", nullable=True),
    sa.Column("tipo_item", sa.String(20), nullable=False,
              comment="producto o platillo (lo define el tipo de negocio)"),
    sa.Column("nombre", sa.String(120), nullable=False),
    sa.Column("descripcion", sa.String(500), nullable=True),
    sa.Column("se_vende", Booleano, nullable=False, server_default=sa.text("1")),
    *cols_auditoria(),
    sa.Column("margen_objetivo", sa.Numeric(5, 4), nullable=True,
              comment="Margen objetivo propio (nulo = el del negocio)"),
    sa.CheckConstraint("tipo_item IN ('producto','platillo')", name="tipo_item"),
    sa.CheckConstraint("margen_objetivo IS NULL OR "
                       "(margen_objetivo >= 0 AND margen_objetivo <= 0.9)",
                       name="margen_objetivo"),
    sa.Index(None, "negocio_id"),
    sa.Index(None, "categoria_id"),
    comment="Productos y platillos que vende el negocio",
    **OPCIONES_TABLA,
)

ops_item_variante = sa.Table(
    "ops_item_variante", metadata,
    col_id(),
    _fk("negocio_id", UUIDBinario(), "core_negocio.id"),
    _fk("item_id", UUIDBinario(), "ops_item.id"),
    sa.Column("nombre", sa.String(80), nullable=False, server_default="Única"),
    sa.Column("precio_venta", sa.Numeric(14, 2), nullable=False),
    *cols_auditoria(),
    sa.Column("codigo", sa.String(60), nullable=True, comment="Código del proveedor (SKC) o SKU"),
    sa.Column("atributos", sa.JSON(), nullable=True,
              comment="Ej. {Talla: M, Color: Rosa}; nulo = Única"),
    sa.CheckConstraint("precio_venta >= 0", name="precio_venta"),
    sa.Index(None, "negocio_id"),
    sa.Index(None, "item_id"),
    comment="Presentaciones de un ítem; la implícita 'Única' guarda el precio",
    **OPCIONES_TABLA,
)

ops_venta = sa.Table(
    "ops_venta", metadata,
    col_id(),
    _fk("negocio_id", UUIDBinario(), "core_negocio.id"),
    sa.Column("numero", sa.Integer(), nullable=False, comment="Consecutivo por negocio"),
    sa.Column("fecha_hora", FechaHora, nullable=False, comment="UTC"),
    sa.Column("estado", sa.String(12), nullable=False, server_default="pagada"),
    sa.Column("total", sa.Numeric(14, 2), nullable=False),
    _fk("moneda_codigo", sa.CHAR(3), "cat_moneda.codigo"),
    sa.Column("anulada_en", FechaHora, nullable=True),
    sa.Column("anulada_por", UUIDBinario(), nullable=True),
    sa.Column("motivo_anulacion", sa.String(200), nullable=True),
    *cols_auditoria(),
    sa.UniqueConstraint("negocio_id", "numero"),
    sa.CheckConstraint("estado IN ('pagada','anulada')", name="estado"),
    sa.CheckConstraint("total >= 0", name="total"),
    sa.Index(None, "negocio_id", "fecha_hora"),
    sa.Index(None, "moneda_codigo"),
    comment="Ventas (inmutables; se corrigen anulando)",
    **OPCIONES_TABLA,
)

ops_venta_linea = sa.Table(
    "ops_venta_linea", metadata,
    col_id(),
    _fk("negocio_id", UUIDBinario(), "core_negocio.id"),
    _fk("venta_id", UUIDBinario(), "ops_venta.id"),
    _fk("item_id", UUIDBinario(), "ops_item.id"),
    _fk("item_variante_id", UUIDBinario(), "ops_item_variante.id"),
    sa.Column("nombre", sa.String(120), nullable=False, comment="Congelado al vender"),
    sa.Column("cantidad", sa.Numeric(14, 4), nullable=False),
    sa.Column("precio_unitario", sa.Numeric(14, 2), nullable=False, comment="Congelado al vender"),
    sa.Column("total", sa.Numeric(14, 2), nullable=False),
    *cols_auditoria(),
    sa.CheckConstraint("cantidad > 0", name="cantidad"),
    sa.CheckConstraint("precio_unitario >= 0", name="precio_unitario"),
    sa.Index(None, "negocio_id"),
    sa.Index(None, "venta_id"),
    sa.Index(None, "item_id"),
    sa.Index(None, "item_variante_id"),
    comment="Líneas de una venta, con nombre y precio congelados",
    **OPCIONES_TABLA,
)

ops_pago = sa.Table(
    "ops_pago", metadata,
    col_id(),
    _fk("negocio_id", UUIDBinario(), "core_negocio.id"),
    _fk("venta_id", UUIDBinario(), "ops_venta.id"),
    sa.Column("medio_pago", sa.String(20), nullable=False),
    sa.Column("monto", sa.Numeric(14, 2), nullable=False),
    *cols_auditoria(),
    sa.CheckConstraint("medio_pago IN ('efectivo','tarjeta','transferencia')", name="medio_pago"),
    sa.CheckConstraint("monto >= 0", name="monto"),
    sa.Index(None, "negocio_id"),
    sa.Index(None, "venta_id"),
    comment="Pagos de una venta (hoy uno por venta; el pago dividido llegará después)",
    **OPCIONES_TABLA,
)

ops_atributo = sa.Table(
    "ops_atributo", metadata,
    col_id(),
    _fk("negocio_id", UUIDBinario(), "core_negocio.id"),
    sa.Column("nombre", sa.String(40), nullable=False),
    sa.Column("orden", sa.SmallInteger(), nullable=False, server_default=sa.text("0")),
    *cols_auditoria(),
    sa.Index(None, "negocio_id"),
    comment="Atributos de variante del negocio (talla, color…)",
    **OPCIONES_TABLA,
)

ops_atributo_valor = sa.Table(
    "ops_atributo_valor", metadata,
    col_id(),
    _fk("negocio_id", UUIDBinario(), "core_negocio.id"),
    _fk("atributo_id", UUIDBinario(), "ops_atributo.id"),
    sa.Column("valor", sa.String(40), nullable=False),
    sa.Column("orden", sa.SmallInteger(), nullable=False, server_default=sa.text("0")),
    *cols_auditoria(),
    sa.Index(None, "negocio_id"),
    sa.Index(None, "atributo_id"),
    comment="Valores de un atributo (S, M, L; Negro, Rosa…)",
    **OPCIONES_TABLA,
)

ops_categoria_atributo = sa.Table(
    "ops_categoria_atributo", metadata,
    col_id(),
    _fk("negocio_id", UUIDBinario(), "core_negocio.id"),
    _fk("categoria_id", UUIDBinario(), "ops_categoria.id"),
    _fk("atributo_id", UUIDBinario(), "ops_atributo.id"),
    sa.Column("orden", sa.SmallInteger(), nullable=False, server_default=sa.text("0")),
    *cols_auditoria(),
    sa.Index(None, "negocio_id"),
    sa.Index(None, "categoria_id"),
    sa.Index(None, "atributo_id"),
    comment="Qué atributos usan los productos de cada categoría",
    **OPCIONES_TABLA,
)

ops_categoria_gasto = sa.Table(
    "ops_categoria_gasto", metadata,
    col_id(),
    _fk("negocio_id", UUIDBinario(), "core_negocio.id"),
    sa.Column("nombre", sa.String(80), nullable=False),
    sa.Column("icono", sa.String(40), nullable=True),
    sa.Column("es_fijo", Booleano, nullable=False, server_default=sa.text("0"),
              comment="Gasto fijo (renta, sueldos) o variable"),
    sa.Column("rol_cuenta_codigo", sa.String(40), nullable=True,
              comment="Rol de cuenta contable (lo usará el motor contable)"),
    sa.Column("orden", sa.SmallInteger(), nullable=False, server_default=sa.text("0")),
    *cols_auditoria(),
    sa.Index(None, "negocio_id"),
    comment="Categorías de gasto de cada negocio",
    **OPCIONES_TABLA,
)

ops_gasto = sa.Table(
    "ops_gasto", metadata,
    col_id(),
    _fk("negocio_id", UUIDBinario(), "core_negocio.id"),
    _fk("categoria_gasto_id", UUIDBinario(), "ops_categoria_gasto.id"),
    sa.Column("fecha", sa.Date(), nullable=False, comment="Día del gasto (calendario local)"),
    sa.Column("monto", sa.Numeric(14, 2), nullable=False),
    sa.Column("medio_pago", sa.String(20), nullable=False),
    sa.Column("descripcion", sa.String(200), nullable=True),
    sa.Column("es_fijo", Booleano, nullable=False, server_default=sa.text("0")),
    *cols_auditoria(),
    sa.Column("con_factura", Booleano, nullable=False, server_default=sa.text("0"),
              comment="Trae factura (IVA por cobrar en el régimen general)"),
    sa.CheckConstraint("monto > 0", name="monto"),
    sa.CheckConstraint("medio_pago IN ('efectivo','tarjeta','transferencia')", name="medio_pago"),
    sa.Index(None, "negocio_id", "fecha"),
    sa.Index(None, "categoria_gasto_id"),
    comment="Gastos del negocio",
    **OPCIONES_TABLA,
)

ops_insumo = sa.Table(
    "ops_insumo", metadata,
    col_id(),
    _fk("negocio_id", UUIDBinario(), "core_negocio.id"),
    sa.Column("nombre", sa.String(80), nullable=False),
    _fk("unidad_codigo", sa.String(10), "cat_unidad_medida.codigo", comment="Unidad de uso"),
    sa.Column("existencia_base", sa.Numeric(18, 4), nullable=False, server_default=sa.text("0"),
              comment="En unidad base; puede ser negativa"),
    sa.Column("costo_promedio_base", sa.Numeric(18, 8), nullable=False,
              server_default=sa.text("0"), comment="Costo promedio ponderado por unidad base"),
    sa.Column("stock_minimo_base", sa.Numeric(18, 4), nullable=False, server_default=sa.text("0"),
              comment="Aviso de 'te queda poco'"),
    _fk("item_id", UUIDBinario(), "ops_item.id", nullable=True,
        comment="Producto del que este insumo es la mercadería (se compra hecho para revenderlo)"),
    *cols_auditoria(),
    sa.CheckConstraint("costo_promedio_base >= 0", name="costo_promedio_base"),
    sa.CheckConstraint("stock_minimo_base >= 0", name="stock_minimo_base"),
    sa.Index(None, "negocio_id"),
    sa.Index(None, "unidad_codigo"),
    sa.Index(None, "item_id"),
    sa.Column("item_variante_id", UUIDBinario(), sa.ForeignKey("ops_item_variante.id"),
              nullable=True, comment="Variante de la que este insumo es la mercadería"),
    sa.Index(None, "item_variante_id"),
    comment="Insumos que el negocio compra y consume",
    **OPCIONES_TABLA,
)

ops_movimiento_inventario = sa.Table(
    "ops_movimiento_inventario", metadata,
    col_id(),
    _fk("negocio_id", UUIDBinario(), "core_negocio.id"),
    _fk("insumo_id", UUIDBinario(), "ops_insumo.id"),
    sa.Column("fecha_hora", FechaHora, nullable=False, comment="UTC"),
    sa.Column("tipo", sa.String(20), nullable=False),
    sa.Column("cantidad_base", sa.Numeric(18, 4), nullable=False, comment="Con signo"),
    sa.Column("costo_unitario_base", sa.Numeric(18, 8), nullable=False),
    sa.Column("origen_tipo", sa.String(20), nullable=True),
    sa.Column("origen_id", UUIDBinario(), nullable=True),
    sa.Column("nota", sa.String(200), nullable=True),
    sa.Column("creado_en", FechaHora, nullable=False, server_default=AHORA),
    sa.Column("creado_por", UUIDBinario(), nullable=True),
    sa.CheckConstraint(
        "tipo IN ('entrada','merma','ajuste','consumo_venta','reverso_venta','inicial',"
        "'reverso_compra')",
        name="tipo"),
    sa.CheckConstraint("costo_unitario_base >= 0", name="costo_unitario_base"),
    sa.Index(None, "negocio_id", "insumo_id", "fecha_hora"),
    sa.Index(None, "insumo_id"),
    comment="Movimientos de inventario (inmutables; se corrigen con otro movimiento)",
    **OPCIONES_TABLA,
)

ops_receta_linea = sa.Table(
    "ops_receta_linea", metadata,
    col_id(),
    _fk("negocio_id", UUIDBinario(), "core_negocio.id"),
    _fk("item_id", UUIDBinario(), "ops_item.id"),
    _fk("insumo_id", UUIDBinario(), "ops_insumo.id"),
    sa.Column("cantidad", sa.Numeric(14, 4), nullable=False,
              comment="Por una unidad vendida, en `unidad_codigo`"),
    _fk("unidad_codigo", sa.String(10), "cat_unidad_medida.codigo"),
    *cols_auditoria(),
    sa.CheckConstraint("cantidad > 0", name="cantidad"),
    sa.Index(None, "negocio_id"),
    sa.Index(None, "item_id"),
    sa.Index(None, "insumo_id"),
    sa.Index(None, "unidad_codigo"),
    sa.Column("item_variante_id", UUIDBinario(), sa.ForeignKey("ops_item_variante.id"),
              nullable=True, comment="Nulo = la línea es de todas las variantes"),
    sa.Index(None, "item_variante_id"),
    comment="Líneas de receta: insumos que consume cada ítem vendido",
    **OPCIONES_TABLA,
)

ops_proveedor = sa.Table(
    "ops_proveedor", metadata,
    col_id(),
    _fk("negocio_id", UUIDBinario(), "core_negocio.id"),
    sa.Column("nombre", sa.String(120), nullable=False),
    sa.Column("telefono", sa.String(30), nullable=True),
    *cols_auditoria(),
    sa.Index(None, "negocio_id"),
    comment="Proveedores del negocio",
    **OPCIONES_TABLA,
)

ops_compra = sa.Table(
    "ops_compra", metadata,
    col_id(),
    _fk("negocio_id", UUIDBinario(), "core_negocio.id"),
    _fk("proveedor_id", UUIDBinario(), "ops_proveedor.id", nullable=True),
    sa.Column("fecha", sa.Date(), nullable=False, comment="Día de la compra (calendario local)"),
    sa.Column("numero_factura", sa.String(40), nullable=True),
    sa.Column("medio_pago", sa.String(20), nullable=False),
    sa.Column("total", sa.Numeric(14, 2), nullable=False),
    sa.Column("estado", sa.String(12), nullable=False, server_default="registrada"),
    sa.Column("nota", sa.String(200), nullable=True),
    sa.Column("anulada_en", FechaHora, nullable=True),
    sa.Column("anulada_por", UUIDBinario(), nullable=True),
    sa.Column("motivo_anulacion", sa.String(200), nullable=True),
    *cols_auditoria(),
    sa.CheckConstraint("medio_pago IN ('efectivo','tarjeta','transferencia')", name="medio_pago"),
    sa.CheckConstraint("estado IN ('registrada','anulada')", name="estado"),
    sa.CheckConstraint("total >= 0", name="total"),
    sa.Index(None, "negocio_id", "fecha"),
    sa.Index(None, "proveedor_id"),
    comment="Compras (inmutables; se corrigen anulando)",
    **OPCIONES_TABLA,
)

ops_compra_linea = sa.Table(
    "ops_compra_linea", metadata,
    col_id(),
    _fk("negocio_id", UUIDBinario(), "core_negocio.id"),
    _fk("compra_id", UUIDBinario(), "ops_compra.id"),
    _fk("insumo_id", UUIDBinario(), "ops_insumo.id"),
    sa.Column("nombre", sa.String(80), nullable=False, comment="Congelado al comprar"),
    sa.Column("cantidad", sa.Numeric(14, 4), nullable=False, comment="En `unidad_codigo`"),
    _fk("unidad_codigo", sa.String(10), "cat_unidad_medida.codigo"),
    sa.Column("costo_total", sa.Numeric(14, 2), nullable=False),
    *cols_auditoria(),
    sa.CheckConstraint("cantidad > 0", name="cantidad"),
    sa.CheckConstraint("costo_total >= 0", name="costo_total"),
    sa.Index(None, "negocio_id"),
    sa.Index(None, "compra_id"),
    sa.Index(None, "insumo_id"),
    sa.Index(None, "unidad_codigo"),
    comment="Líneas de una compra",
    **OPCIONES_TABLA,
)

ops_sesion_caja = sa.Table(
    "ops_sesion_caja", metadata,
    col_id(),
    _fk("negocio_id", UUIDBinario(), "core_negocio.id"),
    sa.Column("fecha", sa.Date(), nullable=False, comment="Día de la apertura (calendario local)"),
    sa.Column("abierta_en", FechaHora, nullable=False, comment="UTC"),
    sa.Column("monto_apertura", sa.Numeric(14, 2), nullable=False),
    sa.Column("estado", sa.String(10), nullable=False, server_default="abierta"),
    sa.Column("cerrada_en", FechaHora, nullable=True),
    sa.Column("cerrada_por", UUIDBinario(), nullable=True),
    sa.Column("efectivo_esperado", sa.Numeric(14, 2), nullable=True),
    sa.Column("efectivo_contado", sa.Numeric(14, 2), nullable=True),
    sa.Column("diferencia", sa.Numeric(14, 2), nullable=True, comment="contado - esperado"),
    sa.Column("nota", sa.String(200), nullable=True),
    *cols_auditoria(),
    sa.CheckConstraint("estado IN ('abierta','cerrada')", name="estado"),
    sa.CheckConstraint("monto_apertura >= 0", name="monto_apertura"),
    sa.CheckConstraint("efectivo_contado IS NULL OR efectivo_contado >= 0",
                       name="efectivo_contado"),
    sa.Index(None, "negocio_id", "estado"),
    sa.Index(None, "negocio_id", "fecha"),
    comment="Caja del día: apertura y cierre",
    **OPCIONES_TABLA,
)

ops_movimiento_dueno = sa.Table(
    "ops_movimiento_dueno", metadata,
    col_id(),
    _fk("negocio_id", UUIDBinario(), "core_negocio.id"),
    sa.Column("tipo", sa.String(10), nullable=False),
    sa.Column("monto", sa.Numeric(14, 2), nullable=False),
    sa.Column("medio", sa.String(10), nullable=False),
    sa.Column("fecha", sa.Date(), nullable=False, comment="Calendario local"),
    sa.Column("nota", sa.String(200), nullable=True),
    *cols_auditoria(),
    sa.CheckConstraint("tipo IN ('aporte','retiro')", name="tipo"),
    sa.CheckConstraint("medio IN ('efectivo','banco')", name="medio"),
    sa.CheckConstraint("monto > 0", name="monto"),
    sa.Index(None, "negocio_id", "fecha"),
    comment="Dinero que el dueño pone o saca del negocio",
    **OPCIONES_TABLA,
)

ops_importacion = sa.Table(
    "ops_importacion", metadata,
    col_id(),
    _fk("negocio_id", UUIDBinario(), "core_negocio.id"),
    sa.Column("plataforma", sa.String(30), nullable=False),
    sa.Column("numero_factura", sa.String(60), nullable=True),
    sa.Column("numero_orden", sa.String(60), nullable=True),
    sa.Column("fecha_factura", sa.Date(), nullable=True),
    _fk("moneda_codigo", sa.CHAR(3), "cat_moneda.codigo"),
    sa.Column("garantia_envio", sa.Numeric(14, 4), nullable=False, server_default=sa.text("0")),
    sa.Column("costo_importacion", sa.Numeric(14, 4), nullable=False, server_default=sa.text("0")),
    sa.Column("otros_cobros", sa.Numeric(14, 4), nullable=False, server_default=sa.text("0")),
    sa.Column("total_origen", sa.Numeric(14, 4), nullable=False,
              comment="Líneas + cargos, en su moneda"),
    sa.Column("tipo_cambio", sa.Numeric(18, 8), nullable=False, comment="Q por unidad"),
    sa.Column("total_q", sa.Numeric(14, 2), nullable=False, comment="Lo que se pagó en Q"),
    sa.Column("medio_pago", sa.String(20), nullable=False),
    sa.Column("estado", sa.String(20), nullable=False, server_default="en_camino"),
    sa.Column("recibida_en", FechaHora, nullable=True),
    sa.Column("guia", sa.String(60), nullable=True),
    sa.Column("courier_q", sa.Numeric(14, 2), nullable=True),
    sa.Column("envio_local_q", sa.Numeric(14, 2), nullable=True),
    sa.Column("medio_pago_courier", sa.String(20), nullable=True),
    sa.Column("nota", sa.String(200), nullable=True),
    sa.Column("anulada_en", FechaHora, nullable=True),
    sa.Column("anulada_por", UUIDBinario(), nullable=True),
    sa.Column("motivo_anulacion", sa.String(200), nullable=True),
    *cols_auditoria(),
    sa.CheckConstraint("estado IN ('en_camino','recibida','recibida_parcial','anulada')",
                       name="estado"),
    sa.CheckConstraint("medio_pago IN ('efectivo','tarjeta','transferencia')", name="medio_pago"),
    sa.CheckConstraint("tipo_cambio > 0", name="tipo_cambio"),
    sa.Index(None, "negocio_id", "estado"),
    sa.Index(None, "moneda_codigo"),
    comment="Importaciones (pedido en camino y su recepción) con su rastreo",
    **OPCIONES_TABLA,
)

ops_importacion_linea = sa.Table(
    "ops_importacion_linea", metadata,
    col_id(),
    _fk("negocio_id", UUIDBinario(), "core_negocio.id"),
    _fk("importacion_id", UUIDBinario(), "ops_importacion.id"),
    sa.Column("producto_nombre", sa.String(120), nullable=False),
    sa.Column("categoria_nombre", sa.String(80), nullable=True),
    sa.Column("codigo", sa.String(60), nullable=True),
    sa.Column("descripcion", sa.String(500), nullable=True),
    sa.Column("atributos", sa.JSON(), nullable=True),
    _fk("item_id", UUIDBinario(), "ops_item.id", nullable=True),
    _fk("item_variante_id", UUIDBinario(), "ops_item_variante.id", nullable=True),
    sa.Column("cantidad", sa.Integer(), nullable=False),
    sa.Column("precio_unitario", sa.Numeric(14, 4), nullable=False,
              comment="En la moneda de la factura"),
    sa.Column("cargos_origen", sa.Numeric(14, 4), nullable=False, server_default=sa.text("0"),
              comment="Su parte de garantía, importación y otros cobros"),
    sa.Column("costo_pedido_q", sa.Numeric(14, 2), nullable=False,
              comment="Su parte de lo pagado en Q"),
    sa.Column("cantidad_recibida", sa.Integer(), nullable=True),
    sa.Column("courier_q", sa.Numeric(14, 2), nullable=True,
              comment="Su parte del courier y envío local"),
    sa.Column("costo_unitario_q", sa.Numeric(18, 8), nullable=True,
              comment="Puesto en Guatemala, por unidad recibida"),
    sa.Column("orden", sa.SmallInteger(), nullable=False, server_default=sa.text("0")),
    *cols_auditoria(),
    sa.CheckConstraint("cantidad > 0", name="cantidad"),
    sa.Index(None, "negocio_id"),
    sa.Index(None, "importacion_id"),
    sa.Index(None, "item_id"),
    sa.Index(None, "item_variante_id"),
    comment="Líneas de una importación (una por talla/color)",
    **OPCIONES_TABLA,
)

# ---------------------------------------------------------------- cont_ (contabilidad)

cont_cfg_rol_cuenta = sa.Table(
    "cont_cfg_rol_cuenta", metadata,
    sa.Column("codigo", sa.String(40), primary_key=True),
    sa.Column("descripcion_simple", sa.String(120), nullable=False),
    sa.Column("naturaleza", sa.String(10), nullable=False),
    *cols_tiempo(),
    sa.CheckConstraint("naturaleza IN ('deudora','acreedora')", name="naturaleza"),
    comment="Roles de cuenta que usa el motor (global)",
    **OPCIONES_TABLA,
)

cont_cfg_plantilla_plan_cuentas = sa.Table(
    "cont_cfg_plantilla_plan_cuentas", metadata,
    sa.Column("pais_codigo", sa.CHAR(2), sa.ForeignKey("cat_pais.codigo"), primary_key=True),
    sa.Column("tipo_negocio_codigo", sa.String(40), sa.ForeignKey("cat_tipo_negocio.codigo"),
              primary_key=True),
    sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
    sa.Column("contenido", sa.JSON(), nullable=False),
    *cols_tiempo(),
    sa.Index(None, "tipo_negocio_codigo"),
    comment="Plan de cuentas de ejemplo por país y tipo de negocio",
    **OPCIONES_TABLA,
)

cont_cfg_regla_contable = sa.Table(
    "cont_cfg_regla_contable", metadata,
    sa.Column("codigo", sa.String(60), primary_key=True),
    _fk("pais_codigo", sa.CHAR(2), "cat_pais.codigo"),
    sa.Column("tipo_evento", sa.String(30), nullable=False),
    sa.Column("tratamiento_iva", sa.String(12), nullable=False),
    sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
    sa.Column("vigente_desde", sa.Date(), nullable=False),
    sa.Column("descripcion_simple", sa.String(120), nullable=False),
    sa.Column("lineas", sa.JSON(), nullable=False),
    *cols_tiempo(),
    sa.CheckConstraint("tratamiento_iva IN ('separado','sin_separar')", name="tratamiento_iva"),
    sa.Index(None, "pais_codigo", "tipo_evento", "tratamiento_iva"),
    comment="Reglas contables: evento -> líneas por rol de cuenta (a validar por el contador)",
    **OPCIONES_TABLA,
)

cont_libro = sa.Table(
    "cont_libro", metadata,
    col_id(),
    _fk("negocio_id", UUIDBinario(), "core_negocio.id"),
    sa.Column("ultimo_numero", sa.Integer(), nullable=False, server_default=sa.text("0")),
    sa.Column("plan_version", sa.Integer(), nullable=True,
              comment="Versión de la plantilla con que se sembró el plan"),
    *cols_auditoria(),
    sa.UniqueConstraint("negocio_id"),
    comment="Libro de cada negocio: numera los asientos",
    **OPCIONES_TABLA,
)

cont_cuenta_contable = sa.Table(
    "cont_cuenta_contable", metadata,
    col_id(),
    _fk("negocio_id", UUIDBinario(), "core_negocio.id"),
    sa.Column("codigo", sa.String(20), nullable=False),
    sa.Column("nombre", sa.String(120), nullable=False),
    sa.Column("nombre_simple", sa.String(120), nullable=True),
    sa.Column("tipo", sa.String(12), nullable=False),
    sa.Column("naturaleza", sa.String(10), nullable=False),
    _fk("padre_id", UUIDBinario(), "cont_cuenta_contable.id", nullable=True),
    sa.Column("acepta_movimientos", Booleano, nullable=False, server_default=sa.text("1")),
    _fk("rol_cuenta_codigo", sa.String(40), "cont_cfg_rol_cuenta.codigo", nullable=True),
    *cols_auditoria(),
    sa.UniqueConstraint("negocio_id", "codigo"),
    sa.CheckConstraint("tipo IN ('activo','pasivo','patrimonio','ingreso','costo','gasto')",
                       name="tipo"),
    sa.CheckConstraint("naturaleza IN ('deudora','acreedora')", name="naturaleza"),
    sa.Index(None, "padre_id"),
    sa.Index(None, "rol_cuenta_codigo"),
    comment="Plan de cuentas propio de cada negocio",
    **OPCIONES_TABLA,
)

cont_asiento = sa.Table(
    "cont_asiento", metadata,
    col_id(),
    _fk("negocio_id", UUIDBinario(), "core_negocio.id"),
    sa.Column("numero", sa.Integer(), nullable=False, comment="Consecutivo por negocio"),
    sa.Column("fecha", sa.Date(), nullable=False, comment="Día contable (calendario local)"),
    sa.Column("descripcion_simple", sa.String(200), nullable=False),
    sa.Column("tipo_evento", sa.String(30), nullable=False),
    sa.Column("origen_tipo", sa.String(20), nullable=True),
    sa.Column("origen_id", UUIDBinario(), nullable=True),
    sa.Column("regla_codigo", sa.String(60), nullable=True),
    sa.Column("regla_version", sa.Integer(), nullable=True),
    sa.Column("tratamiento_iva", sa.String(12), nullable=True),
    _fk("reverso_de_asiento_id", UUIDBinario(), "cont_asiento.id", nullable=True),
    sa.Column("creado_en", FechaHora, nullable=False, server_default=AHORA),
    sa.Column("creado_por", UUIDBinario(), nullable=True),
    sa.UniqueConstraint("negocio_id", "numero"),
    sa.Index(None, "negocio_id", "fecha"),
    sa.Index(None, "origen_id"),
    sa.Index(None, "reverso_de_asiento_id"),
    comment="Asientos contables (inmutables; se corrigen con un reverso)",
    **OPCIONES_TABLA,
)

cont_asiento_linea = sa.Table(
    "cont_asiento_linea", metadata,
    col_id(),
    _fk("negocio_id", UUIDBinario(), "core_negocio.id"),
    _fk("asiento_id", UUIDBinario(), "cont_asiento.id"),
    _fk("cuenta_contable_id", UUIDBinario(), "cont_cuenta_contable.id"),
    sa.Column("debe", sa.Numeric(14, 2), nullable=False, server_default=sa.text("0")),
    sa.Column("haber", sa.Numeric(14, 2), nullable=False, server_default=sa.text("0")),
    sa.Column("concepto", sa.String(120), nullable=True),
    sa.Column("creado_en", FechaHora, nullable=False, server_default=AHORA),
    sa.Column("creado_por", UUIDBinario(), nullable=True),
    sa.CheckConstraint("(debe > 0 AND haber = 0) OR (debe = 0 AND haber > 0)",
                       name="debe_o_haber"),
    sa.Index(None, "negocio_id"),
    sa.Index(None, "asiento_id"),
    sa.Index(None, "cuenta_contable_id"),
    comment="Líneas de un asiento (inmutables)",
    **OPCIONES_TABLA,
)

PREFIJOS_PERMITIDOS = (
    "cat_", "core_", "fiscal_", "ops_", "cont_", "ia_", "integ_", "dw_", "rpt_", "audit_",
)
