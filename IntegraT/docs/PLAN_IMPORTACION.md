# Plan: importaciones con la plantilla de factura — paso I2 de `PROPUESTA_IMPORTACIONES.md`

> Decisiones del dueño (2026-11-25): **se mantiene la plantilla actual** (`Factura_camino`: una fila
> `ENCABEZADO` + filas `PRODUCTO`) como la ruta para cargar productos; **moneda** de `moneda_codigo` y
> conversión con lo que cobró la tarjeta en Q; **variantes de verdad** (mismo `skc` con otra talla/color);
> **categoría por palabras clave**, editable; **atributos según la categoría**; **IVA y aranceles del courier
> = costo** [verificar con el contador].

## Flujo
1. **Subir la plantilla** (Compras → "Importación"): la API la lee y devuelve una **vista previa** sin guardar
   nada: encabezado (plataforma, factura, orden, fecha, moneda, total y cargos), líneas y su **cuadre**
   (líneas + garantía + importación + otros = total), y por línea: **nombre corto** sugerido, **categoría**
   sugerida, si el producto **ya existe** (por código de variante o por nombre) y su variante (talla/color).
2. **Revisión:** "¿Cuánto te cobró tu tarjeta en quetzales?" (de ahí sale el tipo de cambio; si no, el de la
   plantilla), medio de pago, y por línea el nombre y la categoría (una o varias a la vez). Confirmar crea la
   importación **en camino** con su asiento (Mercadería en camino / Banco o Caja).
3. **"Me llegó el paquete":** cobro del courier y envío local en Q, guía, y qué llegó de cada línea (por
   defecto todo). Confirmar:
   - crea los productos nuevos con sus variantes (como mercadería) y su categoría (la sugerida se crea si no
     existe, con sus atributos);
   - reparte courier + envío local por valor y suma el inventario de cada variante al **costo puesto en
     Guatemala**;
   - lo que no llegó se da por perdido (Mercadería en camino → Merma);
   - asiento: Inventario / Mercadería en camino + Caja o Banco (courier).
4. La importación queda con su **rastreo** (plataforma, factura, orden, guía, fechas, tipo de cambio, cargos y
   costo por línea) y cada producto con su **precio sugerido** por variante.

## Reglas (las aplica la API)
- Tipo de cambio = cobro en Q ÷ total de la factura (8 decimales). Sin cobro, el `tipo_cambio` de la plantilla.
- Prorrateo **por valor** (precio × cantidad): cargos de la factura al pedir; courier y envío local al recibir,
  entre lo que llegó. El último renglón absorbe el redondeo: la suma cuadra al centavo.
- Costo unitario de una línea = (su parte de la factura en Q + su parte del courier) ÷ unidades recibidas.
- El cuadre de la factura es un **aviso** (no bloquea): la persona puede confirmar si la diferencia es suya.
- Máximo 500 líneas por plantilla; `proveedor_id` (de la v1) se ignora; filas `PRODUCTO` sin `skc` se aceptan
  (se agrupan por nombre).
- Importación en camino: se puede **anular** (reverso del asiento). Recibida: no se edita.
- `Idempotency-Key` al confirmar y al recibir; `negocio_id` siempre del token.

## Modelo de datos (migración `0017`)
| Tabla | Columnas |
|---|---|
| `ops_importacion` | plataforma, numero_factura, numero_orden, fecha_factura, moneda_codigo, total_factura, garantia_envio, costo_importacion, otros_cobros, cobro_q, tipo_cambio, medio_pago, estado (`en_camino`/`recibida`/`recibida_parcial`/`anulada`), recibida_en, guia, courier_q, envio_local_q, medio_pago_courier, nota, anulada_en/por, motivo_anulacion, auditoría |
| `ops_importacion_linea` | importacion_id, codigo (skc), descripcion, nombre, categoria_nombre, atributos (JSON), item_id / item_variante_id (si ya existía; o los creados al recibir), cantidad, precio_unitario (moneda), cargos (moneda), costo_pedido_q, cantidad_recibida, courier_q, costo_unitario_q, auditoría |
| `cat_moneda` | + MXN, EUR, CNY |
| plan de cuentas v3 | + `1109 Mercadería en camino` (`INVENTARIO_TRANSITO`) |

