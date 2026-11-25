"""Vender según la existencia (docs/ANALISIS_INVENTARIO_Y_CLIENTES.md).

Tiendas: los productos nacen como mercadería en 0 y no se vende lo que no hay. Restaurantes: avisan
y dejan vender; un platillo sin receta se vende libre. La regla se cambia por negocio.
"""

import threading

import pytest
import sqlalchemy as sa
from conftest import cliente_desde, con_token, crear_negocio_api, ip_nueva, registrar_usuario


@pytest.fixture
def tienda(cliente_api):
    sesion = registrar_usuario(cliente_api, "Ana")
    negocio = crear_negocio_api(cliente_api, sesion, "Tienda de Ana", "ventas_en_linea")
    return cliente_api, negocio, con_token(negocio["acceso"])


@pytest.fixture
def restaurante(cliente_api):
    sesion = registrar_usuario(cliente_api, "Mari")
    negocio = crear_negocio_api(cliente_api, sesion, "Comedor Doña Mari", "restaurante")
    return cliente_api, negocio, con_token(negocio["acceso"])


def producto(cliente, h, nombre="Camisa", precio="99.00"):
    r = cliente.post("/v1/items", headers=h, json={"nombre": nombre, "precio_venta": precio})
    assert r.status_code == 201, r.text
    return r.json()


def insumo_de(cliente, h, item, nombre=None):
    return next(i for i in cliente.get("/v1/insumos", headers=h).json()["insumos"]
                if i["item_id"] == item["id"] and (nombre is None or i["nombre"] == nombre))


def comprar(cliente, h, insumo, cantidad, costo="10.00"):
    r = cliente.post("/v1/compras", headers=h, json={
        "lineas": [{"insumo_id": insumo["id"], "cantidad": str(cantidad), "costo_total": costo}],
        "medio_pago": "efectivo"})
    assert r.status_code == 201, r.text


def vender(cliente, h, *lineas):
    return cliente.post("/v1/ventas", headers=h, json={
        "lineas": [{"item_id": i["id"], "cantidad": n,
                    **({"item_variante_id": v["id"]} if v else {})} for i, n, v in lineas],
        "medio_pago": "efectivo"})


def regla(cliente, negocio, h, valor):
    return cliente.put(f"/v1/negocios/{negocio['id']}/ventas", headers=h,
                       json={"vender_sin_existencia": valor})


# ------------------------------------------------------------------ tiendas


def test_en_una_tienda_el_producto_nace_como_mercaderia_en_cero(tienda):
    cliente, negocio, h = tienda
    assert cliente.get(f"/v1/negocios/{negocio['id']}",
                       headers=h).json()["vender_sin_existencia"] == "bloquear"
    camisa = producto(cliente, h)
    assert camisa["controla_inventario"] is True and camisa["disponible"] == 0
    assert insumo_de(cliente, h, camisa)["existencia"] == "0"


def test_no_se_vende_lo_que_no_hay(tienda):
    cliente, _, h = tienda
    camisa = producto(cliente, h)
    r = vender(cliente, h, (camisa, 1, None))
    assert r.status_code == 409 and "Camisa (agotado)" in r.json()["detail"]
    comprar(cliente, h, insumo_de(cliente, h, camisa), 3)
    r = vender(cliente, h, (camisa, 4, None))
    assert r.status_code == 409 and "solo quedan 3" in r.json()["detail"]
    assert vender(cliente, h, (camisa, 3, None)).status_code == 201
    assert cliente.get(f"/v1/items/{camisa['id']}", headers=h).json()["disponible"] == 0
    assert cliente.get("/v1/ventas", headers=h).json()["resumen"]["cantidad"] == 1  # nada a medias


def test_si_una_linea_no_alcanza_no_se_cobra_ninguna(tienda):
    cliente, _, h = tienda
    camisa, gorra = producto(cliente, h), producto(cliente, h, "Gorra", "50")
    comprar(cliente, h, insumo_de(cliente, h, camisa), 5)
    r = vender(cliente, h, (camisa, 1, None), (gorra, 1, None))
    assert r.status_code == 409
    assert "Gorra" in r.json()["detail"] and "Camisa" not in r.json()["detail"]
    assert insumo_de(cliente, h, camisa)["existencia"] == "5"


