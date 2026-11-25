"""Motor contable: plan por negocio, asientos de cada operación, IVA por régimen y lecturas."""

from decimal import Decimal

import pytest
import sqlalchemy as sa
from conftest import con_token, crear_negocio_api, registrar_usuario

# ------------------------------------------------------------------ ayudantes


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


def regimen(cliente, negocio, h, valor):
    return cliente.put(f"/v1/negocios/{negocio['id']}/impuestos", headers=h,
                       json={"regimen_iva": valor})


def item(cliente, h, nombre="Pepián", precio="45.00"):
    r = cliente.post("/v1/items", json={"nombre": nombre, "precio_venta": precio}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


def insumo(cliente, h, nombre="Pollo", unidad="LB", existencia=None, costo=None):
    cuerpo = {"nombre": nombre, "unidad_codigo": unidad}
    if existencia is not None:
        cuerpo |= {"existencia_inicial": str(existencia), "costo_total_inicial": str(costo)}
    r = cliente.post("/v1/insumos", json=cuerpo, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


def receta(cliente, h, plato, ins, cantidad):
    r = cliente.put(f"/v1/items/{plato['id']}/receta", headers=h,
                    json={"lineas": [{"insumo_id": ins["id"], "cantidad": str(cantidad)}]})
    assert r.status_code == 200, r.text


def vender(cliente, h, plato, cantidad=1, medio="efectivo"):
    r = cliente.post("/v1/ventas", headers=h, json={
        "lineas": [{"item_id": plato["id"], "cantidad": cantidad}], "medio_pago": medio})
    assert r.status_code == 201, r.text
    return r.json()


def categoria(cliente, h, nombre):
    return next(c for c in cliente.get("/v1/gastos/categorias", headers=h).json()
                if c["nombre"] == nombre)


def gastar(cliente, h, cat, monto, medio="efectivo", **extra):
    r = cliente.post("/v1/gastos", headers=h, json={
        "categoria_id": cat["id"], "monto": str(monto), "medio_pago": medio, **extra})
    assert r.status_code == 201, r.text
    return r.json()


def comprar(cliente, h, ins, cantidad, costo, medio="efectivo", **extra):
    r = cliente.post("/v1/compras", headers=h, json={
        "lineas": [{"insumo_id": ins["id"], "cantidad": str(cantidad), "costo_total": str(costo)}],
        "medio_pago": medio, **extra})
    assert r.status_code == 201, r.text
    return r.json()


def saldos(cliente, h) -> dict[str, Decimal]:
    """Saldo de cada cuenta de movimiento, por código."""
    r = cliente.get("/v1/cuentas", headers=h)
    assert r.status_code == 200, r.text
    return {c["codigo"]: Decimal(c["saldo"]) for c in r.json()["cuentas"]
            if c["acepta_movimientos"]}


def con_saldo(cliente, h) -> dict[str, Decimal]:
    return {k: v for k, v in saldos(cliente, h).items() if v != 0}


def resultados(cliente, h, mes=None):
    r = cliente.get("/v1/resultados", headers=h, params={"mes": mes} if mes else None)
    assert r.status_code == 200, r.text
    return r.json()


def libro(cliente, h):
    r = cliente.get("/v1/asientos", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def D(texto) -> Decimal:
    return Decimal(texto)


# ------------------------------------------------------------------ plan de cuentas


def test_cada_negocio_nace_con_su_plan_de_cuentas(restaurante, tienda):
    rest = saldos(restaurante[0], restaurante[2])
    en_linea = saldos(tienda[0], tienda[2])
    assert "4102" in rest and "4101" not in rest       # alimentos y bebidas
    assert "4101" in en_linea and "4102" not in en_linea  # mercadería
    assert set(rest.values()) == {D("0")}
    cuentas = restaurante[0].get("/v1/cuentas", headers=restaurante[2]).json()["cuentas"]
    caja = next(c for c in cuentas if c["rol"] == "CAJA")
    assert caja["nombre_simple"] == "Efectivo" and caja["acepta_movimientos"]
    grupo = next(c for c in cuentas if c["codigo"] == "1")
    assert grupo["acepta_movimientos"] is False


def test_un_negocio_anterior_a_la_contabilidad_recibe_su_libro_al_operar(restaurante, bd_migrada):
    cliente, negocio, h = restaurante
    with bd_migrada.begin() as con:  # simula un negocio creado antes de la migración 0013
        con.execute(sa.text("UPDATE cont_cuenta_contable SET padre_id = NULL "
                            "WHERE negocio_id = UUID_TO_BIN(:n)"), {"n": negocio["id"]})
        for tabla in ("cont_cuenta_contable", "cont_libro"):
            con.execute(sa.text(f"DELETE FROM {tabla} WHERE negocio_id = UUID_TO_BIN(:n)"),
                        {"n": negocio["id"]})
    vender(cliente, h, item(cliente, h))
    assert con_saldo(cliente, h) == {"1101": D("45.00"), "4102": D("45.00")}


# ------------------------------------------------------------------ ventas


def test_una_venta_en_efectivo_sin_regimen(restaurante):
    cliente, _, h = restaurante
    vender(cliente, h, item(cliente, h), cantidad=2)
    assert con_saldo(cliente, h) == {"1101": D("90.00"), "4102": D("90.00")}
    mes = resultados(cliente, h)
    assert mes["vendiste"] == "90.00" and mes["te_queda"] == "90.00"
    assert mes["sin_iva"] is False


@pytest.mark.parametrize("medio", ["tarjeta", "transferencia"])
def test_tarjeta_y_transferencia_van_al_banco(restaurante, medio):
    cliente, _, h = restaurante
    vender(cliente, h, item(cliente, h), medio=medio)
    assert con_saldo(cliente, h) == {"1103": D("45.00"), "4102": D("45.00")}


def test_la_venta_con_receta_registra_su_costo(restaurante):
    cliente, _, h = restaurante
    pollo = insumo(cliente, h, existencia=10, costo="150.00")  # Q15 la libra
    pepian = item(cliente, h)
    receta(cliente, h, pepian, pollo, "0.5")
    vender(cliente, h, pepian, cantidad=2)  # 1 lb de pollo = Q15
    assert con_saldo(cliente, h) == {
        "1101": D("90.00"), "1108": D("135.00"), "3101": D("150.00"),
        "4102": D("90.00"), "5101": D("15.00"),
    }
    mes = resultados(cliente, h)
    assert mes["costo_de_lo_vendido"] == "15.00" and mes["te_queda"] == "75.00"


def test_la_mercaderia_sale_de_su_propia_cuenta(tienda):
    cliente, _, h = tienda
    gaseosa = item(cliente, h, "Gaseosa", "10.00")
    r = cliente.put(f"/v1/items/{gaseosa['id']}/mercaderia", headers=h, json={"activa": True})
    assert r.status_code == 200, r.text
    ins = cliente.get(f"/v1/items/{gaseosa['id']}/mercaderia", headers=h).json()["insumo"]
    comprar(cliente, h, ins, 12, "72.00")
    vender(cliente, h, gaseosa, cantidad=3)
    assert con_saldo(cliente, h) == {
        "1101": D("-42.00"), "1107": D("54.00"), "4101": D("30.00"), "5101": D("18.00"),
    }


def test_anular_una_venta_la_revierte_con_su_costo(restaurante):
    cliente, _, h = restaurante
    pollo = insumo(cliente, h, existencia=10, costo="150.00")
    pepian = item(cliente, h)
    receta(cliente, h, pepian, pollo, "1")
    venta = vender(cliente, h, pepian)
    r = cliente.post(f"/v1/ventas/{venta['id']}/anular", headers=h, json={"motivo": "Error"})
    assert r.status_code == 200, r.text
    assert con_saldo(cliente, h) == {"1108": D("150.00"), "3101": D("150.00")}
    asientos = libro(cliente, h)["asientos"]
    reverso = asientos[-1]
    original = next(a for a in asientos if a["id"] == reverso["reverso_de_asiento_id"])
    assert reverso["tipo_evento"] == "REVERSO" and reverso["fecha"] == original["fecha"]
    assert {(ln["cuenta_codigo"], ln["debe"], ln["haber"]) for ln in reverso["lineas"]} == {
        (ln["cuenta_codigo"], ln["haber"], ln["debe"]) for ln in original["lineas"]}
    assert resultados(cliente, h)["vendiste"] == "0.00"


# ------------------------------------------------------------------ IVA según el régimen


def test_el_regimen_se_fija_y_se_lee(restaurante):
    cliente, negocio, h = restaurante
    assert cliente.get(f"/v1/negocios/{negocio['id']}", headers=h).json()["regimen_iva"] == "no_se"
    assert regimen(cliente, negocio, h, "general").status_code == 204
    leido = cliente.get(f"/v1/negocios/{negocio['id']}", headers=h).json()
    assert leido["regimen_iva"] == "general" and leido["da_factura"] == "si"
    assert regimen(cliente, negocio, h, "pequeno").status_code == 204
    assert cliente.get(f"/v1/negocios/{negocio['id']}",
                       headers=h).json()["regimen_iva"] == "pequeno"
    assert regimen(cliente, negocio, h, "no_se").status_code == 204
    assert cliente.get(f"/v1/negocios/{negocio['id']}", headers=h).json()["regimen_iva"] == "no_se"
    assert regimen(cliente, negocio, h, "otro").status_code == 422


def test_el_regimen_general_separa_el_iva_de_la_venta(restaurante):
    cliente, negocio, h = restaurante
    regimen(cliente, negocio, h, "general")
    vender(cliente, h, item(cliente, h, precio="112.00"))
    assert con_saldo(cliente, h) == {"1101": D("112.00"), "2103": D("12.00"), "4102": D("100.00")}
    mes = resultados(cliente, h)
    assert mes["vendiste"] == "100.00" and mes["sin_iva"] is True


def test_el_redondeo_del_iva_siempre_cuadra(restaurante):
    cliente, negocio, h = restaurante
    regimen(cliente, negocio, h, "general")
    vender(cliente, h, item(cliente, h, precio="45.00"))  # 45 / 1.12 = 40.178...
    assert con_saldo(cliente, h) == {"1101": D("45.00"), "2103": D("4.82"), "4102": D("40.18")}


def test_el_pequeno_contribuyente_no_separa_iva(restaurante):
    cliente, negocio, h = restaurante
    regimen(cliente, negocio, h, "pequeno")
    vender(cliente, h, item(cliente, h, precio="112.00"))
    assert con_saldo(cliente, h) == {"1101": D("112.00"), "4102": D("112.00")}


def test_cambiar_de_regimen_no_toca_lo_ya_registrado(restaurante):
    cliente, negocio, h = restaurante
    plato = item(cliente, h, precio="112.00")
    vender(cliente, h, plato)
    regimen(cliente, negocio, h, "general")
    vender(cliente, h, plato)
    assert con_saldo(cliente, h) == {"1101": D("224.00"), "2103": D("12.00"), "4102": D("212.00")}


def test_solo_el_dueno_cambia_el_regimen_y_solo_el_suyo(restaurante, tienda, bd_migrada):
    cliente, negocio, h = restaurante
    assert regimen(cliente, tienda[1], h, "general").status_code == 404
    with bd_migrada.begin() as con:
        con.execute(sa.text("UPDATE core_membresia SET rol = 'administrador' "
                            "WHERE negocio_id = UUID_TO_BIN(:n)"), {"n": negocio["id"]})
    assert regimen(cliente, negocio, h, "general").status_code == 403


# ------------------------------------------------------------------ gastos


def test_un_gasto_va_a_la_cuenta_de_su_categoria(restaurante):
    cliente, _, h = restaurante
    gastar(cliente, h, categoria(cliente, h, "Renta"), "2000.00", medio="transferencia")
    assert con_saldo(cliente, h) == {"1103": D("-2000.00"), "6101": D("2000.00")}
    mes = resultados(cliente, h)
    assert mes["gastaste"] == "2000.00" and mes["te_queda"] == "-2000.00"


def test_una_categoria_sin_rol_va_a_gastos_varios(restaurante):
    cliente, _, h = restaurante
    nueva = cliente.post("/v1/gastos/categorias", headers=h, json={"nombre": "Gas"}).json()
    gastar(cliente, h, nueva, "50.00")
    assert con_saldo(cliente, h) == {"1101": D("-50.00"), "6190": D("50.00")}


def test_corregir_un_gasto_revierte_y_registra_de_nuevo(restaurante):
    cliente, _, h = restaurante
    gasto = gastar(cliente, h, categoria(cliente, h, "Renta"), "2000.00")
    r = cliente.patch(f"/v1/gastos/{gasto['id']}", headers=h,
                      json={"version": gasto["version"], "monto": "2500.00",
                            "medio_pago": "tarjeta"})
    assert r.status_code == 200, r.text
    assert con_saldo(cliente, h) == {"1103": D("-2500.00"), "6101": D("2500.00")}
    tipos = [a["tipo_evento"] for a in libro(cliente, h)["asientos"]]
    assert tipos == ["GASTO", "REVERSO", "GASTO"]
    # Cambiar solo la nota no toca la contabilidad.
    r = cliente.patch(f"/v1/gastos/{gasto['id']}", headers=h,
                      json={"version": r.json()["version"], "descripcion": "Noviembre"})
    assert r.status_code == 200
    assert len(libro(cliente, h)["asientos"]) == 3


def test_archivar_un_gasto_lo_revierte(restaurante):
    cliente, _, h = restaurante
    gasto = gastar(cliente, h, categoria(cliente, h, "Renta"), "2000.00")
    assert cliente.delete(f"/v1/gastos/{gasto['id']}", headers=h).status_code == 204
    assert con_saldo(cliente, h) == {}
    assert resultados(cliente, h)["gastaste"] == "0.00"


def test_el_gasto_con_factura_separa_iva_solo_en_el_regimen_general(restaurante):
    cliente, negocio, h = restaurante
    renta = categoria(cliente, h, "Renta")
    gasto = gastar(cliente, h, renta, "2240.00", con_factura=True)
    assert gasto["con_factura"] is True
    assert con_saldo(cliente, h) == {"1101": D("-2240.00"), "6101": D("2240.00")}
    regimen(cliente, negocio, h, "general")
    gastar(cliente, h, renta, "2240.00", con_factura=True)
    gastar(cliente, h, renta, "100.00")  # sin factura: todo es gasto
    assert con_saldo(cliente, h) == {
        "1101": D("-4580.00"), "1110": D("240.00"), "6101": D("4340.00")}


# ------------------------------------------------------------------ compras


def test_una_compra_sube_el_inventario_y_sale_del_pago(restaurante):
    cliente, _, h = restaurante
    pollo = insumo(cliente, h)
    comprar(cliente, h, pollo, 10, "150.00", medio="tarjeta")
    assert con_saldo(cliente, h) == {"1103": D("-150.00"), "1108": D("150.00")}
    assert resultados(cliente, h)["gastaste"] == "0.00"  # comprar no es gastar


def test_la_compra_con_factura_en_regimen_general_entra_sin_iva(restaurante):
    cliente, negocio, h = restaurante
    regimen(cliente, negocio, h, "general")
    pollo = insumo(cliente, h)
    comprar(cliente, h, pollo, 10, "168.00", numero_factura="A-1")
    assert con_saldo(cliente, h) == {"1101": D("-168.00"), "1108": D("150.00"),
                                     "1110": D("18.00")}
    leido = cliente.get(f"/v1/insumos/{pollo['id']}", headers=h).json()
    assert leido["costo_unitario"] == "15.00" and leido["valor"] == "150.00"
    # Sin número de factura no hay crédito fiscal: todo es costo.
    comprar(cliente, h, pollo, 10, "168.00")
    assert con_saldo(cliente, h)["1108"] == D("318.00")


def test_anular_una_compra_la_revierte(restaurante):
    cliente, _, h = restaurante
    pollo = insumo(cliente, h)
    compra = comprar(cliente, h, pollo, 10, "150.00")
    r = cliente.post(f"/v1/compras/{compra['id']}/anular", headers=h, json={"motivo": "Error"})
    assert r.status_code == 200, r.text
    assert con_saldo(cliente, h) == {}


# ------------------------------------------------------------------ inventario a mano


def test_los_movimientos_a_mano_tienen_su_asiento(restaurante):
    cliente, _, h = restaurante
    pollo = insumo(cliente, h, existencia=10, costo="150.00")  # aporte del dueño
    url = f"/v1/insumos/{pollo['id']}/movimientos"
    for cuerpo in ({"tipo": "entrada", "cantidad": "2", "costo_total": "30.00"},
                   {"tipo": "merma", "cantidad": "1"},
                   {"tipo": "ajuste", "cantidad": "9"},
                   {"tipo": "ajuste", "cantidad": "10"}):
        assert cliente.post(url, headers=h, json=cuerpo).status_code == 201
    # 10 + 2 (Q30, caja) - 1 merma - 2 faltante + 1 sobrante = 10 lb a Q15
    assert con_saldo(cliente, h) == {
        "1101": D("-30.00"), "1108": D("150.00"), "3101": D("150.00"),
        "4201": D("15.00"), "5102": D("45.00")}
    mes = resultados(cliente, h)
    assert mes["se_perdio"] == "45.00" and mes["otros_ingresos"] == "15.00"
    assert mes["te_queda"] == "-30.00"


# ------------------------------------------------------------------ libros y permisos


def test_el_libro_diario_cuadra_y_numera_en_orden(restaurante):
    cliente, _, h = restaurante
    vender(cliente, h, item(cliente, h))
    gastar(cliente, h, categoria(cliente, h, "Renta"), "100.00")
    diario = libro(cliente, h)
    assert diario["total_debe"] == diario["total_haber"] == "145.00"
    assert [a["numero"] for a in diario["asientos"]] == [1, 2]
    for asiento in diario["asientos"]:
        assert sum(D(ln["debe"]) for ln in asiento["lineas"]) == sum(
            D(ln["haber"]) for ln in asiento["lineas"])


def test_un_mes_sin_movimientos_y_un_mes_invalido(restaurante):
    cliente, _, h = restaurante
    assert resultados(cliente, h, "2020-01")["te_queda"] == "0.00"
    assert cliente.get("/v1/resultados", headers=h, params={"mes": "2026-13"}).status_code == 422
    assert cliente.get("/v1/asientos", headers=h, params={"mes": "nov"}).status_code == 422


def test_cada_negocio_ve_solo_sus_libros(restaurante, tienda):
    cliente, _, h = restaurante
    vender(cliente, h, item(cliente, h))
    otro, _, h_otro = tienda
    assert libro(otro, h_otro)["asientos"] == []
    assert con_saldo(otro, h_otro) == {}
    assert resultados(otro, h_otro)["vendiste"] == "0.00"


@pytest.mark.parametrize("ruta", ["/v1/resultados", "/v1/asientos", "/v1/cuentas"])
def test_el_cajero_no_ve_los_libros(restaurante, bd_migrada, ruta):
    cliente, negocio, h = restaurante
    with bd_migrada.begin() as con:
        con.execute(sa.text("UPDATE core_membresia SET rol = 'cajero' "
                            "WHERE negocio_id = UUID_TO_BIN(:n)"), {"n": negocio["id"]})
    assert cliente.get(ruta, headers=h).status_code == 403


def test_todos_los_asientos_de_la_base_cuadran(bd_migrada):
    """Invariante global: después de todas las pruebas anteriores, ningún asiento descuadra."""
    with bd_migrada.connect() as con:
        descuadrados = con.execute(sa.text(
            "SELECT asiento_id FROM cont_asiento_linea GROUP BY asiento_id "
            "HAVING SUM(debe) <> SUM(haber)")).all()
        vacios = con.execute(sa.text(
            "SELECT a.id FROM cont_asiento a LEFT JOIN cont_asiento_linea l "
            "ON l.asiento_id = a.id WHERE l.id IS NULL")).all()
    assert descuadrados == [] and vacios == []


# ------------------------------------------------------------------ datos para la meta del mes


def test_resultados_entrega_gastos_fijos_y_margen_objetivo(restaurante):
    cliente, _, h = restaurante
    mes = resultados(cliente, h)
    assert mes["gastos_fijos"] == "0.00" and mes["margen_objetivo"] == "0.3500"
    gastar(cliente, h, categoria(cliente, h, "Renta"), "2000.00")          # fijo
    gastar(cliente, h, categoria(cliente, h, "Desechables"), "50.00")      # variable
    assert resultados(cliente, h)["gastos_fijos"] == "2000.00"


def test_sin_fijos_este_mes_usa_los_del_mes_anterior(restaurante):
    from datetime import date, timedelta

    cliente, _, h = restaurante
    hoy = date.today()
    del_mes_pasado = (hoy.replace(day=1) - timedelta(days=1)).isoformat()
    gastar(cliente, h, categoria(cliente, h, "Renta"), "1800.00", fecha=del_mes_pasado)
    assert resultados(cliente, h)["gastos_fijos"] == "1800.00"
    gastar(cliente, h, categoria(cliente, h, "Sueldos"), "500.00")  # ya hay fijos este mes
    assert resultados(cliente, h)["gastos_fijos"] == "500.00"
