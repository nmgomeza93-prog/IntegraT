"""Límite de intentos de login, registro y refresco (fuerza bruta y registro masivo)."""

import logging
from datetime import timedelta

import pytest
import sqlalchemy as sa
from conftest import CLAVE_OK, cliente_desde, correo_unico, ip_nueva, registrar_usuario

from integrat.auth import limitador


def _login(cliente, correo, clave):
    return cliente.post("/v1/auth/login", json={"correo": correo, "clave": clave})


def test_el_sexto_intento_fallido_de_un_correo_se_bloquea(cliente_api):
    correo = registrar_usuario(cliente_api)["usuario"]["correo"]
    for _ in range(5):
        assert _login(cliente_api, correo, "clave-equivocada").status_code == 401
    r = _login(cliente_api, correo, "clave-equivocada")
    assert r.status_code == 429
    assert "Demasiados intentos" in r.json()["detail"]
    assert int(r.headers["Retry-After"]) > 0
    # Bloqueado incluso con la contraseña correcta: así un ataque no puede seguir probando
    assert _login(cliente_api, correo, CLAVE_OK).status_code == 429


def test_un_correo_inexistente_se_bloquea_igual_y_no_revela_nada(cliente_api):
    correo = correo_unico("nadie")
    for _ in range(5):
        assert _login(cliente_api, correo, "x" * 10).status_code == 401
    assert _login(cliente_api, correo, "x" * 10).status_code == 429


def test_el_bloqueo_de_un_correo_no_afecta_a_otros(cliente_api):
    victima = registrar_usuario(cliente_api)["usuario"]["correo"]
    otra = registrar_usuario(cliente_api)["usuario"]["correo"]
    for _ in range(6):
        _login(cliente_api, victima, "mala-mala-mala")
    assert _login(cliente_api, victima, CLAVE_OK).status_code == 429
    assert _login(cliente_api, otra, CLAVE_OK).status_code == 200


def test_el_bloqueo_por_correo_vale_desde_cualquier_ip(cliente_api):
    """Un atacante no se libra del bloqueo cambiando (o falseando) su IP."""
    correo = registrar_usuario(cliente_api)["usuario"]["correo"]
    for _ in range(5):
        _login(cliente_api, correo, "mala-mala-mala")
    desde_otra_ip = cliente_desde(ip_nueva())
    assert _login(desde_otra_ip, correo, CLAVE_OK).status_code == 429


def test_un_login_correcto_borra_los_fallos_del_correo(cliente_api):
    correo = registrar_usuario(cliente_api)["usuario"]["correo"]
    for _ in range(4):
        _login(cliente_api, correo, "mala-mala-mala")
    assert _login(cliente_api, correo, CLAVE_OK).status_code == 200
    for _ in range(4):
        assert _login(cliente_api, correo, "mala-mala-mala").status_code == 401
    assert _login(cliente_api, correo, CLAVE_OK).status_code == 200


def test_pasado_el_tiempo_se_puede_volver_a_intentar(cliente_api, monkeypatch):
    correo = registrar_usuario(cliente_api)["usuario"]["correo"]
    for _ in range(5):
        _login(cliente_api, correo, "mala-mala-mala")
    assert _login(cliente_api, correo, CLAVE_OK).status_code == 429
    ahora = limitador._ahora()
    monkeypatch.setattr(limitador, "_ahora", lambda: ahora + timedelta(minutes=16))
    assert _login(cliente_api, correo, CLAVE_OK).status_code == 200


def test_una_ip_que_prueba_muchos_correos_se_bloquea(cliente_api):
    for _ in range(20):
        assert _login(cliente_api, correo_unico("x"), "mala-mala-mala").status_code == 401
    r = _login(cliente_api, correo_unico("x"), "mala-mala-mala")
    assert r.status_code == 429
    # Otra IP sigue pudiendo entrar
    otra = cliente_desde(ip_nueva())
    sesion = registrar_usuario(otra)
    assert _login(otra, sesion["usuario"]["correo"], CLAVE_OK).status_code == 200


def test_el_registro_masivo_desde_una_ip_se_bloquea(cliente_api):
    for _ in range(10):
        registrar_usuario(cliente_api)
    r = cliente_api.post("/v1/auth/registro", json={
        "nombre": "Otro", "correo": correo_unico(), "clave": CLAVE_OK})
    assert r.status_code == 429
    assert "Retry-After" in r.headers
    # Desde otra IP se puede registrar
    registrar_usuario(cliente_desde(ip_nueva()))


def test_los_registros_fallidos_tambien_cuentan(cliente_api):
    existente = registrar_usuario(cliente_api)["usuario"]["correo"]
    for _ in range(9):
        r = cliente_api.post("/v1/auth/registro", json={
            "nombre": "Otro", "correo": existente, "clave": CLAVE_OK})
        assert r.status_code == 409
    r = cliente_api.post("/v1/auth/registro", json={
        "nombre": "Otro", "correo": correo_unico(), "clave": CLAVE_OK})
    assert r.status_code == 429  # el 1.º registro bueno + 9 repetidos = 10 intentos


def test_los_refrescos_invalidos_repetidos_se_bloquean(cliente_api):
    for _ in range(30):
        r = cliente_api.post("/v1/auth/refrescar", json={"refresh_token": "x" * 40})
        assert r.status_code == 401
    r = cliente_api.post("/v1/auth/refrescar", json={"refresh_token": "x" * 40})
    assert r.status_code == 429


def test_la_base_guarda_huellas_y_no_correos_ni_ips(cliente_api, bd_migrada):
    correo = correo_unico("huella")
    _login(cliente_api, correo, "mala-mala-mala")
    with bd_migrada.connect() as con:
        filas = con.execute(sa.text(
            "SELECT accion, clave_tipo, clave_hash FROM core_intento_acceso")).all()
    assert filas
    for accion, tipo, hash_ in filas:
        assert len(hash_) == 64 and "@" not in hash_ and "." not in hash_
        assert accion in {"login", "registro", "refrescar"} and tipo in {"ip", "correo"}
    assert limitador.seguridad.huella(correo) in {f[2] for f in filas}


def test_los_logs_registran_el_intento_sin_correo_completo_ni_clave(cliente_api, caplog):
    correo = correo_unico("logs")
    with caplog.at_level(logging.INFO):
        for _ in range(6):
            _login(cliente_api, correo, "clave-secreta-de-prueba")
    assert "login fallido" in caplog.text and "bloqueo de login" in caplog.text
    assert correo not in caplog.text
    assert "clave-secreta-de-prueba" not in caplog.text


def test_la_limpieza_borra_lo_viejo(cliente_api, bd_migrada, monkeypatch):
    correo = correo_unico("viejo")
    _login(cliente_api, correo, "mala-mala-mala")
    ahora = limitador._ahora()
    monkeypatch.setattr(limitador, "_ahora", lambda: ahora + timedelta(days=2))
    monkeypatch.setattr(limitador.random, "random", lambda: 0.0)  # fuerza la limpieza
    _login(cliente_api, correo_unico("otro"), "mala-mala-mala")
    with bd_migrada.connect() as con:
        quedan = con.execute(sa.text(
            "SELECT COUNT(*) FROM core_intento_acceso WHERE creado_en < :corte"),
            {"corte": ahora + timedelta(days=1)}).scalar_one()
    assert quedan == 0


@pytest.mark.parametrize("accion", ["login", "registro", "refrescar"])
def test_todas_las_acciones_tienen_reglas(accion):
    assert limitador.REGLAS[accion]
