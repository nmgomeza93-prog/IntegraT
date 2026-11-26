"""Clientes (docs/ANALISIS_INVENTARIO_Y_CLIENTES.md, C1): datos fijos, campos propios, validaciones,
duplicados, búsqueda, ficha con sus compras y a quién se le vendió."""

import pytest
import sqlalchemy as sa
from conftest import con_token, crear_negocio_api, registrar_usuario

from integrat import validaciones as val


@pytest.fixture
def tienda(cliente_api):
    sesion = registrar_usuario(cliente_api, "Ana")
    negocio = crear_negocio_api(cliente_api, sesion, "Tienda de Ana", "restaurante")
    return cliente_api, negocio, con_token(negocio["acceso"])


def nuevo(cliente, h, **datos):
    return cliente.post("/v1/clientes", headers=h, json={"nombre": "María López", **datos})


def poner_rol(bd, negocio, rol):
    with bd.begin() as con:
        con.execute(sa.text("UPDATE core_membresia SET rol = :r "
                            "WHERE negocio_id = UUID_TO_BIN(:n)"), {"r": rol, "n": negocio["id"]})


# ------------------------------------------------------------------ validaciones (sin base)

@pytest.mark.parametrize(("entrada", "esperado"), [
    ("5555-1234", "+50255551234"), ("5555 1234", "+50255551234"),
    ("+502 5555 1234", "+50255551234"),
    ("50255551234", "+50255551234"), ("+1 (305) 555-0100", "+13055550100"),
])
def test_telefonos_validos_se_normalizan(entrada, esperado):
    assert val.telefono(entrada) == esperado


@pytest.mark.parametrize("entrada", ["5555", "5555-12345", "+502 5555 123", "cinco", "+12"])
def test_telefonos_invalidos(entrada):
    with pytest.raises(val.DatoInvalido):
        val.telefono(entrada)


def test_nit_cui_y_correo():
    assert val.nit("1234567-9") == "12345679"
    with pytest.raises(val.DatoInvalido):
        val.nit("1234567-8")
    with pytest.raises(val.DatoInvalido):
        val.nit("12-34A")
    assert val.cui("1234 56789 0101") == "1234567890101"
    for malo in ("1234567880101", "1234567892301", "123"):
        with pytest.raises(val.DatoInvalido):
            val.cui(malo)
    assert val.id_fiscal("CF", "lo que sea") is None
    assert val.correo(" Maria@Gmail.com ") == "maria@gmail.com"
    with pytest.raises(val.DatoInvalido):
        val.correo("maria@gmail")


def test_nit_con_k():
    # Cuerpo cuyo verificador da 10 → K.
    def verificador(n: int) -> int:
        digitos = reversed(str(n))
        return (11 - sum(int(d) * f for d, f in zip(digitos, range(2, 9), strict=False)) % 11) % 11

    cuerpo = str(next(n for n in range(1000, 99999) if verificador(n) == 10))
    assert val.nit(cuerpo + "-k") == cuerpo + "K"


def test_valores_de_campos_propios():
    assert val.valor_de_campo("Talla", "texto", "  M ") == "M"
    assert val.valor_de_campo("Hijos", "numero", "2") == "2"
    assert val.valor_de_campo("Cumple", "fecha", "1990-05-17") == "1990-05-17"
    assert val.valor_de_campo("Mayorista", "si_no", True) is True
    assert val.valor_de_campo("Talla", "texto", "") is None
    for tipo, malo in (("numero", "dos"), ("fecha", "17/05/1990"), ("si_no", "sí"),
                       ("numero", True)):
        with pytest.raises(val.DatoInvalido):
            val.valor_de_campo("Campo", tipo, malo)


# ------------------------------------------------------------------ API

def test_agregar_buscar_y_ver_un_cliente(tienda):
    cliente, _, h = tienda
    r = nuevo(cliente, h, telefono="5555-1234", correo="Maria@Gmail.com", tipo_id_fiscal="NIT",
              id_fiscal="1234567-9", direccion="Zona 10")
    assert r.status_code == 201, r.text
    maria = r.json()
    assert (maria["telefono"], maria["correo"], maria["id_fiscal"]) == (
        "+50255551234", "maria@gmail.com", "12345679")
    nuevo(cliente, h, nombre="Pedro Pérez")
    buscar = lambda q: [c["nombre"] for c in cliente.get(  # noqa: E731
        "/v1/clientes", headers=h, params={"q": q}).json()]
    assert buscar("maria") == ["María López"]          # sin tildes ni mayúsculas
    assert buscar("1234") == ["María López"]           # por teléfono
    assert buscar("") == ["María López", "Pedro Pérez"]
    ficha = cliente.get(f"/v1/clientes/{maria['id']}", headers=h).json()
    assert ficha["compras"] == {"cantidad": 0, "total": "0.00", "ultima": None, "ultimas": []}


