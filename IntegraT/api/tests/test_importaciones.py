"""Importaciones con la plantilla de factura (docs/PLAN_IMPORTACION.md).

La plantilla de las pruebas imita la del dueño (hoja Factura_camino, ENCABEZADO + PRODUCTO), con
datos inventados.
"""

import io
from decimal import Decimal

import pytest
import sqlalchemy as sa
from conftest import con_token, crear_negocio_api, registrar_usuario
from openpyxl import Workbook

from integrat.importaciones.plantilla import nombre_sugerido
from integrat.importaciones.servicio import repartir

COLUMNAS = ["tipo_registro", "proveedor_id", "numero_factura", "numero_orden_plataforma",
            "plataforma", "fecha_factura", "moneda_codigo", "tipo_cambio", "total_factura",
            "garantia_envio", "costo_importacion", "otros_cobros", "skc", "cantidad",
            "precio_unitario_fob", "descripcion_proveedor", "nombre_operativo", "talla", "color",
            "precio_venta_ref"]
PRODUCTOS = [  # skc, cantidad, precio MXN, descripción, talla, color
    ("si100", 1, "100.00", "SilkySpell Conjunto de pijama con encaje", "M", "Negro"),
    ("si200", 1, "150.00", "Dream Adore Conjunto de ropa de estar en casa con lazo", "S", "Rosa"),
    ("si200", 2, "150.00", "Dream Adore Conjunto de ropa de estar en casa con lazo", "M", "Rosa"),
    ("sq300", 1, "300.00", "Camara de salpicadero 1080P de 3 canales", "S", "Negro"),
]


def plantilla_xlsx(productos=PRODUCTOS, total="969.00", garantia="19", importacion="100",
                   moneda="MXN", tipo_cambio=None) -> bytes:
    libro = Workbook()
    hoja = libro.active
    hoja.title = "Factura_camino"
    hoja.append(COLUMNAS)
    hoja.append(["ENCABEZADO", 1, "INVPRUEBA001", "ORD-PRUEBA-1", "shein", "2026-11-03", moneda,
                 tipo_cambio, float(total) if total else None, float(garantia),
                 float(importacion), 0] + [None] * 8)
    for skc, cantidad, precio, descripcion, talla, color in productos:
        hoja.append(["PRODUCTO"] + [None] * 11 + [skc, cantidad, float(precio), descripcion, None,
                                                   talla, color, None])
    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()


@pytest.fixture
def tienda(cliente_api):
    sesion = registrar_usuario(cliente_api, "Ana")
    negocio = crear_negocio_api(cliente_api, sesion, "Tienda de Ana", "ventas_en_linea")
    return cliente_api, negocio, con_token(negocio["acceso"])


def previa(cliente, h, contenido=None, nombre="factura.xlsx"):
    return cliente.post("/v1/importaciones/vista-previa", headers=h,
                        files={"archivo": (nombre, contenido or plantilla_xlsx(),
                                           "application/octet-stream")})


def a_confirmacion(vista: dict, cobro_q="387.60", medio="tarjeta") -> dict:
    """La revisión tal cual la sugiere la vista previa (la app manda esto al confirmar)."""
    e = vista["encabezado"]
    return {
        "plataforma": e["plataforma"], "numero_factura": e["numero_factura"],
        "numero_orden": e["numero_orden"], "fecha_factura": e["fecha_factura"],
        "moneda_codigo": e["moneda_codigo"], "garantia_envio": e["garantia_envio"],
        "costo_importacion": e["costo_importacion"], "otros_cobros": e["otros_cobros"],
        "cobro_q": cobro_q, "medio_pago": medio,
        "productos": [{
            "nombre": p["nombre"], "categoria": p["categoria"], "item_id": p["item_id"],
            "lineas": [{"codigo": x["codigo"], "descripcion": x["descripcion"],
                        "atributos": x["atributos"], "cantidad": x["cantidad"],
                        "precio_unitario": x["precio_unitario"],
                        "item_variante_id": x["item_variante_id"]} for x in p["lineas"]],
        } for p in vista["productos"]],
    }


