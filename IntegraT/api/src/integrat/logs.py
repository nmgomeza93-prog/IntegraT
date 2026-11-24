"""Logging de la API con enmascarado de secretos.

Regla del proyecto: ninguna credencial aparece en logs. Este filtro es una segunda
línea de defensa: reemplaza cualquier valor secreto conocido y patrones típicos
(password=..., pwd: ..., Bearer ...) por ****.
"""

import logging
import re

MASCARA = "****"

_PATRONES = [
    re.compile(r"(?i)(password|passwd|pwd|secret|token|api[_-]?key)(\s*[=:]\s*)([^\s,;'\"]+)"),
    re.compile(r"(?i)(bearer\s+)([A-Za-z0-9\-._~+/]+=*)"),
    re.compile(r"(?i)(mysql\+pymysql://[^:/\s]+:)([^@\s]+)(@)"),
]


class FiltroSecretos(logging.Filter):
    def __init__(self, secretos: list[str] | None = None) -> None:
        super().__init__()
        self._secretos = sorted({s for s in (secretos or []) if s and len(s) >= 4},
                                key=len, reverse=True)

    def enmascarar(self, texto: str) -> str:
        for secreto in self._secretos:
            texto = texto.replace(secreto, MASCARA)
        texto = _PATRONES[0].sub(lambda m: f"{m.group(1)}{m.group(2)}{MASCARA}", texto)
        texto = _PATRONES[1].sub(lambda m: f"{m.group(1)}{MASCARA}", texto)
        texto = _PATRONES[2].sub(lambda m: f"{m.group(1)}{MASCARA}{m.group(3)}", texto)
        return texto

    def filter(self, registro: logging.LogRecord) -> bool:
        mensaje = registro.getMessage()
        registro.msg = self.enmascarar(mensaje)
        registro.args = None
        if registro.exc_info:
            # El traceback podría contener secretos: se formatea y enmascara aquí.
            registro.exc_text = self.enmascarar(
                logging.Formatter().formatException(registro.exc_info)
            )
            registro.exc_info = None
        return True


def secretos_conocidos() -> list[str]:
    """Valores secretos de la configuración actual (para enmascararlos)."""
    from integrat.config import config_bd

    secretos: list[str] = []
    try:
        secretos.append(config_bd().password.get_secret_value())
    except Exception:  # noqa: S110 - sin configuración no hay secreto que ocultar
        pass
    return secretos


def configurar_logs(nivel: int = logging.INFO) -> None:
    filtro = FiltroSecretos(secretos_conocidos())
    manejador = logging.StreamHandler()
    manejador.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    manejador.addFilter(filtro)
    raiz = logging.getLogger()
    raiz.handlers = [manejador]
    raiz.setLevel(nivel)
    for nombre in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        registro = logging.getLogger(nombre)
        registro.handlers = []
        registro.propagate = True
