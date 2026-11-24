# FASE 0 — Análisis de la v1 y propuesta de IntegraT

## Reglas que no se negocian
- La v1 está en C:\APP-Emprende\Emprende (R/Shiny). Es SOLO DE REFERENCIA:
  no modifiques, muevas ni borres nada ahí. No ejecutes scripts de esa carpeta
  ni te conectes a su base de datos, y no reutilices sus credenciales ni sus archivos de datos.
- IntegraT es un producto NUEVO en C:\APP-IntegraT, inspirado en la v1,
  no una migración ni una copia de código.
- En esta fase NO escribas código de la aplicación. Solo análisis y propuesta.
  Al terminar, espera mi aprobación.

## Visión del producto
IntegraT es una app para que emprendedores y pequeñas empresas SIN conocimientos
de tecnología, contabilidad ni finanzas administren su negocio. La app hace el
trabajo administrativo para que el usuario se enfoque solo en VENDER y generar
ingresos. Administrar el negocio no debe ser el cuello de botella: si el producto
es bueno, la app debe ayudar a que el negocio crezca.
La meta es ser la app número 1 y la más fácil de usar del mercado para administrar,
dar seguimiento y fortalecer emprendimientos.

### Tipos de negocio
- Al registrarse, el usuario elige su tipo de negocio y la app se adapta.
- Prioridad inicial: **Ventas en línea** y **Restaurantes**.
- La arquitectura debe permitir agregar nuevos tipos (tienda, servicios,
  manufactura artesanal, etc.) por CONFIGURACIÓN, sin duplicar código.

### Qué debe resolver la app
- Catálogo de productos o menú con fotos.
- Inventario (en restaurantes: insumos y recetas, con costo por platillo).
- Compras y gastos, incluyendo gastos fijos y variables.
- Costos y **precios sugeridos** calculados a partir del costo y el margen deseado.
- Ventas y caja (apertura, cierre y cuadre).
- **Contabilidad automática**: la app lleva los libros contables por detrás
  (partida doble) sin que el usuario vea términos técnicos.
- **Asesor financiero**: informes claros en lenguaje sencillo (cuánto gané,
  en qué gasto más, qué producto deja más), y **punto de equilibrio**:
  cuánto y cuándo debe vender para no perder.
- Contexto inicial: Guatemala (IVA, SAT, factura electrónica FEL), pero
  la parte fiscal debe ser configurable por país.

### Facturas por foto (mejora clave sobre la v1)
- Hoy la v1 carga facturas con una plantilla. En IntegraT el usuario solo
  TOMA UNA FOTO de la factura de compra.
- La app extrae proveedor, fecha, productos, cantidades y precios, y le muestra
  al usuario una vista previa editable para confirmar. Al confirmar, carga
  inventario y costos y recalcula precios sugeridos.
- Propón el servicio de extracción (OCR / IA con visión), sus costos y cómo
  manejar errores de lectura.

### Imágenes en Cloudflare R2
- Usaremos Cloudflare R2 para fotos del catálogo y de facturas.
- Investiga la documentación oficial de R2 (API compatible con S3, URLs
  prefirmadas, buckets públicos y privados, costos) y propón: estructura de
  carpetas o llaves por negocio, subida directa desde el celular,
  miniaturas u optimización de imágenes, y separación entre fotos públicas
  (catálogo) y privadas (facturas).
- Revisa si la v1 ya usa algún servicio de fotos y qué conviene mejorar.
- Las credenciales de R2 irán en un archivo .env que nunca se sube a Git.

## Stack base: Shiny con R y Python
- La v1 está hecha en R/Shiny. IntegraT se mantendrá en el ecosistema Shiny,
  pero quiero aprovechar al máximo R y Python juntos:
  - **Python**: IA y lectura de facturas por foto, integración con Cloudflare R2,
    APIs externas y automatizaciones.
  - **R**: análisis financiero, proyecciones, punto de equilibrio y reportes.
- Shiny para R y Shiny para Python son frameworks separados. Evalúa y compara:
  A) Shiny R como app principal + Python vía reticulate.
  B) Shiny para Python como app principal (+ R donde aporte valor).
  C) Arquitectura híbrida: interfaz Shiny + API en Python (p. ej. FastAPI)
     para IA, facturas, R2 e integraciones.
- Revisa cómo la v1 combina R y Python (carpeta python/, renv, reticulate)
  y qué problemas tuvo.
- Evalúa con honestidad si Shiny cumple la visión: experiencia mobile-first,
  velocidad, muchos usuarios a la vez (multi-negocio), despliegue
  (rsconnect, Posit Connect, shinyapps.io, contenedores) y costos.
  Si ves límites importantes, dímelo y propón cómo mitigarlos.
- Recomienda la opción final con pros y contras, y cómo se organiza el
  proyecto (carpetas, entornos renv/venv, pruebas en R y Python).

## Rediseño total: simple, minimalista y potente
La v1 NO es referencia visual. Diseña IntegraT desde cero con un principio:
**cualquier persona, aunque casi no use tecnología, debe poder usarla sin ayuda.**
Por fuera es minimalista; por dentro, potente.

Principios de diseño:
- **Una pantalla, una tarea.** Cada pantalla tiene un objetivo claro y
  un botón principal evidente ("Vender", "Agregar producto", "Tomar foto").
- **Máximo 3 toques** para las acciones frecuentes: registrar una venta,
  cargar una factura por foto, ver cómo va el negocio.