def confirmar(cliente, h, cuerpo, clave=None):
    cabeceras = {**h, **({"Idempotency-Key": clave} if clave else {})}
    return cliente.post("/v1/importaciones", headers=cabeceras, json=cuerpo)


def saldos(cliente, h) -> dict[str, Decimal]:
    cuentas = cliente.get("/v1/cuentas", headers=h).json()["cuentas"]
    return {c["codigo"]: Decimal(c["saldo"]) for c in cuentas
            if c["acepta_movimientos"] and Decimal(c["saldo"]) != 0}


# ------------------------------------------------------------------ piezas sueltas


def test_repartir_cuadra_al_centavo():
    partes = repartir([Decimal("1"), Decimal("1"), Decimal("1")], Decimal("10.00"))
    assert partes == [Decimal("3.33"), Decimal("3.33"), Decimal("3.34")]
    assert sum(partes) == Decimal("10.00")


@pytest.mark.parametrize(("descripcion", "esperado"), [
    ("SilkySpell Conjunto de pijama con top de camiseta", "SilkySpell Conjunto de pijama"),
    ("Camara de salpicadero 1080P de 3 canales - Grabacion frontal",
     "Camara de salpicadero 1080P de 3 canales"),
    ("LuxeNights Conjunto de 2 piezas de pijama de seda sexy y elegante para mujer",
     "LuxeNights Conjunto de 2 piezas de pijama de seda sexy"),
])
def test_nombre_corto_sugerido(descripcion, esperado):
    assert nombre_sugerido(descripcion) == esperado


# ------------------------------------------------------------------ vista previa


def test_la_vista_previa_agrupa_sugiere_y_cuadra(tienda):
    cliente, _, h = tienda
    r = previa(cliente, h)
    assert r.status_code == 200, r.text
    v = r.json()
    e = v["encabezado"]
    assert e["plataforma"] == "shein" and e["moneda_codigo"] == "MXN" and e["moneda_conocida"]
    assert v["cuadre"] == {"lineas": "850.00", "cargos": "119.00", "total_calculado": "969.00",
                           "total_factura": "969.00", "diferencia": "0.00", "cuadra": True}
    assert v["unidades"] == 5 and len(v["productos"]) == 3
    pijama, casa, camara = v["productos"]
    assert pijama["nombre"] == "SilkySpell Conjunto de pijama"
    assert pijama["categoria"] == "Ropa de dormir" and pijama["existente"] is False
    assert [x["atributos"] for x in casa["lineas"]] == [{"Talla": "S", "Color": "Rosa"},
                                                        {"Talla": "M", "Color": "Rosa"}]
    assert camara["categoria"] == "Electrónica"
    assert camara["lineas"][0]["atributos"] == {"Color": "Negro"}  # sin la talla "S"


def test_la_vista_previa_avisa_si_no_cuadra(tienda):
    cliente, _, h = tienda
    v = previa(cliente, h, plantilla_xlsx(total="1000.00")).json()
    assert v["cuadre"]["cuadra"] is False and v["cuadre"]["diferencia"] == "31.00"
    assert any("no cuadra" in a for a in v["avisos"])


@pytest.mark.parametrize(("contenido", "nombre", "mensaje"), [
    (b"hola", "factura.pdf", "Excel"),
    (b"no es un excel", "factura.xlsx", "No pudimos leer"),
    (b"tipo_registro,skc\nPRODUCTO,si1\n", "factura.csv", "Faltan columnas"),
])
def test_plantillas_invalidas(tienda, contenido, nombre, mensaje):
    cliente, _, h = tienda
    r = previa(cliente, h, contenido, nombre)
    assert r.status_code == 422 and mensaje in r.json()["detail"]


