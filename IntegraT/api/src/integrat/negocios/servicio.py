"""Crear y leer negocios. Todo acceso a tablas de negocio pasa por db.aislamiento."""

import hashlib
import json
import uuid
from datetime import timedelta

import sqlalchemy as sa
from sqlalchemy.engine import Connection, Engine

from integrat import validaciones as val
from integrat.contabilidad import motor as contabilidad
from integrat.db import aislamiento as ais
from integrat.db.tablas import (
    cat_pais,
    cat_tipo_negocio,
    core_cfg_tipo_negocio_capacidad,
    core_cfg_tipo_negocio_plantilla,
    core_cfg_tipo_negocio_vocabulario,
    core_idempotencia,
    core_membresia,
    core_membresia_titular,
    core_negocio,
    core_negocio_capacidad,
    core_titular,
    ops_compra,
    ops_gasto,
    ops_insumo,
    ops_item,
    ops_venta,
)
from integrat.db.tipos import ahora_utc, uuid7
from integrat.gastos.servicio import sembrar_categorias as sembrar_categorias_gasto
from integrat.insumos.recetas import contar_items_con_receta
from integrat.items.servicio import sembrar_catalogo
from integrat.negocios.esquemas import (
    DatosNegocioIn,
    ImpuestosIn,
    NegocioIn,
    NegocioOut,
    PreciosIn,
    PrimerPaso,
    ReglasVentaIn,
)

PAIS_INICIAL = "GT"  # Guatemala; el país será configurable cuando haya más
OPERACION_CREAR_NEGOCIO = "crear_negocio"
# Régimen de IVA simple -> código de `fiscal_cfg_regimen` (Guatemala). [verificar]
REGIMEN_IVA = {"general": "GT_IVA_GENERAL", "pequeno": "GT_IVA_PEQ_CONTRIBUYENTE", "no_se": None}
VIGENCIA_IDEMPOTENCIA = timedelta(hours=24)


class TipoNegocioInvalido(Exception):
    pass


class ClaveReutilizada(Exception):
    """La misma Idempotency-Key llegó con datos distintos."""


def _huella(datos: NegocioIn) -> str:
    return hashlib.sha256(json.dumps(datos.model_dump(), sort_keys=True).encode()).hexdigest()


def crear_negocio_idempotente(
    engine: Engine, usuario_id: uuid.UUID, datos: NegocioIn, clave: str | None
) -> tuple[NegocioOut, uuid.UUID]:
    """Crea el negocio una sola vez por (usuario, Idempotency-Key).

    Repetir la misma clave con los mismos datos devuelve el mismo negocio (dobles toques,
    reintentos por red caída). Sin clave, cada llamada crea un negocio nuevo.
    """
    if clave is None:
        with engine.begin() as con:
            ctx = crear_negocio(con, usuario_id, datos)
            return leer_negocio(con, ctx), ctx.negocio_id  # type: ignore[return-value]

    huella = _huella(datos)
    filtro = sa.and_(
        core_idempotencia.c.usuario_id == usuario_id,
        core_idempotencia.c.operacion == OPERACION_CREAR_NEGOCIO,
        core_idempotencia.c.clave == clave,
    )
    for intento in (1, 2):
        try:
            with engine.begin() as con:
                previo = con.execute(sa.select(core_idempotencia).where(filtro)).mappings().first()
                if previo is not None and previo["creado_en"] < ahora_utc() - VIGENCIA_IDEMPOTENCIA:
                    con.execute(sa.delete(core_idempotencia).where(filtro))  # clave vencida
                    previo = None
                if previo is not None:
                    if previo["huella"] != huella:
                        raise ClaveReutilizada
                    ctx = ais.ContextoNegocio(previo["recurso_id"], usuario_id)
                    negocio = leer_negocio(con, ctx)
                    if negocio is not None:
                        return negocio, ctx.negocio_id
                    con.execute(sa.delete(core_idempotencia).where(filtro))  # ya no existe
                ctx = crear_negocio(con, usuario_id, datos)
                con.execute(sa.insert(core_idempotencia).values(
                    id=uuid7(), usuario_id=usuario_id, operacion=OPERACION_CREAR_NEGOCIO,
                    clave=clave, huella=huella, recurso_id=ctx.negocio_id, creado_por=usuario_id,
                ))
                return leer_negocio(con, ctx), ctx.negocio_id  # type: ignore[return-value]
        except sa.exc.IntegrityError:
            # Carrera: otra petición con la misma clave se confirmó primero. Se reintenta una
            # vez y ahora la encuentra (y devuelve su negocio).
            if intento == 2:
                raise
    raise AssertionError("inalcanzable")


