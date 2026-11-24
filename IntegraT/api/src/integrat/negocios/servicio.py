"""Crear y leer negocios. Todo acceso a tablas de negocio pasa por db.aislamiento."""

import uuid

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from integrat.db import aislamiento as ais
from integrat.db.tablas import (
    cat_pais,
    cat_tipo_negocio,
    core_cfg_tipo_negocio_capacidad,
    core_cfg_tipo_negocio_plantilla,
    core_cfg_tipo_negocio_vocabulario,
    core_membresia,
    core_membresia_titular,
    core_negocio,
    core_negocio_capacidad,
    core_titular,
)
from integrat.db.tipos import uuid7
from integrat.negocios.esquemas import NegocioIn, NegocioOut, PrimerPaso

PAIS_INICIAL = "GT"  # Guatemala; el país será configurable cuando haya más


class TipoNegocioInvalido(Exception):
    pass


def crear_negocio(con: Connection, usuario_id: uuid.UUID, datos: NegocioIn) -> ais.ContextoNegocio:
    """Crea negocio + membresía de dueño + capacidades del tipo (+ titular si da factura).

    Todo ocurre en la transacción de `con`: si algo falla no queda nada a medias.
    """
    tipo = con.execute(
        sa.select(cat_tipo_negocio.c.codigo).where(
            cat_tipo_negocio.c.codigo == datos.tipo_negocio_codigo,
            cat_tipo_negocio.c.activo.is_(True),
        )
    ).scalar_one_or_none()
    if tipo is None:
        raise TipoNegocioInvalido
    pais = con.execute(
        sa.select(cat_pais.c.moneda_codigo, cat_pais.c.zona_horaria_defecto)
        .where(cat_pais.c.codigo == PAIS_INICIAL)
    ).one()

    titular_id = None
    if datos.da_factura == "si":
        # Solo se abre el titular (pendiente): NIT y régimen se piden después, con el contador.
        titular_id = uuid7()
        con.execute(sa.insert(core_titular).values(
            id=titular_id, pais_codigo=PAIS_INICIAL, estado="pendiente", creado_por=usuario_id,
        ))

    negocio_id = uuid7()
    con.execute(sa.insert(core_negocio).values(
        id=negocio_id, titular_id=titular_id, nombre=datos.nombre,
        tipo_negocio_codigo=tipo, pais_codigo=PAIS_INICIAL,
        zona_horaria=pais.zona_horaria_defecto, moneda_codigo=pais.moneda_codigo,
        estado_onboarding={"da_factura": datos.da_factura, "pasos_hechos": []},
        creado_por=usuario_id,
    ))
    ctx = ais.ContextoNegocio(negocio_id, usuario_id)
    con.execute(ais.insertar(ctx, core_membresia,
                             {"id": uuid7(), "usuario_id": usuario_id, "rol": "dueno"}))
    if titular_id is not None:
        con.execute(sa.insert(core_membresia_titular).values(
            id=uuid7(), usuario_id=usuario_id, titular_id=titular_id, rol="titular_admin",
            creado_por=usuario_id,
        ))
    capacidades = con.execute(
        sa.select(core_cfg_tipo_negocio_capacidad.c.capacidad,
                  core_cfg_tipo_negocio_capacidad.c.activa_por_defecto)
        .where(core_cfg_tipo_negocio_capacidad.c.tipo_negocio_codigo == tipo)
    ).all()
    for c in capacidades:
        con.execute(ais.insertar(ctx, core_negocio_capacidad, {
            "id": uuid7(), "capacidad": c.capacidad, "activa": c.activa_por_defecto,
        }))
    return ctx


def leer_negocio(con: Connection, ctx: ais.ContextoNegocio) -> NegocioOut | None:
    """El negocio del contexto, con su vocabulario y su checklist de primeros pasos."""
    negocio = con.execute(
        sa.select(core_negocio).where(
            core_negocio.c.id == ctx.negocio_id, core_negocio.c.eliminado_en.is_(None)
        )
    ).mappings().first()
    if negocio is None:
        return None
    tipo = negocio["tipo_negocio_codigo"]
    capacidades = con.execute(
        ais.seleccionar(ctx, core_negocio_capacidad, core_negocio_capacidad.c.capacidad)
        .where(core_negocio_capacidad.c.activa.is_(True))
        .order_by(core_negocio_capacidad.c.capacidad)
    ).scalars().all()
    vocabulario = {
        f.clave: f.texto for f in con.execute(
            sa.select(core_cfg_tipo_negocio_vocabulario.c.clave,
                      core_cfg_tipo_negocio_vocabulario.c.texto)
            .where(core_cfg_tipo_negocio_vocabulario.c.tipo_negocio_codigo == tipo)
        )
    }
    plantilla = con.execute(
        sa.select(core_cfg_tipo_negocio_plantilla.c.contenido).where(
            core_cfg_tipo_negocio_plantilla.c.tipo_negocio_codigo == tipo,
            core_cfg_tipo_negocio_plantilla.c.tipo_plantilla == "onboarding",
        )
    ).scalar_one_or_none() or {}
    estado = negocio["estado_onboarding"] or {}
    hechos = set(estado.get("pasos_hechos", []))
    pasos = [PrimerPaso(**p, hecho=p["clave"] in hechos)
             for p in plantilla.get("primeros_pasos", [])]
    return NegocioOut(
        id=negocio["id"], nombre=negocio["nombre"], tipo_negocio_codigo=tipo,
        pais_codigo=negocio["pais_codigo"], moneda_codigo=negocio["moneda_codigo"],
        zona_horaria=negocio["zona_horaria"], da_factura=estado.get("da_factura", "no_se"),
        capacidades=list(capacidades), vocabulario=vocabulario, primeros_pasos=pasos,
    )
