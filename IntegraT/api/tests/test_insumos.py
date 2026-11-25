"""Insumos, existencias y costo promedio: /v1/insumos y /v1/unidades."""

import threading
import uuid

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


def crear(cliente, h, nombre="Harina", unidad="LB", **extra):
    r = cliente.post("/v1/insumos", json={"nombre": nombre, "unidad_codigo": unidad, **extra},
                     headers=h)
    assert r.status_code == 201, r.text
    return r.json()


def mover(cliente, h, insumo, tipo, cantidad, **extra):
    r = cliente.post(f"/v1/insumos/{insumo['id']}/movimientos", headers=h,
                     json={"tipo": tipo, "cantidad": str(cantidad), **extra})
    assert r.status_code == 201, r.text
    return r.json()


def ver(cliente, h, insumo):
    return cliente.get(f"/v1/insumos/{insumo['id']}", headers=h).json()


def poner_rol(bd, rol):
    with bd.begin() as con:
        con.execute(sa.text(
            "UPDATE core_membresia SET rol = :r WHERE negocio_id IN (SELECT negocio_id FROM "
            "(SELECT negocio_id FROM core_membresia ORDER BY creado_en DESC LIMIT 1) t)"),
            {"r": rol})


# ------------------------------------------------------------------ unidades

def test_las_unidades_ofrecidas_tienen_conversion_fija(restaurante):
    cliente, _, h = restaurante
    unidades = cliente.get("/v1/unidades", headers=h).json()
    codigos = {u["codigo"] for u in unidades}
    assert {"UN", "DOC", "G", "KG", "LB", "OZ", "QQ", "ML", "L", "GAL"} <= codigos
    assert "CAJA" not in codigos and "PAQ" not in codigos  # su tamaño depende del producto
    assert {u["codigo"]: u["tipo"] for u in unidades}["LB"] == "masa"


# ------------------------------------------------------------------ crear

def test_un_insumo_nuevo_sin_existencia_aparece_como_falta(restaurante):
    cliente, _, h = restaurante
    harina = crear(cliente, h)
    assert harina["existencia"] == "0" and harina["estado"] == "falta"
    assert harina["valor"] == "0.00" and harina["unidad_nombre"] == "Libra"
    lista = cliente.get("/v1/insumos", headers=h).json()
    assert lista["total"] == 1 and lista["por_reponer"] == 1


def test_un_insumo_con_lo_que_ya_tienes_guarda_cantidad_y_costo(restaurante):
    cliente, _, h = restaurante
    harina = crear(cliente, h, existencia_inicial="10", costo_total_inicial="150")
    assert harina["existencia"] == "10" and harina["costo_unitario"] == "15.00"
    assert harina["valor"] == "150.00" and harina["estado"] == "ok"
    historial = cliente.get(f"/v1/insumos/{harina['id']}/movimientos", headers=h).json()
    assert [m["tipo"] for m in historial["movimientos"]] == ["inicial"]
    assert historial["movimientos"][0]["cantidad"] == "10"


def test_datos_incompletos_o_repetidos_se_rechazan(restaurante):
    cliente, _, h = restaurante
    crear(cliente, h)
    mal = [
        {"nombre": "harina", "unidad_codigo": "LB"},                       # repetido
        {"nombre": "Sal", "unidad_codigo": "CAJA"},                         # sin conversión
        {"nombre": "Sal", "unidad_codigo": "XX"},                           # no existe
        {"nombre": "Sal", "unidad_codigo": "LB", "existencia_inicial": "3"},  # falta el costo
        {"nombre": "Sal", "unidad_codigo": "LB", "costo_total_inicial": "3"},  # falta la cantidad
        {"nombre": "S", "unidad_codigo": "LB"},                             # nombre muy corto
    ]
    codigos = [cliente.post("/v1/insumos", json=c, headers=h).status_code for c in mal]
    assert codigos == [409, 422, 422, 422, 422, 422]


# ------------------------------------------------------------------ costo promedio

