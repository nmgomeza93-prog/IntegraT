# Plan: precio sugerido (adelanto de la Fase 3)

> Decisiones del dueño (2026-11-25): **margen del negocio ajustable por ítem**, redondeo **hacia arriba a
> Q0.50** y **avisos + aplicar con un toque**. Dueño de la fórmula: la API (`CLAUDE.md`, arquitectura:
> "Precio sugerido" en Python), módulo `integrat/precios.py`.

## Reglas
- Costo de una unidad = su receta al costo promedio de cada insumo (el mismo de la ficha "Receta y costo").
- Margen objetivo = el propio del ítem (`ops_item.margen_objetivo`, migración `0015`) o el del negocio
  (`core_negocio.margen_objetivo_defecto`, 35 % por defecto). Entre 0 y 90 %.
- **Precio sugerido** = costo ÷ (1 − margen), **más el IVA** si el régimen lo separa (el precio de venta lo
  lleva incluido), redondeado **hacia arriba** a Q0.50: nunca queda bajo el margen.
- **Aviso** sobre el precio actual sin IVA: `pierde` (no cubre el costo), `bajo` (cubre el costo pero no el
  margen) u `ok`. Sin receta o con insumos sin costo: sin sugerido ni aviso.
- El margen que muestra la ficha ("Te quedan…") se mide ahora sobre el precio **sin IVA**.

## API
| Ruta | Cambio |
|---|---|
| `GET /items`, `GET/PATCH /items/{id}` | + `precio_sugerido`, `aviso_precio`, `margen_objetivo`, `margen_propio`; `PATCH` acepta `margen_objetivo` (null = el del negocio). |
| `GET /items/{id}/receta` | + `precio_sugerido`, `aviso_precio`, `margen_objetivo_porcentaje`, `margen_propio`. |
| `PUT /negocios/{id}/precios` | Margen objetivo del negocio (dueño y administrador). `GET /negocios/{id}` lo devuelve. |

## App
- Catálogo: marca "Pierdes" (roja) o "Margen bajo" (ámbar) junto al precio.
- Ficha "Receta y costo": tarjeta "Precio sugerido" con su estado, "Usar Q…" y "Cambiar el margen" (propio o
  volver al del negocio).
- Más → "Tu margen de ganancia": el margen del negocio (lo usa también la meta del mes).

## Estado (2026-11-25): hecho (sin commit)
API 311 pruebas (15 nuevas en `tests/test_precios.py`); app `test-precios.R` (25).