def test_tambien_lee_csv(tienda):
    cliente, _, h = tienda
    filas = [",".join(COLUMNAS),
             "ENCABEZADO,,F1,O1,temu,2026-11-01,USD,,25,0,0,0,,,,,,,,",
             "PRODUCTO,,,,,,,,,,,,t1,2,12.50,Gorra bordada de algodon,,,Negro,"]
    v = previa(cliente, h, "\n".join(filas).encode(), "factura.csv").json()
    assert v["encabezado"]["plataforma"] == "temu"
    assert v["productos"][0]["categoria"] == "Accesorios"


# ------------------------------------------------------------------ en camino, recibir, anular


def test_confirmar_deja_la_importacion_en_camino(tienda):
    cliente, _, h = tienda
    r = confirmar(cliente, h, a_confirmacion(previa(cliente, h).json()))
    assert r.status_code == 201, r.text
    imp = r.json()
    assert imp["estado"] == "en_camino" and imp["total_factura"] == "969.00"
    assert imp["total_q"] == "387.60" and imp["tipo_cambio"] == "0.400000"  # 387.60 / 969
    assert sum(Decimal(x["costo_pedido_q"]) for x in imp["lineas"]) == Decimal("387.60")
    assert saldos(cliente, h) == {"1103": Decimal("-387.60"), "1109": Decimal("387.60")}
    assert cliente.get("/v1/items", headers=h).json()["total"] == 0  # aún no llega
    lista = cliente.get("/v1/importaciones", headers=h).json()
    assert [x["id"] for x in lista["en_camino"]] == [imp["id"]]


def test_recibir_crea_productos_variantes_inventario_y_precio(tienda):
    cliente, _, h = tienda
    imp = confirmar(cliente, h, a_confirmacion(previa(cliente, h).json())).json()
    r = cliente.post(f"/v1/importaciones/{imp['id']}/recibir", headers=h,
                     json={"courier_q": "50.00", "envio_local_q": "10.00", "guia": "GT-123"})
    assert r.status_code == 200, r.text
    recibida = r.json()
    assert recibida["estado"] == "recibida" and recibida["guia"] == "GT-123"
    assert sum(Decimal(x["courier_q"]) for x in recibida["lineas"]) == Decimal("60.00")
    # Pijama: 100 MXN + su parte de 119 de cargos (14) = 114 MXN × 0.4 = Q45.60; courier Q7.06
    pijama = recibida["lineas"][0]
    assert pijama["costo_pedido_q"] == "45.60" and pijama["courier_q"] == "7.06"
    assert pijama["costo_unitario_q"] == "52.66"
    assert pijama["precio_sugerido"] == "81.50"  # 52.66 / 0.65 = 81.02 -> 81.50

    productos = {i["nombre"]: i for i in cliente.get("/v1/items", headers=h).json()["items"]}
    assert set(productos) == {"SilkySpell Conjunto de pijama",
                              "Dream Adore Conjunto de ropa de estar en casa",
                              "Camara de salpicadero 1080P de 3 canales"}
    casa = productos["Dream Adore Conjunto de ropa de estar en casa"]
    assert casa["tiene_variantes"] and [v["nombre"] for v in casa["variantes"]] == [
        "S · Rosa", "M · Rosa"]
    assert all(v["codigo"] == "si200" for v in casa["variantes"])
    assert all(Decimal(v["precio_venta"]) > 0 for v in casa["variantes"])  # listo para vender
    categorias = {c["nombre"] for c in cliente.get("/v1/categorias", headers=h).json()}
    assert {"Ropa de dormir", "Electrónica"} <= categorias
    existencias = {i["nombre"]: i["existencia"]
                   for i in cliente.get("/v1/insumos", headers=h).json()["insumos"]}
    assert existencias["Dream Adore Conjunto de ropa de estar en casa · M · Rosa"] == "2"
    # Mercadería en camino queda en cero; el inventario vale lo pagado más el courier.
    s = saldos(cliente, h)
    assert "1109" not in s and s["1107"] == Decimal("447.60")
    assert s["1101"] == Decimal("-60.00")  # courier en efectivo


