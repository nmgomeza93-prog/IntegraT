"""Precio sugerido y avisos de precio (integrat.precios; docs/PLAN_PRECIO_SUGERIDO.md)."""

from decimal import Decimal

import pytest
import sqlalchemy as sa
from conftest import con_token, crear_negocio_api, registrar_usuario

from integrat.contabilidad.motor import Tratamiento
from integrat.precios import evaluar, redondear_arriba, sugerir

SIN_IVA = Tratamiento("sin_separar")
CON_IVA = Tratamiento("separado", Decimal("0.12"))


# ------------------------------------------------------------------ la fórmula


@pytest.mark.parametrize(("valor", "esperado"), [
    ("27.13", "27.50"), ("27.50", "27.50"), ("27.51", "28.00"), ("0.01", "0.50"), ("10", "10.00"),
])
def test_redondea_hacia_arriba_a_medio_quetzal(valor, esperado):
    assert redondear_arriba(Decimal(valor)) == Decimal(esperado)


def test_sugerido_sin_y_con_iva():
    assert sugerir(Decimal("18.00"), Decimal("0.35"), SIN_IVA) == Decimal("28.00")  # 27.69
    assert sugerir(Decimal("18.00"), Decimal("0.35"), CON_IVA) == Decimal("31.50")  # 31.02
    assert sugerir(Decimal("0"), Decimal("0.35"), SIN_IVA) is None


def test_el_sugerido_nunca_queda_bajo_el_margen():
    for costo in ("1.00", "7.33", "18.00", "45.10", "99.99"):
        precio = sugerir(Decimal(costo), Decimal("0.35"), CON_IVA)
        _, aviso = evaluar(precio, Decimal(costo), Decimal("0.35"), CON_IVA)
        assert aviso == "ok", costo


def test_los_avisos_de_precio():
    assert evaluar(Decimal("15.00"), Decimal("18.00"), Decimal("0.35"), SIN_IVA)[1] == "pierde"
    assert evaluar(Decimal("20.00"), Decimal("18.00"), Decimal("0.35"), SIN_IVA)[1] == "bajo"
    margen, aviso = evaluar(Decimal("30.00"), Decimal("18.00"), Decimal("0.35"), SIN_IVA)
    assert aviso == "ok" and margen == Decimal("0.4000")
    # Con IVA, Q20.16 vende Q18.00 netos: cubre el costo justo, sin margen.
    assert evaluar(Decimal("20.16"), Decimal("18.00"), Decimal("0.35"), CON_IVA)[1] == "bajo"
    assert evaluar(Decimal("20.00"), Decimal("18.00"), Decimal("0.35"), CON_IVA)[1] == "pierde"


# ------------------------------------------------------------------ en el catálogo


@pytest.fixture
def restaurante(cliente_api):
    sesion = registrar_usuario(cliente_api, "Mari")
    negocio = crear_negocio_api(cliente_api, sesion, "Comedor Doña Mari", "restaurante")
    return cliente_api, negocio, con_token(negocio["acceso"])


def platillo_con_costo(cliente, h, precio="45.00", costo_lb="36.00", libras="0.5"):
    """Un platillo cuya receta cuesta costo_lb × libras (por defecto Q18)."""
    ins = cliente.post("/v1/insumos", headers=h, json={
        "nombre": f"Pollo {precio}-{costo_lb}", "unidad_codigo": "LB",
        "existencia_inicial": "10", "costo_total_inicial": str(Decimal(costo_lb) * 10)}).json()
    plato = cliente.post("/v1/items", headers=h, json={
        "nombre": f"Pepián {precio}-{costo_lb}", "precio_venta": precio}).json()
    r = cliente.put(f"/v1/items/{plato['id']}/receta", headers=h,
                    json={"lineas": [{"insumo_id": ins["id"], "cantidad": libras}]})
    assert r.status_code == 200, r.text
    return plato


def test_la_ficha_trae_el_sugerido_y_el_aviso(restaurante):
    cliente, _, h = restaurante
    plato = platillo_con_costo(cliente, h, precio="20.00")
    receta = cliente.get(f"/v1/items/{plato['id']}/receta", headers=h).json()
    assert receta["costo_total"] == "18.00"
    assert receta["precio_sugerido"] == "28.00" and receta["aviso_precio"] == "bajo"
    assert receta["margen_objetivo_porcentaje"] == 35 and receta["margen_propio"] is False
    item = cliente.get(f"/v1/items/{plato['id']}", headers=h).json()
    assert item["precio_sugerido"] == "28.00" and item["aviso_precio"] == "bajo"