## API (`/v1`)
| Ruta | Qué hace |
|---|---|
| `POST /importaciones/vista-previa` | Sube la plantilla (xlsx o csv); devuelve la vista previa, sin guardar. |
| `POST /importaciones` | Confirma (JSON de la revisión): queda en camino. |
| `GET /importaciones`, `GET /importaciones/{id}` | En camino y recibidas, con su rastreo. |
| `POST /importaciones/{id}/recibir` | Me llegó el paquete. |
| `POST /importaciones/{id}/anular` | Anula una en camino. |

## Orden de trabajo
| Paso | Contenido |
|---|---|
| M1 | Lector de la plantilla y vista previa (nombre corto, categoría, coincidencias, variantes, cuadre). |
| M2 | Importación en camino, recepción con prorrateo, productos y variantes, inventario, asientos, anulación. |
| M3 | App: subir, revisar, en camino, "Me llegó el paquete", detalle con rastreo. |

## Estado (2026-11-25): M1 a M3 hechos
- API: migración `0017`, monedas MXN/EUR/CNY, plan de cuentas v3 (`1109 Mercadería en camino`), reglas
  `IMPORTACION_PEDIDO` y `IMPORTACION_RECEPCION`; `/v1/importaciones` (vista previa, confirmar, listar, ver,
  recibir, anular). Dependencias nuevas: `openpyxl` y `python-multipart`. Pruebas en
  `tests/test_importaciones.py` (con una plantilla inventada del mismo formato).
- Probado con la plantilla real del dueño (factura SHEIN en MXN, 20 líneas): cuadra al centavo, 18 productos
  (Dream Adore con tallas S, M y L), pijamas en "Ropa de dormir" y cámaras en "Electrónica" (solo color).
- Categoría sugerida: gana la palabra clave que aparece primero en la descripción (lo que el producto es).
- App: Más → "Importaciones (SHEIN, TEMU…)" (`mod_importaciones.R`): subir, revisar (nombre y categoría
  editables, cobro de la tarjeta en Q, medio de pago), en camino, detalle con rastreo, "Me llegó el paquete"
  (courier, envío local, guía, qué llegó) y anular. Pruebas en `test-importaciones.R`.
- Pendiente a propósito: recibir en varias entregas (hoy una sola recepción; lo que no llega se da por
  perdido), prorrateo por peso, lectura del PDF con IA (I3).

## Siguiente (2026-11-25, pedido del dueño): varias entregas y reparto por peso
- **Varias entregas:** cada "Me llegó el paquete" es una **entrega** (`ops_importacion_recepcion`: fecha,
  guía, courier, envío local, medio de pago) con lo que llegó de cada línea en ella
  (`ops_importacion_recepcion_linea`). La importación queda **"Llegando"** mientras falte algo, y se cierra
  cuando llega todo o cuando la persona dice **"lo que falta ya no va a llegar"** (eso se da por perdido:
  Mercadería en camino → Merma). Cada entrega crea los productos que llegan en ella, reparte su courier
  entre lo que llegó en ella y genera su asiento.
- **Reparto por peso:** columna opcional `peso` en la plantilla (cualquier unidad: solo importa la
  proporción; alias `peso_kg`, `peso_lb`, `weight`). Al recibir se elige **por valor** (por defecto) o
  **por peso** (solo si todas las líneas que llegan traen peso). Los cargos de la factura siguen por valor.
- Migración `0018`: estado + `llegando`; líneas + `peso`, `cantidad_perdida`; tablas de entregas.
