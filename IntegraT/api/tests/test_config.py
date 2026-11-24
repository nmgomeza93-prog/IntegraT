import pytest
from pydantic import ValidationError

from integrat.config import ConfigBD, ConfigBDPruebas

SECRETO = "valor-secreto-de-prueba"


def _cfg(**kw):
    base = {"host": "h", "port": 3306, "name": "integrat", "user": "u", "password": SECRETO}
    return ConfigBD(_env_file=None, **{**base, **kw})


def test_la_contrasena_no_aparece_en_repr_ni_str():
    cfg = _cfg()
    assert SECRETO not in repr(cfg)
    assert SECRETO not in str(cfg)
    assert SECRETO not in cfg.descripcion_segura()


def test_solo_se_permiten_bases_integrat():
    with pytest.raises(ValidationError):
        _cfg(name="erp_pyme_gt")
    with pytest.raises(ValidationError):
        _cfg(name="cam_talent_hub_gestion_cl0")


def test_la_base_de_pruebas_debe_ser_local_y_de_prueba():
    with pytest.raises(ValidationError):
        ConfigBDPruebas(_env_file=None, host="centerbeam.proxy.rlwy.net", name="integrat_test",
                        user="u", password="p")
    with pytest.raises(ValidationError):
        ConfigBDPruebas(_env_file=None, host="127.0.0.1", name="integrat", user="u", password="p")
