# Propuesta: importaciones (compras SHEIN/TEMU por casillero) en IntegraT

> Caso real del dueño (2026-11-25): una compra de hasta 40 productos en SHEIN, que sale de México (u otro
> país), pasa por un casillero/courier y entra a Guatemala. La factura de SHEIN más el cobro del courier
> forman el inventario; de ahí sale el precio sugerido; queda el rastreo de la importación y los productos
> listos para vender. Referencia (solo lectura): v1 `modules/mod_compras*.R`, `R/compras_import_transito.R`,
> `R/db_sp_embarques.R`.

## 1. Cómo lo resuelve la v1

| Paso | En la v1 | Lo bueno | Lo que no conviene repetir |
|---|---|---|---|
| **Factura en camino** | Encabezado (proveedor, número de factura, orden de la plataforma, fecha, moneda MXN/USD, tipo de cambio, total, garantía de envío, costo de importación, otros cobros) + líneas (SKC, cantidad, precio FOB, descripción, nombre, talla, color, precio de venta). | Captura todo lo que trae la factura. | Formulario largo de escritorio con selectize y tablas. |
| **Plantilla CSV/XLSX** | Filas `ENCABEZADO` + `PRODUCTO`, alias de columnas, hasta 2,000 líneas, validación con "semáforo". | Carga masiva de 40+ líneas. | Dos tipos de fila en la misma hoja: confunde al usuario. |
| **Tipo de cambio** | Se calcula desde **lo que realmente cobró el banco/tarjeta en quetzales** y debe "cuadrar". | **Excelente idea**: el usuario no tiene que saber el tipo de cambio. | — |
| **Prorrateo** | "Otros cobros" de la factura por valor FOB; al recibir, courier + envío a Guatemala por valor de la factura en Q (el último renglón absorbe el redondeo). | Costo puesto en bodega correcto. | — |
| **Recibir paquete (casillero)** | Asistente de 3 pasos: datos del paquete (casillero, guía, cobro del courier, envío), qué llegó de cada factura (recepción parcial) y resumen. | Recepción parcial; rastreo por guía. | Mucho estado de navegación cruzado (30+ banderas). |
| **Precio** | Factor fijo (×3) sobre el costo, más IVA, redondeado. | Precio listo al recibir. | Un factor fijo no considera el margen real ni el régimen. |
| **Variantes** | SKC del proveedor + talla + color → SKC único. | Ropa por talla/color. | Atado a SHEIN/TEMU y a ropa (ENUMs y columnas por canal). |

## 2. Cómo encaja en IntegraT (ya tenemos casi todas las piezas)

- **Compras** con pantalla de revisión (los 3 modos de `DISENO_UX.md` §4 terminan ahí) → la importación es
  una compra más, con dos momentos: **pedida (en camino)** y **recibida**.
- **Mercadería para revender** (insumo ligado al producto, receta de 1 unidad) → cada línea de la factura
  entra al inventario de su producto, sin duplicar nada.
- **Costo promedio ponderado** → el costo puesto en Guatemala (factura + envío + courier, prorrateado)
  alimenta el costo del producto.
- **Precio sugerido** (`integrat/precios.py`) → al recibir, cada producto trae su sugerido con el margen del
  negocio (o el suyo), con IVA si corresponde; "Usar todos los sugeridos" en un toque. Reemplaza al factor ×3.
- **Motor contable** → nuevo rol `INVENTARIO_TRANSITO` ("Mercadería en camino"): al pagar, Debe Mercadería
  en camino / Haber Banco; al recibir, Debe Inventario / Haber Mercadería en camino + el cobro del courier.
- **D-06 / R-04** (costo de la IA prorrateado como un flete) usa el mismo prorrateo.

## 3. Flujo propuesto (celular, una pantalla por paso)

**A. "Hice un pedido" (Compras → Importación)**
1. **Plataforma y pedido:** SHEIN, TEMU, Amazon u otra; número de orden (opcional); fecha.
2. **Productos:** tres formas que llegan a la misma revisión:
   - **Subir la factura (PDF o foto) con IA** → la IA lee las 40 líneas (Fase 3; opcional y con costo
     visible, regla 7 de `CLAUDE.md`).
   - **Plantilla Excel** sencilla: **una fila por producto**, sin filas de encabezado
     (`nombre`, `cantidad`, `precio`, y opcionales `talla`, `color`, `codigo`, `precio_venta`).
   - **A mano**, línea por línea (para pedidos chicos).
3. **Lo que pagaste:** total de la factura en su moneda (MXN/USD) y **"¿Cuánto te cobró tu tarjeta en
   quetzales?"**. La API calcula el tipo de cambio y convierte todo a Q (idea de la v1).
