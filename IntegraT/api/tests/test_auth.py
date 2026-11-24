"""Registro, login, refresco y /v1/yo."""

from datetime import UTC, datetime, timedelta

import jwt
import sqlalchemy as sa
from conftest import CLAVE_OK, SECRETO_JWT_PRUEBAS, con_token, correo_unico, registrar_usuario

from integrat.db.tablas import core_usuario


def test_registro_devuelve_sesion_y_guarda_la_clave_con_argon2id(cliente_api, bd_migrada):
    correo = correo_unico()
    r = cliente_api.post("/v1/auth/registro", json={
        "nombre": "  Mari  ", "correo": correo.upper(), "clave": CLAVE_OK})
    assert r.status_code == 201
    cuerpo = r.json()
    assert cuerpo["usuario"]["nombre"] == "Mari"
    assert cuerpo["usuario"]["correo"] == correo  # normalizado a minúsculas
    assert cuerpo["negocio_id"] is None  # todavía no tiene negocio
    assert cuerpo["access_token"] and cuerpo["refresh_token"]
    with bd_migrada.connect() as con:
        hash_ = con.execute(sa.select(core_usuario.c.clave_hash)
                            .where(core_usuario.c.correo == correo)).scalar_one()
    assert hash_.startswith("$argon2id$")
    assert CLAVE_OK not in hash_


def test_registro_con_correo_repetido_da_409_sin_importar_mayusculas(cliente_api):
    sesion = registrar_usuario(cliente_api)
    r = cliente_api.post("/v1/auth/registro", json={
        "nombre": "Otra", "correo": sesion["usuario"]["correo"].upper(), "clave": CLAVE_OK})
    assert r.status_code == 409


def test_registro_valida_datos(cliente_api):
    base = {"nombre": "Mari", "correo": correo_unico(), "clave": CLAVE_OK}
    assert cliente_api.post("/v1/auth/registro", json={**base, "clave": "corta"}).status_code == 422
    assert cliente_api.post("/v1/auth/registro",
                            json={**base, "correo": "no-es-correo"}).status_code == 422
    assert cliente_api.post("/v1/auth/registro", json={**base, "nombre": " "}).status_code == 422


def test_login_correcto_y_mensaje_unico_si_falla(cliente_api):
    sesion = registrar_usuario(cliente_api)
    correo = sesion["usuario"]["correo"]
    ok = cliente_api.post("/v1/auth/login", json={"correo": correo, "clave": CLAVE_OK})
    assert ok.status_code == 200 and ok.json()["usuario"]["id"] == sesion["usuario"]["id"]

    mala = cliente_api.post("/v1/auth/login", json={"correo": correo, "clave": "otra-clave-xx"})
    inexistente = cliente_api.post("/v1/auth/login",
                                   json={"correo": correo_unico("nadie"), "clave": CLAVE_OK})
    assert mala.status_code == inexistente.status_code == 401
    assert mala.json() == inexistente.json()  # no revela si el correo existe


def test_yo_exige_token_y_describe_al_usuario(cliente_api):
    assert cliente_api.get("/v1/yo").status_code == 401
    sesion = registrar_usuario(cliente_api, "Mari")
    r = cliente_api.get("/v1/yo", headers=con_token(sesion))
    assert r.status_code == 200
    assert r.json()["usuario"]["nombre"] == "Mari"
    assert r.json()["negocios"] == [] and r.json()["negocio_actual_id"] is None


def test_tokens_invalidos_se_rechazan(cliente_api):
    sesion = registrar_usuario(cliente_api)
    usuario_id = sesion["usuario"]["id"]
    ahora = datetime.now(UTC)

    def firmar(secreto=SECRETO_JWT_PRUEBAS, **extra):
        claims = {"iss": "integrat", "typ": "acceso", "sub": usuario_id, "neg": None,
                  "iat": ahora, "exp": ahora + timedelta(minutes=5), **extra}
        return jwt.encode(claims, secreto, algorithm="HS256")

    def llamar(token):
        return cliente_api.get("/v1/yo", headers={"Authorization": f"Bearer {token}"}).status_code

    assert llamar(firmar()) == 200
    assert llamar(firmar(exp=ahora - timedelta(minutes=1))) == 401  # vencido
    assert llamar(firmar(secreto="otro-secreto-distinto-de-32-caracteres-xx")) == 401  # firma
    assert llamar(firmar(typ="refresco")) == 401  # tipo equivocado
    assert llamar(firmar(iss="otro")) == 401
    assert llamar("esto.no.es-un-jwt") == 401
    sin_firma = jwt.encode({"sub": usuario_id}, key="", algorithm="none")
    assert llamar(sin_firma) == 401  # alg=none


def test_refresco_rota_el_token_y_detecta_reutilizacion(cliente_api):
    sesion = registrar_usuario(cliente_api)
    viejo = sesion["refresh_token"]

    r1 = cliente_api.post("/v1/auth/refrescar", json={"refresh_token": viejo})
    assert r1.status_code == 200
    nuevo = r1.json()["refresh_token"]
    assert nuevo != viejo
    assert cliente_api.get("/v1/yo", headers=con_token(r1.json())).status_code == 200

    # Reusar el token viejo: se rechaza y se cierran TODAS las sesiones del usuario.
    assert cliente_api.post("/v1/auth/refrescar", json={"refresh_token": viejo}).status_code == 401
    assert cliente_api.post("/v1/auth/refrescar", json={"refresh_token": nuevo}).status_code == 401


def test_salir_revoca_el_token_de_refresco(cliente_api):
    sesion = registrar_usuario(cliente_api)
    refresco = sesion["refresh_token"]

    assert cliente_api.post("/v1/auth/salir", json={"refresh_token": refresco}).status_code == 204
    # Ya no sirve para renovar la sesión
    r = cliente_api.post("/v1/auth/refrescar", json={"refresh_token": refresco})
    assert r.status_code == 401
    # Salir otra vez, o con un token desconocido, también responde 204 (no revela nada)
    assert cliente_api.post("/v1/auth/salir", json={"refresh_token": refresco}).status_code == 204
    assert cliente_api.post("/v1/auth/salir", json={"refresh_token": "x" * 40}).status_code == 204


def test_salir_no_afecta_las_sesiones_de_otras_personas(cliente_api):
    mari = registrar_usuario(cliente_api, "Mari")
    ana = registrar_usuario(cliente_api, "Ana")
    cliente_api.post("/v1/auth/salir", json={"refresh_token": mari["refresh_token"]})
    r = cliente_api.post("/v1/auth/refrescar", json={"refresh_token": ana["refresh_token"]})
    assert r.status_code == 200


def test_refresco_con_token_desconocido_da_401(cliente_api):
    r = cliente_api.post("/v1/auth/refrescar", json={"refresh_token": "x" * 40})
    assert r.status_code == 401


def test_el_refresco_guarda_solo_el_hash(cliente_api, bd_migrada):
    sesion = registrar_usuario(cliente_api)
    with bd_migrada.connect() as con:
        hashes = con.execute(sa.text("SELECT token_hash FROM core_token_refresco")).scalars().all()
    assert sesion["refresh_token"] not in hashes
    assert all(len(h) == 64 for h in hashes)


def test_sin_secreto_jwt_la_api_no_emite_tokens(cliente_api, monkeypatch):
    from integrat.config import config_app

    monkeypatch.setenv("API_JWT_SECRET", "corto")
    config_app.cache_clear()
    r = cliente_api.post("/v1/auth/registro", json={
        "nombre": "Mari", "correo": correo_unico(), "clave": CLAVE_OK})
    assert r.status_code == 503
    assert "corto" not in r.text
