"""Idempotency-Key en POST /v1/negocios: el mismo intento no crea dos negocios."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import sqlalchemy as sa
from conftest import cliente_desde, con_token, ip_nueva, registrar_usuario

from integrat.negocios import servicio

CUERPO = {"nombre": "Comedor Doña Mari", "tipo_negocio_codigo": "restaurante", "da_factura": "no"}


def _crear(cliente, sesion, clave=None, cuerpo=None):
    cabeceras = con_token(sesion)
    if clave:
        cabeceras["Idempotency-Key"] = clave
    return cliente.post("/v1/negocios", headers=cabeceras, json=cuerpo or CUERPO)


def _negocios_de(cliente, sesion) -> list[str]:
    yo = cliente.get("/v1/yo", headers=con_token(sesion)).json()
    return [n["id"] for n in yo["negocios"]]


def test_la_misma_clave_devuelve_el_mismo_negocio(cliente_api):
    sesion = registrar_usuario(cliente_api)
    clave = f"onboarding-{uuid.uuid4().hex}"
    primero = _crear(cliente_api, sesion, clave)
    repetido = _crear(cliente_api, sesion, clave)
    assert primero.status_code == repetido.status_code == 201
    assert primero.json()["id"] == repetido.json()["id"]
    assert _negocios_de(cliente_api, sesion) == [primero.json()["id"]]
    # La respuesta repetida trae un acceso que sirve
    acceso = repetido.json()["acceso"]
    r = cliente_api.get(f"/v1/negocios/{repetido.json()['id']}", headers=con_token(acceso))
    assert r.status_code == 200


def test_sin_clave_cada_llamada_crea_un_negocio(cliente_api):
    sesion = registrar_usuario(cliente_api)
    _crear(cliente_api, sesion)
    _crear(cliente_api, sesion)
    assert len(_negocios_de(cliente_api, sesion)) == 2


def test_claves_distintas_crean_negocios_distintos(cliente_api):
    sesion = registrar_usuario(cliente_api)
    a = _crear(cliente_api, sesion, "clave-numero-uno").json()["id"]
    b = _crear(cliente_api, sesion, "clave-numero-dos").json()["id"]
    assert a != b


def test_la_misma_clave_con_otros_datos_se_rechaza(cliente_api):
    sesion = registrar_usuario(cliente_api)
    _crear(cliente_api, sesion, "clave-compartida-1")
    r = _crear(cliente_api, sesion, "clave-compartida-1",
               {**CUERPO, "nombre": "Otro nombre distinto"})
    assert r.status_code == 422
    assert "otros datos" in r.json()["detail"]
    assert len(_negocios_de(cliente_api, sesion)) == 1


def test_la_clave_es_por_usuario(cliente_api):
    """Dos personas pueden usar la misma clave sin pisarse ni ver el negocio de la otra."""
    mari = registrar_usuario(cliente_api, "Mari")
    ana = registrar_usuario(cliente_api, "Ana")
    de_mari = _crear(cliente_api, mari, "clave-igual-para-las-dos").json()
    de_ana = _crear(cliente_api, ana, "clave-igual-para-las-dos").json()
    assert de_mari["id"] != de_ana["id"]
    assert _negocios_de(cliente_api, ana) == [de_ana["id"]]


def test_una_clave_vencida_se_puede_reutilizar(cliente_api, bd_migrada):
    sesion = registrar_usuario(cliente_api)
    primero = _crear(cliente_api, sesion, "clave-que-vence-1").json()["id"]
    with bd_migrada.begin() as con:
        con.execute(sa.text("UPDATE core_idempotencia SET creado_en = :t WHERE clave = :c"),
                    {"t": servicio.ahora_utc() - timedelta(hours=25), "c": "clave-que-vence-1"})
    segundo = _crear(cliente_api, sesion, "clave-que-vence-1").json()["id"]
    assert primero != segundo


def test_claves_mal_formadas_se_rechazan(cliente_api):
    sesion = registrar_usuario(cliente_api)
    assert _crear(cliente_api, sesion, "corta").status_code == 422
    assert _crear(cliente_api, sesion, "tiene espacios y /raras").status_code == 422
    assert _crear(cliente_api, sesion, "x" * 101).status_code == 422
    assert _negocios_de(cliente_api, sesion) == []


def test_un_error_de_validacion_no_deja_la_clave_gastada(cliente_api):
    sesion = registrar_usuario(cliente_api)
    malo = {**CUERPO, "tipo_negocio_codigo": "no_existe"}
    assert _crear(cliente_api, sesion, "clave-de-reintento", malo).status_code == 422
    bueno = _crear(cliente_api, sesion, "clave-de-reintento")
    assert bueno.status_code == 201


def test_dos_peticiones_simultaneas_con_la_misma_clave_crean_un_solo_negocio(
    cliente_api, bd_migrada
):
    sesion = registrar_usuario(cliente_api)
    clave = f"carrera-{uuid.uuid4().hex}"
    clientes = [cliente_desde(ip_nueva()) for _ in range(4)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        respuestas = list(pool.map(lambda c: _crear(c, sesion, clave), clientes))
    assert all(r.status_code == 201 for r in respuestas), [r.text for r in respuestas]
    assert len({r.json()["id"] for r in respuestas}) == 1
    assert len(_negocios_de(cliente_api, sesion)) == 1