def test_las_entradas_promedian_el_costo(restaurante):
    cliente, _, h = restaurante
    harina = crear(cliente, h, existencia_inicial="10", costo_total_inicial="150")  # 15 por lb
    entrada = mover(cliente, h, harina, "entrada", 10, costo_total="200")           # 20 por lb
    assert entrada["cantidad"] == "10" and entrada["costo_unitario"] == "20.00"
    assert entrada["insumo"]["existencia"] == "20"
    assert entrada["insumo"]["costo_unitario"] == "17.50"
    assert entrada["insumo"]["valor"] == "350.00"


def test_una_entrada_en_otra_unidad_del_mismo_tipo_se_convierte(restaurante):
    cliente, _, h = restaurante
    harina = crear(cliente, h, existencia_inicial="10", costo_total_inicial="150")
    entrada = mover(cliente, h, harina, "entrada", 1, unidad_codigo="KG", costo_total="30")
    assert entrada["insumo"]["existencia"] == "12.2046"        # 10 lb + 1 kg
    assert entrada["cantidad"] == "2.2046"                     # lo que entró, en libras
    assert entrada["costo_unitario"] == "13.6078"              # 30 / 2.2046 por libra


def test_no_se_convierte_peso_a_volumen(restaurante):
    cliente, _, h = restaurante
    harina = crear(cliente, h)
    r = cliente.post(f"/v1/insumos/{harina['id']}/movimientos", headers=h, json={
        "tipo": "entrada", "cantidad": "1", "unidad_codigo": "L", "costo_total": "10"})
    assert r.status_code == 422 and "unidad" in r.json()["detail"].lower()
    r = cliente.post(f"/v1/insumos/{harina['id']}/movimientos", headers=h, json={
        "tipo": "entrada", "cantidad": "1", "unidad_codigo": "CAJA", "costo_total": "10"})
    assert r.status_code == 422


def test_con_existencia_vacia_la_entrada_fija_el_costo(restaurante):
    cliente, _, h = restaurante
    harina = crear(cliente, h, existencia_inicial="10", costo_total_inicial="150")
    mover(cliente, h, harina, "merma", 10)                    # se acabó
    entrada = mover(cliente, h, harina, "entrada", 4, costo_total="100")  # 25 por lb
    assert entrada["insumo"]["costo_unitario"] == "25.00"      # no se promedia con lo que ya no hay


def test_mermas_y_ajustes_no_cambian_el_costo(restaurante):
    cliente, _, h = restaurante
    harina = crear(cliente, h, existencia_inicial="10", costo_total_inicial="150")
    merma = mover(cliente, h, harina, "merma", 2, nota="Se mojó")
    assert merma["cantidad"] == "-2" and merma["costo_unitario"] == "15.00"
    assert merma["insumo"]["existencia"] == "8" and merma["insumo"]["costo_unitario"] == "15.00"
    ajuste = mover(cliente, h, harina, "ajuste", 9)            # al contar hay 9
    assert ajuste["cantidad"] == "1" and ajuste["insumo"]["existencia"] == "9"
    assert ajuste["insumo"]["costo_unitario"] == "15.00" and ajuste["insumo"]["valor"] == "135.00"
    bajo = mover(cliente, h, harina, "ajuste", 0)
    assert bajo["cantidad"] == "-9" and bajo["insumo"]["estado"] == "falta"


def test_la_existencia_puede_quedar_negativa_y_se_avisa(restaurante):
    cliente, _, h = restaurante
    harina = crear(cliente, h, existencia_inicial="1", costo_total_inicial="15")
    r = mover(cliente, h, harina, "merma", 3)
    assert r["insumo"]["existencia"] == "-2" and r["insumo"]["estado"] == "falta"
    assert r["insumo"]["valor"] == "0.00"                      # lo que falta no resta valor


