"""Variantes (docs/PLAN_VARIANTES.md): atributos, por categoría y variantes del producto."""

import pytest
import sqlalchemy as sa
from conftest import con_token, crear_negocio_api, registrar_usuario


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


def producto(cliente, h, nombre="Pijama Luxe", precio="115.00", **extra):
    r = cliente.post("/v1/items", headers=h, json={"nombre": nombre, "precio_venta": precio,
                                                   **extra})
    assert r.status_code == 201, r.text
    return r.json()


def variantes(cliente, h, item, lista):
    return cliente.put(f"/v1/items/{item['id']}/variantes", headers=h, json={"variantes": lista})


def v(talla=None, color=None, precio="115.00", **extra):
    atributos = {k: x for k, x in (("Talla", talla), ("Color", color)) if x}
    return {"atributos": atributos, "precio_venta": precio, **extra}


# ------------------------------------------------------------------ atributos


def test_cada_tipo_de_negocio_recibe_sus_atributos(tienda, restaurante):
    atributos = {a["nombre"]: [x["valor"] for x in a["valores"]]
                 for a in tienda[0].get("/v1/atributos", headers=tienda[2]).json()}
    assert list(atributos) == ["Talla", "Color", "Número"]
    assert "M" in atributos["Talla"] and "Rosa" in atributos["Color"]
    rest = restaurante[0].get("/v1/atributos", headers=restaurante[2]).json()
    assert [a["nombre"] for a in rest] == ["Tamaño"]


def test_crear_un_atributo_y_agregar_valores(tienda):
    cliente, _, h = tienda
    r = cliente.post("/v1/atributos", headers=h, json={"nombre": "Material",
                                                       "valores": ["Satén", "Algodón", "satén"]})
    assert r.status_code == 201, r.text
    material = r.json()
    assert [x["valor"] for x in material["valores"]] == ["Satén", "Algodón"]  # sin repetir
    assert cliente.post("/v1/atributos", headers=h,
                        json={"nombre": "material"}).status_code == 409
    r = cliente.post(f"/v1/atributos/{material['id']}/valores", headers=h, json={"valor": "Seda"})
    assert [x["valor"] for x in r.json()["valores"]] == ["Satén", "Algodón", "Seda"]


# ------------------------------------------------------------------ categorías


def test_una_categoria_sugerida_trae_sus_atributos(tienda):
    cliente, _, h = tienda
    sugeridas = {c["nombre"]: c for c in cliente.get("/v1/categorias/sugeridas", headers=h).json()}
    assert sugeridas["Ropa de dormir"]["atributos"] == ["Talla", "Color"]
    assert "pijama" in sugeridas["Ropa de dormir"]["palabras_clave"]
    assert sugeridas["Electrónica"]["atributos"] == ["Color"]

    ropa = cliente.post("/v1/categorias", headers=h, json={"nombre": "ropa de dormir"}).json()
    assert ropa["atributos"] == ["Talla", "Color"]
    otra = cliente.post("/v1/categorias", headers=h, json={"nombre": "Ofertas"}).json()
    assert otra["atributos"] == []
    color = next(a for a in cliente.get("/v1/atributos", headers=h).json()
                 if a["nombre"] == "Color")
    r = cliente.put(f"/v1/categorias/{otra['id']}/atributos", headers=h,
                    json={"atributo_ids": [color["id"]]})
    assert r.status_code == 200 and r.json() == ["Color"]
    lista = {c["nombre"]: c["atributos"] for c in cliente.get("/v1/categorias", headers=h).json()}
    assert lista["Ofertas"] == ["Color"] and lista["ropa de dormir"] == ["Talla", "Color"]


# ------------------------------------------------------------------ variantes


def test_dar_tallas_a_un_producto(tienda):
    cliente, _, h = tienda
    pijama = producto(cliente, h)
    assert pijama["tiene_variantes"] is False and pijama["variantes"] == []
    r = variantes(cliente, h, pijama, [v("S", "Rosa", "110.00"), v("M", "Rosa"),
                                       v("l", "rosa", "120.00", codigo="si2605251914")])
    assert r.status_code == 200, r.text
    item = r.json()
    assert item["tiene_variantes"] is True and item["precio_venta"] == "110.00"  # el más bajo
    assert [x["nombre"] for x in item["variantes"]] == ["S · Rosa", "M · Rosa", "L · Rosa"]
    assert item["variantes"][2]["atributos"] == {"Talla": "L", "Color": "Rosa"}  # valores canónicos
    assert item["variantes"][2]["codigo"] == "si2605251914"
    lista = cliente.get("/v1/items", headers=h).json()
    assert lista["total"] == 1 and len(lista["items"][0]["variantes"]) == 3  # un renglón por ítem


