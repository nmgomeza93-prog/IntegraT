# Registro de decisiones: IntegraT

> Decisiones aprobadas por el dueño del producto al cierre de la Fase 0 (2026-11-23).
> Cada decisión remite al documento donde se desarrolla. Para cambiar una decisión, se agrega una entrada nueva; no se borra la anterior.

| # | Decisión | Detalle | Documento |
|---|---|---|---|
| D-01 | **Arquitectura híbrida (opción C)** | Interfaz en **Shiny para R** + API **FastAPI (Python)** + worker Python. Frontera R/Python documentada | `PROPUESTA_ARQUITECTURA.md` §2–3 |
| D-02 | **Shiny para R (no Shiny para Python) para la interfaz** | Elegida por madurez de bslib y componentes, analítica R en el mismo proceso y soporte documentado en shinyapps.io | `PROPUESTA_ARQUITECTURA.md` §2.2 |
| D-03 | **Aislamiento por NEGOCIO** | Cada negocio tiene sus propios libros, catálogo, inventario y caja. RLS por `negocio_id` | `MODELO_DATOS.md` §2.5 |
| D-04 | **Capa "titular" (NIT)** | Agrupa negocios con el mismo NIT, solo para reportes fiscales consolidados ante la SAT. El régimen fiscal vive en el titular | `MODELO_DATOS.md` §5.2, `REVISION_CONTADOR.md` §3 |
| D-05 | **Dos modos de carga de facturas** | (a) **Sin IA**: guiada a mano o con plantilla simple; es un flujo de primera clase. (b) **Con IA**: opcional, con costo visible antes de usarla, interruptor, límite mensual e historial | `PROPUESTA_ARQUITECTURA.md` §5, `DISENO_UX.md` §3.3 |
| D-06 | **El costo de la IA se reparte a los productos de la factura** | Se prorratea como un flete y entra al precio sugerido. El tratamiento contable debe validarlo el contador | `PROPUESTA_ARQUITECTURA.md` §5.6, `REVISION_CONTADOR.md` §7 |
| D-07 | **Prueba de modelos antes de elegir** | Unas 30 facturas reales; se comparan Opus 5.5, Sonnet 5.5 y Haiku 5.5 por precisión por campo, costo y tiempo | `PRUEBA_MODELOS_IA.md` |
| D-08 | **Fotos de facturas en un bucket R2 privado** | Se declara en la política de privacidad | `PROPUESTA_ARQUITECTURA.md` §4 y §10 |
| D-09 | **Hospedaje del piloto** | Shiny en **shinyapps.io**; API, worker y base de datos en el **servidor propio** *(reemplazado por D-19 y D-21: MySQL y API en Railway)*. Base **nueva** `integrat`. Todo preparado para migrar a **Azure** (contenedores y variables de entorno) | `CONFIGURACION_SERVIDOR.md` |
| D-10 | **Credenciales solo en `.env`** | `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` y las demás. Nunca en código, documentos ni logs. Se versiona `.env.example` sin valores | `CONFIGURACION_SERVIDOR.md` §2 |
| D-11 | **Fotos públicas por `r2.dev` en el piloto** | Se migra a dominio propio para producción (plan documentado) | `PROPUESTA_ARQUITECTURA.md` §4.3 |
| D-12 | **Contabilidad y fiscal de Guatemala a validar** | Toda decisión contable y fiscal pasa por un contador | `REVISION_CONTADOR.md` |
| D-13 | **Trato al usuario: "tú"** | — | `DISENO_UX.md` §5.5 |
| D-14 | **Siempre en línea** | No hay modo sin conexión. Sí hay reconexión automática y borradores guardados en el servidor | `PROPUESTA_ARQUITECTURA.md` §2.4 |
| D-15 | **FEL: lista para integrarse, no se emite en el MVP** | El modelo de datos y la capa de integración quedan preparados para un certificador | `PLAN_FEL.md` |
| D-16 | **Despachos, marketing de Instagram y planilla quedan para después** | — | `PROPUESTA_ARQUITECTURA.md` §11 |
| D-17 | **Marca: azul índigo; sin dominio por ahora** | — | `DISENO_UX.md` §5.1 |
| D-18 | **La v1 es solo de referencia** | No se modifica, ejecuta ni conecta. No se usa su base de datos (`erp_pyme_gt`) ni sus credenciales | `CLAUDE.md` |