def test_ajustar_a_la_cantidad_que_ya_hay_no_hace_nada(restaurante):
    cliente, _, h = restaurante
    harina = crear(cliente, h, existencia_inicial="5", costo_total_inicial="50")
    r = cliente.post(f"/v1/insumos/{harina['id']}/movimientos", headers=h,
                     json={"tipo": "ajuste", "cantidad": "5"})
    assert r.status_code == 422
    assert len(cliente.get(f"/v1/insumos/{harina['id']}/movimientos",
                           headers=h).json()["movimientos"]) == 1


def test_movimientos_mal_formados_se_rechazan(restaurante):
    cliente, _, h = restaurante
    harina = crear(cliente, h, existencia_inicial="5", costo_total_inicial="50")
    ruta = f"/v1/insumos/{harina['id']}/movimientos"
    malos = [
        {"tipo": "entrada", "cantidad": "2"},                                    # sin costo
        {"tipo": "entrada", "cantidad": "0", "costo_total": "5"},                # cantidad cero
        {"tipo": "entrada", "cantidad": "-1", "costo_total": "5"},               # negativa
        {"tipo": "merma", "cantidad": "1", "costo_total": "5"},                  # costo en merma
        {"tipo": "merma", "cantidad": "0"},
        {"tipo": "ajuste", "cantidad": "-1"},
        {"tipo": "regalo", "cantidad": "1"},
        {"tipo": "entrada", "cantidad": "1.00001", "costo_total": "5"},          # 5 decimales
        {"tipo": "entrada", "cantidad": "1", "costo_total": "5.123"},            # 3 decimales
    ]
    assert [cliente.post(ruta, json=m, headers=h).status_code for m in malos] == [422] * len(malos)
    assert ver(cliente, h, harina)["existencia"] == "5"


def test_el_historial_va_de_lo_nuevo_a_lo_viejo(restaurante):
    cliente, _, h = restaurante
    harina = crear(cliente, h, existencia_inicial="10", costo_total_inicial="150")
    mover(cliente, h, harina, "entrada", 5, costo_total="100")
    mover(cliente, h, harina, "merma", 1)
    h_ = cliente.get(f"/v1/insumos/{harina['id']}/movimientos", headers=h).json()["movimientos"]
    assert [(m["tipo"], m["cantidad"]) for m in h_] == [
        ("merma", "-1"), ("entrada", "5"), ("inicial", "10")]
    assert "insumo" in h_[0] and h_[0]["insumo"] is None


# ------------------------------------------------------------------ aviso de "te queda poco"

def test_el_minimo_avisa_cuando_queda_poco(restaurante):
    cliente, _, h = restaurante
    harina = crear(cliente, h, stock_minimo="5", existencia_inicial="20", costo_total_inicial="200")
    assert harina["stock_minimo"] == "5" and harina["estado"] == "ok"
    assert mover(cliente, h, harina, "merma", 15)["insumo"]["estado"] == "poco"   # quedan 5
    assert mover(cliente, h, harina, "merma", 5)["insumo"]["estado"] == "falta"
    lista = cliente.get("/v1/insumos", headers=h).json()
    assert lista["por_reponer"] == 1


# ------------------------------------------------------------------ lista, edición y archivado

def test_la_lista_busca_y_suma_el_valor_del_inventario(restaurante):
    cliente, _, h = restaurante
    crear(cliente, h, "Harina", existencia_inicial="10", costo_total_inicial="150")
    crear(cliente, h, "Aceite", "L", existencia_inicial="2", costo_total_inicial="40")
    crear(cliente, h, "Sal")
    lista = cliente.get("/v1/insumos", headers=h).json()
    assert [i["nombre"] for i in lista["insumos"]] == ["Aceite", "Harina", "Sal"]
    assert lista["valor_inventario"] == "190.00" and lista["por_reponer"] == 1
    busca = cliente.get("/v1/insumos", headers=h, params={"buscar": "ace"}).json()
    assert [i["nombre"] for i in busca["insumos"]] == ["Aceite"]
    assert cliente.get("/v1/insumos", headers=h, params={"buscar": "%"}).json()["total"] == 0


