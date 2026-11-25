import logging

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from integrat.config import ConfigBDPruebas
from integrat.db.conexion import crear_engine
from integrat.main import app
from integrat.salud.router import obtener_engine

CLAVE_INCORRECTA = "clave-incorrecta-de-prueba"


@pytest.fixture(autouse=True)
def entorno_dev(monkeypatch):
    """Estas pruebas describen el comportamiento en dev, sin importar el APP_ENV del .env."""
    from integrat.config import config_app

    monkeypatch.setenv("APP_ENV", "dev")
    config_app.cache_clear()
    yield
    config_app.cache_clear()


@pytest.fixture
def cliente():
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_salud_ok_con_base_migrada(cliente, bd_migrada):
    app.dependency_overrides[obtener_engine] = lambda: bd_migrada
    r = cliente.get("/v1/salud")
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["estado"] == "ok"
    assert cuerpo["bd"]["conectada"] is True
    assert cuerpo["bd"]["migracion"] == "0014"
    assert cuerpo["bd"]["latencia_ms"] >= 0


def test_salud_sin_base_no_filtra_secretos(cliente, caplog):
    cfg = ConfigBDPruebas().model_copy(update={"password": SecretStr(CLAVE_INCORRECTA),
                                               "connect_timeout": 3})
    app.dependency_overrides[obtener_engine] = lambda: crear_engine(cfg)
    with caplog.at_level(logging.DEBUG):
        r = cliente.get("/v1/salud")
    assert r.status_code == 503
    assert r.json()["estado"] == "degradado"
    assert r.json()["bd"] == {"conectada": False, "latencia_ms": None, "migracion": None}
    for texto in (r.text, caplog.text):
        assert CLAVE_INCORRECTA not in texto
        assert cfg.user not in texto
        assert cfg.host not in texto


def test_openapi_publicado_en_dev():
    from integrat.main import crear_app

    r = TestClient(crear_app()).get("/v1/openapi.json")
    assert r.status_code == 200
    assert "/v1/salud" in r.json()["paths"]
