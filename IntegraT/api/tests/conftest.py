"""Fixtures de pruebas. Usan SOLO la base local `integrat_test` (Docker), nunca la real.

Antes de correr las pruebas de base de datos:
    docker compose -f infra/docker-compose.yml --env-file .env up -d --wait mysql-test
"""

import itertools
import uuid

import pytest
import sqlalchemy as sa
from bd_utils import migrar, vaciar_base
from fastapi.testclient import TestClient

from integrat.config import ConfigBDPruebas
from integrat.db.conexion import crear_engine


@pytest.fixture(scope="session")
def engine_pruebas():
    cfg = ConfigBDPruebas()  # type: ignore[call-arg]
    engine = crear_engine(cfg)
    try:
        with engine.connect() as con:
            con.execute(sa.text("SELECT 1"))
    except sa.exc.OperationalError as e:
        pytest.fail(
            "No hay conexión con la base local de pruebas. Levántala con:\n"
            "  docker compose -f infra/docker-compose.yml --env-file .env up -d --wait mysql-test\n"
            f"Detalle: {type(e.__cause__).__name__}"
        )
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def bd_migrada(engine_pruebas):
    """Base de pruebas vacía, migrada a la última versión y con semillas."""
    from integrat.db.semillas import cargar_semillas

    vaciar_base(engine_pruebas)
    migrar(engine_pruebas)
    cargar_semillas(engine_pruebas)
    return engine_pruebas


SECRETO_JWT_PRUEBAS = "secreto-solo-para-pruebas-0123456789-abcdefghij"  # no es un secreto real


@pytest.fixture
def cliente_api(bd_migrada, monkeypatch):
    """TestClient de la API contra integrat_test y con un secreto JWT de pruebas."""
    from integrat.config import config_app
    from integrat.dependencias import obtener_engine
    from integrat.main import app

    monkeypatch.setenv("API_JWT_SECRET", SECRETO_JWT_PRUEBAS)
    config_app.cache_clear()
    app.dependency_overrides[obtener_engine] = lambda: bd_migrada
    # Cada prueba llega desde su propia IP: los límites de intentos son reales (por IP y por
    # correo) y no deben acumularse entre pruebas.
    yield cliente_desde(ip_nueva())
    app.dependency_overrides.clear()
    config_app.cache_clear()


_contador_ip = itertools.count(1)


def ip_nueva() -> str:
    n = next(_contador_ip)
    return f"10.{(n >> 16) & 255}.{(n >> 8) & 255}.{n & 255}"


def cliente_desde(ip: str) -> TestClient:
    from integrat.main import app

    return TestClient(app, client=(ip, 50000))


def correo_unico(prefijo: str = "u") -> str:
    return f"{prefijo}-{uuid.uuid4().hex[:12]}@prueba-integrat.com"


CLAVE_OK = "clave-de-prueba-123"


def registrar_usuario(cliente, nombre: str = "Mari", correo: str | None = None) -> dict:
    r = cliente.post("/v1/auth/registro", json={
        "nombre": nombre, "correo": correo or correo_unico(), "clave": CLAVE_OK})
    assert r.status_code == 201, r.text
    return r.json()


def con_token(sesion: dict) -> dict:
    return {"Authorization": f"Bearer {sesion['access_token']}"}


def crear_negocio_api(cliente, sesion: dict, nombre: str = "Comedor Doña Mari",
                      tipo: str = "restaurante", da_factura: str = "no_se") -> dict:
    r = cliente.post("/v1/negocios", headers=con_token(sesion), json={
        "nombre": nombre, "tipo_negocio_codigo": tipo, "da_factura": da_factura})
    assert r.status_code == 201, r.text
    return r.json()
