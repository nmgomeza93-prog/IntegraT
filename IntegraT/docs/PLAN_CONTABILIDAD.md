# Plan: motor contable (Fase 2, sexto módulo del Grupo B)

> Decisiones del dueño (2026-11-25): **asientos automáticos de todo lo ya hecho** (ventas, gastos, compras e
> inventario), **IVA según el régimen** (con reglas configurables, a validar por el contador), **tarjeta y
> transferencia van directo a Banco** y el usuario ve un **resumen del mes en el Inicio** (sin jerga).
> Modelo de referencia: `MODELO_DATOS.md` §5.5, `REVISION_CONTADOR.md` §5, §6 y §13 y `CONVENCIONES_BD.md`.
> Todo lo contable y fiscal sigue **[verificar]** hasta la revisión del contador (D-12).

## Qué incluye
- **Plan de cuentas por negocio**, copiado de una plantilla por país y tipo de negocio al crear el negocio
  (y la primera vez que se usa, para los negocios que ya existían).
- **Asientos en partida doble** generados por la API **en la misma transacción** de cada operación:
  venta, anulación de venta, gasto (anotar, corregir, archivar), compra y su anulación, y los movimientos
  de inventario hechos a mano (lo que ya tenías, compra anotada, pérdida, corrección).
- **Reglas configurables** (`cont_cfg_regla_contable`): evento → líneas por **rol de cuenta** → cuenta del
  plan del negocio. El código nunca usa códigos de cuenta.
- **Régimen de IVA del negocio**: general, pequeño contribuyente o "todavía no sé". Se elige en la app.
- **"¿Te dieron factura?"** en los gastos (solo se pregunta en el régimen general).
- **Resumen del mes** en el Inicio: Lo que vendiste, Lo que te costó, Lo que gastaste y **Lo que te queda**.
- Para el contador (solo API): libro diario del mes y saldos por cuenta.

## Qué NO incluye (entregas siguientes)
Periodos y cierre de mes · provisión mensual del 5 % del pequeño contribuyente y liquidación de IVA ·
ISR · aporte y retiro del dueño · caja (apertura y cierre, faltantes y sobrantes) · comisiones de tarjeta ·
crédito a clientes y proveedores · editar el plan de cuentas desde la app · consolidado por titular (NIT) ·
regenerar asientos de operaciones anteriores a este módulo.

## Reglas (las aplica la API)
- **Inmutables.** Un asiento no se edita ni se borra: se corrige con un **reverso** (mismas líneas con debe y
  haber invertidos, misma fecha que el original, `reverso_de_asiento_id`). La API **valida que cuadre**
  (suma del debe = suma del haber, > 0) antes de guardarlo; si no cuadra, se revierte toda la operación.
- **Fecha** del asiento = fecha de la operación en el calendario del negocio (la venta: el día local de su
  hora; el gasto y la compra: su fecha). **Número** consecutivo por negocio (`cont_libro`).
- **Medio de pago → rol:** efectivo → `CAJA`; tarjeta y transferencia → `BANCO`.
- **Tratamiento del IVA** (sale del régimen del titular; sin titular o sin régimen = "sin separar"):
  - `separado` (régimen general, `usa_credito_fiscal`): la tasa sale de `fiscal_cfg_regimen.parametros.tasa`
    (12 %, incluida en el precio). `base = total / (1 + tasa)` redondeada a centavos; `IVA = total − base`.
    Ventas → IVA por pagar. Compras con número de factura y gastos con factura → IVA por cobrar; la
    **compra entra al inventario al costo sin IVA** (el costo promedio y el costo por platillo quedan netos).
  - `sin_separar` (pequeño contribuyente y negocios sin régimen): todo el monto es venta, costo o gasto.
  - Un cambio de régimen aplica a las operaciones **siguientes**; lo ya registrado no cambia.
- **Costo de lo vendido:** lo que la venta sacó del inventario (consumos al costo promedio). Va a
  `INVENTARIO_MERCADERIA` si el insumo es mercadería de un producto y a `INVENTARIO_INSUMOS` si no.
  Un ítem sin receta no tiene costo (se avisa en la ficha, como hoy).
- **Gastos:** la cuenta sale del rol de su categoría (`GASTO_VARIOS` si no tiene). Corregir un gasto crea el
  reverso del asiento vigente y uno nuevo; archivarlo, solo el reverso.
- **Inventario a mano:** "Lo que ya tenías" = aporte del dueño (`CAPITAL`); "Anoté una compra" = compra en
  efectivo sin factura (`CAJA`); pérdida y corrección hacia abajo → `MERMA`; corrección hacia arriba →
  `OTROS_INGRESOS`. Los movimientos sin valor (costo 0) no generan asiento.
- `negocio_id` siempre del token; todo pasa por `db.aislamiento`.
- Permisos: el resumen del mes lo ven dueño, administrador y contador; el libro diario y los saldos, dueño,
  administrador y contador; el régimen lo cambia solo el dueño.

## Modelo de datos (migración `0013`)

