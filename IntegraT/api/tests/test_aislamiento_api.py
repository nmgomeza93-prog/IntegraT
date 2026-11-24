"""A nivel de API: un negocio nunca ve ni toca los datos de otro.

El negocio sale SIEMPRE del token. Estas pruebas intentan cruzar la frontera de varias formas.
"""

import uuid

import jwt
import pytest
from conftest import (
    SECRETO_JWT_PRUEBAS,
    con_token,
    crear_negocio_api,
    registrar_usuario,
)

from integrat.auth import seguridad


@pytest.fixture
def dos_cuentas(cliente_api):
    """Mari (restaurante) y Ana (tienda en línea), cada una con su negocio y su token."""
    sesion_a = registrar_usuario(cliente_api, "Mari")
    negocio_a = crear_negocio_api(cliente_api, sesion_a, "Comedor Doña Mari", "restaurante")
    sesion_b = registrar_usuario(cliente_api, "Ana")
    negocio_b = crear_negocio_api(cliente_api, sesion_b, "Tienda de Ana", "ventas_en_linea")
    return cliente_api, (sesion_a, negocio_a), (sesion_b, negocio_b)


def test_cada_cuenta_ve_solo_su_negocio(dos_cuentas):
    cliente, (sa_, na), (sb, nb) = dos_cuentas
    a = cliente.get(f"/v1/negocios/{na['id']}", headers=con_token(na["acceso"])).json()
    b = cliente.get(f"/v1/negocios/{nb['id']}", headers=con_token(nb["acceso"])).json()
    assert a["nombre"] == "Comedor Doña Mari" and b["nombre"] == "Tienda de Ana"
    assert a["vocabulario"]["catalogo"] == "Menú" and b["vocabulario"]["catalogo"] == "Productos"
    assert [x["id"] for x in cliente.get("/v1/yo", headers=con_token(sa_)).json()["negocios"]] \
        in ([], [na["id"]])
    yo_b = cliente.get("/v1/yo", headers=con_token(nb["acceso"])).json()
    assert [x["id"] for x in yo_b["negocios"]] == [nb["id"]]


def test_pedir_el_negocio_de_otro_da_404(dos_cuentas):
    cliente, (_, na), (_, nb) = dos_cuentas
    # Ana intenta leer el negocio de Mari poniendo su id en la ruta.
    r = cliente.get(f"/v1/negocios/{na['id']}", headers=con_token(nb["acceso"]))
    assert r.status_code == 404
    assert "Mari" not in r.text
    # Y al revés.
    assert cliente.get(f"/v1/negocios/{nb['id']}",
                       headers=con_token(na["acceso"])).status_code == 404


def test_un_id_inventado_da_el_mismo_404(dos_cuentas):
    cliente, (_, na), _ = dos_cuentas
    r = cliente.get("/v1/negocios/018f0000-0000-7000-8000-000000000000",
                    headers=con_token(na["acceso"]))
    assert r.status_code == 404


def test_un_token_firmado_con_otro_secreto_no_sirve(dos_cuentas):
    cliente, (_, na), (sb, _) = dos_cuentas
    falso = jwt.encode({
        "iss": "integrat", "typ": "acceso", "sub": sb["usuario"]["id"], "neg": na["id"],
        "iat": 1_800_000_000, "exp": 4_000_000_000,
    }, "un-secreto-que-no-es-el-de-la-api-0123456789", algorithm="HS256")
    r = cliente.get(f"/v1/negocios/{na['id']}", headers={"Authorization": f"Bearer {falso}"})
    assert r.status_code == 401


def test_un_token_bien_firmado_con_negocio_ajeno_se_rechaza_por_membresia(dos_cuentas):
    """Defensa en profundidad: aunque alguien lograra firmar, la membresía se revalida."""
    cliente, (_, na), (sb, _) = dos_cuentas
    token, _ = seguridad.crear_token_acceso(
        usuario_id=uuid.UUID(sb["usuario"]["id"]),
        negocio_id=uuid.UUID(na["id"]),
    )
    assert jwt.decode(token, SECRETO_JWT_PRUEBAS, algorithms=["HS256"], issuer="integrat")
    r = cliente.get(f"/v1/negocios/{na['id']}", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_el_cliente_no_puede_elegir_el_negocio_al_crear(dos_cuentas):
    cliente, (_, na), (sb, _) = dos_cuentas
    # Ana manda el negocio_id de Mari en el cuerpo: se ignora y se crea un negocio NUEVO de Ana.
    r = cliente.post("/v1/negocios", headers=con_token(sb), json={
        "nombre": "Otro de Ana", "tipo_negocio_codigo": "ventas_en_linea",
        "negocio_id": na["id"]})
    assert r.status_code == 201
    assert r.json()["id"] != na["id"]
    mari = cliente.get(f"/v1/negocios/{na['id']}", headers=con_token(na["acceso"])).json()
    assert mari["nombre"] == "Comedor Doña Mari"


def test_las_capacidades_de_cada_negocio_son_independientes(dos_cuentas):
    cliente, (_, na), (_, nb) = dos_cuentas
    assert "mesas" in na["capacidades"] and "mesas" not in nb["capacidades"]
    assert "entregas" in nb["capacidades"] and "entregas" not in na["capacidades"]