def test_datos_invalidos_dicen_que_corregir(tienda):
    cliente, _, h = tienda
    r = nuevo(cliente, h, nombre="M")
    assert r.status_code == 422
    assert r.json()["detail"] == "Revisa el nombre: escribe al menos 2 letras."
    r = nuevo(cliente, h, tipo_id_fiscal="RUT")
    assert r.json()["detail"] == "Revisa el tipo de factura: elige una de las opciones."
    r = cliente.post("/v1/clientes", headers=h, json={"telefono": "55551234"})
    assert r.json()["detail"] == "Revisa el nombre: falta."
    # La app (R) manda los datos propios vacíos como []: se acepta.
    assert nuevo(cliente, h, nombre="Sin datos", datos=[]).status_code == 201
    r = nuevo(cliente, h, telefono="1234")
    assert r.status_code == 422 and "8 dígitos" in r.json()["detail"]
    r = nuevo(cliente, h, tipo_id_fiscal="NIT", id_fiscal="1234567-8")
    assert r.status_code == 422 and "NIT" in r.json()["detail"]
    r = nuevo(cliente, h, tipo_id_fiscal="CUI")
    assert r.status_code == 422 and "Consumidor final" in r.json()["detail"]


def test_un_telefono_o_nit_repetido_avisa_y_se_puede_guardar_igual(tienda):
    cliente, _, h = tienda
    assert nuevo(cliente, h, telefono="5555 1234").status_code == 201
    r = nuevo(cliente, h, nombre="Mamá de María", telefono="+502 5555-1234")
    assert r.status_code == 409 and "Ya tienes a María López con ese teléfono" in r.json()["detail"]
    r = nuevo(cliente, h, nombre="Mamá de María", telefono="55551234", aunque_se_repita=True)
    assert r.status_code == 201


def test_cambiar_y_archivar(tienda):
    cliente, _, h = tienda
    maria = nuevo(cliente, h, telefono="55551234").json()
    r = cliente.patch(f"/v1/clientes/{maria['id']}", headers=h,
                      json={"version": maria["version"], "telefono": None, "notas": "Paga puntual"})
    assert r.status_code == 200 and r.json()["telefono"] is None
    assert r.json()["notas"] == "Paga puntual"
    viejo = cliente.patch(f"/v1/clientes/{maria['id']}", headers=h,
                          json={"version": maria["version"], "nombre": "Otra"})
    assert viejo.status_code == 409
    assert cliente.delete(f"/v1/clientes/{maria['id']}", headers=h).status_code == 204
    ficha = cliente.get(f"/v1/clientes/{maria['id']}", headers=h).json()
    assert ficha["archivado"] is True  # la ficha sigue: sus ventas la nombran
    assert cliente.get("/v1/clientes", headers=h).json() == []
    archivados = cliente.get("/v1/clientes", headers=h, params={"archivados": True}).json()
    assert [c["nombre"] for c in archivados] == ["María López"]
    # Archivada no se cambia; se recupera y vuelve a la lista.
    r = cliente.patch(f"/v1/clientes/{maria['id']}", headers=h,
                      json={"version": ficha["version"], "nombre": "Otra"})
    assert r.status_code == 404
    r = cliente.post(f"/v1/clientes/{maria['id']}/recuperar", headers=h)
    assert r.status_code == 200 and r.json()["archivado"] is False
    assert [c["nombre"] for c in cliente.get("/v1/clientes", headers=h).json()] == ["María López"]
    assert cliente.post(f"/v1/clientes/{maria['id']}/recuperar", headers=h).status_code == 404