| Tabla | Columnas | Notas |
|---|---|---|
| `cont_cfg_rol_cuenta` | codigo (PK), descripcion_simple, naturaleza (`deudora`/`acreedora`) | Global (semillas). |
| `cont_cfg_plantilla_plan_cuentas` | pais_codigo + tipo_negocio_codigo (PK), version, contenido JSON | Lista de cuentas con código, nombre, nombre simple, tipo, padre y rol. |
| `cont_cfg_regla_contable` | codigo (PK), pais_codigo, tipo_evento, tratamiento_iva (`separado`/`sin_separar`), version, vigente_desde, lineas JSON | Cada línea: `lado`, `rol` (o `@pago`, `@gasto`) e `importe` (`total`, `base`, `iva`, `costo`…). Las líneas en cero se omiten. |
| `cont_libro` | negocio_id (único), ultimo_numero, plan_version, auditoría | Un renglón por negocio: numera los asientos y marca el plan sembrado. Se bloquea **al final** de cada operación (sin bloqueos cruzados). |
| `cont_cuenta_contable` | negocio_id, codigo, nombre, nombre_simple, tipo, naturaleza, padre_id, acepta_movimientos, rol_cuenta_codigo, auditoría | `uq (negocio_id, codigo)`. |
| `cont_asiento` | negocio_id, numero, fecha, descripcion_simple, tipo_evento, origen_tipo, origen_id, regla_codigo, regla_version, tratamiento_iva, reverso_de_asiento_id, creado_en/por | **Inmutable.** `uq (negocio_id, numero)`. |
| `cont_asiento_linea` | negocio_id, asiento_id, cuenta_contable_id, debe, haber, concepto, creado_en/por | **Inmutable.** Debe o haber, nunca ambos. |
| `ops_gasto` | + `con_factura` (bool, defecto 0) | Solo cuenta en el régimen general. |

## API (`/v1`)

| Método y ruta | Qué hace |
|---|---|
| `PUT /negocios/{id}/impuestos` | Fija el régimen de IVA: `general`, `pequeno` o `no_se` (abre el titular si no existe). `GET /negocios/{id}` devuelve `regimen_iva`. |
| `GET /resultados?mes=AAAA-MM` | Resumen del mes desde los asientos: vendiste, costo de lo vendido, lo que se perdió, gastaste, otros ingresos y te queda. |
| `GET /asientos?mes=AAAA-MM` | Libro diario del mes con sus líneas (para el contador). |
| `GET /cuentas` | Plan de cuentas con su saldo (para el contador). |
| `POST /gastos`, `PATCH /gastos/{id}` | + `con_factura`. |

## App
1. **Inicio:** tarjeta "Tu mes" con Lo que vendiste, Lo que te costó, Lo que gastaste y Lo que te queda (verde
   si ganas, rojo si pierdes). En el régimen general dice "sin IVA".
2. **Más → "Tus impuestos":** ¿Cómo pagas impuestos? (Régimen general · Pequeño contribuyente · Todavía no sé).
3. **Gastos:** interruptor "Me dieron factura" (solo en el régimen general).

## Orden de trabajo

| Paso | Contenido | Cómo lo pruebas |
|---|---|---|
| C1 | Migración `0013`, semillas (roles, plantillas, reglas), motor (sembrar plan, aplicar regla, cuadre, reverso) y régimen de IVA. | `pytest` |
| C2 | Asientos de ventas, gastos, compras e inventario, con pruebas de cuadre, reversos y aislamiento. | `pytest` |
| C3 | API de lectura: resultados del mes, libro diario y saldos. | `pytest` + `/docs` |
| C4 | App: "Tu mes" en el Inicio, "Tus impuestos" y "Me dieron factura", con API falsa y pruebas de navegador. | Pruebas R + recorrido visual |

## Estado (2026-11-25): C1 a C4 hechos (sin commit, a la espera de tu prueba)
- API: migración `0013` (roles, plantillas, reglas, libro, plan por negocio, asientos y `ops_gasto.con_factura`),
  semillas `db/semillas/07_contabilidad_gt.yaml`, motor y eventos conectados a ventas, gastos, compras e
  inventario; `PUT /negocios/{id}/impuestos`, `GET /resultados`, `GET /asientos` y `GET /cuentas`.
  280 pruebas (30 nuevas en `tests/test_contabilidad.py`, incluida una que verifica que **ningún asiento de
  la base descuadre** después de todas las demás).
- App: "Tu mes" en el Inicio, "Tus impuestos" en Más y "Me dieron factura con mi NIT" en los gastos del
  régimen general; API falsa y pruebas de navegador al día (`test-contabilidad.R`).
- Candados: el libro (`cont_libro`) se bloquea al final de cada operación. Un negocio nuevo inserta su libro
  directamente; uno anterior a la contabilidad lo crea serializado por la fila del negocio (dos búsquedas con
  bloqueo de una fila inexistente se traban en MySQL por los candados de "hueco").
- Las operaciones registradas **antes** de la migración `0013` no tienen asientos (no se regeneran).
- Pendiente a propósito: lo listado en "Qué NO incluye". La tarjeta "Hoy" del Inicio sigue siendo de muestra.
