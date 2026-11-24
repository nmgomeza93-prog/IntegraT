import sqlalchemy as sa

from integrat.db.semillas import cargar_semillas


def _contar(engine, tabla: str) -> int:
    with engine.connect() as con:
        return con.execute(sa.text(f"SELECT COUNT(*) FROM `{tabla}`")).scalar_one()


def test_catalogos_cargados(bd_migrada):
    assert _contar(bd_migrada, "cat_pais") == 1
    assert _contar(bd_migrada, "cat_division_territorial") == 22
    assert _contar(bd_migrada, "cat_tipo_negocio") == 2
    assert _contar(bd_migrada, "fiscal_cfg_regimen") == 5
    with bd_migrada.connect() as con:
        factor = con.execute(sa.text(
            "SELECT factor_a_base FROM cat_unidad_medida WHERE codigo = 'GAL'"
        )).scalar_one()
    assert float(factor) == 3785.411784


def test_las_semillas_son_idempotentes(bd_migrada):
    antes = {t: _contar(bd_migrada, t) for t in ("cat_unidad_medida",
                                                  "core_cfg_tipo_negocio_capacidad")}
    cargar_semillas(bd_migrada)
    cargar_semillas(bd_migrada)
    despues = {t: _contar(bd_migrada, t) for t in antes}
    assert antes == despues


def test_regimenes_pendientes_de_validacion_del_contador(bd_migrada):
    with bd_migrada.connect() as con:
        validados = con.execute(sa.text(
            "SELECT COUNT(*) FROM fiscal_cfg_regimen WHERE validado_por_contador = 1"
        )).scalar_one()
    assert validados == 0