def test_cambiar_quitar_y_volver_sin_variantes(tienda):
    cliente, _, h = tienda
    pijama = producto(cliente, h)
    item = variantes(cliente, h, pijama, [v("S"), v("M")]).json()
    s, m = item["variantes"]
    item = variantes(cliente, h, pijama, [{**v("S", precio="99.00"), "id": s["id"]}]).json()
    assert [(x["id"], x["precio_venta"]) for x in item["variantes"]] == [(s["id"], "99.00")]
    item = variantes(cliente, h, pijama, []).json()
    assert item["tiene_variantes"] is False and item["precio_venta"] == "115.00"  # vuelve la Única
    assert m["id"] not in str(item)


def test_un_valor_nuevo_se_agrega_al_atributo(tienda):
    cliente, _, h = tienda
    item = variantes(cliente, h, producto(cliente, h), [v("M", "Neblina azul")]).json()
    assert item["variantes"][0]["nombre"] == "M · Neblina azul"
    color = next(a for a in cliente.get("/v1/atributos", headers=h).json()
                 if a["nombre"] == "Color")
    assert "Neblina azul" in [x["valor"] for x in color["valores"]]


@pytest.mark.parametrize(("lista", "mensaje"), [
    ([{"atributos": {"Sabor": "Fresa"}, "precio_venta": "10"}], "Sabor"),
    ([v("M", "Rosa"), v("m", "ROSA")], "iguales"),
    ([{"atributos": {}, "precio_venta": "10"}], None),
    ([{"id": "00000000-0000-7000-8000-000000000000", **v("M")}], "no es de este"),
])
def test_variantes_invalidas(tienda, lista, mensaje):
    cliente, _, h = tienda
    r = variantes(cliente, h, producto(cliente, h), lista)
    assert r.status_code == 422
    if mensaje:
        assert mensaje in r.json()["detail"]


def test_variantes_de_otro_negocio_y_permisos(tienda, restaurante, bd_migrada):
    cliente, negocio, h = tienda
    pijama = producto(cliente, h)
    s = variantes(cliente, h, pijama, [v("S")]).json()["variantes"][0]
    otro, _, h_otro = restaurante
    assert variantes(otro, h_otro, pijama, [v("S")]).status_code == 404
    plato = producto(otro, h_otro, "Pepián", "45")
    r = variantes(otro, h_otro, plato, [{"id": s["id"], "atributos": {"Tamaño": "Grande"},
                                         "precio_venta": "50"}])
    assert r.status_code == 422  # la variante de la tienda no es de su platillo
    with bd_migrada.begin() as con:
        con.execute(sa.text("UPDATE core_membresia SET rol = 'cajero' "
                            "WHERE negocio_id = UUID_TO_BIN(:n)"), {"n": negocio["id"]})
    assert variantes(cliente, h, pijama, [v("M")]).status_code == 403
    assert cliente.get("/v1/atributos", headers=h).status_code == 200  # ver sí puede


# ------------------------------------------------------------------ vender, inventario y precio


def mercaderia(cliente, h, item, activa=True):
    r = cliente.put(f"/v1/items/{item['id']}/mercaderia", headers=h, json={"activa": activa})
    assert r.status_code == 200, r.text
    return r.json()


def insumos_de(cliente, h, item):
    """Insumos vivos ligados al producto, por nombre."""
    return {i["nombre"]: i for i in cliente.get("/v1/insumos", headers=h).json()["insumos"]
            if i["item_id"] == item["id"]}


def comprar(cliente, h, insumo, cantidad, costo):
    r = cliente.post("/v1/compras", headers=h, json={
        "lineas": [{"insumo_id": insumo["id"], "cantidad": str(cantidad),
                    "costo_total": str(costo)}], "medio_pago": "efectivo"})
    assert r.status_code == 201, r.text


def vender(cliente, h, item, variante=None, cantidad=1):
    linea = {"item_id": item["id"], "cantidad": cantidad,
             **({"item_variante_id": variante["id"]} if variante else {})}
    return cliente.post("/v1/ventas", headers=h, json={"lineas": [linea],
                                                       "medio_pago": "efectivo"})