def test_campos_propios(tienda):
    cliente, _, h = tienda
    r = cliente.put("/v1/clientes/campos", headers=h, json={"campos": [
        {"nombre": "Instagram", "tipo": "texto"}, {"nombre": "Cumpleaños", "tipo": "fecha"},
        {"nombre": "Mayorista", "tipo": "si_no"}]})
    assert r.status_code == 200, r.text
    ig, cumple, mayorista = r.json()
    maria = nuevo(cliente, h, datos={ig["id"]: "@maria", cumple["id"]: "1990-05-17"}).json()
    assert maria["datos"] == {ig["id"]: "@maria", cumple["id"]: "1990-05-17"}
    malo = nuevo(cliente, h, nombre="Pedro", datos={cumple["id"]: "mayo"})
    assert malo.status_code == 422 and "Cumpleaños" in malo.json()["detail"]
    # Se mezcla con lo que había; null lo quita.
    r = cliente.patch(f"/v1/clientes/{maria['id']}", headers=h, json={
        "version": maria["version"], "datos": {mayorista["id"]: True, ig["id"]: None}})
    assert r.json()["datos"] == {cumple["id"]: "1990-05-17", mayorista["id"]: True}
    # Quitar un campo lo archiva: ya no se muestra; no se le cambia el tipo.
    r = cliente.put("/v1/clientes/campos", headers=h, json={"campos": [
        {"id": cumple["id"], "nombre": "Cumple", "tipo": "fecha"}]})
    assert [c["nombre"] for c in r.json()] == ["Cumple"]
    assert cliente.get(f"/v1/clientes/{maria['id']}", headers=h).json()["datos"] == {
        cumple["id"]: "1990-05-17"}
    r = cliente.put("/v1/clientes/campos", headers=h, json={"campos": [
        {"id": cumple["id"], "nombre": "Cumple", "tipo": "texto"}]})
    assert r.status_code == 422
    r = cliente.put("/v1/clientes/campos", headers=h, json={"campos": [
        {"nombre": "Talla", "tipo": "texto"}, {"nombre": "talla", "tipo": "texto"}]})
    assert r.status_code == 422


def test_vender_a_un_cliente_y_ver_sus_compras(tienda):
    cliente, _, h = tienda
    maria = nuevo(cliente, h).json()
    taco = cliente.post("/v1/items", headers=h,
                        json={"nombre": "Taco", "precio_venta": "15"}).json()
    venta = lambda **extra: cliente.post("/v1/ventas", headers=h, json={  # noqa: E731
        "lineas": [{"item_id": taco["id"], "cantidad": 2}], "medio_pago": "efectivo", **extra})
    r = venta(cliente_id=maria["id"])
    assert r.status_code == 201, r.text
    assert (r.json()["cliente_id"], r.json()["cliente_nombre"]) == (maria["id"], "María López")
    sin_cliente = venta()
    assert sin_cliente.json()["cliente_nombre"] is None  # Consumidor final
    otra = venta(cliente_id=maria["id"]).json()
    cliente.post(f"/v1/ventas/{otra['id']}/anular", headers=h, json={"motivo": "Me equivoqué"})
    compras = cliente.get(f"/v1/clientes/{maria['id']}", headers=h).json()["compras"]
    assert (compras["cantidad"], compras["total"]) == (1, "30.00")  # la anulada no cuenta
    assert [u["venta_id"] for u in compras["ultimas"]] == [r.json()["id"]]
    # Archivado: sus ventas siguen diciendo a quién; ya no se le puede vender.
    cliente.delete(f"/v1/clientes/{maria['id']}", headers=h)
    assert cliente.get(f"/v1/ventas/{r.json()['id']}", headers=h).json()["cliente_nombre"] == \
        "María López"
    r = venta(cliente_id=maria["id"])
    assert r.status_code == 422 and "Consumidor final" in r.json()["detail"]


def test_cada_negocio_ve_solo_sus_clientes(tienda, cliente_api):
    cliente, _, h = tienda
    maria = nuevo(cliente, h, telefono="55551234").json()
    otro = crear_negocio_api(cliente_api, registrar_usuario(cliente_api, "Luis"), "Luis",
                             "restaurante")
    h2 = con_token(otro["acceso"])
    assert cliente.get(f"/v1/clientes/{maria['id']}", headers=h2).status_code == 404
    assert cliente.get("/v1/clientes", headers=h2).json() == []
    assert nuevo(cliente, h2, telefono="55551234").status_code == 201  # no es duplicado allá
    taco = cliente.post("/v1/items", headers=h2,
                        json={"nombre": "Taco", "precio_venta": "15"}).json()
    r = cliente.post("/v1/ventas", headers=h2, json={
        "lineas": [{"item_id": taco["id"], "cantidad": 1}], "medio_pago": "efectivo",
        "cliente_id": maria["id"]})
    assert r.status_code == 422


def test_el_cajero_anota_clientes_pero_no_archiva_ni_define_campos(tienda, bd_migrada):
    cliente, negocio, h = tienda
    poner_rol(bd_migrada, negocio, "cajero")
    maria = nuevo(cliente, h)
    assert maria.status_code == 201
    assert cliente.get("/v1/clientes/campos", headers=h).status_code == 200
    assert cliente.put("/v1/clientes/campos", headers=h, json={"campos": []}).status_code == 403
    assert cliente.delete(f"/v1/clientes/{maria.json()['id']}", headers=h).status_code == 403
    poner_rol(bd_migrada, negocio, "contador")
    assert cliente.get("/v1/clientes", headers=h).status_code == 200
    assert nuevo(cliente, h, nombre="Pedro").status_code == 403
