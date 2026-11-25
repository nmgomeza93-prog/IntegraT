"""Caja del día (/v1/caja) y dinero del dueño (/v1/dueno), con sus asientos."""

from decimal import Decimal

import pytest
import sqlalchemy as sa
from conftest import con_token, crear_negocio_api, registrar_usuario


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


def D(texto) -> Decimal:
    return Decimal(texto)


def abrir(cliente, h, monto="200.00"):
    return cliente.post("/v1/caja/abrir", headers=h, json={"monto_apertura": monto})


def cerrar(cliente, h, contado, clave=None, nota=None):
    cabeceras = {**h, **({"Idempotency-Key": clave} if clave else {})}
    cuerpo = {"efectivo_contado": contado, **({"nota": nota} if nota else {})}
    return cliente.post("/v1/caja/cerrar", headers=cabeceras, json=cuerpo)


def vender(cliente, h, precio="45.00", cantidad=1, medio="efectivo"):
    r = cliente.post("/v1/items", headers=h, json={"nombre": f"Plato {precio}-{medio}-{cantidad}",
                                                   "precio_venta": precio})
    assert r.status_code == 201, r.text
    r = cliente.post("/v1/ventas", headers=h, json={
        "lineas": [{"item_id": r.json()["id"], "cantidad": cantidad}], "medio_pago": medio})
    assert r.status_code == 201, r.text
    return r.json()


def gastar(cliente, h, monto, medio="efectivo"):
    cat = cliente.get("/v1/gastos/categorias", headers=h).json()[0]
    r = cliente.post("/v1/gastos", headers=h, json={
        "categoria_id": cat["id"], "monto": monto, "medio_pago": medio})
    assert r.status_code == 201, r.text
    return r.json()


def dueno(cliente, h, tipo, monto, medio="efectivo", clave=None, **extra):
    cabeceras = {**h, **({"Idempotency-Key": clave} if clave else {})}
    return cliente.post("/v1/dueno", headers=cabeceras,
                        json={"tipo": tipo, "monto": monto, "medio": medio, **extra})


def con_saldo(cliente, h) -> dict[str, Decimal]:
    cuentas = cliente.get("/v1/cuentas", headers=h).json()["cuentas"]
    return {c["codigo"]: D(c["saldo"]) for c in cuentas
            if c["acepta_movimientos"] and D(c["saldo"]) != 0}