def test_lo_que_no_llega_se_da_por_perdido(tienda):
    cliente, _, h = tienda
    imp = confirmar(cliente, h, a_confirmacion(previa(cliente, h).json())).json()
    camara = imp["lineas"][3]
    r = cliente.post(f"/v1/importaciones/{imp['id']}/recibir", headers=h, json={
        "lineas": [{"linea_id": camara["id"], "cantidad_recibida": 0}]})
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "recibida_parcial"
    s = saldos(cliente, h)
    assert s["5102"] == Decimal(camara["costo_pedido_q"]) and "1109" not in s
    assert cliente.post(f"/v1/importaciones/{imp['id']}/recibir", headers=h,
                        json={}).status_code == 409  # ya se recibió


def test_una_segunda_importacion_suma_al_producto_que_ya_existe(tienda):
    cliente, _, h = tienda
    primera = confirmar(cliente, h, a_confirmacion(previa(cliente, h).json())).json()
    cliente.post(f"/v1/importaciones/{primera['id']}/recibir", headers=h, json={})
    v = previa(cliente, h, plantilla_xlsx(productos=[PRODUCTOS[2]], total="419.00")).json()
    casa = v["productos"][0]
    assert casa["existente"] is True and casa["lineas"][0]["item_variante_id"] is not None
    segunda = confirmar(cliente, h, a_confirmacion(v, cobro_q="167.60")).json()
    cliente.post(f"/v1/importaciones/{segunda['id']}/recibir", headers=h, json={})
    productos = cliente.get("/v1/items", headers=h).json()
    assert productos["total"] == 3  # no se duplicó
    existencias = {i["nombre"]: i["existencia"]
                   for i in cliente.get("/v1/insumos", headers=h).json()["insumos"]}
    assert existencias["Dream Adore Conjunto de ropa de estar en casa · M · Rosa"] == "4"


def test_anular_una_importacion_en_camino(tienda):
    cliente, _, h = tienda
    imp = confirmar(cliente, h, a_confirmacion(previa(cliente, h).json())).json()
    r = cliente.post(f"/v1/importaciones/{imp['id']}/anular", headers=h,
                     json={"motivo": "Pedido cancelado"})
    assert r.status_code == 200 and r.json()["estado"] == "anulada"
    assert saldos(cliente, h) == {}
    assert cliente.post(f"/v1/importaciones/{imp['id']}/recibir", headers=h,
                        json={}).status_code == 409


def test_sin_cobro_ni_tipo_de_cambio_y_la_misma_clave(tienda):
    cliente, _, h = tienda
    cuerpo = a_confirmacion(previa(cliente, h).json())
    cuerpo["cobro_q"] = None
    assert confirmar(cliente, h, cuerpo).status_code == 422
    cuerpo["tipo_cambio"] = "0.41"
    a = confirmar(cliente, h, cuerpo, clave="importacion-0001")
    b = confirmar(cliente, h, cuerpo, clave="importacion-0001")
    assert a.status_code == 201 and a.json()["id"] == b.json()["id"]
    assert a.json()["total_q"] == "397.29"  # 969 × 0.41
    assert len(cliente.get("/v1/importaciones", headers=h).json()["en_camino"]) == 1


def test_permisos_y_aislamiento(tienda, cliente_api, bd_migrada):
    cliente, negocio, h = tienda
    imp = confirmar(cliente, h, a_confirmacion(previa(cliente, h).json())).json()
    otra = crear_negocio_api(cliente_api, registrar_usuario(cliente_api, "Bea"), "Otra",
                             "ventas_en_linea")
    h_otra = con_token(otra["acceso"])
    assert cliente.get(f"/v1/importaciones/{imp['id']}", headers=h_otra).status_code == 404
    assert cliente.post(f"/v1/importaciones/{imp['id']}/recibir", headers=h_otra,
                        json={}).status_code == 404
    with bd_migrada.begin() as con:
        con.execute(sa.text("UPDATE core_membresia SET rol = 'cajero' "
                            "WHERE negocio_id = UUID_TO_BIN(:n)"), {"n": negocio["id"]})
    assert cliente.get("/v1/importaciones", headers=h).status_code == 403
    assert previa(cliente, h).status_code == 403
