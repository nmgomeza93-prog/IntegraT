"""Catálogos públicos de solo lectura: GET /v1/tipos-negocio y GET /v1/regimenes."""

from typing import Annotated

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.engine import Engine

from integrat.db.tablas import cat_tipo_negocio, fiscal_cfg_regimen
from integrat.dependencias import obtener_engine

router = APIRouter(tags=["catalogos"])
Motor = Annotated[Engine, Depends(obtener_engine)]


class TipoNegocioOut(BaseModel):
    codigo: str
    nombre: str
    descripcion: str
    icono: str


class RegimenOut(BaseModel):
    codigo: str
    impuesto: str
    nombre_simple: str
    usa_credito_fiscal: bool
    validado_por_contador: bool  # mientras sea False, no se presenta como definitivo


@router.get("/tipos-negocio", response_model=list[TipoNegocioOut],
            summary="Tipos de negocio disponibles")
def tipos_negocio(engine: Motor) -> list[TipoNegocioOut]:
    with engine.connect() as con:
        filas = con.execute(
            sa.select(cat_tipo_negocio.c.codigo, cat_tipo_negocio.c.nombre,
                      cat_tipo_negocio.c.descripcion, cat_tipo_negocio.c.icono)
            .where(cat_tipo_negocio.c.activo.is_(True))
            .order_by(cat_tipo_negocio.c.orden, cat_tipo_negocio.c.codigo)
        ).all()
    return [TipoNegocioOut(**f._asdict()) for f in filas]


@router.get("/regimenes", response_model=list[RegimenOut], summary="Regímenes fiscales de un país")
def regimenes(engine: Motor, pais: Annotated[str, Query(min_length=2, max_length=2)] = "GT"
              ) -> list[RegimenOut]:
    with engine.connect() as con:
        filas = con.execute(
            sa.select(fiscal_cfg_regimen.c.codigo, fiscal_cfg_regimen.c.impuesto,
                      fiscal_cfg_regimen.c.nombre_simple, fiscal_cfg_regimen.c.usa_credito_fiscal,
                      fiscal_cfg_regimen.c.validado_por_contador)
            .where(fiscal_cfg_regimen.c.pais_codigo == pais.upper())
            .order_by(fiscal_cfg_regimen.c.codigo)
        ).all()
    return [RegimenOut(**f._asdict()) for f in filas]