def test_editar_usa_version_y_no_toca_la_existencia(restaurante):
    cliente, _, h = restaurante
    harina = crear(cliente, h, existencia_inicial="10", costo_total_inicial="150")
    mover(cliente, h, harina, "merma", 1)                      # mover existencias no cambia version
    r = cliente.patch(f"/v1/insumos/{harina['id']}", headers=h,
                      json={"version": 1, "nombre": "Harina de trigo", "stock_minimo": "3"})
    assert r.status_code == 200, r.text
    nuevo = r.json()
    assert nuevo["nombre"] == "Harina de trigo" and nuevo["stock_minimo"] == "3"
    assert nuevo["version"] == 2 and nuevo["existencia"] == "9"
    assert cliente.patch(f"/v1/insumos/{harina['id']}", headers=h,
                         json={"version": 1, "nombre": "Otra"}).status_code == 409
    crear(cliente, h, "Sal")
    assert cliente.patch(f"/v1/insumos/{harina['id']}", headers=h,
                         json={"version": 2, "nombre": "sal"}).status_code == 409


def test_archivar_conserva_los_movimientos(restaurante, bd_migrada):
    cliente, _, h = restaurante
    harina = crear(cliente, h, existencia_inicial="10", costo_total_inicial="150")
    assert cliente.delete(f"/v1/insumos/{harina['id']}", headers=h).status_code == 204
    assert cliente.get("/v1/insumos", headers=h).json()["total"] == 0
    assert cliente.get(f"/v1/insumos/{harina['id']}", headers=h).status_code == 404
    r = cliente.post(f"/v1/insumos/{harina['id']}/movimientos", headers=h,
                     json={"tipo": "merma", "cantidad": "1"})
    assert r.status_code == 404
    with bd_migrada.connect() as con:
        n = con.execute(sa.text("SELECT COUNT(*) FROM ops_movimiento_inventario WHERE insumo_id = "
                                ":i"), {"i": uuid.UUID(harina["id"]).bytes}).scalar_one()
    assert n == 1
    # Su nombre queda libre para uno nuevo
    assert crear(cliente, h, "Harina")["existencia"] == "0"


# ------------------------------------------------------------------ idempotencia y concurrencia

def test_repetir_la_clave_no_duplica_la_entrada(restaurante):
    cliente, _, h = restaurante
    harina = crear(cliente, h)
    ruta = f"/v1/insumos/{harina['id']}/movimientos"
    cuerpo = {"tipo": "entrada", "cantidad": "4", "costo_total": "60"}
    clave = {**h, "Idempotency-Key": "entrada-reintento-1"}
    a = cliente.post(ruta, json=cuerpo, headers=clave)
    b = cliente.post(ruta, json=cuerpo, headers=clave)
    assert a.status_code == b.status_code == 201 and a.json()["id"] == b.json()["id"]
    assert ver(cliente, h, harina)["existencia"] == "4"
    otro = cliente.post(ruta, json={**cuerpo, "cantidad": "5"}, headers=clave)
    assert otro.status_code == 422 and "clave" in otro.json()["detail"]
    otro_insumo = crear(cliente, h, "Sal")
    cruzado = cliente.post(f"/v1/insumos/{otro_insumo['id']}/movimientos", json=cuerpo,
                           headers=clave)
    assert cruzado.status_code == 422                          # misma clave, otro insumo


def test_entradas_a_la_vez_no_pierden_cantidad(restaurante):
    cliente, _, h = restaurante
    pollo = crear(cliente, h, "Pollo", "UN")
    resultados = []

    def entrar():
        c = cliente_desde(ip_nueva())
        resultados.append(c.post(f"/v1/insumos/{pollo['id']}/movimientos", headers=h, json={
            "tipo": "entrada", "cantidad": "1", "costo_total": "10"}))

    hilos = [threading.Thread(target=entrar) for _ in range(6)]
    for t in hilos:
        t.start()
    for t in hilos:
        t.join()
    assert all(r.status_code == 201 for r in resultados), [r.text for r in resultados]
    final = ver(cliente, h, pollo)
    assert final["existencia"] == "6" and final["costo_unitario"] == "10.00"
    assert len(cliente.get(f"/v1/insumos/{pollo['id']}/movimientos",
                           headers=h).json()["movimientos"]) == 6


