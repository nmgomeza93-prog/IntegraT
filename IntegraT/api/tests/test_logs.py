import logging

from integrat.logs import MASCARA, FiltroSecretos

SECRETO = "S3cr3to-Muy-Privado!"


def _formatear(filtro: FiltroSecretos, msg: str, *args, exc_info=None) -> str:
    registro = logging.LogRecord("x", logging.INFO, __file__, 1, msg, args, exc_info)
    filtro.filter(registro)
    return logging.Formatter("%(message)s").format(registro)


def test_enmascara_secretos_conocidos():
    filtro = FiltroSecretos([SECRETO])
    salida = _formatear(filtro, "conectando con %s", SECRETO)
    assert SECRETO not in salida and MASCARA in salida


def test_enmascara_patrones_comunes():
    filtro = FiltroSecretos()
    salida = _formatear(filtro, "password=abc123 token: xyz Bearer eyJhbGciOi.abc")
    assert "abc123" not in salida and "xyz" not in salida and "eyJhbGciOi" not in salida
    url = _formatear(filtro, "mysql+pymysql://usuario:otraClave@host:3306/integrat")
    assert "otraClave" not in url


def test_enmascara_secretos_en_tracebacks():
    filtro = FiltroSecretos([SECRETO])
    try:
        raise RuntimeError(f"fallo con {SECRETO}")
    except RuntimeError:
        import sys

        salida = _formatear(filtro, "error", exc_info=sys.exc_info())
    assert SECRETO not in salida
    assert "RuntimeError" in salida
