# Prueba de modelos de IA para leer facturas

> **Fase 0 · Diseño de la prueba** (se ejecuta al inicio de la Fase 3, antes de elegir el modelo).
> Objetivo: elegir con datos, no por intuición, qué modelo lee las facturas de compra:
> `claude-opus-5-5`, `claude-sonnet-5-5` o `claude-haiku-5-5`.

---

## 1. Preguntas que responde

1. ¿Qué tan bien lee cada modelo **cada campo** de una factura guatemalteca real?
2. ¿Cuánto cuesta **por página** y **por factura**?
3. ¿Cuánto tarda (p50 y p95)?
4. ¿Conviene un **esquema escalonado** (un modelo barato primero y uno más capaz solo cuando la confianza es baja o fallan las validaciones)?
5. ¿Qué precio por página fijamos para el usuario (`PROPUESTA_ARQUITECTURA.md` §5.7)?

## 2. Conjunto de prueba (~30 facturas reales)

| Grupo | Cantidad | Ejemplos |
|---|---|---|
| FEL impresas (carta o media carta) | 8 | Distribuidoras, ferreterías, supermercados |
| Tickets térmicos FEL | 7 | Supermercado, gasolinera, farmacia |
| Facturas de pequeño contribuyente | 5 | Mercado, proveedores pequeños |
| Escritas a mano / notas de envío / recibos | 5 | Mercado municipal, proveedor informal |
| Difíciles | 5 | Arrugadas, con poca luz, en ángulo, de 2 páginas, con mucho texto |

- **Mitad de ventas en línea y mitad de restaurante**: mercadería frente a insumos con unidades variadas (lb, qq, galón, caja, docena).
- **Origen**: facturas reales donadas por los negocios del piloto, con **consentimiento escrito**.
  Se guardan en el bucket privado de **desarrollo**, no se comparten y se borran al terminar la prueba si así se acuerda.
- Las fotos se toman **con celulares de gama media**, a través del mismo flujo de compresión de la app (1600 px). Se prueba lo que de verdad llegará en producción.

## 3. Verdad de referencia ("respuesta correcta")

- Dos personas transcriben cada factura de forma independiente en una hoja con el **mismo esquema** que usa el modelo. Una tercera resuelve las diferencias.
- Esquema (igual al JSON Schema de producción):
  - `proveedor.nombre`, `proveedor.nit`
  - `documento.tipo`, `serie`, `numero`, `autorizacion_fel`, `fecha`
  - `moneda`, `subtotal`, `iva`, `total`
  - `lineas[]`: `descripcion`, `cantidad`, `unidad`, `precio_unitario`, `descuento`, `total`

## 4. Ejecución

- Los 3 modelos reciben el **mismo prompt, el mismo JSON Schema (salidas estructuradas)** y las mismas imágenes.
- **3 corridas por modelo y factura** para medir la variación: 30 × 3 × 3 = 270 llamadas.
  El costo total estimado es **menor a US$15**, con los precios vigentes al 2026-11-23 (Opus 5.5: US$4/20, Sonnet 5.5: US$2/10, Haiku 5.5: US$0.10/0.50 por millón de tokens de entrada/salida).
- Cada llamada registra: tokens de entrada y salida (desde `usage`), costo, tiempo total, si el JSON es válido y la razón de detención.
- Se ejecuta con un script Python en `api/` (modo evaluación), **contra el bucket de desarrollo**, nunca contra datos de producción.
- Se repite con **caché de prompt** (instrucciones y esquema) activada, para medir el ahorro.
- **Variante con QR**: los campos que da el QR de la FEL se comparan aparte (no dependen del modelo).

## 5. Métricas

| Métrica | Cómo se mide | Meta mínima |
|---|---|---|
| **Exactitud por campo crítico** | NIT, fecha, número/serie, total: coincidencia exacta (montos ±Q0.01) | ≥ 98 % |
| Exactitud de otros campos | Nombre del proveedor (similitud ≥ 0.9), subtotal, IVA | ≥ 95 % |
| **Líneas: F1** | Se emparejan líneas por similitud de descripción. Acierto = cantidad exacta + total de línea ±Q0.01 | ≥ 95 % |
| Coherencia | Porcentaje de facturas donde la suma de líneas coincide con el total del modelo | ≥ 95 % |
| **Campos que el usuario tendría que corregir** | Campos erróneos / campos totales | ≤ 10 % (meta de producto) |
| "Confianza" bien calibrada | Porcentaje de errores marcados por el modelo como confianza baja | ≥ 70 % |
| Costo por página y por factura | USD reales desde `usage` | Informativo |
| Tiempo | p50 y p95 por factura | p95 ≤ 20 s |
| Estabilidad | Diferencias entre las 3 corridas | Informativo |

Resultados por **grupo de factura**: puede pasar que Haiku resuelva bien las FEL impresas y falle en las manuscritas.

## 6. Regla de decisión

1. Se descarta cualquier modelo que no cumpla las metas mínimas de **campos críticos** y **F1 de líneas**.
2. Entre los que cumplen, se elige el de **menor costo por factura**.
3. Si ninguno barato cumple en todos los grupos, se evalúa el **esquema escalonado**: modelo barato → si la confianza es baja o falla una validación → modelo más capaz.
   Se recalcula el costo promedio con la proporción real de escalamientos.
4. Con el costo promedio resultante se fija `IA_PRECIO_POR_PAGINA_GTQ` (fórmula en `PROPUESTA_ARQUITECTURA.md` §5.7).
5. La prueba se **repite** cuando salga un modelo nuevo o cambien los precios, usando el mismo conjunto (que se conserva con consentimiento).

## 7. Entregable

`docs/RESULTADO_PRUEBA_IA.md` con:
- Tabla de métricas por modelo y grupo.
- Costo y tiempo.
- 5 ejemplos de errores típicos.
- Decisión tomada y precio por página propuesto.