# ------------------------------------------------------------------ aislamiento y permisos

def test_un_negocio_no_ve_los_insumos_de_otro(restaurante, tienda):
    cliente, _, h_rest = restaurante
    _, _, h_tienda = tienda
    harina = crear(cliente, h_rest, existencia_inicial="10", costo_total_inicial="150")
    assert cliente.get("/v1/insumos", headers=h_tienda).json()["total"] == 0
    ruta = f"/v1/insumos/{harina['id']}"
    for r in (
        cliente.get(ruta, headers=h_tienda),
        cliente.get(f"{ruta}/movimientos", headers=h_tienda),
        cliente.patch(ruta, headers=h_tienda, json={"version": 1, "nombre": "Mía"}),
        cliente.delete(ruta, headers=h_tienda),
        cliente.post(f"{ruta}/movimientos", headers=h_tienda,
                     json={"tipo": "merma", "cantidad": "1"}),
    ):
        assert r.status_code == 404
    assert ver(cliente, h_rest, harina)["existencia"] == "10"
    # y el mismo nombre se puede usar en cada negocio
    assert crear(cliente, h_tienda, "Harina")["existencia"] == "0"


def test_el_cajero_no_ve_ni_cambia_el_inventario(restaurante, bd_migrada):
    cliente, _, h = restaurante
    harina = crear(cliente, h, existencia_inicial="10", costo_total_inicial="150")
    poner_rol(bd_migrada, "cajero")
    ruta = f"/v1/insumos/{harina['id']}"
    for r in (
        cliente.get("/v1/unidades", headers=h),
        cliente.get("/v1/insumos", headers=h),
        cliente.get(ruta, headers=h),
        cliente.get(f"{ruta}/movimientos", headers=h),
        cliente.post("/v1/insumos", headers=h, json={"nombre": "Sal", "unidad_codigo": "LB"}),
        cliente.patch(ruta, headers=h, json={"version": 1, "nombre": "Otra"}),
        cliente.delete(ruta, headers=h),
        cliente.post(f"{ruta}/movimientos", headers=h, json={"tipo": "merma", "cantidad": "1"}),
    ):
        assert r.status_code == 403


def test_un_contador_ve_los_costos_pero_no_cambia(restaurante, bd_migrada):
    cliente, _, h = restaurante
    harina = crear(cliente, h, existencia_inicial="10", costo_total_inicial="150")
    poner_rol(bd_migrada, "contador")
    ruta = f"/v1/insumos/{harina['id']}"
    assert cliente.get("/v1/insumos", headers=h).status_code == 200
    assert cliente.get(ruta, headers=h).status_code == 200
    assert cliente.get(f"{ruta}/movimientos", headers=h).status_code == 200
    assert cliente.post("/v1/insumos", headers=h,
                        json={"nombre": "Sal", "unidad_codigo": "LB"}).status_code == 403
    assert cliente.post(f"{ruta}/movimientos", headers=h,
                        json={"tipo": "merma", "cantidad": "1"}).status_code == 403
    assert cliente.delete(ruta, headers=h).status_code == 403


def test_sin_sesion_no_hay_acceso(cliente_api):
    assert cliente_api.get("/v1/insumos").status_code == 401
    assert cliente_api.get("/v1/unidades").status_code == 401


# ------------------------------------------------------------------ checklist

def test_el_primer_insumo_marca_el_paso_del_restaurante(restaurante):
    cliente, negocio, h = restaurante

    def hecho():
        n = cliente.get(f"/v1/negocios/{negocio['id']}", headers=h).json()
        return {p["clave"]: p["hecho"] for p in n["primeros_pasos"]}["primeros_insumos"]

    assert hecho() is False
    harina = crear(cliente, h)
    assert hecho() is True
    cliente.delete(f"/v1/insumos/{harina['id']}", headers=h)
    assert hecho() is False  # archivado, ya no cuenta
