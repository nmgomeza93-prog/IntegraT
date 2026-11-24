"""Formas de entrada y salida de /v1/auth y /v1/yo."""

import uuid
from typing import Annotated

from pydantic import BaseModel, EmailStr, Field, StringConstraints, field_validator

Nombre = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=120)]


class RegistroIn(BaseModel):
    nombre: Nombre
    correo: EmailStr
    clave: Annotated[str, Field(min_length=8, max_length=128)]
    telefono: Annotated[str | None, StringConstraints(strip_whitespace=True, max_length=20)] = None

    @field_validator("correo")
    @classmethod
    def _correo_normalizado(cls, v: str) -> str:
        return v.strip().lower()


class LoginIn(BaseModel):
    correo: EmailStr
    clave: Annotated[str, Field(min_length=1, max_length=128)]

    @field_validator("correo")
    @classmethod
    def _correo_normalizado(cls, v: str) -> str:
        return v.strip().lower()


class RefrescarIn(BaseModel):
    refresh_token: Annotated[str, Field(min_length=20, max_length=200)]


class UsuarioOut(BaseModel):
    id: uuid.UUID
    nombre: str
    correo: str


class TokensOut(BaseModel):
    token_type: str = "bearer"  # noqa: S105 - es el tipo de esquema, no un secreto
    access_token: str
    expira_en: int  # segundos de vida del access_token
    refresh_token: str
    negocio_id: uuid.UUID | None = None  # negocio al que quedó atado el access_token


class SesionOut(TokensOut):
    usuario: UsuarioOut


class NegocioResumen(BaseModel):
    id: uuid.UUID
    nombre: str
    tipo_negocio_codigo: str
    rol: str


class YoOut(BaseModel):
    usuario: UsuarioOut
    negocio_actual_id: uuid.UUID | None  # el del token
    negocios: list[NegocioResumen]
