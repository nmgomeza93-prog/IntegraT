"""Gastos y categorías de gasto: /v1/gastos."""

import threading
import uuid
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


def categoria(cliente, h, nombre):
    cats = cliente.get("/v1/gastos/categorias", headers=h).json()
    return next(c for c in cats if c["nombre"] == nombre)


def anotar(cliente, h, monto="100.00", cat="Renta", medio="efectivo", **extra):
    cuerpo = {"monto": monto, "categoria_id": categoria(cliente, h, cat)["id"],
              "medio_pago": medio, **extra}
    r = cliente.post("/v1/gastos", json=cuerpo, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


def poner_rol(bd, rol):
    with bd.begin() as con:
        con.execute(sa.text(
            "UPDATE core_membresia SET rol = :r WHERE negocio_id IN (SELECT negocio_id FROM "
            "(SELECT negocio_id FROM core_membresia ORDER BY creado_en DESC LIMIT 1) t)"),
            {"r": rol})


# ------------------------------------------------------------------ categorías de ejemplo

def test_cada_tipo_de_negocio_nace_con_sus_categorias_de_gasto(restaurante, tienda):
    rest = restaurante[0].get("/v1/gastos/categorias", headers=restaurante[2]).json()
    assert [c["nombre"] for c in rest] == [
        "Renta", "Sueldos", "Luz, agua y gas", "Desechables", "Teléfono e internet",
        "Mantenimiento"]
    assert {c["nombre"]: c["es_fijo"] for c in rest}["Renta"] is True
    assert {c["nombre"]: c["es_fijo"] for c in rest}["Desechables"] is False
    en_linea = tienda[0].get("/v1/gastos/categorias", headers=tienda[2]).json()
    assert [c["nombre"] for c in en_linea][:3] == ["Publicidad", "Envíos", "Empaques"]


def test_crear_renombrar_y_repetir_categorias(restaurante):
    cliente, _, h = restaurante
    r = cliente.post("/v1/gastos/categorias", headers=h, json={"nombre": "Gas", "es_fijo": False})
    assert r.status_code == 201
    cat = r.json()
    assert cat["orden"] == 6 and cat["es_fijo"] is False  # va al final
    assert cliente.post("/v1/gastos/categorias", headers=h,
                        json={"nombre": "gas"}).status_code == 409
    nuevo = cliente.patch(f"/v1/gastos/categorias/{cat['id']}", headers=h,
                          json={"version": 1, "nombre": "Gas propano", "es_fijo": True})
    assert nuevo.status_code == 200 and nuevo.json()["nombre"] == "Gas propano"
    assert nuevo.json()["es_fijo"] is True and nuevo.json()["version"] == 2
    assert cliente.patch(f"/v1/gastos/categorias/{cat['id']}", headers=h,
                         json={"version": 1, "nombre": "Otra"}).status_code == 409
    assert cliente.patch(f"/v1/gastos/categorias/{cat['id']}", headers=h,
                         json={"version": 2, "nombre": "Renta"}).status_code == 409  # ya existe


def test_archivar_una_categoria_no_toca_sus_gastos(restaurante):
    cliente, _, h = restaurante
    gasto = anotar(cliente, h, "250", cat="Mantenimiento")
    cat = categoria(cliente, h, "Mantenimiento")
    assert cliente.delete(f"/v1/gastos/categorias/{cat['id']}", headers=h).status_code == 204
    assert cat["id"] not in [c["id"] for c in cliente.get("/v1/gastos/categorias",
                                                          headers=h).json()]
    # El gasto sigue ahí con el nombre que tenía...
    visto = cliente.get(f"/v1/gastos/{gasto['id']}", headers=h).json()
    assert visto["categoria_nombre"] == "Mantenimiento"
    assert cliente.get("/v1/gastos", headers=h).json()["resumen"]["total"] == "250.00"
    # ...pero la categoría ya no se ofrece para gastos nuevos
    r = cliente.post("/v1/gastos", headers=h, json={
        "monto": "10", "categoria_id": cat["id"], "medio_pago": "efectivo"})
    assert r.status_code == 422 and "categoría" in r.json()["detail"]


# ------------------------------------------------------------------ anotar

def test_anotar_un_gasto_usa_hoy_y_hereda_fijo_o_variable(restaurante):
    cliente, _, h = restaurante
    renta = anotar(cliente, h, "3500.5", cat="Renta", medio="transferencia")
    assert renta["monto"] == "3500.50"  # dinero como texto con 2 decimales
    assert renta["fecha"] == hoy().isoformat()
    assert renta["es_fijo"] is True and renta["categoria_nombre"] == "Renta"
    assert renta["medio_pago"] == "transferencia" and renta["descripcion"] is None
    assert renta["version"] == 1
    desechables = anotar(cliente, h, "45", cat="Desechables", descripcion="  Bolsas  ")
    assert desechables["es_fijo"] is False and desechables["descripcion"] == "Bolsas"


@pytest.mark.parametrize("cambio", [
    {"monto": "0"}, {"monto": "-5"}, {"monto": "10.999"}, {"monto": "mucho"},
    {"medio_pago": "cheque"}, {"descripcion": "x" * 201},
])
def test_datos_invalidos_dan_422(restaurante, cambio):
    cliente, _, h = restaurante
    cuerpo = {"monto": "10", "categoria_id": categoria(cliente, h, "Renta")["id"],
              "medio_pago": "efectivo", **cambio}
    assert cliente.post("/v1/gastos", json=cuerpo, headers=h).status_code == 422


def test_la_categoria_es_obligatoria_y_debe_existir(restaurante):
    cliente, _, h = restaurante
    assert cliente.post("/v1/gastos", headers=h,
                        json={"monto": "10", "medio_pago": "efectivo"}).status_code == 422
    r = cliente.post("/v1/gastos", headers=h, json={
        "monto": "10", "categoria_id": str(uuid.uuid4()), "medio_pago": "efectivo"})
    assert r.status_code == 422 and "categoría" in r.json()["detail"]


def test_la_fecha_puede_ser_pasada_pero_no_futura(restaurante):
    cliente, _, h = restaurante
    ayer = (hoy() - timedelta(days=1)).isoformat()
    assert anotar(cliente, h, "10", fecha=ayer)["fecha"] == ayer
    futura = (hoy() + timedelta(days=2)).isoformat()
    r = cliente.post("/v1/gastos", headers=h, json={
        "monto": "10", "categoria_id": categoria(cliente, h, "Renta")["id"],
        "medio_pago": "efectivo", "fecha": futura})
    assert r.status_code == 422 and "fecha" in r.json()["detail"]


# ------------------------------------------------------------------ el mes

def test_el_resumen_del_mes_por_categoria_con_porcentajes(restaurante):
    cliente, _, h = restaurante
    anotar(cliente, h, "600", cat="Renta")
    anotar(cliente, h, "300", cat="Luz, agua y gas")
    anotar(cliente, h, "60", cat="Desechables")
    anotar(cliente, h, "40", cat="Desechables")
    mes = cliente.get("/v1/gastos", headers=h).json()
    assert mes["mes"] == hoy().strftime("%Y-%m")
    r = mes["resumen"]
    assert (r["cantidad"], r["total"]) == (4, "1000.00")
    assert (r["total_fijos"], r["total_variables"]) == ("600.00", "400.00")
    assert [(c["nombre"], c["total"], c["porcentaje"]) for c in r["por_categoria"]] == [
        ("Renta", "600.00", 60), ("Luz, agua y gas", "300.00", 30), ("Desechables", "100.00", 10)]
    assert len(mes["gastos"]) == 4


def test_cada_mes_aparte_y_mes_invalido(restaurante):
    cliente, _, h = restaurante
    ayer = hoy() - timedelta(days=45)
    anotar(cliente, h, "100", fecha=ayer.isoformat())
    anotar(cliente, h, "7")
    este = cliente.get("/v1/gastos", headers=h).json()["resumen"]
    assert (este["cantidad"], este["total"]) == (1, "7.00")
    pasado = cliente.get(f"/v1/gastos?mes={ayer.strftime('%Y-%m')}", headers=h).json()
    assert pasado["resumen"]["total"] == "100.00" and pasado["mes"] == ayer.strftime("%Y-%m")
    vacio = cliente.get("/v1/gastos?mes=2020-01", headers=h).json()
    assert vacio["gastos"] == [] and vacio["resumen"]["total"] == "0.00"
    assert vacio["resumen"]["por_categoria"] == []
    for malo in ("2026-13", "2026-1", "noviembre", "2026/11", "26-11"):
        assert cliente.get(f"/v1/gastos?mes={malo}", headers=h).status_code == 422, malo


def test_los_gastos_salen_del_mas_reciente_al_mas_antiguo(restaurante):
    cliente, _, h = restaurante
    uno = (hoy().replace(day=1)).isoformat()
    anotar(cliente, h, "1", fecha=uno)
    anotar(cliente, h, "2")
    montos = [g["monto"] for g in cliente.get("/v1/gastos", headers=h).json()["gastos"]]
    assert montos == ["2.00", "1.00"] or hoy().day == 1  # si hoy es día 1, ambos son de hoy


# ------------------------------------------------------------------ corregir y archivar

def test_corregir_monto_categoria_fecha_y_nota(restaurante):
    cliente, _, h = restaurante
    g = anotar(cliente, h, "100", cat="Desechables", descripcion="Bolsas")
    sueldos = categoria(cliente, h, "Sueldos")
    ayer = (hoy() - timedelta(days=1)).isoformat()
    r = cliente.patch(f"/v1/gastos/{g['id']}", headers=h, json={
        "version": 1, "monto": "125.75", "categoria_id": sueldos["id"], "fecha": ayer,
        "medio_pago": "tarjeta", "descripcion": None})
    assert r.status_code == 200, r.text
    n = r.json()
    assert (n["monto"], n["categoria_nombre"], n["fecha"], n["medio_pago"], n["descripcion"]) == (
        "125.75", "Sueldos", ayer, "tarjeta", None)
    assert n["es_fijo"] is True and n["version"] == 2  # al cambiar a una categoría fija, es fijo


def test_corregir_solo_un_dato_no_toca_los_demas(restaurante):
    cliente, _, h = restaurante
    g = anotar(cliente, h, "100", cat="Renta", descripcion="Noviembre")
    n = cliente.patch(f"/v1/gastos/{g['id']}", headers=h,
                      json={"version": 1, "monto": "110"}).json()
    assert n["monto"] == "110.00" and n["descripcion"] == "Noviembre"
    assert n["categoria_nombre"] == "Renta" and n["fecha"] == g["fecha"]


def test_corregir_con_version_vieja_o_sin_version(restaurante):
    cliente, _, h = restaurante
    g = anotar(cliente, h)
    assert cliente.patch(f"/v1/gastos/{g['id']}", headers=h,
                         json={"version": 1, "monto": "1"}).status_code == 200
    r = cliente.patch(f"/v1/gastos/{g['id']}", headers=h, json={"version": 1, "monto": "99"})
    assert r.status_code == 409 and "Alguien más" in r.json()["detail"]
    assert cliente.patch(f"/v1/gastos/{g['id']}", headers=h,
                         json={"monto": "5"}).status_code == 422
    assert cliente.get(f"/v1/gastos/{g['id']}", headers=h).json()["monto"] == "1.00"


def test_no_se_corrige_a_una_fecha_futura_ni_a_una_categoria_inexistente(restaurante):
    cliente, _, h = restaurante
    g = anotar(cliente, h)
    futura = (hoy() + timedelta(days=3)).isoformat()
    assert cliente.patch(f"/v1/gastos/{g['id']}", headers=h,
                         json={"version": 1, "fecha": futura}).status_code == 422
    assert cliente.patch(f"/v1/gastos/{g['id']}", headers=h, json={
        "version": 1, "categoria_id": str(uuid.uuid4())}).status_code == 422


def test_archivar_oculta_el_gasto_pero_no_lo_borra(restaurante, bd_migrada):
    cliente, _, h = restaurante
    g = anotar(cliente, h, "80")
    assert cliente.delete(f"/v1/gastos/{g['id']}", headers=h).status_code == 204
    assert cliente.get(f"/v1/gastos/{g['id']}", headers=h).status_code == 404
    mes = cliente.get("/v1/gastos", headers=h).json()
    assert mes["gastos"] == [] and mes["resumen"]["total"] == "0.00"
    assert cliente.delete(f"/v1/gastos/{g['id']}", headers=h).status_code == 404
    assert cliente.patch(f"/v1/gastos/{g['id']}", headers=h,
                         json={"version": 1, "monto": "1"}).status_code == 404
    with bd_migrada.connect() as con:
        archivados = con.execute(
            sa.text("SELECT COUNT(*) FROM ops_gasto WHERE eliminado_en IS NOT NULL")).scalar()
    assert archivados >= 1


# ------------------------------------------------------------------ idempotencia

def test_la_misma_clave_no_anota_dos_veces(restaurante):
    cliente, _, h = restaurante
    cuerpo = {"monto": "50", "categoria_id": categoria(cliente, h, "Renta")["id"],
              "medio_pago": "efectivo"}
    clave = {**h, "Idempotency-Key": "gasto-reintento-1"}
    a = cliente.post("/v1/gastos", json=cuerpo, headers=clave)
    b = cliente.post("/v1/gastos", json=cuerpo, headers=clave)
    assert a.status_code == b.status_code == 201 and a.json()["id"] == b.json()["id"]
    assert cliente.get("/v1/gastos", headers=h).json()["resumen"]["cantidad"] == 1
    otro = cliente.post("/v1/gastos", json={**cuerpo, "monto": "60"}, headers=clave)
    assert otro.status_code == 422 and "clave" in otro.json()["detail"]


def test_el_doble_toque_simultaneo_anota_una_vez(restaurante):
    cliente, _, h = restaurante
    cuerpo = {"monto": "50", "categoria_id": categoria(cliente, h, "Renta")["id"],
              "medio_pago": "efectivo"}
    resultados = []

    def anotar_una():
        c = cliente_desde(ip_nueva())
        resultados.append(c.post("/v1/gastos", json=cuerpo,
                                 headers={**h, "Idempotency-Key": "gasto-doble-01"}))

    hilos = [threading.Thread(target=anotar_una) for _ in range(4)]
    for t in hilos:
        t.start()
    for t in hilos:
        t.join()
    assert all(r.status_code == 201 for r in resultados), [r.text for r in resultados]
    assert len({r.json()["id"] for r in resultados}) == 1
    assert cliente.get("/v1/gastos", headers=h).json()["resumen"]["cantidad"] == 1


# ------------------------------------------------------------------ aislamiento y permisos

def test_un_negocio_no_ve_ni_toca_los_gastos_de_otro(restaurante, tienda):
    cliente = restaurante[0]
    h_mari, h_ana = restaurante[2], tienda[2]
    g = anotar(cliente, h_mari, "999", cat="Sueldos")
    cat_mari = categoria(cliente, h_mari, "Sueldos")

    assert cliente.get("/v1/gastos", headers=h_ana).json()["gastos"] == []
    assert cat_mari["id"] not in [c["id"] for c in
                                  cliente.get("/v1/gastos/categorias", headers=h_ana).json()]
    for r in (
        cliente.get(f"/v1/gastos/{g['id']}", headers=h_ana),
        cliente.patch(f"/v1/gastos/{g['id']}", headers=h_ana, json={"version": 1, "monto": "1"}),
        cliente.delete(f"/v1/gastos/{g['id']}", headers=h_ana),
        cliente.patch(f"/v1/gastos/categorias/{cat_mari['id']}", headers=h_ana,
                      json={"version": 1, "nombre": "Robada"}),
        cliente.delete(f"/v1/gastos/categorias/{cat_mari['id']}", headers=h_ana),
    ):
        assert r.status_code == 404 and "Sueldos" not in r.text
    r = cliente.post("/v1/gastos", headers=h_ana, json={
        "monto": "5", "categoria_id": cat_mari["id"], "medio_pago": "efectivo"})
    assert r.status_code == 422
    assert cliente.get(f"/v1/gastos/{g['id']}", headers=h_mari).json()["monto"] == "999.00"


def test_sin_token_o_sin_negocio_no_se_entra(cliente_api):
    assert cliente_api.get("/v1/gastos").status_code == 401
    assert cliente_api.post("/v1/gastos", json={}).status_code == 401
    sesion = registrar_usuario(cliente_api, "Sin negocio")
    assert cliente_api.get("/v1/gastos", headers=con_token(sesion)).status_code == 403


def test_un_cajero_no_ve_ni_toca_los_gastos(restaurante, bd_migrada):
    cliente, _, h = restaurante
    g = anotar(cliente, h)
    poner_rol(bd_migrada, "cajero")
    for r in (
        cliente.get("/v1/gastos", headers=h),
        cliente.get(f"/v1/gastos/{g['id']}", headers=h),
        cliente.get("/v1/gastos/categorias", headers=h),
        cliente.post("/v1/gastos", headers=h, json={
            "monto": "1", "categoria_id": g["categoria_id"], "medio_pago": "efectivo"}),
        cliente.delete(f"/v1/gastos/{g['id']}", headers=h),
    ):
        assert r.status_code == 403


def test_un_contador_ve_pero_no_cambia(restaurante, bd_migrada):
    cliente, _, h = restaurante
    g = anotar(cliente, h)
    poner_rol(bd_migrada, "contador")
    assert cliente.get("/v1/gastos", headers=h).status_code == 200
    assert cliente.get(f"/v1/gastos/{g['id']}", headers=h).status_code == 200
    assert cliente.get("/v1/gastos/categorias", headers=h).status_code == 200
    cuerpo = {"monto": "1", "categoria_id": g["categoria_id"], "medio_pago": "efectivo"}
    assert cliente.post("/v1/gastos", headers=h, json=cuerpo).status_code == 403
    assert cliente.patch(f"/v1/gastos/{g['id']}", headers=h,
                         json={"version": 1, "monto": "2"}).status_code == 403
    assert cliente.delete(f"/v1/gastos/{g['id']}", headers=h).status_code == 403
    assert cliente.post("/v1/gastos/categorias", headers=h,
                        json={"nombre": "Nueva"}).status_code == 403


# ------------------------------------------------------------------ checklist

def test_anotar_un_gasto_fijo_marca_el_paso_de_la_tienda(tienda):
    cliente, negocio, h = tienda

    def hecho():
        n = cliente.get(f"/v1/negocios/{negocio['id']}", headers=h).json()
        return {p["clave"]: p["hecho"] for p in n["primeros_pasos"]}["gastos_fijos"]

    assert hecho() is False
    anotar(cliente, h, "50", cat="Publicidad")  # variable: no cuenta
    assert hecho() is False
    g = anotar(cliente, h, "300", cat="Renta")  # fijo: sí
    assert hecho() is True
    cliente.delete(f"/v1/gastos/{g['id']}", headers=h)
    assert hecho() is False  # archivado, ya no cuenta


# ------------------------------------------------------------------ negocios previos a los gastos

def _quitar_categorias(bd, tabla):
    """Deja al negocio más reciente como los creados antes de este módulo: sin categorías."""
    with bd.begin() as con:
        con.execute(sa.text(f"DELETE FROM {tabla} WHERE negocio_id IN (SELECT id FROM "
                            "(SELECT id FROM core_negocio ORDER BY creado_en DESC LIMIT 1) t)"))


def test_un_negocio_anterior_recibe_sus_categorias_la_primera_vez(restaurante, bd_migrada):
    cliente, _, h = restaurante
    _quitar_categorias(bd_migrada, "ops_categoria_gasto")
    nombres = [c["nombre"] for c in cliente.get("/v1/gastos/categorias", headers=h).json()]
    assert nombres[:2] == ["Renta", "Sueldos"] and len(nombres) == 6
    # La segunda vez no las repite
    assert len(cliente.get("/v1/gastos/categorias", headers=h).json()) == 6


def test_las_categorias_de_ejemplo_no_se_siembran_dos_veces_a_la_vez(restaurante, bd_migrada):
    cliente, _, h = restaurante
    _quitar_categorias(bd_migrada, "ops_categoria_gasto")
    resultados = []

    def pedir():
        resultados.append(cliente_desde(ip_nueva()).get("/v1/gastos/categorias", headers=h))

    hilos = [threading.Thread(target=pedir) for _ in range(4)]
    for t in hilos:
        t.start()
    for t in hilos:
        t.join()
    assert all(r.status_code == 200 for r in resultados), [r.text for r in resultados]
    assert len(cliente.get("/v1/gastos/categorias", headers=h).json()) == 6


def test_quien_archivo_todas_sus_categorias_no_las_recibe_de_nuevo(restaurante):
    cliente, _, h = restaurante
    for c in cliente.get("/v1/gastos/categorias", headers=h).json():
        assert cliente.delete(f"/v1/gastos/categorias/{c['id']}", headers=h).status_code == 204
    assert cliente.get("/v1/gastos/categorias", headers=h).json() == []
