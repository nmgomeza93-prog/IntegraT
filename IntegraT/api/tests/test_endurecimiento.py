"""Superficie mínima en piloto y producción, y límite de tamaño de las peticiones."""

import pytest
from fastapi.testclient import TestClient

from integrat.config import config_app
from integrat.dependencias import obtener_engine


@pytest.fixture
def app_en():
    """Crea una app nueva como si APP_ENV fuera el indicado."""
    from integrat import main

    def _crear(entorno: str, monkeypatch, bd):
        monkeypatch.setenv("APP_ENV", entorno)
        config_app.cache_clear()
        monkeypatch.setattr(main, "configurar_logs", lambda: None)  # no pisar el log de pytest
        app = main.crear_app()
        app.dependency_overrides[obtener_engine] = lambda: bd
        return TestClient(app)

    yield _crear
    config_app.cache_clear()


@pytest.mark.parametrize("entorno", ["piloto", "prod"])
def test_sin_documentacion_fuera_de_dev(app_en, monkeypatch, bd_migrada, entorno):
    cliente = app_en(entorno, monkeypatch, bd_migrada)
    for ruta in ("/docs", "/redoc", "/v1/openapi.json"):
        assert cliente.get(ruta).status_code == 404, ruta


def test_la_documentacion_existe_en_dev(app_en, monkeypatch, bd_migrada):
    cliente = app_en("dev", monkeypatch, bd_migrada)
    assert cliente.get("/docs").status_code == 200
    assert cliente.get("/v1/openapi.json").status_code == 200


@pytest.mark.parametrize("entorno", ["piloto", "prod"])
def test_la_salud_publica_no_revela_entorno_ni_migracion(app_en, monkeypatch, bd_migrada, entorno):
    cliente = app_en(entorno, monkeypatch, bd_migrada)
    r = cliente.get("/v1/salud")
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["estado"] == "ok" and cuerpo["bd"]["conectada"] is True
    assert cuerpo["entorno"] is None
    assert cuerpo["bd"]["migracion"] is None
    assert entorno not in r.text and "0014" not in r.text


def test_la_salud_en_dev_si_da_el_detalle(app_en, monkeypatch, bd_migrada):
    cuerpo = app_en("dev", monkeypatch, bd_migrada).get("/v1/salud").json()
    assert cuerpo["entorno"] == "dev"
    assert cuerpo["bd"]["migracion"] == "0014"


def test_una_peticion_enorme_se_rechaza_con_413(cliente_api):
    r = cliente_api.post("/v1/auth/login", content=b"x" * 70_000,
                         headers={"Content-Type": "application/json"})
    assert r.status_code == 413
    assert "demasiado grande" in r.json()["detail"]


def test_un_cuerpo_enorme_por_partes_tambien_se_rechaza(cliente_api):
    def partes():
        for _ in range(100):
            yield b"x" * 1000

    r = cliente_api.post("/v1/auth/login", content=partes(),
                         headers={"Content-Type": "application/json"})
    assert r.status_code == 413


def test_una_peticion_normal_pasa_el_limite(cliente_api):
    r = cliente_api.post("/v1/auth/login", json={"correo": "a@b.com", "clave": "x" * 100})
    assert r.status_code == 401  # llegó a la lógica de login, no la cortó el límite


def test_sin_origenes_configurados_no_hay_cors(app_en, monkeypatch, bd_migrada):
    monkeypatch.setenv("API_ALLOWED_ORIGINS", "")
    cliente = app_en("piloto", monkeypatch, bd_migrada)
    r = cliente.get("/v1/salud", headers={"Origin": "https://otro-sitio.example"})
    assert "access-control-allow-origin" not in r.headers
