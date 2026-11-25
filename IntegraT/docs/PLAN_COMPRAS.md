# Plan: compras a mano (Fase 2, quinto módulo del Grupo B)

> Decisiones del dueño (2026-11-24): comprar **insumos y mercadería para revender**, **proveedor opcional que
> se crea al vuelo**, **pagada al momento** (efectivo, tarjeta o transferencia) y de la factura solo la
> **fecha y un número opcional**. Lo fiscal (NIT, serie, IVA) espera la revisión del contador
> (`docs/REVISION_CONTADOR.md`). Modelo de referencia: `MODELO_DATOS.md` §5.2 y `DISENO_UX.md` §4
> (compras en 3 modos que terminan en la misma pantalla de revisión; este es el modo "a mano").

## Qué incluye
Registrar una compra con varias líneas (insumo, cantidad, unidad y **cuánto costó esa línea**), proveedor
opcional, fecha, medio de pago y número de factura opcional. Cada línea sube la existencia del insumo y
recalcula su costo promedio, usando los mismos movimientos del inventario (`entrada`). Historial de
compras, corrección por **anulación con reverso** y lista de proveedores.
**Mercadería para revender:** un producto que compras hecho (ej. una gaseosa) se maneja con el inventario
que ya existe, sin duplicarlo (ver abajo).

## Qué NO incluye (entregas siguientes)
Compra a crédito y cuentas por pagar · compra por plantilla y por foto + IA (llegan a la misma pantalla de
revisión) · NIT, serie e IVA acreditable · asientos contables · órdenes de compra y recepciones ·
varios almacenes.

## Reglas (las aplica la API)
- Una compra tiene al menos una línea. Cada línea: insumo vivo del negocio, cantidad > 0, unidad del
  mismo tipo que la del insumo (como en las recetas) y **costo total de la línea** ≥ 0 con 2 decimales.
  El total de la compra lo calcula la API (suma de líneas); la app solo lo muestra.
- La **fecha** es el día calendario que la persona indica (por defecto hoy en la zona del negocio); no
  puede ser de mañana en adelante. El **número de factura** es texto libre opcional (máx. 40).
- **Proveedor opcional.** Se elige uno existente o se crea al vuelo con solo el nombre (teléfono opcional).
  Nombre único por negocio entre vivos. Archivar un proveedor no toca sus compras.
- **Pagada al momento:** medio de pago efectivo, tarjeta o transferencia. No hay deuda.
- **La compra no es un gasto.** Alimenta el inventario y el costo; los gastos (renta, luz…) siguen aparte.
- **Inmutables:** una compra no se edita. Se **anula con motivo** y la API crea el reverso de cada línea
  (`reverso_compra`) en la misma transacción. El costo promedio se recalcula quitando esa compra; si ya se
  vendió parte de lo comprado el resultado es aproximado, y si la existencia queda en cero o menos el costo
  se conserva.
- `Idempotency-Key` al registrar: un doble toque no compra dos veces. `negocio_id` siempre del token.
- Permisos: dueño y administrador registran y anulan; dueño, administrador y contador ven. El cajero no
  ve compras ni proveedores.

## Mercadería para revender (sin duplicar el inventario)
Un producto que se compra hecho se modela con piezas que ya existen:
- Un **insumo** en unidades (UN) con el mismo nombre, ligado al producto por `ops_insumo.item_id`.
- Una **receta automática** de 1 UN de ese insumo por cada unidad vendida.
Así comprar sube la existencia, vender la descuenta (y la anulación la devuelve), el costo promedio es el
costo del producto y el costo por platillo alimentará el precio sugerido, sin tocar ventas ni recetas.
- En el producto: "Lo compro ya hecho para revenderlo" crea o quita ese par insumo + receta. No cambia
  el precio de venta.
- Archivar el producto archiva su insumo ligado; el insumo ligado no se puede editar a mano como receta.

## Modelo de datos

