# Plan: inventario, insumos y recetas (Fase 2, cuarto módulo del Grupo B)

> Decisiones del dueño (2026-11-24): **insumos + recetas + existencias** (sin compras todavía),
> **las ventas descuentan insumos** si el platillo o producto tiene receta (y la anulación los devuelve),
> **costo promedio ponderado** y **lista fija de unidades con conversión simple**.
> Modelo de referencia: `MODELO_DATOS.md` §5.2 (`item`, `movimiento_inventario`) y `DISENO_UX.md`.

## Qué incluye
Lista de **insumos** (harina, tomate, bolsas…) con su unidad, existencia y costo; **entradas**, **mermas** y
**ajustes** a mano; **receta** de cada platillo/producto con su **costo por platillo** y margen; descuento
automático al vender y devolución al anular. Aviso de "te falta insumo" sin bloquear la venta.
El paso del checklist "Anota tus insumos" (restaurante) se marca solo.

## Qué NO incluye (entregas siguientes)
Compras (proveedor, factura, foto + IA): llegarán como "Registrar compra" y usarán las mismas entradas ·
varios almacenes · lotes y vencimientos · conteo físico guiado · precio sugerido (usará el costo por platillo) ·
asientos contables del inventario (motor contable). Hoy el costo del inventario no genera asientos.

## Reglas (las aplica la API)
- **Insumo** ≠ producto: es lo que el negocio compra y consume. Tabla propia (`ops_insumo`); `ops_item`
  sigue siendo solo lo que se vende.
- Cada insumo tiene una **unidad de uso** (la que ve la persona) de la lista fija: UN, DOC, G, KG, LB, OZ, QQ,
  ML, L, GAL. La API guarda existencia y costo en la **unidad base** (UN, G o ML) y convierte solo dentro
  del mismo tipo (masa↔masa, volumen↔volumen). Pedir una conversión entre tipos distintos es error 422.
- **Existencia y costo promedio** viven en `ops_insumo` (`existencia_base`, `costo_promedio_base`), pero la
  verdad son los movimientos: `ops_movimiento_inventario` es **inmutable** (`tipo`: `entrada`, `merma`,
  `ajuste`, `consumo_venta`, `reverso_venta`, `inicial`; cantidad ±; `costo_unitario_base`; origen).
  Se corrige con otro movimiento, nunca editando.
- **Costo promedio ponderado**: en una entrada con cantidad `q` y costo total `c`,
  `nuevo = (existencia·costo + c) / (existencia + q)`. Mermas, consumos y ajustes de salida **no** cambian el
  costo; salen al costo promedio vigente. Con existencia ≤ 0 la entrada fija el costo de esa entrada.
- Existencia **puede quedar negativa** (se vendió sin haberla anotado): se avisa, no se bloquea la venta.
- **Receta**: líneas `(insumo, cantidad, unidad)` por ítem; la cantidad puede estar en otra unidad del
  mismo tipo que la del insumo. **Costo del platillo** = suma de cantidad × costo promedio; lo calcula la API
  y la app solo lo muestra, junto con margen (`precio − costo`) y porcentaje.
- **Venta**: en la misma transacción que la venta se crean los movimientos `consumo_venta` por cada línea con
  receta (cantidad de la receta × cantidad vendida) al costo promedio del momento, que se congela en el
  movimiento. **Anular** crea `reverso_venta` por los mismos valores. Una venta sin receta no toca inventario.
- Archivar un insumo no borra movimientos; si aparece en una receta, la receta lo conserva y la app lo marca
  como archivado. Archivar un ítem no toca sus recetas.
- Editar con `version`; `Idempotency-Key` en entradas; `negocio_id` siempre del token.
- Permisos: dueño y administrador escriben; dueño, administrador y contador ven costos; el **cajero** vende
  (se descuenta) pero no ve costos ni existencias.
- Los insumos **no se siembran**: sugerirlos (tortillas, pollo, bolsas…) es cosa de la app (I3). Sembrarlos
  marcaría solo el paso "Anota tus insumos" del checklist sin que la persona haya hecho nada.

## Modelo de datos (migraciones `0009` en I1 y `0010` en I2)

| Tabla | Columnas | Notas |
|---|---|---|
| `ops_insumo` (0009) | id, negocio_id, nombre, unidad_codigo, existencia_base, costo_promedio_base (8 decimales), stock_minimo_base, auditoría | `unidad_codigo` → `cat_unidad_medida`; nombre único por negocio entre vivos. Mover existencias no cambia `version`. |
| `ops_movimiento_inventario` (0009) | id, negocio_id, insumo_id, fecha_hora, tipo, cantidad_base (±), costo_unitario_base, origen_tipo, origen_id, nota, creado_en, creado_por | Inmutable: sin `eliminado_en` ni `version` (la prueba de convenciones solo le exige `creado_*`). |
| `ops_receta_linea` (0010) | id, negocio_id, item_id, insumo_id, cantidad, unidad_codigo, auditoría | Única por (ítem, insumo) entre vivas. |

Dinero y cantidades como texto decimal en la API (cantidades con hasta 4 decimales).

## API (`/v1`)

| Método y ruta | Qué hace |
|---|---|
| `GET/POST /insumos`, `GET/PATCH/DELETE /insumos/{id}` | Lista (con existencia, costo y aviso de faltante), alta, edición con `version`, archivar. |
| `POST /insumos/{id}/movimientos` | Entrada (con costo total), merma o ajuste; `Idempotency-Key`. |
| `GET /insumos/{id}/movimientos` | Historial del insumo. |
| `GET/PUT /items/{id}/receta` | Ver y reemplazar la receta; incluye costo, margen y porcentaje. |
| `GET /unidades` | Lista fija de unidades y a cuáles se puede convertir. |
| (existente) `POST /ventas`, anulación | Descuentan y devuelven insumos. Al cobrar, la respuesta trae `insumos_en_falta` (nombres de los que se acabaron); en lecturas posteriores va vacío. Los insumos archivados no se descuentan. |

El checklist gana la regla `insumos_minimo` (ya la evalúa la API desde I1); el paso "Anota tus insumos" del
restaurante se agrega a la plantilla en I4, junto con su botón en la app. En I2, `receta_estrella` pasa a
marcarse solo con `recetas_minimo: 1`.

## App (sección "Más" → "Inventario"; receta en la ficha del producto)
1. Lista de insumos con existencia y aviso "Te queda poco" / "Te falta" (la búsqueda por nombre queda para cuando haya muchos insumos; la API ya la soporta con `buscar`).
2. Agregar insumo: nombre → unidad → (existencia y costo iniciales opcionales). Máximo 3 toques.
3. Ficha del insumo: "Entró", "Se perdió", "Corregir cantidad", historial.
4. En la ficha de un platillo: **Receta** (agregar insumos con cantidad y unidad) y costo por platillo con margen.
5. Al vender, aviso amable si algún insumo queda en negativo (sin bloquear).

## Orden de trabajo (me detengo tras cada paso para que pruebes)

| Paso | Contenido | Cómo lo pruebas |
|---|---|---|
| I1 | Migración `0009`, unidades, insumos y movimientos con costo promedio, regla del checklist, semillas, pruebas. | `pytest` + `/docs` |
| I2 | Recetas y costo por platillo; descuento al vender y reverso al anular (+ aviso de faltante). | `pytest` + `/docs` |
| I3 | App: lista de insumos, agregar, entradas/mermas/ajustes, con API falsa y pruebas de navegador. | Pruebas R + recorrido visual |
| I4 | App: receta y costo en la ficha del platillo, aviso al vender, checklist y pulido en 390 px. | Recorrido en navegador |