def test_la_lista_del_catalogo_marca_los_que_pierden(restaurante):
    cliente, _, h = restaurante
    pierde = platillo_con_costo(cliente, h, precio="15.00")
    bien = platillo_con_costo(cliente, h, precio="45.00", costo_lb="20.00")
    sin_receta = cliente.post("/v1/items", headers=h,
                              json={"nombre": "Horchata", "precio_venta": "8"}).json()
    items = {i["id"]: i for i in cliente.get("/v1/items", headers=h).json()["items"]}
    assert items[pierde["id"]]["aviso_precio"] == "pierde"
    assert items[bien["id"]]["aviso_precio"] == "ok"
    assert items[sin_receta["id"]]["aviso_precio"] is None
    assert items[sin_receta["id"]]["precio_sugerido"] is None


def test_usar_el_precio_sugerido_quita_el_aviso(restaurante):
    cliente, _, h = restaurante
    plato = platillo_con_costo(cliente, h, precio="20.00")
    item = cliente.get(f"/v1/items/{plato['id']}", headers=h).json()
    r = cliente.patch(f"/v1/items/{plato['id']}", headers=h,
                      json={"version": item["version"], "precio_venta": item["precio_sugerido"]})
    assert r.status_code == 200, r.text
    assert r.json()["precio_venta"] == "28.00" and r.json()["aviso_precio"] == "ok"


def test_margen_propio_del_item_y_volver_al_del_negocio(restaurante):
    cliente, _, h = restaurante
    plato = platillo_con_costo(cliente, h)
    r = cliente.patch(f"/v1/items/{plato['id']}", headers=h,
                      json={"version": plato["version"], "margen_objetivo": "0.6000"})
    assert r.status_code == 200, r.text
    assert r.json()["margen_objetivo"] == "0.6000" and r.json()["margen_propio"] is True
    assert r.json()["precio_sugerido"] == "45.00"  # 18 / 0.4
    r = cliente.patch(f"/v1/items/{plato['id']}", headers=h,
                      json={"version": r.json()["version"], "margen_objetivo": None})
    assert r.json()["margen_propio"] is False and r.json()["margen_objetivo"] == "0.3500"
    assert cliente.patch(f"/v1/items/{plato['id']}", headers=h,
                         json={"version": r.json()["version"],
                               "margen_objetivo": "0.95"}).status_code == 422


def test_el_margen_del_negocio_cambia_el_sugerido(restaurante, bd_migrada):
    cliente, negocio, h = restaurante
    plato = platillo_con_costo(cliente, h)
    url = f"/v1/negocios/{negocio['id']}/precios"
    assert cliente.put(url, headers=h, json={"margen_objetivo": "0.5000"}).status_code == 204
    assert cliente.get(f"/v1/negocios/{negocio['id']}",
                       headers=h).json()["margen_objetivo"] == "0.5000"
    assert cliente.get(f"/v1/items/{plato['id']}",
                       headers=h).json()["precio_sugerido"] == "36.00"
    assert cliente.put(url, headers=h, json={"margen_objetivo": "1.2"}).status_code == 422
    with bd_migrada.begin() as con:
        con.execute(sa.text("UPDATE core_membresia SET rol = 'cajero' "
                            "WHERE negocio_id = UUID_TO_BIN(:n)"), {"n": negocio["id"]})
    assert cliente.put(url, headers=h, json={"margen_objetivo": "0.4"}).status_code == 403


def test_en_el_regimen_general_el_sugerido_lleva_iva(restaurante):
    cliente, negocio, h = restaurante
    cliente.put(f"/v1/negocios/{negocio['id']}/impuestos", headers=h,
                json={"regimen_iva": "general"})
    plato = platillo_con_costo(cliente, h, precio="45.00")
    receta = cliente.get(f"/v1/items/{plato['id']}/receta", headers=h).json()
    assert receta["precio_sugerido"] == "31.50"
    assert receta["margen"] == "22.18"         # 45 / 1.12 = 40.18 sin IVA, menos 18
    assert receta["margen_porcentaje"] == 55


def test_sin_costo_completo_no_hay_sugerido(restaurante):
    cliente, _, h = restaurante
    ins = cliente.post("/v1/insumos", headers=h,
                       json={"nombre": "Especias", "unidad_codigo": "G"}).json()  # sin costo
    plato = cliente.post("/v1/items", headers=h,
                         json={"nombre": "Caldo", "precio_venta": "30"}).json()
    cliente.put(f"/v1/items/{plato['id']}/receta", headers=h,
                json={"lineas": [{"insumo_id": ins["id"], "cantidad": "5"}]})
    item = cliente.get(f"/v1/items/{plato['id']}", headers=h).json()
    assert item["precio_sugerido"] is None and item["aviso_precio"] is None
