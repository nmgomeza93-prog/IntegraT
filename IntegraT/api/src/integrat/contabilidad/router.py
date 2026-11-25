"""/v1/resultados, /v1/asientos y /v1/cuentas (solo lectura). El negocio sale siempre del token."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.engine import Engine

from integrat.auth.dependencias import AccesoNegocio, acceso_negocio
from integrat.contabilidad import servicio
from integrat.contabilidad.esquemas import LibroDiarioOut, PlanCuentasOut, ResultadosOut
from integrat.dependencias import obtener_engine

router = APIRouter(tags=["contabilidad"])
Motor = Annotated[Engine, Depends(obtener_engine)]
Acceso = Annotated[AccesoNegocio, Depends(acceso_negocio)]
Mes = Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}$",
                                  description="AAAA-MM; por defecto, este mes.")]

# Ganancias, costos y libros: no son para el cajero.
ROLES_QUE_VEN = {"dueno", "administrador", "contador"}


def _exigir(acceso: AccesoNegocio) -> None:
    if acceso.rol not in ROLES_QUE_VEN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No tienes permiso para ver esto.")


def _mes_invalido() -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Ese mes no es válido.")


@router.get("/resultados", response_model=ResultadosOut, summary="Cómo te fue en el mes")
def resultados(acceso: Acceso, engine: Motor, mes: Mes = None) -> ResultadosOut:
    _exigir(acceso)
    try:
        with engine.connect() as con:
            return servicio.resultados_del_mes(con, acceso.contexto, mes)
    except servicio.MesInvalido:
        raise _mes_invalido() from None


@router.get("/asientos", response_model=LibroDiarioOut, summary="Libro diario del mes")
def asientos(acceso: Acceso, engine: Motor, mes: Mes = None) -> LibroDiarioOut:
    _exigir(acceso)
    try:
        with engine.connect() as con:
            return servicio.libro_diario(con, acceso.contexto, mes)
    except servicio.MesInvalido:
        raise _mes_invalido() from None


@router.get("/cuentas", response_model=PlanCuentasOut, summary="Plan de cuentas con saldos")
def cuentas(acceso: Acceso, engine: Motor) -> PlanCuentasOut:
    _exigir(acceso)
    with engine.begin() as con:
        return servicio.plan_con_saldos(con, acceso.contexto)
