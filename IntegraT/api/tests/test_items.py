"""Catálogo de productos y platillos: /v1/items y /v1/categorias."""

import uuid

import pytest
import sqlalchemy as sa
from conftest import con_token, crear_negocio_api, registrar_usuario


@pytest.fixture
def restaurante(cliente_api):
    sesion = registrar_usuario(cliente_api, "Mari")
    negocio = crear_negocio_api(cliente_api, sesion, "Comedor Doña Mari", "restaurante")
    return cliente_api, sesion, con_token(negocio["acceso"])


@pytest.fixture
def tienda(cliente_api):
    sesion = registrar_usuario(cliente_api, "Ana")
    negocio = crear_negocio_api(cliente_api, sesion, "Tienda de Ana", "ventas_en_linea")
    return cliente_api, sesion, con_token(negocio["acceso"])


def agregar(cliente, h, nombre="Pepián", precio="45.00", **extra):
    r = cliente.post("/v1/items", json={"nombre": nombre, "precio_venta": precio, **extra},
                     headers=h)
    assert r.status_code == 201, r.text
    return r.json()


# ------------------------------------------------------------------ categorías de ejemplo

def test_un_restaurante_nace_con_categorias_de_ejemplo(restaurante):
    cliente, _, h = restaurante
    cats = cliente.get("/v1/categorias", headers=h).json()
    assert [c["nombre"] for c in cats] == ["Entradas", "Platos fuertes", "Bebidas", "Postres"]
    assert all(c["cantidad_items"] == 0 for c in cats)


def test_una_tienda_en_linea_nace_sin_categorias(tienda):
    cliente, _, h = tienda
    assert cliente.get("/v1/categorias", headers=h).json() == []


# ------------------------------------------------------------------ crear y ver

def test_el_tipo_del_item_lo_define_el_tipo_de_negocio(restaurante, tienda):
    plato = agregar(restaurante[0], restaurante[2], "Pepián")
    producto = agregar(tienda[0], tienda[2], "Camisa")
    assert plato["tipo_item"] == "platillo"
    assert producto["tipo_item"] == "producto"


def test_crear_con_solo_nombre_y_precio(restaurante):
    cliente, _, h = restaurante
    item = agregar(cliente, h, "  Pepián  ", "45.5")
    assert item["nombre"] == "Pepián"
    assert item["precio_venta"] == "45.50"  # dinero como texto con 2 decimales
    assert item["categoria_id"] is None and item["archivado"] is False
    assert item["version"] == 1 and item["se_vende"] is True
    assert cliente.get(f"/v1/items/{item['id']}", headers=h).json()["nombre"] == "Pepián"


def test_crear_en_una_categoria(restaurante):
    cliente, _, h = restaurante
    cat = next(c for c in cliente.get("/v1/categorias", headers=h).json()
               if c["nombre"] == "Bebidas")
    item = agregar(cliente, h, "Horchata", "10", categoria_id=cat["id"])
    assert item["categoria_nombre"] == "Bebidas"
    cats = cliente.get("/v1/categorias", headers=h).json()
    assert next(c for c in cats if c["nombre"] == "Bebidas")["cantidad_items"] == 1


@pytest.mark.parametrize("cuerpo", [
    {"nombre": "A", "precio_venta": "10"},                    # nombre muy corto
    {"nombre": "Pepián", "precio_venta": "-1"},               # precio negativo
    {"nombre": "Pepián", "precio_venta": "10.999"},           # más de 2 decimales
    {"nombre": "Pepián", "precio_venta": "texto"},            # no es número
    {"nombre": "Pepián"},                                      # sin precio
    {"precio_venta": "10"},                                    # sin nombre
])
def test_datos_invalidos_dan_422(restaurante, cuerpo):
    cliente, _, h = restaurante
    assert cliente.post("/v1/items", json=cuerpo, headers=h).status_code == 422


def test_precio_cero_es_valido(restaurante):
    cliente, _, h = restaurante
    assert agregar(cliente, h, "Cortesía", "0")["precio_venta"] == "0.00"


