"""Carga idempotente de catálogos y configuración desde `db/semillas/*.yaml`.

Uso:  python -m uv run python -m integrat.db.semillas
Cada archivo YAML es una lista de bloques {tabla: <nombre>, filas: [...]},
y se procesan en orden alfabético de archivo (por eso llevan prefijo numérico).
Se hace INSERT ... ON DUPLICATE KEY UPDATE: ejecutarlo dos veces no duplica nada.
"""

import logging
from pathlib import Path

import sqlalchemy as sa
import yaml
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.engine import Engine

from integrat.config import RAIZ_PROYECTO, config_bd
from integrat.db.tablas import metadata

log = logging.getLogger(__name__)

CARPETA_SEMILLAS = RAIZ_PROYECTO / "db" / "semillas"


def leer_semillas(carpeta: Path = CARPETA_SEMILLAS) -> list[dict]:
    bloques: list[dict] = []
    for archivo in sorted(carpeta.glob("*.yaml")):
        with archivo.open(encoding="utf-8") as f:
            contenido = yaml.safe_load(f) or []
        for bloque in contenido:
            if bloque["tabla"] not in metadata.tables:
                raise ValueError(f"{archivo.name}: tabla desconocida {bloque['tabla']}")
            bloques.append(bloque)
    return bloques


def cargar_semillas(engine: Engine, carpeta: Path = CARPETA_SEMILLAS) -> dict[str, int]:
    """Carga todas las semillas en una transacción. Devuelve filas procesadas por tabla."""
    resumen: dict[str, int] = {}
    with engine.begin() as con:
        for bloque in leer_semillas(carpeta):
            tabla: sa.Table = metadata.tables[bloque["tabla"]]
            filas = bloque["filas"]
            if not filas:
                continue
            columnas_pk = {c.name for c in tabla.primary_key.columns}
            columnas_dato = [c for c in filas[0] if c not in columnas_pk]
            consulta = mysql_insert(tabla).values(filas)
            if columnas_dato:
                consulta = consulta.on_duplicate_key_update(
                    {c: consulta.inserted[c] for c in columnas_dato}
                )
            else:
                consulta = consulta.prefix_with("IGNORE")
            con.execute(consulta)
            resumen[tabla.name] = resumen.get(tabla.name, 0) + len(filas)
    return resumen


def main() -> None:
    from integrat.db.conexion import crear_engine

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    cfg = config_bd()
    log.info("Cargando semillas en %s", cfg.descripcion_segura())
    resumen = cargar_semillas(crear_engine(cfg))
    for tabla, n in resumen.items():
        log.info("  %-36s %4d filas", tabla, n)
    log.info("Semillas cargadas.")


if __name__ == "__main__":
    main()
