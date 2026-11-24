# Visión de producto: IntegraT

> **Fase 0** · Documento de visión. Ordena lo definido en `PROMPT_FASE0.md` y lo aprendido de la v1 (`ANALISIS_V1.md`).

## 1. En una frase

**IntegraT hace el trabajo administrativo de tu negocio para que tú solo te preocupes por vender.**

## 2. Problema

Los emprendedores y pequeños negocios de Guatemala y Latinoamérica:

- No saben con certeza **si están ganando o perdiendo**, ni cuánto.
- Ponen precios "a ojo" y **no conocen el costo real** de lo que venden (en un restaurante, el costo de cada platillo).
- Mezclan el dinero del negocio con el personal y **no cuadran la caja**.
- Guardan las facturas de compra en una caja de zapatos. Cargarlas a un sistema es tedioso.
- Ven la contabilidad y los impuestos como un mundo ajeno y caro, que solo entiende el contador.
- Las herramientas que existen (ERPs, hojas de cálculo, la propia v1) **piden conocimientos que no tienen** y tiempo que no les sobra.

Administrar se vuelve un **cuello de botella**: aunque el producto sea bueno, el negocio no crece porque el dueño no tiene información ni tiempo.

## 3. Para quién

| Persona | Contexto | Lo que necesita escuchar |
|---|---|---|
| **Andrea, vende ropa y accesorios por Instagram y WhatsApp** | Trabaja desde el celular, entrega a domicilio y compra mercadería por lotes | "Este mes ganaste Q4,200. Tu producto estrella es la blusa de lino." |
| **Don Julio, comedor o restaurante pequeño** | Compra insumos casi a diario, tiene 1 o 2 ayudantes y cobra en efectivo y con tarjeta | "Tu pollo frito te cuesta Q18 y lo vendes en Q35. El aceite subió; sube Q2 para mantener tu ganancia." |
| **El contador externo**, secundario | Recibe información del negocio una vez al mes | Un libro contable correcto y exportable, sin perseguir facturas |

Perfil común: **casi no usa tecnología fuera de WhatsApp**, usa un Android de gama media, tiene conexión variable y poco tiempo.

## 4. Propuesta de valor

1. **Vende en 3 toques.** Registrar una venta es más rápido que anotarla en un cuaderno.
2. **Carga tus compras como prefieras.** A mano, guiado paso a paso, o con una plantilla sencilla, **gratis**.
   O, si lo activas, **tomas una foto y la IA la lee por ti**, con el costo visible antes de usarla y bajo tu límite. En cualquier caso se actualizan el inventario, los costos y los precios sugeridos.
3. **Sabe si estás ganando**, todos los días y en lenguaje sencillo.
4. **Precios que sí dejan ganancia.** La app calcula el precio sugerido a partir del costo real y el margen que elijas.
5. **Tu punto de equilibrio, a la vista**: cuánto te falta vender este mes para no perder y en qué fecha lo alcanzas a tu ritmo actual.
6. **La contabilidad se hace sola**, en partida doble y por detrás. El usuario nunca ve un asiento, y el contador recibe libros correctos.

## 5. Principios de producto (no negociables)

- **El usuario ve resultados, no procesos.**
- **Una pantalla, una tarea.** Las acciones frecuentes se hacen en máximo 3 toques.
- **Lenguaje cotidiano**: "Lo que vendiste", "Lo que gastaste", "Lo que te queda".
- **Revelación progresiva**: lo avanzado aparece cuando el negocio lo necesita.
- **Cero miedo a equivocarse**: se puede deshacer, las confirmaciones son amables y los errores dicen cómo resolverse.
- **Mobile-first y para conexiones lentas.**
- **Una sola base y muchos tipos de negocio**: los tipos nuevos se agregan **por configuración**, no duplicando código.
- **Lo fiscal es configurable por país**. Guatemala es el primero, no el único.

## 6. Tipos de negocio

