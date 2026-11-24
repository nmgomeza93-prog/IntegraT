"""Creación del engine SQLAlchemy hacia MySQL, con TLS y salvaguardas de seguridad."""

import ssl
from functools import lru_cache

import sqlalchemy as sa
from sqlalchemy.engine import URL, Engine

from integrat.config import ConfigBD, config_bd


def _args_ssl(cfg: ConfigBD) -> dict:
    if cfg.sslmode == "disabled":
        return {}
    if cfg.sslmode == "verify_identity":
        if not cfg.ssl_ca:
            raise ValueError("DB_SSLMODE=verify_identity requiere DB_SSL_CA.")
        return {"ssl": {"ca": cfg.ssl_ca, "check_hostname": True}}
    # preferred / required: conexión cifrada sin verificar el certificado del servidor
    contexto = ssl.create_default_context()
    contexto.check_hostname = False
    contexto.verify_mode = ssl.CERT_NONE
    return {"ssl": contexto}


def crear_engine(cfg: ConfigBD | None = None, **kwargs) -> Engine:
    """Engine para la base `integrat` (o `integrat_test`). Nunca abre otra base."""
    cfg = cfg or config_bd()
    url = URL.create(
        "mysql+pymysql",
        username=cfg.user,
        password=cfg.password.get_secret_value(),
        host=cfg.host,
        port=cfg.port,
        database=cfg.name,
        query={"charset": cfg.charset},
    )
    engine = sa.create_engine(
        url,
        pool_pre_ping=True,
        pool_recycle=280,
        connect_args={"connect_timeout": cfg.connect_timeout, **_args_ssl(cfg)},
        **kwargs,
    )

    @sa.event.listens_for(engine, "connect")
    def _al_conectar(dbapi_con, _registro):
        with dbapi_con.cursor() as cur:
            # UTC en la sesión; la zona del negocio se aplica en la capa de dominio.
            cur.execute("SET time_zone = '+00:00'")
            # Salvaguarda: la sesión debe estar en la base permitida.
            cur.execute("SELECT DATABASE()")
            (base,) = cur.fetchone()
            if base != cfg.name:
                raise RuntimeError("La conexión no quedó en la base permitida.")

    return engine


@lru_cache
def engine_principal() -> Engine:
    """Engine compartido de la API (base real, DB_* de .env). Se crea una sola vez."""
    return crear_engine(config_bd(), pool_size=5, max_overflow=5, pool_timeout=10)
