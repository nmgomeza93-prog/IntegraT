"""Mercadería para revender: un producto que se compra hecho usa insumo + receta de 1 unidad.

La mecánica se prueba en un negocio cuyos productos NO nacen como mercadería (un restaurante que
revende gaseosas); que en las tiendas nazcan así lo cubre tests/test_existencias.py.
"""

import pytest
import sqlalchemy as sa
from conftest import con_token, crear_negocio_api, registrar_usuario


@pytest.fixture
def tienda(cliente_api):
    sesion = registrar_usuario(cliente_api, "Ana")
    negocio = crear_negocio_api(cliente_api, sesion, "Comedor de Ana", "restaurante")
    return cliente_api, negocio, con_token(negocio["acceso"])


@pytest.fixture
def otra_tienda(cliente_api):
    sesion = registrar_usuario(cliente_api, "Luis")
    negocio = crear_negocio_api(cliente_api, sesion, "Comedor de Luis", "restaurante")
    return cliente_api, negocio, con_token(negocio["acceso"])


def producto(cliente, h, nombre="Gaseosa", precio="10.00"):
    r = cliente.post("/v1/items", json={"nombre": nombre, "precio_venta": precio}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


def activar(cliente, h, prod, activa=True):
    return cliente.put(f"/v1/items/{prod['id']}/mercaderia", json={"activa": activa}, headers=h)


def comprar(cliente, h, ins, cantidad, costo):
    r = cliente.post("/v1/compras", headers=h, json={
        "lineas": [{"insumo_id": ins["id"], "cantidad": str(cantidad), "costo_total": str(costo)}],
        "medio_pago": "efectivo"})
    assert r.status_code == 201, r.text
    return r.json()


def vender(cliente, h, prod, cantidad):
    r = cliente.post("/v1/ventas", headers=h, json={
        "lineas": [{"item_id": prod["id"], "cantidad": cantidad}], "medio_pago": "efectivo"})
    assert r.status_code == 201, r.text
    return r.json()


def poner_rol(bd, rol):
    with bd.begin() as con:
        con.execute(sa.text(
            "UPDATE core_membresia SET rol = :r WHERE negocio_id IN (SELECT negocio_id FROM "
            "(SELECT negocio_id FROM core_membresia ORDER BY creado_en DESC LIMIT 1) t)"),
            {"r": rol})


def test_un_producto_normal_no_es_mercaderia(tienda):
    cliente, _, h = tienda
    gaseosa = producto(cliente, h)
    r = cliente.get(f"/v1/items/{gaseosa['id']}/mercaderia", headers=h)
    assert r.status_code == 200 and r.json() == {"activa": False, "insumo": None}
    assert cliente.get("/v1/items/00000000-0000-7000-8000-000000000000/mercaderia",
                       headers=h).status_code == 404


def test_activarla_crea_el_insumo_y_la_receta_de_una_unidad(tienda):
    cliente, _, h = tienda
    gaseosa = producto(cliente, h)
    r = activar(cliente, h, gaseosa)
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["activa"] is True
    insumo = cuerpo["insumo"]
    assert insumo["nombre"] == "Gaseosa" and insumo["unidad_codigo"] == "UN"
    assert insumo["existencia"] == "0" and insumo["item_id"] == gaseosa["id"]
    receta = cliente.get(f"/v1/items/{gaseosa['id']}/receta", headers=h).json()
    assert [(ln["insumo_id"], ln["cantidad"], ln["unidad_codigo"]) for ln in receta["lineas"]] == [
        (insumo["id"], "1", "UN")]
    # Activarla otra vez no crea un segundo insumo
    otra = activar(cliente, h, gaseosa).json()
    assert otra["insumo"]["id"] == insumo["id"]
    assert cliente.get("/v1/insumos", headers=h).json()["total"] == 1


def test_comprar_vender_y_anular_mueven_la_existencia_y_dan_el_costo(tienda):
    cliente, _, h = tienda
    gaseosa = producto(cliente, h, precio="10.00")
    insumo = activar(cliente, h, gaseosa).json()["insumo"]
    comprar(cliente, h, insumo, 24, 120)                              # 5 cada una
    visto = cliente.get(f"/v1/insumos/{insumo['id']}", headers=h).json()
    assert visto["existencia"] == "24" and visto["costo_unitario"] == "5.00"
    venta = vender(cliente, h, gaseosa, 3)
    assert venta["insumos_en_falta"] == []
    assert cliente.get(f"/v1/insumos/{insumo['id']}", headers=h).json()["existencia"] == "21"
    receta = cliente.get(f"/v1/items/{gaseosa['id']}/receta", headers=h).json()
    assert receta["costo_total"] == "5.00" and receta["margen"] == "5.00"
    assert receta["margen_porcentaje"] == 50 and receta["costo_completo"] is True
    cliente.post(f"/v1/ventas/{venta['id']}/anular", headers=h, json={"motivo": "Me equivoqué"})
    assert cliente.get(f"/v1/insumos/{insumo['id']}", headers=h).json()["existencia"] == "24"


def test_vender_mercaderia_sin_existencia_cobra_y_avisa(tienda):
    cliente, _, h = tienda
    gaseosa = producto(cliente, h)
    activar(cliente, h, gaseosa)
    venta = vender(cliente, h, gaseosa, 2)
    assert venta["estado"] == "pagada" and venta["insumos_en_falta"] == ["Gaseosa"]


def test_quitar_la_mercaderia_archiva_el_insumo_y_la_receta(tienda, bd_migrada):
    cliente, _, h = tienda
    gaseosa = producto(cliente, h)
    insumo = activar(cliente, h, gaseosa).json()["insumo"]
    comprar(cliente, h, insumo, 10, 50)
    r = activar(cliente, h, gaseosa, activa=False)
    assert r.status_code == 200 and r.json() == {"activa": False, "insumo": None}
    assert cliente.get("/v1/insumos", headers=h).json()["total"] == 0
    receta = cliente.get(f"/v1/items/{gaseosa['id']}/receta", headers=h).json()
    assert receta["tiene_receta"] is False
    assert vender(cliente, h, gaseosa, 1)["insumos_en_falta"] == []     # ya no descuenta
    with bd_migrada.connect() as con:
        n = con.execute(sa.text("SELECT COUNT(*) FROM ops_movimiento_inventario")).scalar_one()
    assert n >= 1                                                       # el historial se conserva
    # Quitarla de nuevo no falla, y activarla otra vez crea un insumo nuevo
    assert activar(cliente, h, gaseosa, activa=False).status_code == 200
    nuevo = activar(cliente, h, gaseosa).json()["insumo"]
    assert nuevo["id"] != insumo["id"] and nuevo["existencia"] == "0"


def test_un_nombre_de_insumo_repetido_se_distingue(tienda):
    cliente, _, h = tienda
    cliente.post("/v1/insumos", headers=h, json={"nombre": "Gaseosa", "unidad_codigo": "UN"})
    gaseosa = producto(cliente, h)
    assert activar(cliente, h, gaseosa).json()["insumo"]["nombre"] == "Gaseosa (para vender)"
    otra = producto(cliente, h, "Gaseosa grande")
    assert activar(cliente, h, otra).json()["insumo"]["nombre"] == "Gaseosa grande"


def test_no_se_mezcla_con_una_receta_armada_a_mano(tienda):
    cliente, _, h = tienda
    harina = cliente.post("/v1/insumos", headers=h,
                          json={"nombre": "Harina", "unidad_codigo": "LB"}).json()
    pan = producto(cliente, h, "Pan", "3.00")
    cliente.put(f"/v1/items/{pan['id']}/receta", headers=h, json={
        "lineas": [{"insumo_id": harina["id"], "cantidad": "0.1"}]})
    r = activar(cliente, h, pan)
    assert r.status_code == 409 and "receta" in r.json()["detail"]
    gaseosa = producto(cliente, h)
    activar(cliente, h, gaseosa)
    r = cliente.put(f"/v1/items/{gaseosa['id']}/receta", headers=h, json={
        "lineas": [{"insumo_id": harina["id"], "cantidad": "1"}]})
    assert r.status_code == 409 and "mercadería" in r.json()["detail"]


def test_archivar_el_producto_archiva_su_mercaderia(tienda):
    cliente, _, h = tienda
    gaseosa = producto(cliente, h)
    insumo = activar(cliente, h, gaseosa).json()["insumo"]
    assert cliente.delete(f"/v1/items/{gaseosa['id']}", headers=h).status_code == 204
    assert cliente.get(f"/v1/insumos/{insumo['id']}", headers=h).status_code == 404
    assert cliente.get("/v1/insumos", headers=h).json()["total"] == 0


def test_el_inventario_marca_cual_insumo_es_mercaderia(tienda):
    cliente, _, h = tienda
    gaseosa = producto(cliente, h)
    cliente.post("/v1/insumos", headers=h, json={"nombre": "Bolsas", "unidad_codigo": "UN"})
    activar(cliente, h, gaseosa)
    lista = cliente.get("/v1/insumos", headers=h).json()["insumos"]
    assert {i["nombre"]: i["item_id"] for i in lista} == {"Bolsas": None, "Gaseosa": gaseosa["id"]}


def test_aislamiento_entre_negocios(tienda, otra_tienda):
    cliente, _, h = tienda
    _, _, h_otro = otra_tienda
    gaseosa = producto(cliente, h)
    activar(cliente, h, gaseosa)
    ruta = f"/v1/items/{gaseosa['id']}/mercaderia"
    assert cliente.get(ruta, headers=h_otro).status_code == 404
    assert cliente.put(ruta, headers=h_otro, json={"activa": False}).status_code == 404
    assert cliente.get(ruta, headers=h).json()["activa"] is True


def test_el_cajero_no_ve_ni_cambia_y_el_contador_solo_ve(tienda, bd_migrada):
    cliente, _, h = tienda
    gaseosa = producto(cliente, h)
    activar(cliente, h, gaseosa)
    ruta = f"/v1/items/{gaseosa['id']}/mercaderia"
    poner_rol(bd_migrada, "contador")
    assert cliente.get(ruta, headers=h).status_code == 200
    assert cliente.put(ruta, headers=h, json={"activa": False}).status_code == 403
    poner_rol(bd_migrada, "cajero")
    assert cliente.get(ruta, headers=h).status_code == 403
    assert cliente.put(ruta, headers=h, json={"activa": False}).status_code == 403