def test_vender_un_producto_con_variantes_exige_elegir(tienda):
    cliente, negocio, h = tienda
    cliente.put(f"/v1/negocios/{negocio['id']}/ventas", headers=h,
                json={"vender_sin_existencia": "avisar"})  # sin cargar inventario
    pijama = producto(cliente, h)
    s, m = variantes(cliente, h, pijama, [v("S", precio="110.00"), v("M")]).json()["variantes"]
    r = vender(cliente, h, pijama)
    assert r.status_code == 422 and "talla" in r.json()["detail"]
    r = vender(cliente, h, pijama, s, cantidad=2)
    assert r.status_code == 201, r.text
    linea = r.json()["lineas"][0]
    assert linea["nombre"] == "Pijama Luxe · S" and linea["precio_unitario"] == "110.00"
    assert linea["item_variante_id"] == s["id"] and r.json()["total"] == "220.00"
    otra = producto(cliente, h, "Gorra", "50")
    assert vender(cliente, h, otra, s).status_code == 422  # la variante no es de ese producto


def test_cada_variante_tiene_su_inventario_y_su_precio(tienda):
    cliente, _, h = tienda
    pijama = producto(cliente, h)
    s, m = variantes(cliente, h, pijama, [v("S"), v("M")]).json()["variantes"]
    mercaderia(cliente, h, pijama)
    ins = insumos_de(cliente, h, pijama)
    assert set(ins) == {"Pijama Luxe · S", "Pijama Luxe · M"}
    comprar(cliente, h, ins["Pijama Luxe · S"], 2, "100.00")   # Q50 c/u
    comprar(cliente, h, ins["Pijama Luxe · M"], 3, "240.00")   # Q80 c/u
    vender(cliente, h, pijama, m)
    ins = insumos_de(cliente, h, pijama)
    assert ins["Pijama Luxe · S"]["existencia"] == "2"
    assert ins["Pijama Luxe · M"]["existencia"] == "2"
    item = cliente.get(f"/v1/items/{pijama['id']}", headers=h).json()
    por_nombre = {x["nombre"]: x for x in item["variantes"]}
    assert por_nombre["S"]["precio_sugerido"] == "77.00"   # 50 / 0.65 = 76.92
    assert por_nombre["S"]["aviso_precio"] == "ok"
    assert por_nombre["M"]["precio_sugerido"] == "123.50"  # 80 / 0.65 = 123.08
    assert por_nombre["M"]["aviso_precio"] == "bajo"        # Q115 deja menos del 35 %
    assert item["aviso_precio"] == "bajo" and item["precio_sugerido"] is None  # el más grave
    # El costo de la venta sale del inventario de la talla M (Q80).
    asientos = cliente.get("/v1/asientos", headers=h).json()["asientos"]
    venta = next(a for a in asientos if a["tipo_evento"] == "VENTA")
    assert {"cuenta_codigo": "5101", "cuenta_nombre": "Costo de ventas", "debe": "80.00",
            "haber": "0.00"} in venta["lineas"]


def test_las_variantes_nuevas_y_quitadas_cambian_su_inventario(tienda):
    cliente, _, h = tienda
    gorra = producto(cliente, h, "Gorra", "50")
    mercaderia(cliente, h, gorra)
    comprar(cliente, h, insumos_de(cliente, h, gorra)["Gorra"], 4, "80.00")  # antes de tallas
    item = variantes(cliente, h, gorra, [{"atributos": {"Color": "Negro"}, "precio_venta": "50"},
                                         {"atributos": {"Color": "Rojo"}, "precio_venta": "50"}]
                     ).json()
    assert set(insumos_de(cliente, h, gorra)) == {"Gorra · Negro", "Gorra · Rojo"}
    negro = next(x for x in item["variantes"] if x["nombre"] == "Negro")
    variantes(cliente, h, gorra, [{"id": negro["id"], "atributos": {"Color": "Negro"},
                                   "precio_venta": "50"}])
    assert set(insumos_de(cliente, h, gorra)) == {"Gorra · Negro"}
    variantes(cliente, h, gorra, [])  # sin variantes: vuelve el inventario de antes
    ins = insumos_de(cliente, h, gorra)
    assert set(ins) == {"Gorra"} and ins["Gorra"]["existencia"] == "4"
    r = vender(cliente, h, gorra)
    assert r.status_code == 201 and r.json()["insumos_en_falta"] == []
    assert insumos_de(cliente, h, gorra)["Gorra"]["existencia"] == "3"
