"""Catálogos, creación de negocio por tipo y onboarding."""

import sqlalchemy as sa
from conftest import CLAVE_OK, con_token, crear_negocio_api, registrar_usuario


def test_catalogo_de_tipos_de_negocio_es_publico(cliente_api):
    r = cliente_api.get("/v1/tipos-negocio")
    assert r.status_code == 200
    codigos = [t["codigo"] for t in r.json()]
    assert codigos == ["ventas_en_linea", "restaurante"]  # en el orden del catálogo
    assert all(t["nombre"] and t["icono"] for t in r.json())


def test_catalogo_de_regimenes_marca_lo_no_validado(cliente_api):
    r = cliente_api.get("/v1/regimenes", params={"pais": "gt"})
    assert r.status_code == 200 and r.json()
    # Nada fiscal está validado todavía por un contador (docs/REVISION_CONTADOR.md).
    assert not any(x["validado_por_contador"] for x in r.json())
    assert cliente_api.get("/v1/regimenes", params={"pais": "ZZ"}).json() == []


def test_restaurante_recibe_menu_mesas_y_su_checklist(cliente_api):
    sesion = registrar_usuario(cliente_api)
    n = crear_negocio_api(cliente_api, sesion, "Comedor Doña Mari", "restaurante")
    assert n["nombre"] == "Comedor Doña Mari"
    assert n["pais_codigo"] == "GT" and n["moneda_codigo"] == "GTQ"
    assert n["zona_horaria"] == "America/Guatemala"
    assert n["vocabulario"]["catalogo"] == "Menú"
    assert "mesas" in n["capacidades"] and "recetas" in n["capacidades"]
    assert "entregas" not in n["capacidades"]  # existe pero inactiva: no se lista
    textos = [p["texto"] for p in n["primeros_pasos"]]
    assert textos[0] == "Agrega tus 5 platillos más vendidos"
    assert textos[1:4] == ["Anota tus insumos principales", "Registra tu primera compra",
                           "Dinos qué lleva tu platillo estrella"]
    assert len(textos) == 5 and not any(p["hecho"] for p in n["primeros_pasos"])


def test_negocio_en_linea_cambia_el_vocabulario(cliente_api):
    sesion = registrar_usuario(cliente_api)
    n = crear_negocio_api(cliente_api, sesion, "Tienda de Ana", "ventas_en_linea")
    assert n["vocabulario"]["catalogo"] == "Productos"
    assert "entregas" in n["capacidades"] and "mesas" not in n["capacidades"]
    assert n["primeros_pasos"][0]["texto"] == "Agrega tu primer producto"


def test_la_respuesta_trae_un_acceso_atado_al_negocio(cliente_api):
    sesion = registrar_usuario(cliente_api)
    n = crear_negocio_api(cliente_api, sesion)
    acceso = n["acceso"]
    assert acceso["negocio_id"] == n["id"]
    r = cliente_api.get(f"/v1/negocios/{n['id']}", headers=con_token(acceso))
    assert r.status_code == 200 and r.json()["nombre"] == n["nombre"]
    # El token de antes del negocio no sirve para verlo.
    assert cliente_api.get(f"/v1/negocios/{n['id']}", headers=con_token(sesion)).status_code == 403


def test_al_volver_a_entrar_el_token_ya_trae_el_negocio(cliente_api):
    sesion = registrar_usuario(cliente_api)
    n = crear_negocio_api(cliente_api, sesion)
    correo = sesion["usuario"]["correo"]
    login = cliente_api.post("/v1/auth/login", json={"correo": correo, "clave": CLAVE_OK}).json()
    assert login["negocio_id"] == n["id"]
    yo = cliente_api.get("/v1/yo", headers=con_token(login)).json()
    assert [x["id"] for x in yo["negocios"]] == [n["id"]]
    assert yo["negocios"][0]["rol"] == "dueno"
    renovado = cliente_api.post("/v1/auth/refrescar",
                                json={"refresh_token": login["refresh_token"]}).json()
    assert renovado["negocio_id"] == n["id"]


