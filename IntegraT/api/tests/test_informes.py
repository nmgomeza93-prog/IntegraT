"""Informe del mes (/v1/informes/mes): lo más vendido, a quién y cómo se cobró."""

import pytest
import sqlalchemy as sa
from conftest import con_token, crear_negocio_api, registrar_usuario


@pytest.fixture
def comedor(cliente_api):
    sesion = registrar_usuario(cliente_api, "Mari")
    negocio = crear_negocio_api(cliente_api, sesion, "Comedor", "restaurante")
    return cliente_api, negocio, con_token(negocio["acceso"])


def item(cliente, h, nombre, precio):
    return cliente.post("/v1/items", headers=h, json={"nombre": nombre,
                                                      "precio_venta": precio}).json()


def vender(cliente, h, lineas, medio="efectivo", cliente_id=None):
    r = cliente.post("/v1/ventas", headers=h, json={
        "lineas": [{"item_id": i["id"], "cantidad": n} for i, n in lineas],
        "medio_pago": medio, **({"cliente_id": cliente_id} if cliente_id else {})})
    assert r.status_code == 201, r.text
    return r.json()


def test_informe_del_mes(comedor):
    cliente, _, h = comedor
    pepian, horchata = item(cliente, h, "Pepián", "45"), item(cliente, h, "Horchata", "10")
    maria = cliente.post("/v1/clientes", headers=h, json={"nombre": "María"}).json()
    vender(cliente, h, [(pepian, 2), (horchata, 1)], cliente_id=maria["id"])   # 100
    vender(cliente, h, [(horchata, 3)], medio="tarjeta")                        # 30
    anulada = vender(cliente, h, [(pepian, 1)])
    cliente.post(f"/v1/ventas/{anulada['id']}/anular", headers=h, json={"motivo": "Error"})

    r = cliente.get("/v1/informes/mes", headers=h)
    assert r.status_code == 200, r.text
    inf = r.json()
    assert (inf["ventas"], inf["total"], inf["anuladas"]) == (2, "130.00", 1)
    assert [(p["nombre"], p["cantidad"], p["total"]) for p in inf["productos"]] == [
        ("Pepián", 2, "90.00"), ("Horchata", 4, "40.00")]
    assert [(c["nombre"], c["compras"], c["total"]) for c in inf["clientes"]] == [
        ("María", 1, "100.00")]
    assert (inf["consumidor_final"]["compras"], inf["consumidor_final"]["total"]) == (1, "30.00")
    assert [(m["medio_pago"], m["total"]) for m in inf["medios"]] == [
        ("efectivo", "100.00"), ("tarjeta", "30.00")]


def test_otro_mes_vacio_y_mes_invalido(comedor):
    cliente, _, h = comedor
    inf = cliente.get("/v1/informes/mes", headers=h, params={"mes": "2020-01"}).json()
    assert (inf["mes"], inf["ventas"], inf["total"], inf["productos"]) == (
        "2020-01", 0, "0.00", [])
    assert cliente.get("/v1/informes/mes", headers=h,
                       params={"mes": "2020-13"}).status_code == 422


def test_el_cajero_no_ve_el_informe(comedor, bd_migrada):
    cliente, negocio, h = comedor
    with bd_migrada.begin() as con:
        con.execute(sa.text("UPDATE core_membresia SET rol = 'cajero' "
                            "WHERE negocio_id = UUID_TO_BIN(:n)"), {"n": negocio["id"]})
    assert cliente.get("/v1/informes/mes", headers=h).status_code == 403
