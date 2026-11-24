"""Un negocio nunca ve ni modifica los datos de otro (reemplazo del RLS en MySQL)."""

import pytest
import sqlalchemy as sa

from integrat.db import aislamiento as ais
from integrat.db.tablas import core_negocio, core_negocio_capacidad, metadata
from integrat.db.tipos import uuid7


def _crear_negocio(con, nombre: str):
    negocio_id = uuid7()
    con.execute(sa.insert(core_negocio).values(
        id=negocio_id, nombre=nombre, tipo_negocio_codigo="restaurante", pais_codigo="GT",
        zona_horaria="America/Guatemala", moneda_codigo="GTQ",
    ))
    return negocio_id


@pytest.fixture
def dos_negocios(bd_migrada):
    with bd_migrada.begin() as con:
        a = ais.ContextoNegocio(_crear_negocio(con, "Comedor A"))
        b = ais.ContextoNegocio(_crear_negocio(con, "Comedor B"))
        for ctx in (a, b):
            con.execute(ais.insertar(ctx, core_negocio_capacidad,
                                     {"id": uuid7(), "capacidad": "recetas", "activa": True}))
    return bd_migrada, a, b


def test_cada_negocio_ve_solo_lo_suyo(dos_negocios):
    engine, a, b = dos_negocios
    with engine.connect() as con:
        filas_a = con.execute(ais.seleccionar(a, core_negocio_capacidad)).mappings().all()
    assert filas_a and all(f["negocio_id"] == a.negocio_id for f in filas_a)


def test_no_se_puede_actualizar_datos_de_otro_negocio(dos_negocios):
    engine, a, b = dos_negocios
    with engine.begin() as con:
        id_de_b = con.execute(
            ais.seleccionar(b, core_negocio_capacidad, core_negocio_capacidad.c.id)
        ).scalar_one()
        resultado = con.execute(
            ais.actualizar(a, core_negocio_capacidad, core_negocio_capacidad.c.id == id_de_b)
            .values(activa=False)
        )
    assert resultado.rowcount == 0


def test_no_se_puede_insertar_en_otro_negocio(dos_negocios):
    _, a, b = dos_negocios
    with pytest.raises(ais.ErrorAislamiento):
        ais.insertar(a, core_negocio_capacidad,
                     {"id": uuid7(), "negocio_id": b.negocio_id, "capacidad": "x", "activa": True})


def test_no_se_usa_el_helper_con_tablas_sin_negocio():
    with pytest.raises(ais.ErrorAislamiento):
        ais.seleccionar(ais.ContextoNegocio(uuid7()), metadata.tables["cat_pais"])


def test_los_borrados_logicos_no_se_ven(dos_negocios):
    engine, a, _ = dos_negocios
    with engine.begin() as con:
        con.execute(ais.actualizar(a, core_negocio_capacidad)
                    .values(eliminado_en=sa.func.now(6)))
        visibles = con.execute(ais.seleccionar(a, core_negocio_capacidad)).all()
    assert visibles == []
