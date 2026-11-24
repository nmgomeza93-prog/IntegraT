"""Configuración de IntegraT: se lee SOLO de variables de entorno / archivo .env.

Reglas:
- Ningún valor por defecto contiene secretos.
- Las contraseñas son SecretStr: nunca aparecen en repr(), str() ni en logs.
- La base de datos siempre debe llamarse "integrat" (o "integrat_test" para pruebas).
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# api/src/integrat/config.py -> raíz del proyecto IntegraT
RAIZ_PROYECTO = Path(__file__).resolve().parents[3]
ARCHIVO_ENV = RAIZ_PROYECTO / ".env"

BASES_PERMITIDAS = ("integrat", "integrat_test")

ModoSSL = Literal["disabled", "preferred", "required", "verify_identity"]


class ConfigBD(BaseSettings):
    """Parámetros de conexión a una base MySQL (real o de pruebas)."""

    model_config = SettingsConfigDict(env_file=ARCHIVO_ENV, extra="ignore", frozen=True)

    host: str
    port: int = 3306
    name: str
    user: str
    password: SecretStr
    sslmode: ModoSSL = "preferred"
    ssl_ca: str | None = None
    charset: str = "utf8mb4"
    connect_timeout: int = 15

    @field_validator("name")
    @classmethod
    def _solo_bases_integrat(cls, valor: str) -> str:
        if valor not in BASES_PERMITIDAS:
            raise ValueError(
                f"Base de datos no permitida: solo se admite {BASES_PERMITIDAS} "
                "(regla de seguridad: nunca tocar otras bases del servidor)."
            )
        return valor

    def descripcion_segura(self) -> str:
        """Texto para logs: sin usuario ni contraseña."""
        return f"mysql://{self.host}:{self.port}/{self.name} (ssl={self.sslmode})"


class ConfigBDReal(ConfigBD):
    model_config = SettingsConfigDict(
        env_file=ARCHIVO_ENV, env_prefix="DB_", extra="ignore", frozen=True
    )


class ConfigBDPruebas(ConfigBD):
    model_config = SettingsConfigDict(
        env_file=ARCHIVO_ENV, env_prefix="TEST_DB_", extra="ignore", frozen=True
    )

    @field_validator("host")
    @classmethod
    def _solo_local(cls, valor: str) -> str:
        if valor not in ("127.0.0.1", "localhost"):
            raise ValueError("La base de pruebas debe ser local (las pruebas borran tablas).")
        return valor

    @field_validator("name")
    @classmethod
    def _solo_base_test(cls, valor: str) -> str:
        if valor != "integrat_test":
            raise ValueError("La base de pruebas debe llamarse integrat_test.")
        return valor


@lru_cache
def config_bd() -> ConfigBDReal:
    return ConfigBDReal()  # type: ignore[call-arg]
