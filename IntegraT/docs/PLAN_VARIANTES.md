# Plan: variantes (talla, color…) — paso I1 de `PROPUESTA_IMPORTACIONES.md`

> Decisiones del dueño (2026-11-25): **variantes de verdad** (cada talla/color con su inventario, costo y
> precio); **atributos según la categoría y ampliables** (Ropa → talla y color; Calzado → número y color;
> Electrónica → color); **categoría sugerida por palabras clave**, editable. Base existente: cada ítem ya
> tiene una variante implícita ("Única") en `ops_item_variante`, que guarda su precio.

## Conceptos
- **Atributo** del negocio: "Talla", "Color", "Número"… con sus **valores** (S, M, L…; Negro, Rosa…). El
  negocio agrega valores y atributos cuando quiera; al guardar una variante con un valor nuevo, se agrega solo.
- **Categoría → atributos**: cada categoría dice qué atributos usan sus productos (Ropa: talla y color).
  La plantilla del tipo de negocio trae **categorías sugeridas** con sus atributos y **palabras clave**
  (pijama, vestido → Ropa; cámara, cargador → Electrónica), que también usará la importación (I2).
- **Variante**: una combinación de valores (`{"Talla": "M", "Color": "Rosa"}`), con nombre ("M · Rosa"),
  código opcional (el SKC de SHEIN), precio propio e inventario propio.
- Un producto **sin variantes** sigue igual que hoy (su variante implícita, sin atributos). Al darle tallas o
  colores, la implícita se archiva y quedan las variantes (las ventas viejas conservan la suya).

## Reglas (las aplica la API)
- Las variantes de un producto se guardan **completas** (como la receta): `PUT /items/{id}/variantes`; las que
  no vienen se archivan. No puede haber dos con la misma combinación; cada una con al menos un atributo.
- **Inventario por variante:** la mercadería para revender (insumo ligado) es **por variante**
  (`ops_insumo.item_variante_id`); comprar o importar entra al insumo de esa variante.
- **Recetas:** una línea puede ser de todas las variantes (nula) o de una (`ops_receta_linea.item_variante_id`).
  Al vender una variante se descuentan las líneas comunes más las suyas.
- **Vender:** si el producto tiene variantes, la línea de venta debe decir cuál (si no, 422 "Elige la talla o
  el color"); el nombre congelado incluye la variante ("Pijama Luxe · M · Rosa") y el precio es el de ella.
- **Precio sugerido y avisos por variante** (cada una tiene su costo).

## Modelo de datos (migración `0016`)
| Tabla | Cambio |
|---|---|
| `ops_atributo` | nueva: negocio_id, nombre, orden, auditoría |
| `ops_atributo_valor` | nueva: negocio_id, atributo_id, valor, orden, auditoría |
| `ops_categoria_atributo` | nueva: negocio_id, categoria_id, atributo_id, orden, auditoría |
| `ops_categoria` | + `palabras_clave` (JSON, para sugerir la categoría en la importación) |
| `ops_item_variante` | + `codigo` (SKC/SKU, opcional), + `atributos` (JSON; nulo = la implícita) |
| `ops_insumo` | + `item_variante_id` (mercadería de una variante) |
| `ops_receta_linea` | + `item_variante_id` (línea solo de esa variante) |

## API (`/v1`)
| Ruta | Qué hace |
|---|---|
| `GET /atributos`, `POST /atributos`, `POST /atributos/{id}/valores` | Atributos del negocio y sus valores. |
| `GET /categorias` | + `atributos` de cada categoría. `PUT /categorias/{id}/atributos` los cambia. |
| `GET /items`, `GET /items/{id}` | + `variantes` (id, nombre, atributos, código, precio, sugerido, aviso) y `tiene_variantes`. |
| `PUT /items/{id}/variantes` | Guarda las variantes del producto. |
| `POST /ventas` | Las líneas aceptan `item_variante_id`. |

## App
- Ficha del producto: "Tallas y colores" → lista de variantes con su precio; agregar con chips de los valores
  de cada atributo (y "otro"), precio (por defecto el del producto) y código opcional.
- Vender: tocar un producto con variantes abre una hoja para elegir talla/color.
- Catálogo: "3 variantes · desde Q 115.00".

## Orden de trabajo
| Paso | Contenido |
|---|---|
| V1 | Migración `0016`, semillas (atributos y categorías sugeridas), API de atributos y de variantes. |
| V2 | Inventario, mercadería, recetas, ventas y precio sugerido por variante. |
| V3 | App: variantes en la ficha, elegir variante al vender, catálogo. |

## Estado (2026-11-25): V1 a V3 hechos (sin commit)
- API: migración `0016`, plantilla `variantes` por tipo de negocio (atributos y categorías sugeridas con
  palabras clave), `/v1/atributos`, `/v1/categorias/sugeridas`, `/v1/categorias/{id}/atributos`,
  `PUT /v1/items/{id}/variantes`; ventas, inventario (mercadería por variante), recetas y precio sugerido por
  variante. Pruebas en `tests/test_variantes.py`.
- App: "Tallas y colores" en la ficha (chips por atributo, "otro", precio, código, cambiar y quitar), selector
  de talla/color al vender, "N variantes · desde Q…" en el catálogo. Pruebas en `test-variantes.R`.
- Pendiente a propósito: existencia por variante en la ficha (hoy se ve en Inventario, un insumo por
  variante); editar las categorías y sus atributos desde la app (la API ya lo permite); al convertir en
  variantes un producto que ya tenía existencia, esa existencia queda en su insumo anterior (archivado) y
  vuelve si se le quitan las variantes.