def test_cada_talla_tiene_su_existencia(tienda):
    cliente, _, h = tienda
    pijama = producto(cliente, h, "Pijama", "115")
    item = cliente.put(f"/v1/items/{pijama['id']}/variantes", headers=h, json={"variantes": [
        {"atributos": {"Talla": "S"}, "precio_venta": "115"},
        {"atributos": {"Talla": "M"}, "precio_venta": "115"}]}).json()
    s, m = item["variantes"]
    comprar(cliente, h, insumo_de(cliente, h, pijama, "Pijama · M"), 2)
    item = cliente.get(f"/v1/items/{pijama['id']}", headers=h).json()
    assert [v["disponible"] for v in item["variantes"]] == [0, 2] and item["disponible"] == 2
    assert vender(cliente, h, (pijama, 1, s)).status_code == 409
    assert vender(cliente, h, (pijama, 2, m)).status_code == 201


def test_con_la_regla_avisar_se_cobra_y_se_avisa(tienda):
    cliente, negocio, h = tienda
    assert regla(cliente, negocio, h, "avisar").status_code == 204
    camisa = producto(cliente, h)
    r = vender(cliente, h, (camisa, 2, None))
    assert r.status_code == 201 and r.json()["insumos_en_falta"] == ["Camisa"]


def test_los_productos_anteriores_pasan_a_mercaderia(tienda, bd_migrada):
    """Productos de una tienda creados antes de esta regla (sin inventario) se convierten solos."""
    cliente, _, h = tienda
    camisa = producto(cliente, h)
    cliente.put(f"/v1/items/{camisa['id']}/mercaderia", headers=h, json={"activa": False})
    lista = cliente.get("/v1/items", headers=h).json()["items"]
    assert lista[0]["controla_inventario"] is True and lista[0]["disponible"] == 0


def test_dos_ventas_a_la_vez_no_se_llevan_la_ultima(tienda):
    cliente, _, h = tienda
    camisa = producto(cliente, h)
    comprar(cliente, h, insumo_de(cliente, h, camisa), 1)
    resultados = []

    def intento():
        resultados.append(vender(cliente_desde(ip_nueva()), h, (camisa, 1, None)).status_code)

    hilos = [threading.Thread(target=intento) for _ in range(2)]
    for t in hilos:
        t.start()
    for t in hilos:
        t.join()
    assert sorted(resultados) == [201, 409]


# ------------------------------------------------------------------ restaurantes y permisos


def test_en_un_restaurante_se_avisa_y_sin_receta_se_vende_libre(restaurante):
    cliente, negocio, h = restaurante
    assert cliente.get(f"/v1/negocios/{negocio['id']}",
                       headers=h).json()["vender_sin_existencia"] == "avisar"
    pepian = producto(cliente, h, "Pepián", "45")
    assert pepian["controla_inventario"] is False and pepian["disponible"] is None
    assert vender(cliente, h, (pepian, 3, None)).status_code == 201


def test_un_restaurante_que_bloquea_revisa_los_ingredientes(restaurante):
    cliente, negocio, h = restaurante
    regla(cliente, negocio, h, "bloquear")
    pollo = cliente.post("/v1/insumos", headers=h, json={
        "nombre": "Pollo", "unidad_codigo": "LB", "existencia_inicial": "1",
        "costo_total_inicial": "30"}).json()
    pepian = producto(cliente, h, "Pepián", "45")
    cliente.put(f"/v1/items/{pepian['id']}/receta", headers=h,
                json={"lineas": [{"insumo_id": pollo["id"], "cantidad": "0.5"}]})
    assert cliente.get(f"/v1/items/{pepian['id']}", headers=h).json()["disponible"] == 2
    r = vender(cliente, h, (pepian, 3, None))
    assert r.status_code == 409 and "solo quedan 2" in r.json()["detail"]
    sin_receta = producto(cliente, h, "Horchata", "10")
    r = vender(cliente, h, (sin_receta, 1, None))
    assert r.status_code == 409 and "aún no tiene inventario" in r.json()["detail"]


def test_solo_dueno_o_administrador_cambia_la_regla(tienda, bd_migrada):
    cliente, negocio, h = tienda
    assert regla(cliente, negocio, h, "nunca").status_code == 422
    with bd_migrada.begin() as con:
        con.execute(sa.text("UPDATE core_membresia SET rol = 'cajero' "
                            "WHERE negocio_id = UUID_TO_BIN(:n)"), {"n": negocio["id"]})
    assert regla(cliente, negocio, h, "avisar").status_code == 403