| D-19 | **Motor de base de datos: MySQL 9.x** (Railway), en lugar de PostgreSQL | Reemplaza lo dicho sobre PostgreSQL en los demás documentos. Como MySQL no tiene RLS, esquemas ni restricciones diferidas, el aislamiento por negocio y el cuadre de asientos se garantizan en la API; `MODELO_DATOS.md` se adapta en el paso 2 de la Fase 1 | `PLAN_FASE1.md` paso 2 |
| D-20 | **Credenciales actuales (`camprd`) para el desarrollo** | Decisión del dueño (2026-11-23). Riesgo aceptado: el usuario tiene privilegios globales en el servidor. El código **solo opera sobre la base `integrat`** y nunca toca otras bases | `CLAUDE.md` |
| D-21 | **La API del piloto corre en Railway**, junto a la base (no en servidor propio) | Decisión del dueño (2026-11-24). Railway da HTTPS con certificado válido sin comprar dominio (resuelve R-03). No se puede limitar por IP a shinyapps.io, así que se endurece la API antes de abrirla | `PLAN_CIERRE_FASE1.md` |
| D-22 | **Motor contable: IVA según el régimen; tarjeta y transferencia directo a Banco** | Decisión del dueño (2026-11-25). Régimen general: se separa el 12 % incluido (débito en ventas; crédito solo en compras con número de factura y gastos con factura, y la compra entra al inventario sin IVA). Pequeño contribuyente y "todavía no sé": sin separar. Sin comisiones de tarjeta por ahora. Todo en reglas configurables, a validar por el contador (D-12) | `PLAN_CONTABILIDAD.md` |
| D-23 | **El piloto se despliega en Azure, no en Railway** | Decisión del dueño (2026-11-25). La API va a Azure Container Apps y MySQL a Azure Database for MySQL Flexible Server, con secretos en Key Vault; Railway deja de usarse. La app Shiny sigue en shinyapps.io por ahora. Reemplaza D-19 (solo en dónde vive MySQL; sigue siendo MySQL) y D-21. Hay que rehacer la receta de despliegue (`infra/railway.md` queda como histórico) | `CONFIGURACION_SERVIDOR.md` §7 |

## Recomendaciones derivadas (pendientes de tu visto bueno)

| # | Recomendación | Por qué |
|---|---|---|
| R-01 | **shinyapps.io habla solo con la API (HTTPS) y no con la base de datos** | Así la BD no se expone a internet y la app Shiny no necesita credenciales de BD dentro del bundle. La conexión directa queda documentada como alternativa (`CONFIGURACION_SERVIDOR.md` §5) |
| R-02 | **Cobrar la IA con un saldo prepagado en quetzales** ("Saldo IA") + lecturas incluidas en el plan | Es fácil de entender, no genera deudas y el saldo funciona como tope natural (`PROPUESTA_ARQUITECTURA.md` §5.7) |
| R-03 | ✅ **Resuelta por D-21:** la API en Railway usa el dominio HTTPS que Railway genera (antes: obtener un nombre de host para la API) | shinyapps.io debe llamar a la API por HTTPS con un certificado válido (`CONFIGURACION_SERVIDOR.md` §4) |
| R-04 | **Política contable por defecto para el costo de la IA:** prorratearlo como un flete (lo que pediste), configurable a "gasto" si el contador lo indica | Bajo NIIF para las PYMES podría considerarse un gasto administrativo (`REVISION_CONTADOR.md` §7) |