def test_nombre_repetido_avisa_pero_deja_crear(restaurante):
    cliente, _, h = restaurante
    assert agregar(cliente, h, "Pollo")["aviso"] is None
    segundo = agregar(cliente, h, "pollo")  # mismo nombre sin importar mayúsculas
    assert segundo["aviso"] == "Ya tienes un platillo con ese nombre."
    assert cliente.get("/v1/items", headers=h).json()["total"] == 2


def test_categoria_inexistente_o_ajena_da_422(restaurante):
    cliente, _, h = restaurante
    r = cliente.post("/v1/items", headers=h, json={
        "nombre": "Pepián", "precio_venta": "45", "categoria_id": str(uuid.uuid4())})
    assert r.status_code == 422 and "categoría" in r.json()["detail"]


# ------------------------------------------------------------------ listar y buscar

def test_listar_buscar_filtrar_y_paginar(restaurante):
    cliente, _, h = restaurante
    bebidas = next(c for c in cliente.get("/v1/categorias", headers=h).json()
                   if c["nombre"] == "Bebidas")
    agregar(cliente, h, "Pepián")
    agregar(cliente, h, "Pollo guisado")
    agregar(cliente, h, "Café", "8", categoria_id=bebidas["id"])
    agregar(cliente, h, "100% natural")

    todo = cliente.get("/v1/items", headers=h).json()
    assert todo["total"] == 4
    assert [i["nombre"] for i in todo["items"]] == sorted(
        (i["nombre"] for i in todo["items"]), key=str.lower)

    assert [i["nombre"] for i in cliente.get("/v1/items?buscar=pol", headers=h)
            .json()["items"]] == ["Pollo guisado"]
    assert [i["nombre"] for i in cliente.get("/v1/items?buscar=cafe", headers=h)
            .json()["items"]] == ["Café"]  # sin importar tildes
    # El % y el _ se buscan tal cual, no como comodines
    assert [i["nombre"] for i in cliente.get("/v1/items?buscar=%25", headers=h)
            .json()["items"]] == ["100% natural"]
    assert cliente.get("/v1/items?buscar=_", headers=h).json()["total"] == 0

    por_categoria = cliente.get(f"/v1/items?categoria_id={bebidas['id']}", headers=h).json()
    assert [i["nombre"] for i in por_categoria["items"]] == ["Café"]

    pagina = cliente.get("/v1/items?limite=2&desplazar=2", headers=h).json()
    assert pagina["total"] == 4 and len(pagina["items"]) == 2
    assert cliente.get("/v1/items?limite=0", headers=h).status_code == 422


# ------------------------------------------------------------------ editar

def test_editar_nombre_precio_y_categoria(restaurante):
    cliente, _, h = restaurante
    postres = next(c for c in cliente.get("/v1/categorias", headers=h).json()
                   if c["nombre"] == "Postres")
    item = agregar(cliente, h, "Flan", "15")
    r = cliente.patch(f"/v1/items/{item['id']}", headers=h, json={
        "version": item["version"], "nombre": "Flan de vainilla", "precio_venta": "18.00",
        "categoria_id": postres["id"], "descripcion": "Con caramelo"})
    assert r.status_code == 200, r.text
    nuevo = r.json()
    assert (nuevo["nombre"], nuevo["precio_venta"], nuevo["categoria_nombre"],
            nuevo["descripcion"]) == ("Flan de vainilla", "18.00", "Postres", "Con caramelo")
    assert nuevo["version"] == item["version"] + 1


def test_editar_solo_el_precio_no_toca_lo_demas(restaurante):
    cliente, _, h = restaurante
    item = agregar(cliente, h, "Flan", "15", descripcion="Casero")
    nuevo = cliente.patch(f"/v1/items/{item['id']}", headers=h,
                          json={"version": 1, "precio_venta": "16"}).json()
    assert nuevo["precio_venta"] == "16.00"
    assert nuevo["nombre"] == "Flan" and nuevo["descripcion"] == "Casero"


def test_quitar_la_categoria_con_null(restaurante):
    cliente, _, h = restaurante
    cat = cliente.get("/v1/categorias", headers=h).json()[0]
    item = agregar(cliente, h, "Tostadas", "20", categoria_id=cat["id"])
    nuevo = cliente.patch(f"/v1/items/{item['id']}", headers=h,
                          json={"version": 1, "categoria_id": None}).json()
    assert nuevo["categoria_id"] is None and nuevo["categoria_nombre"] is None