| Tipo | Prioridad | Rasgos que activa |
|---|---|---|
| **Ventas en línea** (redes, WhatsApp, tienda web) | MVP | Catálogo con fotos, variantes (talla y color), pedidos con entrega, canal de origen, cobro contra entrega |
| **Restaurante** (comedor, cafetería, comida rápida) | MVP | Menú con fotos, insumos, recetas y costo por platillo, ventas rápidas (para comer aquí, para llevar, a domicilio), consumo de insumos |
| Tienda física (abarrotería, librería) | Después | Ventas rápidas por código o búsqueda, inventario de reventa |
| Servicios (salón, taller) | Después | Servicios sin inventario, citas, insumos por servicio |
| Manufactura artesanal | Después | Recetas o fórmulas de producción y lotes |

Los tipos de negocio son **perfiles de configuración**. Cada perfil define:
- Qué capacidades se activan: recetas, variantes, entregas, mesas, etc.
- El vocabulario que se muestra: producto o platillo, catálogo o menú.
- El onboarding.
- Las categorías de gasto iniciales.
- La plantilla del plan de cuentas.
- Los indicadores del panel de Inicio.

## 7. Alcance funcional

| Área | Qué hace | Cómo se llama en la app |
|---|---|---|
| Catálogo / menú | Productos o platillos con foto, precio y categoría | "Mis productos" / "Mi menú" |
| Inventario | Existencias, alertas de "se te está acabando", ajustes | "Lo que tengo" |
| Insumos y recetas (restaurante) | Ingredientes por platillo y costo por platillo | "Receta" dentro de cada platillo |
| Compras | A mano (guiado), con plantilla simple o con foto + IA (opcional, con costo visible, límite mensual e historial); actualiza costos | "Registrar compra" |
| Gastos | Fijos (renta, luz, sueldos) y variables, con recordatorios | "Lo que gastaste" |
| Precios | Precio sugerido según costo y margen, con aviso si un costo sube | "Precio sugerido" |
| Ventas | Venta rápida, cobro en efectivo, tarjeta o transferencia, por canal | "Vender" |
| Caja | Apertura, cierre y cuadre guiado | "Cerrar el día" |
| Contabilidad | Partida doble automática, libros y exportación para el contador | Invisible; "Para tu contador" en Más |
| Asesor financiero | Informes en lenguaje sencillo, punto de equilibrio y consejos | "Cómo va mi negocio" |
| Fiscal | IVA, régimen e impuestos por país (GT: pequeño contribuyente / general). Consolidado por NIT cuando un titular tiene varios negocios. FEL preparada (se emite en una fase posterior) | "Tus impuestos" (con revelación progresiva) |
| Varios negocios | Cada negocio aislado (sus propios libros, catálogo, inventario y caja); el titular (NIT) ve el consolidado fiscal | "Mis negocios" |

## 8. Cómo mediremos el éxito

| Métrica | Meta inicial (piloto) |
|---|---|
| Tiempo para registrar una venta típica | menos de 10 s y 3 toques o menos |
| Tiempo desde la foto de la factura hasta la compra confirmada (modo IA) | menos de 60 s |
| Tiempo para cargar a mano una factura de 5 líneas (modo sin IA) | menos de 2 min |
| Campos que el usuario corrige tras la lectura con IA | menos del 10 % |
| Usuarios que completan el onboarding sin ayuda | más del 80 % |
| Negocios que cierran caja al menos 4 días por semana (retención de hábito) | más del 60 % |
| El panel de Inicio responde "¿estoy ganando?" | en menos de 5 s (carga + lectura) |
| Negocios que vuelven a la semana 4 | más del 50 % |

## 9. Qué no es IntegraT (por ahora)

- No es un ERP para empresas medianas. Planilla completa, activos fijos y multi-moneda avanzada van después.
- No es un sistema contable para contadores. La contabilidad es un subproducto.
- No es una tienda en línea. Se **integra** con ellas.
- No funciona sin conexión: **la app es siempre en línea** (decisión D-14), con reconexión automática y borradores guardados en el servidor.
- No emite facturas electrónicas (FEL) en el MVP, aunque queda preparada (`PLAN_FEL.md`).
- Despachos, marketing de Instagram y planilla quedan para fases posteriores.

## 10. Decisiones

Las decisiones aprobadas están en `DECISIONES.md`.
