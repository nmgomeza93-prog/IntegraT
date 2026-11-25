"""Recetas, costo por platillo y descuento de insumos al vender y al anular."""

import threading

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


def insumo(cliente, h, nombre="Harina", unidad="LB", existencia=None, costo=None):
    cuerpo = {"nombre": nombre, "unidad_codigo": unidad}
    if existencia is not None:
        cuerpo |= {"existencia_inicial": str(existencia), "costo_total_inicial": str(costo)}
    r = cliente.post("/v1/insumos", json=cuerpo, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


def receta(cliente, h, plato, *lineas):
    """lineas: (insumo, cantidad) o (insumo, cantidad, unidad)."""
    cuerpo = {"lineas": [
        {"insumo_id": ln[0]["id"], "cantidad": str(ln[1]),
         **({"unidad_codigo": ln[2]} if len(ln) > 2 else {})} for ln in lineas]}
    return cliente.put(f"/v1/items/{plato['id']}/receta", json=cuerpo, headers=h)


def vender(cliente, h, *lineas, clave=None):
    cabeceras = {**h, **({"Idempotency-Key": clave} if clave else {})}
    r = cliente.post("/v1/ventas", headers=cabeceras, json={
        "lineas": [{"item_id": p["id"], "cantidad": c} for p, c in lineas],
        "medio_pago": "efectivo"})
    assert r.status_code == 201, r.text
    return r.json()


def anular(cliente, h, venta):
    return cliente.post(f"/v1/ventas/{venta['id']}/anular", headers=h,
                        json={"motivo": "Me equivoqué"})


def ver(cliente, h, ins):
    return cliente.get(f"/v1/insumos/{ins['id']}", headers=h).json()


def historial(cliente, h, ins):
    return cliente.get(f"/v1/insumos/{ins['id']}/movimientos",
                       headers=h).json()["movimientos"]


def poner_rol(bd, rol):
    with bd.begin() as con:
        con.execute(sa.text(
            "UPDATE core_membresia SET rol = :r WHERE negocio_id IN (SELECT negocio_id FROM "
            "(SELECT negocio_id FROM core_membresia ORDER BY creado_en DESC LIMIT 1) t)"),
            {"r": rol})


# ------------------------------------------------------------------ la receta y su costo

def test_la_receta_calcula_costo_y_margen(restaurante):
    cliente, _, h = restaurante
    harina = insumo(cliente, h, existencia=10, costo=150)             # 15 por libra
    pollo = insumo(cliente, h, "Pollo", "UN", existencia=4, costo=100)  # 25 por unidad
    pepian = item(cliente, h, precio="45.00")
    r = receta(cliente, h, pepian, (harina, "0.5"), (pollo, "0.25"))
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["tiene_receta"] is True and cuerpo["item_nombre"] == "Pepián"
    assert [(ln["insumo_nombre"], ln["cantidad"], ln["costo"]) for ln in cuerpo["lineas"]] == [
        ("Harina", "0.5", "7.50"), ("Pollo", "0.25", "6.25")]
    assert cuerpo["costo_total"] == "13.75" and cuerpo["costo_completo"] is True
    assert cuerpo["precio_venta"] == "45.00" and cuerpo["margen"] == "31.25"
    assert cuerpo["margen_porcentaje"] == 69
    assert cliente.get(f"/v1/items/{pepian['id']}/receta", headers=h).json() == cuerpo


def test_una_receta_puede_usar_otra_unidad_del_mismo_tipo(restaurante):
    cliente, _, h = restaurante
    harina = insumo(cliente, h, existencia=10, costo=150)             # 15 por libra
    pepian = item(cliente, h)
    cuerpo = receta(cliente, h, pepian, (harina, "250", "G")).json()
    linea = cuerpo["lineas"][0]
    assert linea["unidad_codigo"] == "G" and linea["cantidad"] == "250"
    assert linea["costo"] == "8.27"                                    # 250 g = 0.551 lb


def test_un_insumo_sin_costo_avisa_que_el_total_se_queda_corto(restaurante):
    cliente, _, h = restaurante
    sal = insumo(cliente, h, "Sal")                                    # nunca entró con precio
    pepian = item(cliente, h)
    cuerpo = receta(cliente, h, pepian, (sal, "1")).json()
    assert cuerpo["lineas"][0]["sin_costo"] is True and cuerpo["costo_completo"] is False
    assert cuerpo["costo_total"] == "0.00"


def test_reemplazar_y_quitar_la_receta(restaurante):
    cliente, _, h = restaurante
    harina = insumo(cliente, h, existencia=10, costo=150)
    sal = insumo(cliente, h, "Sal", existencia=2, costo=4)
    pepian = item(cliente, h)
    assert receta(cliente, h, pepian, (harina, "1")).json()["costo_total"] == "15.00"
    nueva = receta(cliente, h, pepian, (sal, "1")).json()              # reemplaza, no suma
    assert [ln["insumo_nombre"] for ln in nueva["lineas"]] == ["Sal"]
    vacia = receta(cliente, h, pepian).json()
    assert vacia["tiene_receta"] is False and vacia["lineas"] == []
    assert vacia["margen"] is None and vacia["costo_total"] == "0.00"


def test_la_receta_cambia_con_el_costo_promedio(restaurante):
    cliente, _, h = restaurante
    harina = insumo(cliente, h, existencia=10, costo=150)
    pepian = item(cliente, h)
    receta(cliente, h, pepian, (harina, "1"))
    cliente.post(f"/v1/insumos/{harina['id']}/movimientos", headers=h, json={
        "tipo": "entrada", "cantidad": "10", "costo_total": "200"})    # promedio 17.50
    assert cliente.get(f"/v1/items/{pepian['id']}/receta",
                       headers=h).json()["costo_total"] == "17.50"


def test_recetas_mal_formadas_se_rechazan(restaurante, tienda):
    cliente, _, h = restaurante
    _, _, h_otro = tienda
    harina = insumo(cliente, h, existencia=10, costo=150)
    ajeno = insumo(cliente, h_otro, "Harina ajena")
    pepian = item(cliente, h)
    ruta = f"/v1/items/{pepian['id']}/receta"
    uno = {"insumo_id": harina["id"], "cantidad": "1"}
    malos = [
        {"lineas": [uno, uno]},                                              # repetido
        {"lineas": [{**uno, "cantidad": "0"}]},                              # cantidad cero
        {"lineas": [{**uno, "unidad_codigo": "L"}]},                         # peso con volumen
        {"lineas": [{**uno, "unidad_codigo": "CAJA"}]},                      # sin conversión
        {"lineas": [{"insumo_id": ajeno["id"], "cantidad": "1"}]},           # de otro negocio
        {"lineas": [{"insumo_id": "00000000-0000-7000-8000-000000000000", "cantidad": "1"}]},
    ]
    assert [cliente.put(ruta, json=m, headers=h).status_code for m in malos] == [422] * len(malos)
    assert cliente.get(ruta, headers=h).json()["tiene_receta"] is False
    inexistente = "/v1/items/00000000-0000-7000-8000-000000000000/receta"
    assert cliente.get(inexistente, headers=h).status_code == 404
    assert cliente.put(inexistente, json={"lineas": []}, headers=h).status_code == 404


def test_un_insumo_archivado_se_marca_en_la_receta(restaurante):
    cliente, _, h = restaurante
    harina = insumo(cliente, h, existencia=10, costo=150)
    pepian = item(cliente, h)
    receta(cliente, h, pepian, (harina, "1"))
    cliente.delete(f"/v1/insumos/{harina['id']}", headers=h)
    linea = cliente.get(f"/v1/items/{pepian['id']}/receta", headers=h).json()["lineas"][0]
    assert linea["archivado"] is True and linea["insumo_nombre"] == "Harina"
    # y vender el platillo no falla ni lo descuenta
    vender(cliente, h, (pepian, 1))


# ------------------------------------------------------------------ al vender

def test_vender_descuenta_los_insumos_de_la_receta(restaurante):
    cliente, _, h = restaurante
    harina = insumo(cliente, h, existencia=10, costo=150)
    pepian = item(cliente, h)
    receta(cliente, h, pepian, (harina, "0.5"))
    venta = vender(cliente, h, (pepian, 3))
    assert venta["insumos_en_falta"] == []
    assert ver(cliente, h, harina)["existencia"] == "8.5"
    consumo = historial(cliente, h, harina)[0]
    assert (consumo["tipo"], consumo["cantidad"], consumo["costo_unitario"]) == (
        "consumo_venta", "-1.5", "15.00")
    assert ver(cliente, h, harina)["costo_unitario"] == "15.00"  # el promedio no cambia


def test_lo_que_no_tiene_receta_no_toca_el_inventario(restaurante):
    cliente, _, h = restaurante
    harina = insumo(cliente, h, existencia=10, costo=150)
    agua = item(cliente, h, "Agua", "5.00")
    vender(cliente, h, (agua, 2))
    assert ver(cliente, h, harina)["existencia"] == "10"
    assert len(historial(cliente, h, harina)) == 1                     # solo el inicial


def test_dos_platillos_con_el_mismo_insumo_se_descuentan_juntos(restaurante):
    cliente, _, h = restaurante
    harina = insumo(cliente, h, existencia=10, costo=150)
    pepian = item(cliente, h)
    tamal = item(cliente, h, "Tamal", "10.00")
    receta(cliente, h, pepian, (harina, "0.5"))
    receta(cliente, h, tamal, (harina, "200", "G"))
    vender(cliente, h, (pepian, 2), (tamal, 1))
    gastado = 1 + 200 / 453.59237
    assert float(ver(cliente, h, harina)["existencia"]) == pytest.approx(10 - gastado, abs=1e-4)
    assert [m["tipo"] for m in historial(cliente, h, harina)] == ["consumo_venta", "inicial"]


def test_si_falta_insumo_se_cobra_y_se_avisa(restaurante):
    cliente, _, h = restaurante
    harina = insumo(cliente, h, existencia=1, costo=15)
    pepian = item(cliente, h)
    receta(cliente, h, pepian, (harina, "0.5"))
    venta = vender(cliente, h, (pepian, 3))                            # pide 1.5 lb y hay 1
    assert venta["estado"] == "pagada" and venta["insumos_en_falta"] == ["Harina"]
    assert ver(cliente, h, harina)["existencia"] == "-0.5"
    assert ver(cliente, h, harina)["estado"] == "falta"
    # El aviso es solo del momento de cobrar
    assert cliente.get(f"/v1/ventas/{venta['id']}", headers=h).json()["insumos_en_falta"] == []


def test_anular_devuelve_los_insumos_al_costo_con_que_salieron(restaurante):
    cliente, _, h = restaurante
    harina = insumo(cliente, h, existencia=10, costo=150)              # 15 por libra
    pepian = item(cliente, h)
    receta(cliente, h, pepian, (harina, "1"))
    venta = vender(cliente, h, (pepian, 2))
    cliente.post(f"/v1/insumos/{harina['id']}/movimientos", headers=h, json={
        "tipo": "entrada", "cantidad": "10", "costo_total": "200"})    # sube el promedio
    promedio = ver(cliente, h, harina)["costo_unitario"]
    assert anular(cliente, h, venta).status_code == 200
    despues = ver(cliente, h, harina)
    assert despues["existencia"] == "20" and despues["costo_unitario"] == promedio
    reverso = historial(cliente, h, harina)[0]
    assert (reverso["tipo"], reverso["cantidad"], reverso["costo_unitario"]) == (
        "reverso_venta", "2", "15.00")                                 # el costo de cuando salió
    # anular otra vez no devuelve dos veces
    assert anular(cliente, h, venta).status_code == 409
    assert ver(cliente, h, harina)["existencia"] == "20"


def test_anular_una_venta_sin_receta_no_hace_movimientos(restaurante):
    cliente, _, h = restaurante
    harina = insumo(cliente, h, existencia=10, costo=150)
    agua = item(cliente, h, "Agua", "5.00")
    assert anular(cliente, h, vender(cliente, h, (agua, 1))).status_code == 200
    assert len(historial(cliente, h, harina)) == 1


def test_repetir_el_cobro_con_la_misma_clave_descuenta_una_vez(restaurante):
    cliente, _, h = restaurante
    harina = insumo(cliente, h, existencia=10, costo=150)
    pepian = item(cliente, h)
    receta(cliente, h, pepian, (harina, "1"))
    a = vender(cliente, h, (pepian, 1), clave="cobro-receta-01")
    b = vender(cliente, h, (pepian, 1), clave="cobro-receta-01")
    assert a["id"] == b["id"]
    assert ver(cliente, h, harina)["existencia"] == "9"


def test_ventas_a_la_vez_descuentan_cada_una(restaurante):
    cliente, _, h = restaurante
    harina = insumo(cliente, h, existencia=10, costo=150)
    pepian = item(cliente, h)
    receta(cliente, h, pepian, (harina, "0.5"))
    resultados = []

    def cobrar():
        c = cliente_desde(ip_nueva())
        resultados.append(c.post("/v1/ventas", headers=h, json={
            "lineas": [{"item_id": pepian["id"], "cantidad": 1}], "medio_pago": "efectivo"}))

    hilos = [threading.Thread(target=cobrar) for _ in range(5)]
    for t in hilos:
        t.start()
    for t in hilos:
        t.join()
    assert all(r.status_code == 201 for r in resultados), [r.text for r in resultados]
    assert ver(cliente, h, harina)["existencia"] == "7.5"


# ------------------------------------------------------------------ permisos y aislamiento

def test_el_cajero_vende_y_descuenta_pero_no_ve_recetas(restaurante, bd_migrada):
    cliente, _, h = restaurante
    harina = insumo(cliente, h, existencia=10, costo=150)
    pepian = item(cliente, h)
    receta(cliente, h, pepian, (harina, "1"))
    poner_rol(bd_migrada, "cajero")
    venta = vender(cliente, h, (pepian, 1))
    assert venta["insumos_en_falta"] == []
    ruta = f"/v1/items/{pepian['id']}/receta"
    assert cliente.get(ruta, headers=h).status_code == 403
    assert cliente.put(ruta, json={"lineas": []}, headers=h).status_code == 403
    poner_rol(bd_migrada, "dueno")
    assert ver(cliente, h, harina)["existencia"] == "9"


def test_un_contador_ve_la_receta_pero_no_la_cambia(restaurante, bd_migrada):
    cliente, _, h = restaurante
    harina = insumo(cliente, h, existencia=10, costo=150)
    pepian = item(cliente, h)
    receta(cliente, h, pepian, (harina, "1"))
    poner_rol(bd_migrada, "contador")
    ruta = f"/v1/items/{pepian['id']}/receta"
    assert cliente.get(ruta, headers=h).status_code == 200
    assert cliente.put(ruta, json={"lineas": []}, headers=h).status_code == 403


def test_un_negocio_no_ve_ni_cambia_las_recetas_de_otro(restaurante, tienda):
    cliente, _, h = restaurante
    _, _, h_otro = tienda
    harina = insumo(cliente, h, existencia=10, costo=150)
    pepian = item(cliente, h)
    receta(cliente, h, pepian, (harina, "1"))
    ruta = f"/v1/items/{pepian['id']}/receta"
    assert cliente.get(ruta, headers=h_otro).status_code == 404
    assert cliente.put(ruta, json={"lineas": []}, headers=h_otro).status_code == 404
    assert cliente.get(ruta, headers=h).json()["tiene_receta"] is True


# ------------------------------------------------------------------ checklist

def test_la_primera_receta_marca_el_paso_del_restaurante(restaurante):
    cliente, negocio, h = restaurante

    def hecho():
        n = cliente.get(f"/v1/negocios/{negocio['id']}", headers=h).json()
        return {p["clave"]: p["hecho"] for p in n["primeros_pasos"]}["receta_estrella"]

    harina = insumo(cliente, h, existencia=10, costo=150)
    pepian = item(cliente, h)
    assert hecho() is False
    receta(cliente, h, pepian, (harina, "1"))
    assert hecho() is True
    receta(cliente, h, pepian)                                          # la quita
    assert hecho() is False