4. **Revisión:** cada línea con su producto: **"nuevo"** (se crea solo, como mercadería) o **"ya lo tienes"**
   (coincidencia por código o nombre, editable). Envío y cargos de la factura ya prorrateados.
   → Queda **"En camino"**: aparece en Compras con su número de orden y los días transcurridos.

**B. "Me llegó el paquete" (desde la importación en camino)**
1. **Cobro del courier/casillero** en Q (y envío local, si hubo), número de guía (opcional).
2. **¿Llegó todo?** Sí (un toque) o marcar lo que no llegó (queda pendiente o "no llegó" → reclamo).
3. **Revisión con precios:** costo puesto en Guatemala por unidad y **precio sugerido** de cada producto;
   "Usar todos los sugeridos". → El inventario sube y los productos quedan listos para vender.

**Rastreo:** cada importación guarda plataforma, orden, guía, fechas (pedido, recibido), monedas, tipo de
cambio calculado, cargos y su prorrateo por línea. Estados: `en_camino`, `recibida`, `recibida_parcial`,
`anulada`.

## 4. Reglas (las aplica la API)
- Tipo de cambio = cobro en Q ÷ total de la factura en su moneda (6 decimales). Si no se conoce el cobro,
  se acepta un tipo de cambio escrito a mano.
- **Prorrateo por valor** (lo que costó cada línea en Q) de: envío y cargos de la factura (al pedir) y
  courier + envío local (al recibir). El último renglón absorbe el redondeo, para que la suma cuadre exacta.
  Por peso, más adelante, si hace falta.
- El inventario sube **al recibir**, no al pedir (lo que viene en camino no se puede vender).
- IVA y aranceles de importación cobrados por el courier: **costo** del producto por defecto (sin crédito
  fiscal) — **[verificar con el contador]** (`REVISION_CONTADOR.md` §6).
- Una importación pedida se puede **anular** (reverso del asiento); una recibida se corrige con los reversos
  que ya existen.

## 4 bis. Decisiones del dueño (2026-11-25)
- **Se mantiene la plantilla actual** (`plantilla-factura-camino-<factura>.xlsx`, hoja `Factura_camino`, filas
  `ENCABEZADO` + `PRODUCTO`, mismas columnas) como **la ruta para cargar productos**. `proveedor_id` (de la v1)
  se ignora: el proveedor sale de `plataforma`. Se valida que líneas + `garantia_envio` +
  `costo_importacion` + `otros_cobros` = `total_factura` (en la factura de ejemplo cuadra al centavo).
- **Moneda** de la columna `moneda_codigo` (MXN, USD…); conversión con el cobro de la tarjeta en Q o con
  `tipo_cambio` si viene lleno.
- **Variantes de verdad:** el mismo `skc` con otra talla/color es una variante del mismo producto (en el
  ejemplo, "Dream Adore" en S, M y L).
- **Nombre corto** sugerido desde `descripcion_proveedor` cuando `nombre_operativo` viene vacío; editable.
- **Categoría sugerida por palabras clave** (por tipo de negocio), editable en la revisión, una línea o varias
  a la vez, o una categoría nueva.
- **Atributos de variante según la categoría, ampliables:** Ropa → talla y color; Calzado → número y color;
  Electrónica y otros → color (o ninguno; la talla "S" de una cámara se ignora). El usuario agrega valores y
  atributos.
- **IVA y aranceles del courier: costo del producto** (sin crédito fiscal) [verificar con el contador].

## 5. Variantes (talla/color) — decidido: variantes de verdad
Para ropa de SHEIN, "Pijama Luxe" en M y en L son la misma prenda con inventario distinto. Opciones:
1. **Variantes de verdad** (`ops_item_variante` ya existe; la capacidad `variantes` está activa para "ventas en
   línea"): un producto con tallas/colores, cada una con su inventario y su precio. Más trabajo, mejor
   resultado.
2. **Un producto por talla/color** ("Pijama Luxe — M"): funciona hoy, pero el catálogo crece mucho.

## 6. Orden de trabajo sugerido
| Paso | Contenido |
|---|---|
| I1 | (Si se elige) variantes de talla/color en catálogo, venta e inventario. |
| I2 | Importación a mano: pedido en camino con moneda y cobro en Q, recepción con courier, prorrateo, inventario, precio sugerido, rastreo y asientos. |
| I3 | Plantilla Excel de una fila por producto (descargar, llenar, subir, revisar). |
| I4 | Factura PDF/foto con IA (con la prueba de modelos de la Fase 3, `PRUEBA_MODELOS_IA.md`). |