- **Lo complejo queda escondido.** Contabilidad, costos, impuestos y asientos
  se calculan solos por detrás. El usuario ve resultados, no procesos.
- **Revelación progresiva:** al inicio solo lo esencial. Las opciones
  avanzadas aparecen cuando el negocio las necesita, sin saturar.
- **Lenguaje cotidiano:** "Lo que vendiste", "Lo que gastaste", "Lo que te
  queda". Nada de "pasivo", "devengado" ni "asiento". Si hace falta un
  término técnico, va con una explicación de una línea.
- **Visual antes que texto:** íconos claros, colores con significado
  (verde = bien, ámbar = atención, rojo = alerta), números grandes y legibles.
- **Mobile-first:** pensada para usarse con una mano en el celular, con
  botones grandes y navegación inferior de pocas secciones (máximo 4-5).
- **Cero miedo a equivocarse:** confirmaciones amables, "deshacer"
  disponible y mensajes de error que dicen cómo resolverlo.
- **Acompañamiento:** onboarding guiado según el tipo de negocio, pantallas
  vacías que enseñan qué hacer ("Agrega tu primer producto tomando una foto")
  y consejos del asesor financiero en el momento justo.
- **Accesible:** buen contraste, textos ajustables y diseño que funcione
  con conexión lenta.

El panel de inicio responde en 5 segundos: ¿cómo va mi negocio hoy?,
¿estoy ganando o perdiendo?, ¿cuánto me falta para el punto de equilibrio?
y ¿qué debo hacer ahora?

Propón:
- Mapa de navegación completo (todas las pantallas y cómo se conectan).
- Flujos clave paso a paso: registro y elección de tipo de negocio, primera
  venta, factura por foto, cierre de caja y ver el informe del mes.
- Wireframes en texto o ASCII de las pantallas principales.
- Sistema de diseño base: paleta, tipografía, espaciado, componentes
  (botones, tarjetas, formularios) y tono de voz.
- Cómo cambia la interfaz entre "Ventas en línea" y "Restaurante"
  manteniendo la misma base.
- Componentes y librerías de UI recomendados para Shiny (por ejemplo bslib)
  para lograrlo.

## Base de datos: `integrat`
- Nombre de la base de datos: **integrat**.
- Recomienda el motor (por ejemplo PostgreSQL o SQL Server) y justifica la elección.
- Nombres lógicos y consistentes, con prefijos o esquemas que separen
  claramente: dimensiones (dim_), hechos (fact_), vistas (vw_),
  procedimientos (sp_), funciones (fn_), tablas de configuración y catálogos
  maestros. Propón la convención completa y documéntala.
- Evalúa la separación entre la capa transaccional (operación diaria
  normalizada) y la capa analítica (modelo estrella de dimensiones y hechos
  para informes), y cómo se alimenta una de la otra.
- Multi-negocio y multi-empresa desde el inicio (aislamiento de datos por negocio).
- Optimizable y expandible: índices, llaves, columnas de auditoría
  (creado_por, fecha_creacion, etc.), borrado lógico, versionado con migraciones.
- Fácil de integrar con plataformas externas (tiendas en línea, apps de
  delivery, pasarelas de pago, facturación electrónica): API-first,
  identificadores estables y webhooks o eventos.

## Tareas
1. Lee primero CLAUDE.md, CURSOR_CONTEXT.md y .cursorrules de la v1.
   Luego revisa R/, modules/, python/, data/, www/, scripts/ y tests/.
2. Analiza la v1:
   a. Qué hace la app, sus módulos y flujos principales.
   b. Stack, dependencias y cómo maneja los datos y archivos.
   c. Modelo de datos actual (entidades y relaciones).
   d. Qué partes están atadas a un solo tipo de negocio.
   e. Deuda técnica y malas prácticas que no debemos repetir.
   f. Qué ideas conviene conservar (como concepto, no como código).
   g. Usabilidad: qué confunde o sobra hoy en la interfaz.
3. Compara la v1 contra la visión de IntegraT: qué existe, qué falta
   y qué hay que rediseñar.
4. Propón para IntegraT:
   - Stack tecnológico recomendado dentro del ecosistema Shiny R + Python
     (según la sección "Stack base"), más base de datos, almacenamiento e IA.
   - Arquitectura general y estructura de carpetas.
   - Rediseño UX/UI completo según la sección "Rediseño total".
   - Modelo de datos inicial de `integrat` (con diagrama en Mermaid).
   - Diseño del motor contable automático (cómo cada venta, compra o gasto
     genera sus asientos).
   - Roadmap por fases, empezando por un MVP con Ventas en línea y Restaurantes.
   - Riesgos y preguntas abiertas para que yo decida.

## Entregables (dentro de C:\APP-IntegraT\docs\)
- `ANALISIS_V1.md`: el análisis completo de la v1 (tarea 2).
- `VISION_PRODUCTO.md`: la visión de IntegraT, ordenada y clara.
- `PROPUESTA_ARQUITECTURA.md`: stack Shiny R + Python, arquitectura, R2,
  facturas por foto, motor contable y roadmap.
- `MODELO_DATOS.md`: convención de nombres, esquemas, diagrama y tablas iniciales.
- `DISENO_UX.md`: principios, mapa de navegación, flujos clave,
  wireframes y sistema de diseño.

Al terminar, dame un resumen corto con las decisiones que necesito tomar.
No crees el CLAUDE.md todavía: lo haremos cuando yo apruebe la propuesta.