def caja(cliente, h):
    r = cliente.get("/v1/caja", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def poner_rol(bd, negocio, rol):
    with bd.begin() as con:
        con.execute(sa.text("UPDATE core_membresia SET rol = :r "
                            "WHERE negocio_id = UUID_TO_BIN(:n)"), {"r": rol, "n": negocio["id"]})


# ------------------------------------------------------------------ abrir


def test_sin_abrir_no_hay_caja_y_se_puede_vender(restaurante):
    cliente, _, h = restaurante
    assert caja(cliente, h) == {"abierta": None, "ultimo_cierre": None}
    vender(cliente, h)  # vender no exige abrir la caja
    assert cerrar(cliente, h, "0.00").status_code == 409


def test_abrir_la_caja_y_no_abrirla_dos_veces(restaurante):
    cliente, _, h = restaurante
    r = abrir(cliente, h, "150.50")
    assert r.status_code == 201, r.text
    sesion = r.json()
    assert sesion["estado"] == "abierta" and sesion["monto_apertura"] == "150.50"
    assert sesion["efectivo_esperado"] == "150.50"
    assert abrir(cliente, h).status_code == 409
    assert caja(cliente, h)["abierta"]["id"] == sesion["id"]
    assert abrir(cliente, h, "-1").status_code == 422


# ------------------------------------------------------------------ el día en vivo y el cierre


def test_el_efectivo_esperado_sale_de_los_libros(restaurante):
    cliente, _, h = restaurante
    abrir(cliente, h, "200.00")
    vender(cliente, h, "45.00", cantidad=2)                 # +90 en efectivo
    vender(cliente, h, "30.00", medio="tarjeta")             # no pasa por la caja
    vender(cliente, h, "20.00", medio="transferencia")       # tampoco
    mala = vender(cliente, h, "10.00")                       # +10 y luego se anula
    cliente.post(f"/v1/ventas/{mala['id']}/anular", headers=h, json={"motivo": "Error"})
    gastar(cliente, h, "25.00")                              # -25
    gastar(cliente, h, "500.00", medio="transferencia")      # no pasa por la caja
    assert dueno(cliente, h, "retiro", "15.00").status_code == 201   # -15
    assert dueno(cliente, h, "aporte", "100.00", medio="banco").status_code == 201  # banco
    abierta = caja(cliente, h)["abierta"]
    assert abierta["efectivo_esperado"] == "250.00"  # 200 + 90 - 25 - 15
    resumen = abierta["resumen"]
    assert resumen["ventas"] == "90.00" and resumen["gastos"] == "-25.00"
    assert resumen["dueno"] == "-15.00" and resumen["compras"] == "0.00"
    assert resumen["cantidad_ventas"] == 3  # la anulada no cuenta
    assert resumen["ventas_tarjeta"] == "30.00" and resumen["ventas_transferencia"] == "20.00"


def test_cerrar_sin_diferencia_no_genera_asiento(restaurante):
    cliente, _, h = restaurante
    abrir(cliente, h, "100.00")
    vender(cliente, h, "45.00")
    r = cerrar(cliente, h, "145.00", nota="Todo bien")
    assert r.status_code == 200, r.text
    cierre = r.json()
    assert cierre["estado"] == "cerrada" and cierre["diferencia"] == "0.00"
    assert cierre["efectivo_esperado"] == "145.00" and cierre["efectivo_contado"] == "145.00"
    assert cierre["nota"] == "Todo bien" and cierre["resumen"]["ventas"] == "45.00"
    estado = caja(cliente, h)
    assert estado["abierta"] is None and estado["ultimo_cierre"]["id"] == cierre["id"]
    tipos = [a["tipo_evento"] for a in cliente.get("/v1/asientos", headers=h).json()["asientos"]]
    assert tipos == ["VENTA"]


def test_un_faltante_es_un_gasto_y_un_sobrante_otro_ingreso(restaurante):
    cliente, _, h = restaurante
    abrir(cliente, h, "0.00")
    vender(cliente, h, "100.00")
    faltante = cerrar(cliente, h, "80.00").json()
    assert faltante["diferencia"] == "-20.00"
    assert con_saldo(cliente, h) == {"1101": D("80.00"), "4102": D("100.00"), "6191": D("20.00")}
    mes = cliente.get("/v1/resultados", headers=h).json()
    assert mes["gastaste"] == "20.00" and mes["te_queda"] == "80.00"

    abrir(cliente, h, "80.00")
    sobrante = cerrar(cliente, h, "85.00").json()
    assert sobrante["diferencia"] == "5.00"
    assert con_saldo(cliente, h)["4201"] == D("5.00")
    assert con_saldo(cliente, h)["1101"] == D("85.00")


def test_el_cierre_no_cuenta_lo_que_paso_antes_de_abrir(restaurante):
    cliente, _, h = restaurante
    vender(cliente, h, "500.00")  # antes de abrir
    abrir(cliente, h, "50.00")
    vender(cliente, h, "10.00")
    assert caja(cliente, h)["abierta"]["efectivo_esperado"] == "60.00"


def test_la_misma_clave_no_cierra_dos_veces(restaurante):
    cliente, _, h = restaurante
    abrir(cliente, h, "100.00")
    primero = cerrar(cliente, h, "90.00", clave="cierre-0001-abc")
    assert primero.status_code == 200
    abrir(cliente, h, "90.00")
    repetido = cerrar(cliente, h, "90.00", clave="cierre-0001-abc")
    assert repetido.status_code == 200 and repetido.json()["id"] == primero.json()["id"]
    assert caja(cliente, h)["abierta"] is not None  # la segunda caja sigue abierta
    assert cerrar(cliente, h, "1.00", clave="cierre-0001-abc").status_code == 422


def test_historial_de_cierres_del_mes(restaurante):
    cliente, _, h = restaurante
    for contado in ("10.00", "20.00"):
        abrir(cliente, h, contado)
        cerrar(cliente, h, contado)
    r = cliente.get("/v1/caja/cierres", headers=h)
    assert r.status_code == 200
    assert [c["efectivo_contado"] for c in r.json()["cierres"]] == ["20.00", "10.00"]
    assert cliente.get("/v1/caja/cierres", headers=h,
                       params={"mes": "2020-01"}).json()["cierres"] == []
    assert cliente.get("/v1/caja/cierres", headers=h,
                       params={"mes": "2026-13"}).status_code == 422


# ------------------------------------------------------------------ dueño


def test_aporte_y_retiro_van_al_capital_sin_tocar_lo_que_te_queda(restaurante):
    cliente, _, h = restaurante
    assert dueno(cliente, h, "aporte", "1000.00", medio="banco").status_code == 201
    r = dueno(cliente, h, "retiro", "300.00", nota="Para la casa")
    assert r.status_code == 201, r.text
    assert r.json()["nota"] == "Para la casa" and r.json()["medio"] == "efectivo"
    assert con_saldo(cliente, h) == {"1101": D("-300.00"), "1103": D("1000.00"),
                                     "3101": D("1000.00"), "3102": D("300.00")}
    mes = cliente.get("/v1/resultados", headers=h).json()
    assert mes["te_queda"] == "0.00" and mes["gastaste"] == "0.00"
    lista = cliente.get("/v1/dueno", headers=h).json()
    assert lista["total_aportes"] == "1000.00" and lista["total_retiros"] == "300.00"
    assert len(lista["movimientos"]) == 2


def test_borrar_un_movimiento_del_dueno_lo_revierte(restaurante):
    cliente, _, h = restaurante
    mov = dueno(cliente, h, "aporte", "500.00").json()
    assert cliente.delete(f"/v1/dueno/{mov['id']}", headers=h).status_code == 204
    assert con_saldo(cliente, h) == {}
    assert cliente.get("/v1/dueno", headers=h).json()["movimientos"] == []
    assert cliente.delete(f"/v1/dueno/{mov['id']}", headers=h).status_code == 404


def test_el_dueno_valida_sus_datos_y_no_anota_dos_veces(restaurante):
    cliente, _, h = restaurante
    assert dueno(cliente, h, "regalo", "10.00").status_code == 422
    assert dueno(cliente, h, "aporte", "0").status_code == 422
    assert dueno(cliente, h, "aporte", "10.00", medio="tarjeta").status_code == 422
    assert dueno(cliente, h, "aporte", "10.00", fecha="2999-01-01").status_code == 422
    a = dueno(cliente, h, "aporte", "10.00", clave="dueno-0001-abc")
    b = dueno(cliente, h, "aporte", "10.00", clave="dueno-0001-abc")
    assert a.json()["id"] == b.json()["id"]
    assert len(cliente.get("/v1/dueno", headers=h).json()["movimientos"]) == 1


# ------------------------------------------------------------------ permisos y aislamiento


def test_el_cajero_maneja_la_caja_pero_no_el_dinero_del_dueno(restaurante, bd_migrada):
    cliente, negocio, h = restaurante
    poner_rol(bd_migrada, negocio, "cajero")
    assert abrir(cliente, h).status_code == 201
    assert cerrar(cliente, h, "200.00").status_code == 200
    assert cliente.get("/v1/dueno", headers=h).status_code == 403
    assert dueno(cliente, h, "retiro", "10.00").status_code == 403
    poner_rol(bd_migrada, negocio, "administrador")
    assert cliente.get("/v1/dueno", headers=h).status_code == 200
    assert dueno(cliente, h, "retiro", "10.00").status_code == 403  # solo el dueño


def test_cada_negocio_tiene_su_caja(restaurante, tienda):
    cliente, _, h = restaurante
    abrir(cliente, h)
    mov = dueno(cliente, h, "aporte", "50.00").json()
    otro, _, h_otro = tienda
    assert caja(otro, h_otro)["abierta"] is None
    assert otro.get("/v1/dueno", headers=h_otro).json()["movimientos"] == []
    assert otro.delete(f"/v1/dueno/{mov['id']}", headers=h_otro).status_code == 404


def test_un_plan_anterior_recibe_la_cuenta_de_faltantes(restaurante, bd_migrada):
    """Negocios con el plan v1 (sin 6191) la reciben al abrir su libro."""
    cliente, negocio, h = restaurante
    with bd_migrada.begin() as con:
        con.execute(sa.text("DELETE FROM cont_cuenta_contable WHERE codigo = '6191' "
                            "AND negocio_id = UUID_TO_BIN(:n)"), {"n": negocio["id"]})
        con.execute(sa.text("UPDATE cont_libro SET plan_version = 1 "
                            "WHERE negocio_id = UUID_TO_BIN(:n)"), {"n": negocio["id"]})
    abrir(cliente, h, "10.00")
    assert cerrar(cliente, h, "5.00").status_code == 200
    assert con_saldo(cliente, h)["6191"] == D("5.00")
