# Plan: caja del día y dinero del dueño (Fase 2, séptimo módulo del Grupo B)

> Decisiones del dueño (2026-11-25): **abrir y cerrar el día** (se puede vender sin abrir), **aporte y retiro
> del dueño** (en efectivo o banco) y al cerrar un **resumen del día** con historial de cierres.
> Modelo de referencia: `MODELO_DATOS.md` §5.3 (`sesion_caja`), `REVISION_CONTADOR.md` §9 y
> `PLAN_CONTABILIDAD.md`. Lo contable sigue [verificar] (D-12).

## Qué incluye
- **Abrir la caja:** "¿Con cuánto efectivo abres?". Una sola caja abierta por negocio.
- **Cerrar el día:** la API calcula cuánto efectivo **debería** haber; la persona cuenta y anota lo que hay;
  la diferencia queda como **faltante** o **sobrante**, con su asiento. Resumen del día e historial de cierres.
- **Dinero del dueño:** "Pusiste dinero en el negocio" (aporte) y "Sacaste dinero para ti" (retiro), en
  efectivo o banco. El retiro **no es un gasto**: no baja "lo que te queda".
- "Cerrar el día" en las acciones rápidas (➕) deja de decir "pronto".

## Qué NO incluye (entregas siguientes)
Varias cajas o turnos por negocio · arqueo por denominación (billetes y monedas) · depósitos de efectivo al
banco · faltante atribuido a un empleado · obligar a abrir la caja para vender · propinas.

## Reglas (las aplica la API)
- **Efectivo esperado** = monto de apertura + lo que entró y salió de la cuenta de **Caja** en los asientos
  registrados desde que se abrió (ventas en efectivo y sus anulaciones, gastos, compras y compras anotadas en
  el inventario, aportes y retiros en efectivo). Sale de los libros: una sola fuente de verdad.
- El resumen del día separa ese movimiento por origen (ventas, gastos, compras, inventario, dueño) y muestra
  también lo vendido con tarjeta y transferencia (no pasa por la caja).
- **Cierre:** diferencia = contado − esperado. Faltante: Debe `DIFERENCIA_CAJA` / Haber `CAJA` (es un gasto).
  Sobrante: Debe `CAJA` / Haber `OTROS_INGRESOS`. Sin diferencia, no hay asiento. Un cierre no se edita.
- La apertura no genera asiento (se cuenta lo que hay; si no coincide con los libros, la diferencia aparece
  en el cierre).
- **Aporte:** Debe `CAJA` o `BANCO` / Haber `CAPITAL`. **Retiro:** Debe `RETIROS_PROPIETARIO` / Haber `CAJA`
  o `BANCO`. Fecha por defecto hoy, nunca futura. Borrar un movimiento del dueño crea su reverso.
- Plan de cuentas versión 2: agrega `6191 Faltantes de caja` (`DIFERENCIA_CAJA`). Los negocios que ya tienen
  plan reciben las cuentas nuevas de la plantilla la próxima vez que se abre su libro.
- `Idempotency-Key` al cerrar y al anotar un movimiento del dueño; `negocio_id` siempre del token.
- Permisos: abrir y cerrar, dueño, administrador y cajero. Movimientos del dueño: los anota y borra solo el
  dueño; los ven dueño, administrador y contador.

## Modelo de datos (migración `0014`)

| Tabla | Columnas | Notas |
|---|---|---|
| `ops_sesion_caja` | negocio_id, fecha (local), abierta_en, monto_apertura, estado (`abierta`/`cerrada`), cerrada_en, cerrada_por, efectivo_esperado, efectivo_contado, diferencia, nota, auditoría | Una abierta por negocio (lo controla la API con bloqueo). |
| `ops_movimiento_dueno` | negocio_id, tipo (`aporte`/`retiro`), monto, medio (`efectivo`/`banco`), fecha, nota, auditoría | Borrado lógico + reverso contable. |

## API (`/v1`)

| Método y ruta | Qué hace |
|---|---|
| `GET /caja` | La caja abierta con su resumen en vivo (o nada) y el último cierre. |
| `POST /caja/abrir` | Abre la caja con el monto de apertura (409 si ya hay una abierta). |
| `POST /caja/cerrar` | Cierra con el efectivo contado (con `Idempotency-Key`); devuelve el resumen del cierre. |
| `GET /caja/cierres?mes=AAAA-MM` | Historial de cierres del mes. |
| `GET/POST /dueno`, `DELETE /dueno/{id}` | Movimientos del dueño del mes; anotar (con `Idempotency-Key`) y borrar. |

## App
1. **Caja del día** (Más → "Caja del día" y ➕ → "Cerrar el día"): abrir con el monto; con la caja abierta,
   el efectivo que debería haber y el resumen en vivo; "Cerrar el día" → contar → revisión con la diferencia
   → confirmar → resumen del cierre. Historial de cierres del mes.
2. **Tu dinero y el negocio** (Más): lista del mes y "Pusiste dinero" / "Sacaste dinero" con monto, medio,
   fecha y nota.

## Orden de trabajo

| Paso | Contenido | Cómo lo pruebas |
|---|---|---|
| K1 | Migración `0014`, semillas (rol, cuenta y reglas), actualización del plan de cuentas, API del dueño. | `pytest` |
| K2 | API de caja: abrir, resumen en vivo, cerrar con diferencia y asiento, historial. | `pytest` |
| K3 | App: Caja del día y Tu dinero y el negocio, con API falsa y pruebas de navegador. | Pruebas R + recorrido visual |

## Estado (2026-11-25): K1 a K3 hechos (sin commit, a la espera de tu prueba)
- API: migración `0014`, plantilla del plan v2 (`6191 Faltantes de caja`, que los planes anteriores reciben al
  abrir su libro), reglas de aporte, retiro, faltante y sobrante; `/v1/caja` y `/v1/dueno`. 294 pruebas.
- App: "Caja del día", "Tu dinero y el negocio" y ➕ "Cerrar el día"; pruebas de navegador en `test-caja.R`.
- Nuevo `integrat/idempotencia.py`: la `Idempotency-Key` en un solo lugar para los comandos nuevos.
