"""Contraseñas (argon2id) y tokens (JWT de acceso + token de refresco opaco)."""

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from integrat.config import config_app

EMISOR = "integrat"
LARGO_MINIMO_SECRETO = 32

_hasher = PasswordHasher()  # argon2id con parámetros por defecto seguros
# Hash de relleno: al fallar el correo se verifica igual, para no revelar por tiempo si existe.
_HASH_RELLENO = _hasher.hash("relleno-para-igualar-tiempos")


class ErrorToken(Exception):
    """Token ausente, inválido o vencido."""


class ErrorConfiguracion(Exception):
    """Falta configuración obligatoria (p. ej. API_JWT_SECRET)."""


def hashear_clave(clave: str) -> str:
    return _hasher.hash(clave)


def verificar_clave(clave: str, hash_guardado: str | None) -> bool:
    """Verifica en tiempo similar exista o no el usuario (hash_guardado=None)."""
    try:
        return _hasher.verify(hash_guardado or _HASH_RELLENO, clave) and hash_guardado is not None
    except (VerificationError, InvalidHashError):
        return False


def _secreto() -> str:
    secreto = config_app().api_jwt_secret
    if secreto is None or len(secreto.get_secret_value()) < LARGO_MINIMO_SECRETO:
        raise ErrorConfiguracion(
            f"API_JWT_SECRET debe estar definido en .env con al menos {LARGO_MINIMO_SECRETO} "
            "caracteres."
        )
    return secreto.get_secret_value()


@dataclass(frozen=True)
class ClaimsAcceso:
    usuario_id: uuid.UUID
    negocio_id: uuid.UUID | None


def crear_token_acceso(usuario_id: uuid.UUID, negocio_id: uuid.UUID | None) -> tuple[str, int]:
    """Devuelve (token, segundos de vida). El negocio del token es el único origen del negocio."""
    segundos = config_app().api_jwt_acceso_minutos * 60
    ahora = datetime.now(UTC)
    claims = {
        "iss": EMISOR,
        "typ": "acceso",
        "sub": str(usuario_id),
        "neg": str(negocio_id) if negocio_id else None,
        "iat": ahora,
        "exp": ahora + timedelta(seconds=segundos),
    }
    return jwt.encode(claims, _secreto(), algorithm="HS256"), segundos


def leer_token_acceso(token: str) -> ClaimsAcceso:
    try:
        datos = jwt.decode(
            token, _secreto(), algorithms=["HS256"], issuer=EMISOR,
            options={"require": ["exp", "iat", "sub", "iss"]},
        )
        if datos.get("typ") != "acceso":
            raise ErrorToken("tipo")
        neg = datos.get("neg")
        return ClaimsAcceso(uuid.UUID(datos["sub"]), uuid.UUID(neg) if neg else None)
    except (jwt.PyJWTError, ValueError, KeyError) as e:
        raise ErrorToken(type(e).__name__) from e


def nuevo_token_refresco() -> tuple[str, str]:
    """Devuelve (token en claro para el cliente, hash para guardar)."""
    plano = secrets.token_urlsafe(48)
    return plano, hash_token_refresco(plano)


def hash_token_refresco(plano: str) -> str:
    return hashlib.sha256(plano.encode()).hexdigest()
