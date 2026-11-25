"""Ventas rápidas: /v1/ventas."""

import threading
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from conftest import cliente_desde, con_token, crear_negocio_api, ip_nueva, registrar_usuario


@pytest.fixture
def restaurante(cliente_api):
    sesion = registrar_usuario(cliente_api, "Mari")
    negocio = crear_negocio_api(cliente_api, sesion, "Comedor Doña Mari", "restaurante")
    return cliente_api, negocio, con_token(negocio["acceso"])


@pytest.fixture
def tienda(cliente_api):
    sesion = registrar_usuario(cliente_api, "Ana")
    negocio = crear_negocio_api(cliente_api, sesion, "Tienda de Ana", "ventas_en_linea")
    return cliente_api, negocio, con_token(negocio["acceso"])


def item(cliente, h, nombre="Pepián", precio="45.00"):
    r = cliente.post("/v1/items", json={"nombre": nombre, "precio_venta": precio}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


def vender(cliente, h, lineas, medio="efectivo", clave=None):
    cabeceras = {**h, **({"Idempotency-Key": clave} if clave else {})}
    return cliente.post("/v1/ventas", headers=cabeceras, json={
        "lineas": [{"item_id": i, "cantidad": c} for i, c in lineas], "medio_pago": medio})


# ------------------------------------------------------------------ cobrar

def test_la_api_calcula_el_total_con_el_precio_vigente(restaurante):
    cliente, _, h = restaurante
    pepian = item(cliente, h, "Pepián", "45.50")
    jugo = item(cliente, h, "Jugo", "10")
    r = vender(cliente, h, [(pepian["id"], 2), (jugo["id"], 3)], "tarjeta")
    assert r.status_code == 201, r.text
    v = r.json()
    assert v["total"] == "121.00"  # 2×45.50 + 3×10.00
    assert v["numero"] == 1 and v["estado"] == "pagada" and v["moneda_codigo"] == "GTQ"
    assert v["medio_pago"] == "tarjeta"
    assert {(x["nombre"], x["cantidad"], x["precio_unitario"], x["total"]) for x in v["lineas"]} \
        == {("Pepián", 2, "45.50", "91.00"), ("Jugo", 3, "10.00", "30.00")}
    assert v["fecha_hora"].endswith("Z") or v["fecha_hora"].endswith("+00:00")


def test_el_mismo_item_repetido_se_suma(restaurante):
    cliente, _, h = restaurante
    a = item(cliente, h, "Café", "8")
    v = vender(cliente, h, [(a["id"], 1), (a["id"], 2)]).json()
    assert len(v["lineas"]) == 1 and v["lineas"][0]["cantidad"] == 3 and v["total"] == "24.00"


def test_los_numeros_de_venta_son_consecutivos_por_negocio(restaurante, tienda):
    cliente, _, h = restaurante
    a = item(cliente, h)
    assert [vender(cliente, h, [(a["id"], 1)]).json()["numero"] for _ in range(3)] == [1, 2, 3]
    producto = item(tienda[0], tienda[2], "Camisa", "99")
    assert vender(tienda[0], tienda[2], [(producto["id"], 1)]).json()["numero"] == 1


def test_el_precio_queda_congelado_aunque_se_cambie_el_catalogo(restaurante):
    cliente, _, h = restaurante
    a = item(cliente, h, "Pepián", "45")
    venta = vender(cliente, h, [(a["id"], 1)]).json()
    cliente.patch(f"/v1/items/{a['id']}", headers=h,
                  json={"version": 1, "nombre": "Pepián especial", "precio_venta": "99"})
    antes = cliente.get(f"/v1/ventas/{venta['id']}", headers=h).json()
    assert antes["total"] == "45.00"
    linea = antes["lineas"][0]
    assert linea["nombre"] == "Pepián" and linea["precio_unitario"] == "45.00"
    # Y la venta nueva ya usa el precio nuevo
    nueva = vender(cliente, h, [(a["id"], 1)]).json()
    assert nueva["total"] == "99.00" and nueva["lineas"][0]["nombre"] == "Pepián especial"


def test_la_app_no_puede_mandar_precios_ni_totales(restaurante):
    cliente, _, h = restaurante
    a = item(cliente, h, "Pepián", "45")
    r = cliente.post("/v1/ventas", headers=h, json={
        "lineas": [{"item_id": a["id"], "cantidad": 1, "precio_unitario": "1.00"}],
        "medio_pago": "efectivo", "total": "0.01"})
    assert r.status_code == 201 and r.json()["total"] == "45.00"  # lo extra se ignora


@pytest.mark.parametrize("cuerpo", [
    {"lineas": [], "medio_pago": "efectivo"},                                     # carrito vacío
    {"lineas": [{"item_id": str(uuid.uuid4()), "cantidad": 0}], "medio_pago": "efectivo"},
    {"lineas": [{"item_id": str(uuid.uuid4()), "cantidad": 1000}], "medio_pago": "efectivo"},
    {"lineas": [{"item_id": str(uuid.uuid4()), "cantidad": 1}], "medio_pago": "cheque"},
    {"lineas": [{"item_id": str(uuid.uuid4()), "cantidad": 1}]},                  # sin medio
    {"medio_pago": "efectivo"},                                                    # sin líneas
])
def test_datos_invalidos_dan_422(restaurante, cuerpo):
    cliente, _, h = restaurante
    assert cliente.post("/v1/ventas", headers=h, json=cuerpo).status_code == 422


def test_no_se_vende_lo_que_no_existe_o_esta_archivado(restaurante):
    cliente, _, h = restaurante
    a = item(cliente, h, "Pepián")
    r = vender(cliente, h, [(str(uuid.uuid4()), 1)])
    assert r.status_code == 422 and "ya no está disponible" in r.json()["detail"]
    cliente.delete(f"/v1/items/{a['id']}", headers=h)
    assert vender(cliente, h, [(a["id"], 1)]).status_code == 422
    # Una línea mala no deja ventas a medias
    b = item(cliente, h, "Café")
    assert vender(cliente, h, [(b["id"], 1), (str(uuid.uuid4()), 1)]).status_code == 422
    assert cliente.get("/v1/ventas", headers=h).json()["resumen"]["cantidad"] == 0


# ------------------------------------------------------------------ idempotencia y concurrencia

def test_la_misma_clave_no_cobra_dos_veces(restaurante):
    cliente, _, h = restaurante
    a = item(cliente, h)
    r1 = vender(cliente, h, [(a["id"], 1)], clave="venta-reintento-1")
    r2 = vender(cliente, h, [(a["id"], 1)], clave="venta-reintento-1")  # respuesta perdida
    assert r1.status_code == r2.status_code == 201 and r1.json()["id"] == r2.json()["id"]
    assert cliente.get("/v1/ventas", headers=h).json()["resumen"]["cantidad"] == 1
    otro = vender(cliente, h, [(a["id"], 2)], clave="venta-reintento-1")
    assert otro.status_code == 422 and "clave" in otro.json()["detail"]


def test_ventas_simultaneas_no_repiten_numero(restaurante):
    cliente, negocio, h = restaurante
    a = item(cliente, h)
    resultados = []

    def cobrar_una():
        c = cliente_desde(ip_nueva())
        resultados.append(vender(c, h, [(a["id"], 1)]))

    hilos = [threading.Thread(target=cobrar_una) for _ in range(6)]
    for t in hilos:
        t.start()
    for t in hilos:
        t.join()
    assert [r.status_code for r in resultados] == [201] * 6, [r.text for r in resultados]
    numeros = sorted(r.json()["numero"] for r in resultados)
    assert numeros == [1, 2, 3, 4, 5, 6]


def test_el_doble_toque_simultaneo_con_la_misma_clave_cobra_una_vez(restaurante):
    cliente, _, h = restaurante
    a = item(cliente, h)
    resultados = []

    def cobrar_una():
        c = cliente_desde(ip_nueva())
        resultados.append(vender(c, h, [(a["id"], 1)], clave="doble-toque-01"))

    hilos = [threading.Thread(target=cobrar_una) for _ in range(4)]
    for t in hilos:
        t.start()
    for t in hilos:
        t.join()
    assert all(r.status_code == 201 for r in resultados)
    assert len({r.json()["id"] for r in resultados}) == 1
    assert cliente.get("/v1/ventas", headers=h).json()["resumen"]["cantidad"] == 1


# ------------------------------------------------------------------ lo vendido hoy

def test_el_resumen_del_dia_separa_por_medio_y_no_cuenta_anuladas(restaurante):
    cliente, _, h = restaurante
    a = item(cliente, h, "Pepián", "45")
    vender(cliente, h, [(a["id"], 2)], "efectivo")
    vender(cliente, h, [(a["id"], 1)], "tarjeta")
    mala = vender(cliente, h, [(a["id"], 4)], "transferencia").json()
    cliente.post(f"/v1/ventas/{mala['id']}/anular", headers=h, json={"motivo": "Me equivoqué"})
    dia = cliente.get("/v1/ventas", headers=h).json()
    assert dia["resumen"] == {"cantidad": 2, "total": "135.00",
                              "por_medio": {"efectivo": "90.00", "tarjeta": "45.00",
                                            "transferencia": "0.00"}}
    assert [v["numero"] for v in dia["ventas"]] == [3, 2, 1]  # la más reciente primero
    assert dia["ventas"][0]["estado"] == "anulada"  # se ve, pero no suma


def test_un_dia_sin_ventas_y_otro_dia(restaurante):
    cliente, _, h = restaurante
    a = item(cliente, h)
    vender(cliente, h, [(a["id"], 1)])
    ayer = (datetime.now(UTC) - timedelta(days=2)).date().isoformat()
    vacio = cliente.get(f"/v1/ventas?fecha={ayer}", headers=h).json()
    assert vacio["ventas"] == [] and vacio["resumen"]["total"] == "0.00"
    assert cliente.get("/v1/ventas?fecha=no-es-fecha", headers=h).status_code == 422


def test_el_dia_se_cuenta_en_la_zona_horaria_del_negocio(restaurante, bd_migrada):
    """Una venta a las 02:00 UTC es del día anterior en Guatemala (UTC-6)."""
    cliente, negocio, h = restaurante
    a = item(cliente, h)
    v = vender(cliente, h, [(a["id"], 1)]).json()
    with bd_migrada.begin() as con:
        con.execute(sa.text("UPDATE ops_venta SET fecha_hora = '2026-03-10 02:00:00' "
                            "WHERE id = :i"), {"i": uuid.UUID(v["id"]).bytes})
    del_9 = cliente.get("/v1/ventas?fecha=2026-03-09", headers=h).json()
    del_10 = cliente.get("/v1/ventas?fecha=2026-03-10", headers=h).json()
    assert del_9["resumen"]["cantidad"] == 1 and del_10["resumen"]["cantidad"] == 0


# ------------------------------------------------------------------ anular

def test_anular_guarda_el_motivo_y_no_borra(restaurante, bd_migrada):
    cliente, _, h = restaurante
    a = item(cliente, h)
    v = vender(cliente, h, [(a["id"], 1)]).json()
    r = cliente.post(f"/v1/ventas/{v['id']}/anular", headers=h, json={"motivo": "  Cobré de más "})
    assert r.status_code == 200, r.text
    anulada = r.json()
    assert anulada["estado"] == "anulada" and anulada["motivo_anulacion"] == "Cobré de más"
    assert anulada["anulada_en"] is not None and anulada["total"] == v["total"]
    assert cliente.get(f"/v1/ventas/{v['id']}", headers=h).json()["estado"] == "anulada"
    with bd_migrada.connect() as con:
        anuladas = con.execute(
            sa.text("SELECT COUNT(*) FROM ops_venta WHERE estado = 'anulada'")).scalar()
    assert anuladas >= 1
    # No se anula dos veces, ni sin motivo, ni una que no existe
    assert cliente.post(f"/v1/ventas/{v['id']}/anular", headers=h,
                        json={"motivo": "Otra vez"}).status_code == 409
    nueva = vender(cliente, h, [(a["id"], 1)]).json()
    assert cliente.post(f"/v1/ventas/{nueva['id']}/anular", headers=h,
                        json={"motivo": "ab"}).status_code == 422
    assert cliente.post(f"/v1/ventas/{uuid.uuid4()}/anular", headers=h,
                        json={"motivo": "No existe"}).status_code == 404


def test_no_hay_forma_de_editar_ni_borrar_una_venta(restaurante):
    cliente, _, h = restaurante
    a = item(cliente, h)
    v = vender(cliente, h, [(a["id"], 1)]).json()
    for metodo in ("put", "patch", "delete"):
        assert getattr(cliente, metodo)(f"/v1/ventas/{v['id']}", headers=h).status_code == 405


# ------------------------------------------------------------------ aislamiento y permisos

def test_un_negocio_no_ve_ni_anula_las_ventas_de_otro(restaurante, tienda):
    cliente = restaurante[0]
    h_mari, h_ana = restaurante[2], tienda[2]
    a = item(cliente, h_mari, "Pepián", "45")
    v = vender(cliente, h_mari, [(a["id"], 1)]).json()

    assert cliente.get("/v1/ventas", headers=h_ana).json()["ventas"] == []
    assert cliente.get(f"/v1/ventas/{v['id']}", headers=h_ana).status_code == 404
    r = cliente.post(f"/v1/ventas/{v['id']}/anular", headers=h_ana, json={"motivo": "Sabotaje"})
    assert r.status_code == 404 and "Pepián" not in r.text
    # Ana tampoco puede vender un platillo de Mari
    assert vender(cliente, h_ana, [(a["id"], 1)]).status_code == 422
    assert cliente.get(f"/v1/ventas/{v['id']}", headers=h_mari).json()["estado"] == "pagada"


def test_sin_token_o_sin_negocio_no_se_entra(cliente_api):
    assert cliente_api.get("/v1/ventas").status_code == 401
    assert cliente_api.post("/v1/ventas", json={}).status_code == 401
    sesion = registrar_usuario(cliente_api, "Sin negocio")
    assert cliente_api.get("/v1/ventas", headers=con_token(sesion)).status_code == 403


def test_un_cajero_vende_pero_no_anula(restaurante, bd_migrada):
    cliente, _, h = restaurante
    a = item(cliente, h)
    v = vender(cliente, h, [(a["id"], 1)]).json()
    with bd_migrada.begin() as con:
        con.execute(sa.text("UPDATE core_membresia SET rol = 'cajero' WHERE negocio_id IN "
                            "(SELECT negocio_id FROM (SELECT negocio_id FROM core_membresia "
                            "ORDER BY creado_en DESC LIMIT 1) t)"))
    assert vender(cliente, h, [(a["id"], 1)]).status_code == 201
    assert cliente.post(f"/v1/ventas/{v['id']}/anular", headers=h,
                        json={"motivo": "Intento"}).status_code == 403
    assert cliente.get("/v1/ventas", headers=h).status_code == 200


def test_un_rol_sin_permiso_de_venta_no_puede_cobrar(restaurante, bd_migrada):
    cliente, _, h = restaurante
    a = item(cliente, h)
    with bd_migrada.begin() as con:
        con.execute(sa.text("UPDATE core_membresia SET rol = 'contador' WHERE negocio_id IN "
                            "(SELECT negocio_id FROM (SELECT negocio_id FROM core_membresia "
                            "ORDER BY creado_en DESC LIMIT 1) t)"))
    assert vender(cliente, h, [(a["id"], 1)]).status_code == 403
    assert cliente.get("/v1/ventas", headers=h).status_code == 200  # ver sí


# ------------------------------------------------------------------ checklist

def test_la_primera_venta_marca_el_paso_del_checklist(restaurante):
    cliente, negocio, h = restaurante
    a = item(cliente, h)

    def hechos():
        n = cliente.get(f"/v1/negocios/{negocio['id']}", headers=h).json()
        return {p["clave"]: p["hecho"] for p in n["primeros_pasos"]}

    assert hechos()["primera_venta"] is False
    v = vender(cliente, h, [(a["id"], 1)]).json()
    assert hechos()["primera_venta"] is True
    cliente.post(f"/v1/ventas/{v['id']}/anular", headers=h, json={"motivo": "Prueba"})
    assert hechos()["primera_venta"] is False  # una venta anulada no cuenta
