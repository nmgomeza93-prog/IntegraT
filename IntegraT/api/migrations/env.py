"""Entorno de Alembic para `integrat`. Las credenciales salen de .env; nunca se imprimen."""

from alembic import context

from integrat.config import ConfigBDPruebas, config_bd
from integrat.db.conexion import crear_engine
from integrat.db.tablas import metadata

config = context.config
target_metadata = metadata


def _engine():
    if context.get_x_argument(as_dictionary=True).get("pruebas") == "si":
        cfg = ConfigBDPruebas()  # type: ignore[call-arg]
    else:
        cfg = config_bd()
    print(f"Migrando {cfg.descripcion_segura()}")
    return crear_engine(cfg)


def run_migrations_online() -> None:
    conexion_externa = config.attributes.get("connection")
    if conexion_externa is not None:  # usada por las pruebas automáticas
        context.configure(connection=conexion_externa, target_metadata=target_metadata,
                          compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
        return

    with _engine().connect() as conexion:
        context.configure(connection=conexion, target_metadata=target_metadata,
                          compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    raise SystemExit("El modo offline no está soportado; ejecuta las migraciones en línea.")
run_migrations_online()
