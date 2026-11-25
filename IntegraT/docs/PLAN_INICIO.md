# Plan: Inicio con datos reales (Fase 2, octavo módulo del Grupo B)

> Decisiones del dueño (2026-11-25): la tarjeta **"Hoy"** muestra lo vendido hoy y la caja (cuánto debería
> haber, o un botón para abrirla); **"Tu meta del mes"** es un **punto de equilibrio simple**, marcado como
> estimado. Arquitectura (`PROPUESTA_ARQUITECTURA.md` §3 y §8): la API entrega los datos y la fórmula vive en
> R, en `integrat.analitica` (un solo dueño); la versión completa de la Fase 3 crecerá ahí mismo.

## Qué incluye
- **Hoy:** total vendido y número de ventas del día (`GET /v1/ventas`); si la caja está abierta, cuánto debería
  haber (`GET /v1/caja`); si no, "Abrir la caja".
- **Tu meta del mes:** cuánto vender en el mes para no perder, con barra de avance y cuánto falta.
  `meta = gastos fijos del mes ÷ margen`, con `margen = 1 − costo de lo vendido ÷ lo vendido` del mes; si aún
  no hay ventas con costo, se usa el margen objetivo del negocio (35 % por defecto) y se dice "estimada".
- Sin gastos fijos anotados, la tarjeta invita a anotarlos (como hoy). Si el costo iguala o supera a las
  ventas, avisa que con esos precios no hay meta posible.

## Datos (API)
`GET /v1/resultados` suma dos campos: `gastos_fijos` (gastos fijos del mes; si aún no hay ninguno este mes,
los del mes anterior, para que la meta exista desde el día 1) y `margen_objetivo` (del negocio).

## Fórmula (R)
`integrat.analitica::meta_del_mes(gastos_fijos, ventas, costo_ventas, margen_objetivo)`: pura, con pruebas.
La app la carga al arrancar desde `analitica/R` sin instalar el paquete; `infra/desplegar_app.R` copia esos
archivos al paquete que se sube.

## Orden de trabajo
| Paso | Contenido | Cómo lo pruebas |
|---|---|---|
| H1 | API: `gastos_fijos` y `margen_objetivo` en `/resultados`. Analítica: `meta_del_mes()` con pruebas. | `pytest` + `testthat` |
| H2 | App: carga de la analítica, tarjetas "Hoy" y "Tu meta del mes", despliegue con la analítica. | Pruebas R + recorrido |
