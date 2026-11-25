"""Motor contable: plan de cuentas por negocio, reglas, cuadre, numeración y reversos.

Reglas (docs/PLAN_CONTABILIDAD.md):
- El código nunca usa códigos de cuenta: una regla dice qué ROL va al debe o al haber y con qué
  importe; el rol apunta a una cuenta del plan del negocio.
- Los asientos son inmutables. Se corrigen con un reverso (líneas invertidas, misma fecha).
- MySQL no tiene restricciones diferidas: el cuadre se valida aquí, antes de guardar, dentro de
  la transacción de la operación (si no cuadra, no queda nada).
- El renglón de `cont_libro` se bloquea AL FINAL de cada operación, después de los insumos: así
  el orden de los candados es siempre el mismo y no hay bloqueos cruzados.
"""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from integrat.db import aislamiento as ais
from integrat.db.tablas import (
    cont_asiento,
    cont_asiento_linea,
    cont_cfg_plantilla_plan_cuentas,
    cont_cfg_regla_contable,
    cont_cuenta_contable,
    cont_libro,
    core_negocio,
    core_titular,
    fiscal_cfg_regimen,
)
from integrat.db.tipos import uuid7

CENTAVOS = Decimal("0.01")
CERO = Decimal("0.00")
SEPARADO = "separado"
SIN_SEPARAR = "sin_separar"
EVENTO_REVERSO = "REVERSO"

# Medio de pago -> rol (decisión del dueño, 2026-11-25: tarjeta y transferencia, directo a Banco).
ROL_POR_MEDIO = {"efectivo": "CAJA", "tarjeta": "BANCO", "transferencia": "BANCO"}


class AsientoDescuadrado(Exception):
    """La suma del debe no es igual a la del haber: error del motor o de una regla."""


class ReglaFaltante(Exception):
    pass


class CuentaFaltante(Exception):
    """El plan del negocio no tiene una cuenta de movimiento para un rol."""


@dataclass(frozen=True)
class Tratamiento:
    """Cómo se trata el IVA del negocio hoy: `separado` (con su tasa) o `sin_separar`."""

    codigo: str
    tasa: Decimal = Decimal("0")

    @property
    def separa(self) -> bool:
        return self.codigo == SEPARADO


def centavos(valor: Decimal) -> Decimal:
    return Decimal(valor).quantize(CENTAVOS, ROUND_HALF_UP)


# ------------------------------------------------------------------ IVA

def tratamiento_iva(con: Connection, ctx: ais.ContextoNegocio) -> Tratamiento:
    """Sale del régimen de IVA del titular. Sin titular o sin régimen: sin separar."""
    fila = con.execute(
        sa.select(fiscal_cfg_regimen.c.usa_credito_fiscal, fiscal_cfg_regimen.c.parametros)
        .select_from(
            core_negocio
            .join(core_titular, core_titular.c.id == core_negocio.c.titular_id)
            .join(fiscal_cfg_regimen,
                  fiscal_cfg_regimen.c.codigo == core_titular.c.regimen_iva_codigo))
        .where(core_negocio.c.id == ctx.negocio_id)
    ).first()
    if fila is None or not fila.usa_credito_fiscal:
        return Tratamiento(SIN_SEPARAR)
    tasa = Decimal(str((fila.parametros or {}).get("tasa", 0)))
    if tasa <= 0:
        return Tratamiento(SIN_SEPARAR)
    return Tratamiento(SEPARADO, tasa)


def separar_iva(total: Decimal, trat: Tratamiento, aplica: bool = True) -> tuple[Decimal, Decimal]:
    """(base, iva) de un monto con IVA incluido. Sin IVA: (total, 0)."""
    total = centavos(total)
    if not (aplica and trat.separa):
        return total, CERO
    base = centavos(total / (1 + trat.tasa))
    return base, total - base


# ------------------------------------------------------------------ plan de cuentas

