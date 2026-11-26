"""/v1/informes/mes: el informe del mes (solo lectura). El negocio sale siempre del token."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.engine import Engine

from integrat.auth.dependencias import AccesoNegocio, acceso_negocio
from integrat.dependencias import obtener_engine
from integrat.informes import servicio

router = APIRouter(tags=["informes"])
Motor = Annotated[Engine, Depends(obtener_engine)]
Acceso = Annotated[AccesoNegocio, Depends(acceso_negocio)]
Mes = Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}$",
                                  description="AAAA-MM; por defecto, este mes.")]

ROLES_QUE_VEN = {"dueno", "administrador", "contador"}


@router.get("/informes/mes", response_model=servicio.InformeMesOut,
            summary="Informe del mes: lo más vendido, tus mejores clientes y cómo te pagaron")
def informe_mes(acceso: Acceso, engine: Motor, mes: Mes = None) -> servicio.InformeMesOut:
    if acceso.rol not in ROLES_QUE_VEN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No tienes permiso para ver esto.")
    try:
        with engine.connect() as con:
            return servicio.informe_del_mes(con, acceso.contexto, mes)
    except servicio.MesInvalido:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "Ese mes no es válido.") from None