def _regla_inicial(con: Connection, tipo: str) -> str:
    contenido = con.execute(
        sa.select(core_cfg_tipo_negocio_plantilla.c.contenido).where(
            core_cfg_tipo_negocio_plantilla.c.tipo_negocio_codigo == tipo,
            core_cfg_tipo_negocio_plantilla.c.tipo_plantilla == "operacion")
    ).scalar_one_or_none() or {}
    return contenido.get("vender_sin_existencia", "avisar")


def _minimo_inicial(con: Connection, tipo: str):
    contenido = con.execute(
        sa.select(core_cfg_tipo_negocio_plantilla.c.contenido).where(
            core_cfg_tipo_negocio_plantilla.c.tipo_negocio_codigo == tipo,
            core_cfg_tipo_negocio_plantilla.c.tipo_plantilla == "operacion")
    ).scalar_one_or_none() or {}
    return contenido.get("minimo_defecto", 0)


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
        vender_sin_existencia=_regla_inicial(con, tipo),
        minimo_defecto=_minimo_inicial(con, tipo),
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
    sembrar_catalogo(con, ctx, tipo)  # categorías de ejemplo del tipo de negocio
    sembrar_categorias_gasto(con, ctx, tipo)
    contabilidad.crear_libro(con, ctx)  # libro y plan de cuentas del negocio
    return ctx


def fijar_reglas_venta(con: Connection, ctx: ais.ContextoNegocio, datos: ReglasVentaIn) -> None:
    valores = {"vender_sin_existencia": datos.vender_sin_existencia,
               "actualizado_por": ctx.usuario_id}
    if datos.minimo_defecto is not None:
        valores["minimo_defecto"] = datos.minimo_defecto
    con.execute(sa.update(core_negocio).where(core_negocio.c.id == ctx.negocio_id)
                .values(**valores))
    if datos.minimo_defecto is not None and datos.aplicar_a_todos:
        con.execute(ais.actualizar(ctx, ops_insumo, ops_insumo.c.item_id.is_not(None)).values(
            stock_minimo_base=datos.minimo_defecto, actualizado_por=ctx.usuario_id))


def fijar_precios(con: Connection, ctx: ais.ContextoNegocio, datos: PreciosIn) -> None:
    """Margen objetivo del negocio: lo usan el precio sugerido y la meta del mes."""
    con.execute(sa.update(core_negocio).where(core_negocio.c.id == ctx.negocio_id).values(
        margen_objetivo_defecto=datos.margen_objetivo, actualizado_por=ctx.usuario_id))


def _regimen_simple(codigo: str | None) -> str:
    return next((simple for simple, c in REGIMEN_IVA.items() if c == codigo and c), "no_se")


def _abrir_titular(con: Connection, ctx: ais.ContextoNegocio) -> uuid.UUID:
    """Crea el titular (quien responde ante la SAT) y lo liga a quien lo abre."""
    titular_id = uuid7()
    con.execute(sa.insert(core_titular).values(
        id=titular_id, pais_codigo=PAIS_INICIAL, estado="pendiente", creado_por=ctx.usuario_id,
    ))
    con.execute(sa.insert(core_membresia_titular).values(
        id=uuid7(), usuario_id=ctx.usuario_id, titular_id=titular_id, rol="titular_admin",
        creado_por=ctx.usuario_id,
    ))
    return titular_id


def fijar_datos(con: Connection, ctx: ais.ContextoNegocio, datos: DatosNegocioIn) -> None:
    """Mi negocio: contacto en core_negocio; NIT y nombre fiscal en su titular."""
    enviados = datos.model_fields_set
    valores: dict = {}
    if "nombre" in enviados and datos.nombre is not None:
        valores["nombre"] = datos.nombre
    if "telefono" in enviados:
        valores["telefono"] = val.telefono(datos.telefono) if datos.telefono else None
    if "correo" in enviados:
        valores["correo"] = val.correo(datos.correo) if datos.correo else None
    if "direccion" in enviados:
        valores["direccion"] = datos.direccion or None
    fiscal: dict = {}
    if "nit" in enviados:
        fiscal["nit"] = val.nit(datos.nit) if datos.nit else None
    if "nombre_fiscal" in enviados:
        fiscal["nombre_fiscal"] = datos.nombre_fiscal or None
    negocio = con.execute(sa.select(core_negocio.c.titular_id)
                          .where(core_negocio.c.id == ctx.negocio_id).with_for_update()).one()
    if fiscal:
        titular_id = negocio.titular_id
        if titular_id is None:
            titular_id = _abrir_titular(con, ctx)
            valores["titular_id"] = titular_id
        con.execute(sa.update(core_titular).where(core_titular.c.id == titular_id).values(
            **fiscal, actualizado_por=ctx.usuario_id, version=core_titular.c.version + 1))
    if valores:
        con.execute(sa.update(core_negocio).where(core_negocio.c.id == ctx.negocio_id)
                    .values(**valores, actualizado_por=ctx.usuario_id))