def _plantilla(con: Connection, ctx: ais.ContextoNegocio):
    negocio = con.execute(
        sa.select(core_negocio.c.pais_codigo, core_negocio.c.tipo_negocio_codigo)
        .where(core_negocio.c.id == ctx.negocio_id)
    ).one()
    plantilla = con.execute(
        sa.select(cont_cfg_plantilla_plan_cuentas.c.contenido,
                  cont_cfg_plantilla_plan_cuentas.c.version)
        .where(cont_cfg_plantilla_plan_cuentas.c.pais_codigo == negocio.pais_codigo,
               cont_cfg_plantilla_plan_cuentas.c.tipo_negocio_codigo
               == negocio.tipo_negocio_codigo)
    ).first()
    if plantilla is None:
        raise CuentaFaltante("No hay plantilla de plan de cuentas para este negocio.")
    return plantilla


def _sembrar_plan(con: Connection, ctx: ais.ContextoNegocio, plantilla=None) -> int:
    """Copia al negocio las cuentas de la plantilla que aún no tiene. Devuelve la versión.

    Sirve para el plan nuevo y para ponerlo al día cuando la plantilla sube de versión: las
    cuentas que el negocio ya tiene (por código) no se tocan, aunque el contador las haya cambiado.
    """
    plantilla = plantilla or _plantilla(con, ctx)
    cuentas = plantilla.contenido.get("cuentas", [])
    padres = {c["padre"] for c in cuentas if c.get("padre")}
    ids: dict[str, uuid.UUID] = {
        f.codigo: f.id for f in con.execute(
            ais.seleccionar(ctx, cont_cuenta_contable, cont_cuenta_contable.c.codigo,
                            cont_cuenta_contable.c.id, incluir_eliminados=True))
    }
    for c in cuentas:  # la plantilla lista cada cuenta después de su padre
        if c["codigo"] in ids:
            continue
        ids[c["codigo"]] = uuid7()
        con.execute(ais.insertar(ctx, cont_cuenta_contable, {
            "id": ids[c["codigo"]], "codigo": c["codigo"], "nombre": c["nombre"],
            "nombre_simple": c.get("nombre_simple"), "tipo": c["tipo"],
            "naturaleza": c["naturaleza"], "padre_id": ids.get(c.get("padre")),
            "acepta_movimientos": c["codigo"] not in padres, "rol_cuenta_codigo": c.get("rol"),
        }))
    return plantilla.version


def crear_libro(con: Connection, ctx: ais.ContextoNegocio) -> None:
    """Libro y plan de cuentas de un negocio que se está creando (en su misma transacción)."""
    version = _sembrar_plan(con, ctx)
    con.execute(ais.insertar(ctx, cont_libro, {"id": uuid7(), "plan_version": version}))


def abrir_libro(con: Connection, ctx: ais.ContextoNegocio):
    """Bloquea el libro del negocio (y lo crea, con su plan, si el negocio es anterior a él).

    Primero se mira sin bloquear: si el libro existe, se bloquea solo su fila. Si no existe, se
    serializa por la fila del negocio ANTES de buscarlo con bloqueo, porque dos búsquedas con
    bloqueo de una fila inexistente se traban entre sí al insertar (candados de "hueco").
    Si la plantilla subió de versión, el plan recibe las cuentas nuevas (bajo el mismo bloqueo).
    """
    consulta = ais.seleccionar(ctx, cont_libro, cont_libro.c.id, cont_libro.c.ultimo_numero,
                               cont_libro.c.plan_version)
    if con.execute(consulta).first() is None:
        con.execute(sa.select(core_negocio.c.id).where(core_negocio.c.id == ctx.negocio_id)
                    .with_for_update())
        if con.execute(consulta.with_for_update()).first() is None:
            crear_libro(con, ctx)
    libro = con.execute(consulta.with_for_update()).one()
    plantilla = _plantilla(con, ctx)
    if libro.plan_version is None or libro.plan_version < plantilla.version:
        version = _sembrar_plan(con, ctx, plantilla)
        con.execute(ais.actualizar(ctx, cont_libro, cont_libro.c.id == libro.id)
                    .values(plan_version=version))
    return libro