def test_editar_con_una_version_vieja_da_409(restaurante):
    cliente, _, h = restaurante
    item = agregar(cliente, h, "Flan", "15")
    assert cliente.patch(f"/v1/items/{item['id']}", headers=h,
                         json={"version": 1, "precio_venta": "16"}).status_code == 200
    r = cliente.patch(f"/v1/items/{item['id']}", headers=h,
                      json={"version": 1, "precio_venta": "99"})  # la otra pestaña, desfasada
    assert r.status_code == 409 and "Alguien más" in r.json()["detail"]
    assert cliente.get(f"/v1/items/{item['id']}", headers=h).json()["precio_venta"] == "16.00"


def test_editar_sin_version_da_422(restaurante):
    cliente, _, h = restaurante
    item = agregar(cliente, h)
    assert cliente.patch(f"/v1/items/{item['id']}", headers=h,
                         json={"precio_venta": "1"}).status_code == 422


# ------------------------------------------------------------------ archivar

def test_archivar_oculta_el_item_pero_no_lo_borra(restaurante, bd_migrada):
    cliente, _, h = restaurante
    item = agregar(cliente, h, "Flan", "15")
    assert cliente.delete(f"/v1/items/{item['id']}", headers=h).status_code == 204
    assert cliente.get(f"/v1/items/{item['id']}", headers=h).status_code == 404
    assert cliente.get("/v1/items", headers=h).json()["total"] == 0
    archivados = cliente.get("/v1/items?archivados=true", headers=h).json()
    assert [i["nombre"] for i in archivados["items"]] == ["Flan"]
    assert archivados["items"][0]["archivado"] is True
    assert cliente.delete(f"/v1/items/{item['id']}", headers=h).status_code == 404
    assert cliente.patch(f"/v1/items/{item['id']}", headers=h,
                         json={"version": 1, "nombre": "Otro"}).status_code == 404
    with bd_migrada.connect() as con:  # la fila sigue en la base (borrado lógico)
        assert con.execute(sa.text(
            "SELECT COUNT(*) FROM ops_item WHERE eliminado_en IS NOT NULL")).scalar() >= 1


def test_archivar_una_categoria_deja_sus_items_sin_categoria(restaurante):
    cliente, _, h = restaurante
    cat = cliente.get("/v1/categorias", headers=h).json()[1]
    item = agregar(cliente, h, "Pepián", "45", categoria_id=cat["id"])
    assert cliente.delete(f"/v1/categorias/{cat['id']}", headers=h).status_code == 204
    assert cat["id"] not in [c["id"] for c in cliente.get("/v1/categorias", headers=h).json()]
    despues = cliente.get(f"/v1/items/{item['id']}", headers=h).json()
    assert despues["categoria_id"] is None and despues["nombre"] == "Pepián"


# ------------------------------------------------------------------ categorías

def test_crear_renombrar_y_repetir_categorias(restaurante):
    cliente, _, h = restaurante
    nueva = cliente.post("/v1/categorias", headers=h, json={"nombre": "Sopas"})
    assert nueva.status_code == 201
    cat = nueva.json()
    assert cat["orden"] == 4 and cat["cantidad_items"] == 0  # va al final
    assert cliente.post("/v1/categorias", headers=h,
                        json={"nombre": "sopas"}).status_code == 409
    r = cliente.patch(f"/v1/categorias/{cat['id']}", headers=h,
                      json={"version": cat["version"], "nombre": "Caldos"})
    assert r.status_code == 200 and r.json()["nombre"] == "Caldos"
    assert cliente.patch(f"/v1/categorias/{cat['id']}", headers=h,
                         json={"version": cat["version"], "nombre": "Otra"}).status_code == 409
    assert cliente.patch(f"/v1/categorias/{cat['id']}", headers=h,
                         json={"version": 2, "nombre": "Bebidas"}).status_code == 409


# ------------------------------------------------------------------ idempotencia

def test_la_misma_clave_devuelve_el_mismo_item(restaurante):
    cliente, _, h = restaurante
    cuerpo = {"nombre": "Pepián", "precio_venta": "45"}
    clave = {**h, "Idempotency-Key": "reintento-0001"}
    a = cliente.post("/v1/items", json=cuerpo, headers=clave)
    b = cliente.post("/v1/items", json=cuerpo, headers=clave)  # reintento tras perder la respuesta
    assert a.status_code == b.status_code == 201
    assert a.json()["id"] == b.json()["id"]
    assert cliente.get("/v1/items", headers=h).json()["total"] == 1