def fijar_impuestos(con: Connection, ctx: ais.ContextoNegocio, datos: ImpuestosIn) -> None:
    """Fija el régimen de IVA del titular del negocio (lo abre si aún no existe).

    Aplica a las operaciones siguientes; lo ya registrado conserva su tratamiento.
    """
    negocio = con.execute(
        sa.select(core_negocio.c.titular_id, core_negocio.c.estado_onboarding)
        .where(core_negocio.c.id == ctx.negocio_id).with_for_update()
    ).one()
    codigo = REGIMEN_IVA[datos.regimen_iva]
    titular_id = negocio.titular_id
    if titular_id is None:
        if codigo is None:
            return  # sin titular ya es "todavía no sé"
        titular_id = _abrir_titular(con, ctx)
    con.execute(sa.update(core_titular).where(core_titular.c.id == titular_id).values(
        regimen_iva_codigo=codigo, actualizado_por=ctx.usuario_id,
        version=core_titular.c.version + 1,
    ))
    estado = dict(negocio.estado_onboarding or {})
    if codigo is not None:
        estado["da_factura"] = "si"
    con.execute(sa.update(core_negocio).where(core_negocio.c.id == ctx.negocio_id).values(
        titular_id=titular_id, estado_onboarding=estado, actualizado_por=ctx.usuario_id,
    ))


def _cumple_regla(regla: dict | None, conteos: dict[str, int]) -> bool:
    """Un paso del checklist se marca solo cuando se cumple su regla (definida en la plantilla).

    Cada clave de la regla es `<cosa>_minimo`: items_minimo, ventas_minimo, gastos_fijos_minimo...
    """
    if not regla:
        return False
    return all(
        conteos.get(clave.removesuffix("_minimo"), 0) >= minimo for clave, minimo in regla.items()
    )


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
    regimen = titular = None
    if negocio["titular_id"] is not None:
        titular = con.execute(
            sa.select(core_titular.c.regimen_iva_codigo, core_titular.c.nit,
                      core_titular.c.nombre_fiscal)
            .where(core_titular.c.id == negocio["titular_id"])
        ).first()
        regimen = titular.regimen_iva_codigo if titular else None
    hechos = set(estado.get("pasos_hechos", []))
    items = con.execute(ais.seleccionar(ctx, ops_item, sa.func.count())).scalar_one()
    ventas = con.execute(
        ais.seleccionar(ctx, ops_venta, sa.func.count()).where(ops_venta.c.estado == "pagada")
    ).scalar_one()
    gastos_fijos = con.execute(
        ais.seleccionar(ctx, ops_gasto, sa.func.count()).where(ops_gasto.c.es_fijo.is_(True))
    ).scalar_one()
    insumos = con.execute(ais.seleccionar(ctx, ops_insumo, sa.func.count())).scalar_one()
    conteos = {"items": items, "ventas": ventas, "gastos_fijos": gastos_fijos, "insumos": insumos,
               "recetas": contar_items_con_receta(con, ctx),
               "compras": con.execute(
                   ais.seleccionar(ctx, ops_compra, sa.func.count())
                   .where(ops_compra.c.estado == "registrada")).scalar_one()}
    pasos = [
        PrimerPaso(clave=p["clave"], texto=p["texto"], icono=p["icono"],
                   hecho=p["clave"] in hechos or _cumple_regla(p.get("regla"), conteos))
        for p in plantilla.get("primeros_pasos", [])
    ]
    return NegocioOut(
        id=negocio["id"], nombre=negocio["nombre"], tipo_negocio_codigo=tipo,
        pais_codigo=negocio["pais_codigo"], moneda_codigo=negocio["moneda_codigo"],
        zona_horaria=negocio["zona_horaria"], da_factura=estado.get("da_factura", "no_se"),
        regimen_iva=_regimen_simple(regimen),
        margen_objetivo=f"{negocio['margen_objetivo_defecto']:.4f}",
        vender_sin_existencia=negocio["vender_sin_existencia"],
        minimo_defecto=f"{negocio['minimo_defecto']:.2f}",
        telefono=negocio["telefono"], correo=negocio["correo"], direccion=negocio["direccion"],
        nit=titular.nit if titular else None,
        nombre_fiscal=titular.nombre_fiscal if titular else None,
        capacidades=list(capacidades), vocabulario=vocabulario, primeros_pasos=pasos,
    )