def _cuentas_por_rol(con: Connection, ctx: ais.ContextoNegocio,
                     roles: set[str]) -> dict[str, uuid.UUID]:
    filas = con.execute(
        ais.seleccionar(ctx, cont_cuenta_contable, cont_cuenta_contable.c.id,
                        cont_cuenta_contable.c.rol_cuenta_codigo)
        .where(cont_cuenta_contable.c.rol_cuenta_codigo.in_(roles),
               cont_cuenta_contable.c.acepta_movimientos.is_(True))
        .order_by(cont_cuenta_contable.c.codigo.desc())  # si hay dos, gana el código menor
    ).all()
    cuentas = {f.rol_cuenta_codigo: f.id for f in filas}
    faltan = roles - set(cuentas)
    if faltan:
        raise CuentaFaltante(f"Faltan cuentas para los roles {sorted(faltan)}.")
    return cuentas


def cuenta_de_rol(con: Connection, ctx: ais.ContextoNegocio, rol: str) -> uuid.UUID:
    """La cuenta de movimiento del plan del negocio para un rol (ej. CAJA)."""
    abrir_libro(con, ctx)  # negocios anteriores a la contabilidad: siembra su plan
    return _cuentas_por_rol(con, ctx, {rol})[rol]


# ------------------------------------------------------------------ reglas

def _regla(con: Connection, pais: str, evento: str, trat: Tratamiento, fecha: date):
    """La versión vigente a esa fecha; si no hay una para el tratamiento, la de `sin_separar`."""
    r = cont_cfg_regla_contable.c
    fila = con.execute(
        sa.select(r.codigo, r.version, r.lineas, r.tratamiento_iva, r.descripcion_simple)
        .where(r.pais_codigo == pais, r.tipo_evento == evento, r.vigente_desde <= fecha,
               r.tratamiento_iva.in_({trat.codigo, SIN_SEPARAR}))
        .order_by(sa.case((r.tratamiento_iva == trat.codigo, 0), else_=1), r.version.desc())
        .limit(1)
    ).first()
    if fila is None:
        raise ReglaFaltante(f"No hay regla contable para {evento}.")
    return fila


@dataclass(frozen=True)
class _Linea:
    rol: str
    debe: Decimal
    haber: Decimal
    concepto: str | None = None


def _guardar(con: Connection, ctx: ais.ContextoNegocio, *, fecha: date, descripcion: str,
             evento: str, lineas: list[_Linea], origen_tipo: str | None,
             origen_id: uuid.UUID | None, regla=None, tratamiento: str | None = None,
             reverso_de: uuid.UUID | None = None, cuentas: dict | None = None) -> uuid.UUID:
    debe = sum((linea.debe for linea in lineas), CERO)
    haber = sum((linea.haber for linea in lineas), CERO)
    if debe != haber or debe <= 0:
        raise AsientoDescuadrado(f"{evento}: debe {debe} y haber {haber}.")
    libro = abrir_libro(con, ctx)
    if cuentas is None:
        cuentas = _cuentas_por_rol(con, ctx, {linea.rol for linea in lineas})
    numero = libro.ultimo_numero + 1
    con.execute(ais.actualizar(ctx, cont_libro, cont_libro.c.id == libro.id)
                .values(ultimo_numero=numero, actualizado_por=ctx.usuario_id))
    asiento_id = uuid7()
    con.execute(ais.insertar(ctx, cont_asiento, {
        "id": asiento_id, "numero": numero, "fecha": fecha, "descripcion_simple": descripcion[:200],
        "tipo_evento": evento, "origen_tipo": origen_tipo, "origen_id": origen_id,
        "regla_codigo": None if regla is None else regla.codigo,
        "regla_version": None if regla is None else regla.version,
        "tratamiento_iva": tratamiento, "reverso_de_asiento_id": reverso_de,
    }))
    for linea in lineas:
        con.execute(ais.insertar(ctx, cont_asiento_linea, {
            "id": uuid7(), "asiento_id": asiento_id, "cuenta_contable_id": cuentas[linea.rol],
            "debe": linea.debe, "haber": linea.haber, "concepto": linea.concepto,
        }))
    return asiento_id