def test_la_misma_clave_con_otros_datos_da_422(restaurante):
    cliente, _, h = restaurante
    clave = {**h, "Idempotency-Key": "reintento-0002"}
    assert cliente.post("/v1/items", headers=clave,
                        json={"nombre": "Pepián", "precio_venta": "45"}).status_code == 201
    r = cliente.post("/v1/items", headers=clave, json={"nombre": "Pepián", "precio_venta": "50"})
    assert r.status_code == 422 and "clave" in r.json()["detail"]
    assert cliente.get("/v1/items", headers=h).json()["total"] == 1


# ------------------------------------------------------------------ aislamiento y permisos

def test_un_negocio_no_ve_ni_toca_lo_de_otro(restaurante, tienda):
    cliente = restaurante[0]
    h_mari, h_ana = restaurante[2], tienda[2]
    plato = agregar(cliente, h_mari, "Pepián", "45")
    cat_mari = cliente.get("/v1/categorias", headers=h_mari).json()[0]

    assert cliente.get("/v1/items", headers=h_ana).json() == {"total": 0, "items": []}
    assert cliente.get("/v1/categorias", headers=h_ana).json() == []
    assert cliente.get("/v1/items?buscar=pepi", headers=h_ana).json()["total"] == 0
    for r in (
        cliente.get(f"/v1/items/{plato['id']}", headers=h_ana),
        cliente.patch(f"/v1/items/{plato['id']}", headers=h_ana,
                      json={"version": 1, "nombre": "Robado"}),
        cliente.delete(f"/v1/items/{plato['id']}", headers=h_ana),
        cliente.patch(f"/v1/categorias/{cat_mari['id']}", headers=h_ana,
                      json={"version": 1, "nombre": "Robada"}),
        cliente.delete(f"/v1/categorias/{cat_mari['id']}", headers=h_ana),
    ):
        assert r.status_code == 404
        assert "Pepián" not in r.text and "Entradas" not in r.text
    # Ana no puede colgar su producto de la categoría de Mari
    r = cliente.post("/v1/items", headers=h_ana, json={
        "nombre": "Camisa", "precio_venta": "99", "categoria_id": cat_mari["id"]})
    assert r.status_code == 422
    # Y lo de Mari sigue intacto
    intacto = cliente.get(f"/v1/items/{plato['id']}", headers=h_mari).json()
    assert intacto["nombre"] == "Pepián" and intacto["version"] == 1


def test_sin_token_o_sin_negocio_no_se_entra(cliente_api):
    assert cliente_api.get("/v1/items").status_code == 401
    assert cliente_api.post("/v1/items", json={"nombre": "Ab", "precio_venta": "1"}
                            ).status_code == 401
    sesion = registrar_usuario(cliente_api, "Sin negocio")
    r = cliente_api.get("/v1/items", headers=con_token(sesion))
    assert r.status_code == 403


def test_un_cajero_puede_ver_pero_no_cambiar(restaurante, bd_migrada):
    cliente, _, h = restaurante
    item = agregar(cliente, h, "Pepián", "45")
    with bd_migrada.begin() as con:  # cambia el rol de Mari a cajero
        con.execute(sa.text("UPDATE core_membresia SET rol = 'cajero' WHERE rol = 'dueno' "
                            "AND negocio_id IN (SELECT negocio_id FROM (SELECT negocio_id "
                            "FROM core_membresia ORDER BY creado_en DESC LIMIT 1) t)"))
    assert cliente.get("/v1/items", headers=h).status_code == 200
    assert cliente.post("/v1/items", headers=h,
                        json={"nombre": "Otro", "precio_venta": "1"}).status_code == 403
    assert cliente.patch(f"/v1/items/{item['id']}", headers=h,
                         json={"version": 1, "nombre": "Cambiado"}).status_code == 403
    assert cliente.delete(f"/v1/items/{item['id']}", headers=h).status_code == 403
    assert cliente.post("/v1/categorias", headers=h, json={"nombre": "Nueva"}).status_code == 403
