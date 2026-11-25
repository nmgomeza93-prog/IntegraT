"""Proveedores y compras a mano: /v1/proveedores y /v1/compras."""

import threading
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
import sqlalchemy as sa
from conftest import cliente_desde, con_token, crear_negocio_api, ip_nueva, registrar_usuario

GT = ZoneInfo("America/Guatemala")


def hoy():
    return datetime.now(GT).date()


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


def insumo(cliente, h, nombre="Harina", unidad="LB", existencia=None, costo=None):
    cuerpo = {"nombre": nombre, "unidad_codigo": unidad}
    if existencia is not None:
        cuerpo |= {"existencia_inicial": str(existencia), "costo_total_inicial": str(costo)}
    r = cliente.post("/v1/insumos", json=cuerpo, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


def ver(cliente, h, ins):
    return cliente.get(f"/v1/insumos/{ins['id']}", headers=h).json()


def linea(ins, cantidad, costo, unidad=None):
    return {"insumo_id": ins["id"], "cantidad": str(cantidad), "costo_total": str(costo),
            **({"unidad_codigo": unidad} if unidad else {})}


def comprar(cliente, h, *lineas, medio="efectivo", clave=None, **extra):
    cabeceras = {**h, **({"Idempotency-Key": clave} if clave else {})}
    r = cliente.post("/v1/compras", headers=cabeceras,
                     json={"lineas": list(lineas), "medio_pago": medio, **extra})
    assert r.status_code == 201, r.text
    return r.json()


def anular(cliente, h, compra, motivo="Me equivoqué"):
    return cliente.post(f"/v1/compras/{compra['id']}/anular", headers=h, json={"motivo": motivo})


def poner_rol(bd, rol):
    with bd.begin() as con:
        con.execute(sa.text(
            "UPDATE core_membresia SET rol = :r WHERE negocio_id IN (SELECT negocio_id FROM "
            "(SELECT negocio_id FROM core_membresia ORDER BY creado_en DESC LIMIT 1) t)"),
            {"r": rol})


# ------------------------------------------------------------------ proveedores

def test_crear_cambiar_y_archivar_proveedores(restaurante):
    cliente, _, h = restaurante
    r = cliente.post("/v1/proveedores", headers=h,
                     json={"nombre": "Don Pedro", "telefono": "5555-1234"})
    assert r.status_code == 201
    prov = r.json()
    assert (prov["nombre"], prov["telefono"], prov["version"]) == ("Don Pedro", "5555-1234", 1)
    assert cliente.post("/v1/proveedores", headers=h,
                        json={"nombre": "don pedro"}).status_code == 409
    nuevo = cliente.patch(f"/v1/proveedores/{prov['id']}", headers=h,
                          json={"version": 1, "nombre": "Pedro Pérez", "telefono": None})
    assert nuevo.status_code == 200 and nuevo.json()["nombre"] == "Pedro Pérez"
    assert nuevo.json()["telefono"] is None and nuevo.json()["version"] == 2
    assert cliente.patch(f"/v1/proveedores/{prov['id']}", headers=h,
                         json={"version": 1, "nombre": "Otro"}).status_code == 409
    lista = cliente.get("/v1/proveedores", headers=h).json()
    assert [p["nombre"] for p in lista] == ["Pedro Pérez"]
    assert cliente.delete(f"/v1/proveedores/{prov['id']}", headers=h).status_code == 204
    assert cliente.get("/v1/proveedores", headers=h).json() == []
    assert cliente.delete(f"/v1/proveedores/{prov['id']}", headers=h).status_code == 404


# ------------------------------------------------------------------ registrar

def test_una_compra_sube_las_existencias_y_promedia_el_costo(restaurante):
    cliente, _, h = restaurante
    harina = insumo(cliente, h, existencia=10, costo=150)               # 15 por libra
    aceite = insumo(cliente, h, "Aceite", "L")
    compra = comprar(cliente, h, linea(harina, 10, 200), linea(aceite, 2, 80),
                     proveedor_nuevo={"nombre": "Don Pedro"}, numero_factura="A-123",
                     fecha=str(hoy()), nota="Del mercado")
    assert compra["total"] == "280.00" and compra["estado"] == "registrada"
    assert compra["proveedor_nombre"] == "Don Pedro" and compra["numero_factura"] == "A-123"
    assert compra["medio_pago"] == "efectivo" and compra["fecha"] == str(hoy())
    assert [(ln["nombre"], ln["cantidad"], ln["unidad_codigo"], ln["costo_total"])
            for ln in compra["lineas"]] == [("Harina", "10", "LB", "200.00"),
                                             ("Aceite", "2", "L", "80.00")]
    nueva = ver(cliente, h, harina)
    assert nueva["existencia"] == "20" and nueva["costo_unitario"] == "17.50"
    assert ver(cliente, h, aceite)["existencia"] == "2"
    assert ver(cliente, h, aceite)["costo_unitario"] == "40.00"
    mov = cliente.get(f"/v1/insumos/{harina['id']}/movimientos", headers=h).json()["movimientos"][0]
    assert (mov["tipo"], mov["cantidad"], mov["costo_unitario"]) == ("entrada", "10", "20.00")
    assert cliente.get(f"/v1/compras/{compra['id']}", headers=h).json() == compra
    assert [p["nombre"] for p in cliente.get("/v1/proveedores", headers=h).json()] == ["Don Pedro"]


def test_la_fecha_por_defecto_es_hoy_y_el_proveedor_es_opcional(restaurante):
    cliente, _, h = restaurante
    harina = insumo(cliente, h)
    compra = comprar(cliente, h, linea(harina, 5, 50))
    assert compra["fecha"] == str(hoy())
    assert compra["proveedor_id"] is None and compra["proveedor_nombre"] is None
    assert compra["numero_factura"] is None


def test_una_linea_en_otra_unidad_del_mismo_tipo_se_convierte(restaurante):
    cliente, _, h = restaurante
    harina = insumo(cliente, h, existencia=10, costo=150)
    compra = comprar(cliente, h, linea(harina, 1, 30, "KG"))
    assert compra["lineas"][0]["unidad_codigo"] == "KG"
    assert ver(cliente, h, harina)["existencia"] == "12.2046"


def test_proveedor_existente_nuevo_repetido_y_ajeno(restaurante, tienda):
    cliente, _, h = restaurante
    _, _, h_otro = tienda
    harina = insumo(cliente, h)
    pedro = cliente.post("/v1/proveedores", headers=h, json={"nombre": "Don Pedro"}).json()
    c1 = comprar(cliente, h, linea(harina, 1, 10), proveedor_id=pedro["id"])
    assert c1["proveedor_nombre"] == "Don Pedro"
    c2 = comprar(cliente, h, linea(harina, 1, 10), proveedor_nuevo={"nombre": "don pedro"})
    assert c2["proveedor_id"] == pedro["id"]                           # no se duplica
    assert len(cliente.get("/v1/proveedores", headers=h).json()) == 1
    ajeno = cliente.post("/v1/proveedores", headers=h_otro, json={"nombre": "Ajeno"}).json()
    malos = [
        {"proveedor_id": ajeno["id"]},                                   # de otro negocio
        {"proveedor_id": "00000000-0000-7000-8000-000000000000"},        # no existe
        {"proveedor_id": pedro["id"], "proveedor_nuevo": {"nombre": "Otro"}},  # los dos
    ]
    for extra in malos:
        r = cliente.post("/v1/compras", headers=h, json={
            "lineas": [linea(harina, 1, 10)], "medio_pago": "efectivo", **extra})
        assert r.status_code == 422, extra


def test_archivar_al_proveedor_no_cambia_el_nombre_en_sus_compras(restaurante):
    cliente, _, h = restaurante
    harina = insumo(cliente, h)
    pedro = cliente.post("/v1/proveedores", headers=h, json={"nombre": "Don Pedro"}).json()
    compra = comprar(cliente, h, linea(harina, 1, 10), proveedor_id=pedro["id"])
    cliente.delete(f"/v1/proveedores/{pedro['id']}", headers=h)
    visto = cliente.get(f"/v1/compras/{compra['id']}", headers=h).json()
    assert visto["proveedor_nombre"] == "Don Pedro"
    r = cliente.post("/v1/compras", headers=h, json={
        "lineas": [linea(harina, 1, 10)], "medio_pago": "efectivo", "proveedor_id": pedro["id"]})
    assert r.status_code == 422                                          # ya no se ofrece


def test_compras_mal_formadas_se_rechazan(restaurante, tienda):
    cliente, _, h = restaurante
    _, _, h_otro = tienda
    harina = insumo(cliente, h)
    ajeno = insumo(cliente, h_otro, "Ajeno")
    manana = str(hoy() + timedelta(days=1))
    base = {"lineas": [linea(harina, 1, 10)], "medio_pago": "efectivo"}
    malos = [
        {**base, "lineas": []},                                           # sin líneas
        {**base, "medio_pago": "cheque"},
        {**base, "fecha": manana},                                        # de mañana
        {**base, "lineas": [linea(ajeno, 1, 10)]},                        # insumo de otro negocio
        {**base, "lineas": [linea(harina, 1, 10, "L")]},                  # peso con volumen
        {**base, "lineas": [linea(harina, 1, 10, "CAJA")]},               # sin conversión
        {**base, "lineas": [linea(harina, 0, 10)]},                       # cantidad cero
        {**base, "lineas": [linea(harina, 1, -5)]},                       # costo negativo
        {**base, "lineas": [linea(harina, 1, "10.123")]},                 # 3 decimales
        {**base, "numero_factura": "x" * 41},
    ]
    resultados = [cliente.post("/v1/compras", json=m, headers=h).status_code for m in malos]
    assert resultados == [422] * len(malos)
    assert ver(cliente, h, harina)["existencia"] == "0"                  # nada se aplicó
    assert cliente.get("/v1/compras", headers=h).json()["resumen"]["cantidad"] == 0


def test_una_compra_con_una_linea_mala_no_aplica_ninguna(restaurante):
    cliente, _, h = restaurante
    harina = insumo(cliente, h)
    sal = insumo(cliente, h, "Sal")
    r = cliente.post("/v1/compras", headers=h, json={
        "lineas": [linea(harina, 5, 50), linea(sal, 1, 5, "L")], "medio_pago": "efectivo"})
    assert r.status_code == 422
    assert ver(cliente, h, harina)["existencia"] == "0"


# ------------------------------------------------------------------ idempotencia y concurrencia

def test_repetir_la_clave_no_compra_dos_veces(restaurante):
    cliente, _, h = restaurante
    harina = insumo(cliente, h)
    cuerpo = {"lineas": [linea(harina, 4, 60)], "medio_pago": "efectivo"}
    clave = {**h, "Idempotency-Key": "compra-reintento-1"}
    a = cliente.post("/v1/compras", json=cuerpo, headers=clave)
    b = cliente.post("/v1/compras", json=cuerpo, headers=clave)
    assert a.status_code == b.status_code == 201 and a.json()["id"] == b.json()["id"]
    assert ver(cliente, h, harina)["existencia"] == "4"
    otro = cliente.post("/v1/compras", headers=clave, json={
        **cuerpo, "lineas": [linea(harina, 5, 60)]})
    assert otro.status_code == 422 and "clave" in otro.json()["detail"]


def test_la_misma_clave_a_la_vez_compra_una_sola_vez(restaurante):
    cliente, _, h = restaurante
    harina = insumo(cliente, h)
    cuerpo = {"lineas": [linea(harina, 3, 30)], "medio_pago": "efectivo"}
    resultados = []

    def comprar_una():
        c = cliente_desde(ip_nueva())
        resultados.append(c.post("/v1/compras", json=cuerpo,
                                 headers={**h, "Idempotency-Key": "compra-doble-01"}))

    hilos = [threading.Thread(target=comprar_una) for _ in range(4)]
    for t in hilos:
        t.start()
    for t in hilos:
        t.join()
    assert all(r.status_code == 201 for r in resultados), [r.text for r in resultados]
    assert len({r.json()["id"] for r in resultados}) == 1
    assert ver(cliente, h, harina)["existencia"] == "3"


def test_compras_a_la_vez_no_pierden_cantidad(restaurante):
    cliente, _, h = restaurante
    pollo = insumo(cliente, h, "Pollo", "UN")
    resultados = []

    def comprar_una():
        c = cliente_desde(ip_nueva())
        resultados.append(c.post("/v1/compras", headers=h, json={
            "lineas": [linea(pollo, 1, 10)], "medio_pago": "efectivo",
            "proveedor_nuevo": {"nombre": "Don Pedro"}}))

    hilos = [threading.Thread(target=comprar_una) for _ in range(5)]
    for t in hilos:
        t.start()
    for t in hilos:
        t.join()
    assert all(r.status_code == 201 for r in resultados), [r.text for r in resultados]
    assert ver(cliente, h, pollo)["existencia"] == "5"
    assert len(cliente.get("/v1/proveedores", headers=h).json()) == 1   # un solo proveedor


# ------------------------------------------------------------------ el mes

def test_el_mes_suma_las_vigentes_y_valida_el_formato(restaurante):
    cliente, _, h = restaurante
    harina = insumo(cliente, h)
    comprar(cliente, h, linea(harina, 1, 100))
    segunda = comprar(cliente, h, linea(harina, 1, 40), medio="tarjeta")
    anular(cliente, h, segunda)
    mes = cliente.get("/v1/compras", headers=h).json()
    assert mes["mes"] == hoy().strftime("%Y-%m")
    assert mes["resumen"] == {"cantidad": 1, "total": "100.00"}
    assert [c["estado"] for c in mes["compras"]] == ["anulada", "registrada"]  # la nueva primero
    vacio = cliente.get("/v1/compras", headers=h, params={"mes": "2020-01"}).json()
    assert vacio["resumen"] == {"cantidad": 0, "total": "0.00"} and vacio["compras"] == []
    assert cliente.get("/v1/compras", headers=h, params={"mes": "enero"}).status_code == 422


def test_una_compra_con_fecha_pasada_cae_en_su_mes(restaurante):
    cliente, _, h = restaurante
    harina = insumo(cliente, h)
    comprar(cliente, h, linea(harina, 1, 10), fecha="2026-03-15")
    marzo = cliente.get("/v1/compras", headers=h, params={"mes": "2026-03"}).json()
    assert marzo["resumen"]["cantidad"] == 1 and marzo["compras"][0]["fecha"] == "2026-03-15"


# ------------------------------------------------------------------ anular

def test_anular_devuelve_la_existencia_y_el_costo_anterior(restaurante):
    cliente, _, h = restaurante
    harina = insumo(cliente, h, existencia=10, costo=150)               # 15 por libra
    compra = comprar(cliente, h, linea(harina, 10, 200))               # promedio 17.50
    assert ver(cliente, h, harina)["costo_unitario"] == "17.50"
    r = anular(cliente, h, compra, "  Compré de más ")
    assert r.status_code == 200
    anulada = r.json()
    assert anulada["estado"] == "anulada" and anulada["motivo_anulacion"] == "Compré de más"
    assert anulada["anulada_en"] is not None
    despues = ver(cliente, h, harina)
    assert despues["existencia"] == "10" and despues["costo_unitario"] == "15.00"
    reverso = cliente.get(f"/v1/insumos/{harina['id']}/movimientos",
                          headers=h).json()["movimientos"][0]
    assert (reverso["tipo"], reverso["cantidad"], reverso["costo_unitario"]) == (
        "reverso_compra", "-10", "20.00")
    # Anular otra vez no devuelve dos veces
    assert anular(cliente, h, compra).status_code == 409
    assert ver(cliente, h, harina)["existencia"] == "10"
    # El detalle sigue disponible y el mes ya no la cuenta
    assert cliente.get(f"/v1/compras/{compra['id']}", headers=h).json()["estado"] == "anulada"
    assert cliente.get("/v1/compras", headers=h).json()["resumen"]["cantidad"] == 0


def test_anular_con_lo_comprado_ya_gastado_conserva_el_costo(restaurante):
    cliente, _, h = restaurante
    harina = insumo(cliente, h)
    compra = comprar(cliente, h, linea(harina, 10, 200))               # 20 por libra
    cliente.post(f"/v1/insumos/{harina['id']}/movimientos", headers=h, json={
        "tipo": "merma", "cantidad": "7"})                              # quedan 3
    assert anular(cliente, h, compra).status_code == 200
    despues = ver(cliente, h, harina)
    assert despues["existencia"] == "-7" and despues["costo_unitario"] == "20.00"
    assert despues["estado"] == "falta"


def test_anular_una_de_dos_compras_recalcula_el_promedio(restaurante):
    cliente, _, h = restaurante
    harina = insumo(cliente, h)
    comprar(cliente, h, linea(harina, 10, 100))                         # 10 por libra
    segunda = comprar(cliente, h, linea(harina, 10, 300))               # promedio 20
    assert ver(cliente, h, harina)["costo_unitario"] == "20.00"
    anular(cliente, h, segunda)
    despues = ver(cliente, h, harina)
    assert despues["existencia"] == "10" and despues["costo_unitario"] == "10.00"


def test_anular_con_un_insumo_archivado_no_falla(restaurante):
    cliente, _, h = restaurante
    harina = insumo(cliente, h)
    compra = comprar(cliente, h, linea(harina, 10, 100))
    cliente.delete(f"/v1/insumos/{harina['id']}", headers=h)
    assert anular(cliente, h, compra).status_code == 200


def test_el_motivo_de_anulacion_es_obligatorio(restaurante):
    cliente, _, h = restaurante
    harina = insumo(cliente, h)
    compra = comprar(cliente, h, linea(harina, 1, 10))
    assert cliente.post(f"/v1/compras/{compra['id']}/anular", headers=h, json={}).status_code == 422
    assert anular(cliente, h, compra, "x").status_code == 422
    assert cliente.get(f"/v1/compras/{compra['id']}", headers=h).json()["estado"] == "registrada"


# ------------------------------------------------------------------ permisos y aislamiento

def test_un_negocio_no_ve_las_compras_ni_proveedores_de_otro(restaurante, tienda):
    cliente, _, h = restaurante
    _, _, h_otro = tienda
    harina = insumo(cliente, h)
    pedro = cliente.post("/v1/proveedores", headers=h, json={"nombre": "Don Pedro"}).json()
    compra = comprar(cliente, h, linea(harina, 1, 10), proveedor_id=pedro["id"])
    assert cliente.get("/v1/compras", headers=h_otro).json()["resumen"]["cantidad"] == 0
    assert cliente.get("/v1/proveedores", headers=h_otro).json() == []
    for r in (
        cliente.get(f"/v1/compras/{compra['id']}", headers=h_otro),
        anular(cliente, h_otro, compra),
        cliente.patch(f"/v1/proveedores/{pedro['id']}", headers=h_otro,
                      json={"version": 1, "nombre": "Mío"}),
        cliente.delete(f"/v1/proveedores/{pedro['id']}", headers=h_otro),
    ):
        assert r.status_code == 404
    assert cliente.get(f"/v1/compras/{compra['id']}", headers=h).json()["estado"] == "registrada"


def test_el_cajero_no_ve_ni_cambia_compras(restaurante, bd_migrada):
    cliente, _, h = restaurante
    harina = insumo(cliente, h)
    compra = comprar(cliente, h, linea(harina, 1, 10))
    poner_rol(bd_migrada, "cajero")
    cuerpo = {"lineas": [linea(harina, 1, 10)], "medio_pago": "efectivo"}
    for r in (
        cliente.get("/v1/compras", headers=h),
        cliente.get(f"/v1/compras/{compra['id']}", headers=h),
        cliente.post("/v1/compras", headers=h, json=cuerpo),
        cliente.post(f"/v1/compras/{compra['id']}/anular", headers=h, json={"motivo": "Prueba"}),
        cliente.get("/v1/proveedores", headers=h),
        cliente.post("/v1/proveedores", headers=h, json={"nombre": "Don Pedro"}),
    ):
        assert r.status_code == 403


def test_un_contador_ve_las_compras_pero_no_las_cambia(restaurante, bd_migrada):
    cliente, _, h = restaurante
    harina = insumo(cliente, h)
    compra = comprar(cliente, h, linea(harina, 1, 10))
    poner_rol(bd_migrada, "contador")
    assert cliente.get("/v1/compras", headers=h).status_code == 200
    assert cliente.get(f"/v1/compras/{compra['id']}", headers=h).status_code == 200
    assert cliente.get("/v1/proveedores", headers=h).status_code == 200
    cuerpo = {"lineas": [linea(harina, 1, 10)], "medio_pago": "efectivo"}
    assert cliente.post("/v1/compras", headers=h, json=cuerpo).status_code == 403
    assert anular(cliente, h, compra).status_code == 403
    assert cliente.post("/v1/proveedores", headers=h, json={"nombre": "X1"}).status_code == 403


def test_sin_sesion_no_hay_acceso(cliente_api):
    assert cliente_api.get("/v1/compras").status_code == 401
    assert cliente_api.get("/v1/proveedores").status_code == 401


# ------------------------------------------------------------------ checklist

def test_la_primera_compra_marca_su_paso_y_anularla_lo_desmarca(restaurante, tienda):
    cliente, negocio, h = restaurante

    def hecho(n, h_):
        datos = cliente.get(f"/v1/negocios/{n['id']}", headers=h_).json()
        return {p["clave"]: p["hecho"] for p in datos["primeros_pasos"]}["primera_compra"]

    harina = insumo(cliente, h)
    assert hecho(negocio, h) is False
    compra = comprar(cliente, h, linea(harina, 1, 10))
    assert hecho(negocio, h) is True
    anular(cliente, h, compra)
    assert hecho(negocio, h) is False
    # La tienda en línea también tiene el paso, y es independiente
    _, negocio_t, h_t = tienda
    assert hecho(negocio_t, h_t) is False