def registrar(con: Connection, ctx: ais.ContextoNegocio, *, evento: str, fecha: date,
              descripcion: str, importes: dict[str, Decimal],
              comodines: dict[str, str] | None = None,
              origen_tipo: str | None = None, origen_id: uuid.UUID | None = None,
              tratamiento: Tratamiento | None = None) -> uuid.UUID | None:
    """Aplica la regla del evento a los importes y guarda el asiento.

    Devuelve None si todas las líneas quedan en cero (por ejemplo, una venta de Q0 sin costo).
    """
    trat = tratamiento or Tratamiento(SIN_SEPARAR)
    pais = con.execute(
        sa.select(core_negocio.c.pais_codigo).where(core_negocio.c.id == ctx.negocio_id)
    ).scalar_one()
    regla = _regla(con, pais, evento, trat, fecha)
    comodines = comodines or {}
    lineas: list[_Linea] = []
    for definicion in regla.lineas:
        monto = centavos(importes.get(definicion["importe"], CERO))
        if monto == 0:
            continue
        if monto < 0:
            raise AsientoDescuadrado(f"{evento}: importe negativo en {definicion['importe']}.")
        rol = definicion["rol"]
        if rol.startswith("@"):
            rol = comodines[rol]
        es_debe = definicion["lado"] == "debe"
        lineas.append(_Linea(rol, monto if es_debe else CERO, CERO if es_debe else monto))
    if not lineas:
        return None
    return _guardar(con, ctx, fecha=fecha, descripcion=descripcion, evento=evento, lineas=lineas,
                    origen_tipo=origen_tipo, origen_id=origen_id, regla=regla,
                    tratamiento=regla.tratamiento_iva)


# ------------------------------------------------------------------ reversos

def asientos_vigentes(con: Connection, ctx: ais.ContextoNegocio, origen_tipo: str,
                      origen_id: uuid.UUID) -> list:
    """Asientos de una operación que no son reversos y que aún no se han revertido."""
    revertido = sa.alias(cont_asiento, "revertido")
    ya_revertidos = (
        sa.select(revertido.c.reverso_de_asiento_id)
        .where(revertido.c.negocio_id == ctx.negocio_id,
               revertido.c.reverso_de_asiento_id.is_not(None))
    )
    return con.execute(
        ais.seleccionar(ctx, cont_asiento, cont_asiento.c.id, cont_asiento.c.fecha,
                        cont_asiento.c.descripcion_simple)
        .where(cont_asiento.c.origen_tipo == origen_tipo, cont_asiento.c.origen_id == origen_id,
               cont_asiento.c.reverso_de_asiento_id.is_(None),
               cont_asiento.c.id.not_in(ya_revertidos))
        .order_by(cont_asiento.c.numero)
    ).all()


def revertir_origen(con: Connection, ctx: ais.ContextoNegocio, origen_tipo: str,
                    origen_id: uuid.UUID, descripcion: str) -> int:
    """Revierte cada asiento vigente de una operación. Devuelve cuántos revirtió."""
    vigentes = asientos_vigentes(con, ctx, origen_tipo, origen_id)
    for asiento in vigentes:
        filas = con.execute(
            ais.seleccionar(ctx, cont_asiento_linea, cont_asiento_linea.c.cuenta_contable_id,
                            cont_asiento_linea.c.debe, cont_asiento_linea.c.haber,
                            cont_asiento_linea.c.concepto)
            .where(cont_asiento_linea.c.asiento_id == asiento.id)
            .order_by(cont_asiento_linea.c.creado_en, cont_asiento_linea.c.id)
        ).all()
        # Las cuentas se usan por su id: el rol solo hace falta para armar las líneas.
        lineas = [_Linea(str(f.cuenta_contable_id), f.haber, f.debe, f.concepto) for f in filas]
        cuentas = {str(f.cuenta_contable_id): f.cuenta_contable_id for f in filas}
        _guardar(con, ctx, fecha=asiento.fecha, descripcion=descripcion, evento=EVENTO_REVERSO,
                 lineas=lineas, origen_tipo=origen_tipo, origen_id=origen_id,
                 reverso_de=asiento.id, cuentas=cuentas)
    return len(vigentes)
