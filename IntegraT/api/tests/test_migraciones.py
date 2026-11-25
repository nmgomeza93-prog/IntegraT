import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from bd_utils import desmigrar, migrar, vaciar_base

from integrat.db.semillas import cargar_semillas
from integrat.db.tablas import PREFIJOS_PERMITIDOS, metadata

COLS_AUDITORIA = {"creado_en", "creado_por", "actualizado_en", "actualizado_por",
                  "eliminado_en", "eliminado_por", "version"}
# Inmutables (CLAUDE.md): no se editan ni se borran, se corrigen con otro registro. Solo creación.
TABLAS_INMUTABLES = {"ops_movimiento_inventario", "cont_asiento", "cont_asiento_linea"}
COLS_INMUTABLES = {"creado_en", "creado_por"}


def _tablas(engine) -> set[str]:
    return set(sa.inspect(engine).get_table_names()) - {"alembic_version"}


def test_upgrade_downgrade_upgrade(engine_pruebas):
    vaciar_base(engine_pruebas)
    migrar(engine_pruebas)
    assert _tablas(engine_pruebas) == set(metadata.tables)
    desmigrar(engine_pruebas)
    assert _tablas(engine_pruebas) == set()
    migrar(engine_pruebas)
    assert _tablas(engine_pruebas) == set(metadata.tables)
    cargar_semillas(engine_pruebas)  # deja la base lista para las demás pruebas


def test_la_metadata_coincide_con_la_base_migrada(bd_migrada):
    with bd_migrada.connect() as con:
        contexto = MigrationContext.configure(con, opts={"compare_type": True})
        diferencias = compare_metadata(contexto, metadata)
    assert diferencias == [], f"tablas.py y las migraciones no coinciden: {diferencias}"


def test_convencion_de_nombres():
    for nombre, tabla in metadata.tables.items():
        assert nombre.startswith(PREFIJOS_PERMITIDOS), f"{nombre}: prefijo no permitido"
        assert nombre == nombre.lower()
        if "id" in tabla.c and tabla.c.id.primary_key:
            exigidas = COLS_INMUTABLES if nombre in TABLAS_INMUTABLES else COLS_AUDITORIA
            faltan = exigidas - set(tabla.c.keys())
            assert not faltan, f"{nombre}: faltan columnas de auditoría {faltan}"


def test_tablas_innodb_utf8mb4(bd_migrada):
    with bd_migrada.connect() as con:
        filas = con.execute(sa.text(
            "SELECT table_name, engine, table_collation FROM information_schema.tables "
            "WHERE table_schema = DATABASE() AND table_name <> 'alembic_version'"
        )).all()
    for nombre, motor, collation in filas:
        assert motor == "InnoDB", nombre
        assert collation.startswith("utf8mb4"), nombre
