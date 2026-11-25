# Plan: gastos (Fase 2, tercer módulo del Grupo B)

> Decisiones del dueño (2026-11-24): **anotar gastos y verlos por mes** (sin recurrentes, fotos ni
> impuestos todavía), **categorías sugeridas por tipo de negocio y editables**, **editar y archivar**
> (con `version`) y **medio de pago**: efectivo, tarjeta o transferencia.
> Modelo de referencia: `MODELO_DATOS.md` §5.3 (`categoria_gasto`, `gasto`) y `DISENO_UX.md`.

## Qué incluye
Registrar un gasto (monto, categoría, fecha, medio de pago, nota), verlos por mes con total, total
por categoría (con porcentaje) y total de fijos y variables, corregirlos y archivarlos. El paso
"Anota tus gastos fijos" del checklist se marca solo.

## Qué NO incluye (entregas siguientes)
Gastos recurrentes con recordatorio · foto de respaldo (R2) · documento fiscal e IVA
acreditable/deducible · caja y cuadre · asientos contables · compras de mercadería (son otro
módulo: "Registrar compra" alimenta el costo, no es un gasto). Esas columnas llegarán con su migración.

## Reglas (las aplica la API)
- El monto es mayor que 0 con 2 decimales. Dinero siempre como texto decimal.
- La **fecha** es el día calendario que la persona indica (por defecto hoy, en la zona horaria del
  negocio); no puede ser de mañana en adelante.
- Toda categoría tiene un nombre único por negocio y puede marcarse como **fija** (renta, sueldos)
  o variable; el gasto hereda `es_fijo` de su categoría al crearse y no cambia solo después.
- Archivar una categoría **no toca** los gastos que ya la usan (siguen mostrando su nombre); solo
  deja de ofrecerse para gastos nuevos.
- Editar usa `version`: si otra pestaña cambió el gasto, avisa en vez de pisarlo. Archivar es
  borrado lógico, nunca se borra la fila. Cuando exista el motor contable, un gasto ya contabilizado
  se corregirá con reverso (`CLAUDE.md`).
- `Idempotency-Key` al crear: un doble toque no anota el gasto dos veces.
- Permisos: dueño y administrador anotan y corrigen; dueño, administrador y contador ven. El cajero
  no ve los gastos del negocio (sueldos, renta).
- Las categorías de ejemplo vienen de la plantilla `categorias_gasto` del tipo de negocio y se
  copian al crear el negocio (incluyendo su rol de cuenta contable para el motor futuro).

## Modelo de datos (migración `0008`)

| Tabla | Columnas | Notas |
|---|---|---|
| `ops_categoria_gasto` | id, negocio_id, nombre, icono, es_fijo, rol_cuenta_codigo, orden, auditoría | El rol de cuenta lo usará el motor contable. |
| `ops_gasto` | id, negocio_id, categoria_gasto_id, fecha (DATE), monto, medio_pago, descripcion, es_fijo, auditoría | |

## API (`/v1`)

| Método y ruta | Qué hace |
|---|---|
| `GET/POST /gastos/categorias`, `PATCH/DELETE /gastos/categorias/{id}` | Categorías de gasto del negocio. |
| `POST /gastos` | Anota un gasto. |
| `GET /gastos?mes=AAAA-MM` | Gastos del mes (por defecto, el actual) + resumen. |
| `GET/PATCH/DELETE /gastos/{id}` | Ver, corregir (con `version`) y archivar. |

El checklist gana la regla `gastos_fijos_minimo` (paso "Anota tus gastos fijos").

## App (sección "Más" → "Gastos")
1. Lista del mes con total, por categoría (barras con porcentaje) y navegación entre meses.
2. Agregar: monto → categoría → (medio de pago, fecha y nota opcionales) → Guardar. Máximo 3 toques.
3. Ficha: editar y archivar con confirmación. Crear categorías desde el formulario.
4. Acceso rápido también desde la hoja "¿Qué quieres hacer?" (💸 Registrar gasto).

## Orden de trabajo (me detengo tras cada paso para que pruebes)

| Paso | Contenido | Cómo lo pruebas |
|---|---|---|
| G1 | Migración `0008`, API de gastos y categorías, regla del checklist, pruebas. | `pytest` + `/docs` |
| G2 | App: lista del mes, agregar, editar y archivar, con API falsa y pruebas de navegador. | Pruebas R + recorrido visual |
| G3 | Categorías desde la app, acceso rápido, checklist y pulido en 390 px. | Recorrido en navegador |