| Migración | Tabla | Columnas | Notas |
|---|---|---|---|
| `0011` | `ops_proveedor` | id, negocio_id, nombre, telefono, auditoría | Nombre único por negocio entre vivos. |
| `0011` | `ops_compra` | id, negocio_id, proveedor_id (nulo), fecha (DATE), numero_factura (nulo), medio_pago, total, estado (`registrada`/`anulada`), anulada_en/por, motivo_anulacion, nota, auditoría | Inmutable salvo anulación, como `ops_venta`. |
| `0011` | `ops_compra_linea` | id, negocio_id, compra_id, insumo_id, nombre (congelado), cantidad, unidad_codigo, costo_total, auditoría | |
| `0011` | `ops_movimiento_inventario` | se amplía el CHECK de `tipo` con `reverso_compra` | Origen: `compra` + id de la compra. |
| `0012` | `ops_insumo` | + `item_id` (nulo, FK a `ops_item`) | Marca la mercadería de un producto. |

## API (`/v1`)

| Método y ruta | Qué hace |
|---|---|
| `GET/POST /proveedores`, `PATCH/DELETE /proveedores/{id}` | Proveedores del negocio. |
| `POST /compras` | Registra una compra (con `Idempotency-Key`); acepta un proveedor nuevo en el mismo cuerpo. |
| `GET /compras?mes=AAAA-MM` | Compras del mes con su total. |
| `GET /compras/{id}`, `POST /compras/{id}/anular` | Detalle y anulación con motivo. |
| `PUT /items/{id}/mercaderia` | Activa o quita la mercadería de un producto (crea o archiva insumo + receta). |

El checklist del restaurante y de la tienda en línea podrán ganar el paso "Registra tu primera compra"
(`compras_minimo`), junto con su botón en la app.

## App (sección "Más" → "Compras y proveedores"; acción rápida "Registrar compra")
1. Registrar compra: proveedor (opcional) → agregar insumos con cantidad, unidad y cuánto costó → medio de
   pago y fecha → **pantalla de revisión** con el total → Guardar. Es la pantalla a la que luego llegarán la
   plantilla y la foto con IA.
2. Historial del mes con total, detalle de cada compra y "Anular esta compra" con motivo.
3. Proveedores: lista y alta rápida.
4. En la ficha del producto: "Lo compro ya hecho para revenderlo".

## Orden de trabajo (me detengo tras cada paso para que pruebes)

| Paso | Contenido | Cómo lo pruebas |
|---|---|---|
| P1 | Migración `0011`, API de proveedores y compras (registrar, listar, ver, anular con reverso) y checklist. | `pytest` + `/docs` |
| P2 | Migración `0012` y API de mercadería (insumo ligado + receta automática; archivar el producto). | `pytest` + `/docs` |
| P3 | App: registrar compra con revisión, proveedores al vuelo, con API falsa y pruebas de navegador. | Pruebas R + recorrido visual |
| P4 | App: historial, detalle y anulación; mercadería en la ficha del producto; checklist y pulido en 390 px. | Recorrido en navegador |

## Estado (2026-11-24): P1 a P4 hechos
- API: `0011` (proveedores, compras, líneas y `reverso_compra`) y `0012` (`ops_insumo.item_id`); 250 pruebas.
- App: registrar con revisión, mes, detalle, anulación, proveedores (lista y alta) y mercadería en el producto.
- Checklist: paso "Registra tu primera compra" (`compras_minimo`) en restaurante y tienda en línea.
- Pendiente a propósito: editar o archivar un proveedor desde la app (la API ya lo permite), compra por
  plantilla y por foto + IA, crédito a proveedores, NIT/serie/IVA.
- Se evitó un bloqueo cruzado de MySQL: los insumos se bloquean ANTES de insertar las líneas de la compra
  (insertar una línea toma un candado de lectura sobre el insumo y luego se pediría el de escritura).