def test_da_factura_si_abre_un_titular_pendiente(cliente_api, bd_migrada):
    sesion = registrar_usuario(cliente_api)
    n = crear_negocio_api(cliente_api, sesion, da_factura="si")
    assert n["da_factura"] == "si"
    with bd_migrada.connect() as con:
        titular = con.execute(sa.text(
            "SELECT t.estado, t.nit FROM core_negocio n JOIN core_titular t ON t.id = n.titular_id "
            "WHERE n.id = :id"), {"id": bytes.fromhex(n["id"].replace("-", ""))}).one()
    assert titular.estado == "pendiente" and titular.nit is None


def test_da_factura_no_no_crea_titular(cliente_api, bd_migrada):
    sesion = registrar_usuario(cliente_api)
    n = crear_negocio_api(cliente_api, sesion, da_factura="no")
    with bd_migrada.connect() as con:
        titular_id = con.execute(sa.text("SELECT titular_id FROM core_negocio WHERE id = :id"),
                                 {"id": bytes.fromhex(n["id"].replace("-", ""))}).scalar_one()
    assert titular_id is None


def test_tipo_de_negocio_inexistente_se_rechaza(cliente_api):
    sesion = registrar_usuario(cliente_api)
    r = cliente_api.post("/v1/negocios", headers=con_token(sesion), json={
        "nombre": "Algo", "tipo_negocio_codigo": "no_existe"})
    assert r.status_code == 422
    assert cliente_api.get("/v1/yo", headers=con_token(sesion)).json()["negocios"] == []


def test_crear_negocio_exige_sesion_y_datos_validos(cliente_api):
    cuerpo = {"nombre": "Algo", "tipo_negocio_codigo": "restaurante"}
    assert cliente_api.post("/v1/negocios", json=cuerpo).status_code == 401
    sesion = registrar_usuario(cliente_api)
    malo = {**cuerpo, "nombre": " "}
    assert cliente_api.post("/v1/negocios", headers=con_token(sesion), json=malo).status_code == 422
    malo = {**cuerpo, "da_factura": "quizas"}
    assert cliente_api.post("/v1/negocios", headers=con_token(sesion), json=malo).status_code == 422


# ------------------------------------------------------------------ Mi negocio


def test_mi_negocio_cambia_contacto_y_datos_para_facturar(cliente_api, bd_migrada):
    sesion = registrar_usuario(cliente_api, "Mari")
    negocio = crear_negocio_api(cliente_api, sesion, "Comedor", "restaurante")
    h = con_token(negocio["acceso"])
    ruta = f"/v1/negocios/{negocio['id']}"
    r = cliente_api.put(f"{ruta}/datos", headers=h, json={
        "nombre": "Comedor Doña Mari", "telefono": "5555-1234", "correo": "Mari@Gmail.com",
        "direccion": "Zona 1", "nit": "1234567-9", "nombre_fiscal": "María Pérez"})
    assert r.status_code == 204, r.text
    n = cliente_api.get(ruta, headers=h).json()
    assert (n["nombre"], n["telefono"], n["correo"], n["direccion"], n["nit"],
            n["nombre_fiscal"]) == ("Comedor Doña Mari", "+50255551234", "mari@gmail.com",
                                    "Zona 1", "12345679", "María Pérez")
    # Solo cambia lo que se envía; null lo borra.
    cliente_api.put(f"{ruta}/datos", headers=h, json={"direccion": None})
    n = cliente_api.get(ruta, headers=h).json()
    assert n["direccion"] is None and n["nombre"] == "Comedor Doña Mari"
    r = cliente_api.put(f"{ruta}/datos", headers=h, json={"nit": "1234567-8"})
    assert r.status_code == 422 and "NIT" in r.json()["detail"]
    r = cliente_api.put(f"{ruta}/datos", headers=h, json={"nombre": "C"})
    assert r.json()["detail"] == "Revisa el nombre: escribe al menos 2 letras."
    # Un administrador cambia el contacto, pero no el NIT.
    with bd_migrada.begin() as con:
        con.execute(sa.text("UPDATE core_membresia SET rol = 'administrador' "
                            "WHERE negocio_id = UUID_TO_BIN(:n)"), {"n": negocio["id"]})
    assert cliente_api.put(f"{ruta}/datos", headers=h,
                           json={"telefono": "44441234"}).status_code == 204
    assert cliente_api.put(f"{ruta}/datos", headers=h, json={"nit": "CF"}).status_code == 403
