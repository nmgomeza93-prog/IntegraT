# Plan: ventas rápidas (Fase 2, segundo módulo del Grupo B)

> Decisiones del dueño (2026-11-24): **venta rápida simple** (sin caja, clientes, descuentos ni
> impuestos todavía), **efectivo, tarjeta o transferencia** (un solo pago por venta), **precio
> congelado al vender** y **anular con motivo** (nunca borrar).
> Modelo de referencia: `MODELO_DATOS.md` §5.3 (`venta`, `venta_linea`, `pago`) y `DISENO_UX.md` §3.2.

## Qué incluye
Elegir productos o platillos del catálogo, ver el total, cobrar con un medio de pago y ver lo
vendido hoy. Anular una venta equivocada. El paso "Haz tu primera venta" del Inicio se marca solo.

## Qué NO incluye (entregas siguientes)
Caja y cuadre · clientes y fiado · descuentos, propinas e impuestos (IVA, FEL) · canal de venta ·
mesas y comandas · envíos · variantes visibles · inventario y costo · asientos contables ·
recibo por WhatsApp · pago dividido. Las columnas de esas funciones se agregan con su migración.

## Reglas de negocio (las aplica la API, nunca la app)
- **La API calcula el total** con el precio vigente del catálogo y lo **congela** en cada línea
  (también el nombre). La app no envía precios; así no se puede cobrar un precio inventado ni
  cambia la historia si luego se edita el catálogo.
- Las ventas son **inmutables**: no se editan ni se borran. Un error se corrige **anulando**
  (quién, cuándo y por qué quedan guardados). Una venta anulada deja de contar en los totales.
- Solo se venden ítems vivos del propio negocio y con `se_vende`; archivados o ajenos → error.
- Cantidades enteras de 1 a 999; máximo 50 líneas; el mismo ítem repetido se suma.
- `Idempotency-Key`: un doble toque o un reintento tras perder la respuesta no cobra dos veces.
- El día de "hoy" se calcula en la **zona horaria del negocio** (America/Guatemala), no en UTC.
- Permisos: dueño, administrador y cajero venden; solo dueño y administrador anulan.
- El número de venta es consecutivo **por negocio** (1, 2, 3…).

## Modelo de datos (migración `0007`)

| Tabla | Columnas | Notas |
|---|---|---|
| `ops_venta` | id, negocio_id, numero, fecha_hora (UTC), estado (`pagada`/`anulada`), total, moneda_codigo, anulada_en/por, motivo_anulacion, auditoría | Único (negocio, numero). |
| `ops_venta_linea` | id, negocio_id, venta_id, item_id, item_variante_id, nombre (congelado), cantidad, precio_unitario, total, auditoría | |
| `ops_pago` | id, negocio_id, venta_id, medio_pago (`efectivo`/`tarjeta`/`transferencia`), monto, auditoría | Hoy una fila por venta; el pago dividido llegará sin migrar datos. |

## API (`/v1`)

| Método y ruta | Qué hace |
|---|---|
| `POST /ventas` | Cobra: `{lineas: [{item_id, cantidad}], medio_pago}`. Devuelve la venta con su total. |
| `GET /ventas?fecha=AAAA-MM-DD` | Ventas del día (por defecto hoy) + resumen: cantidad, total y total por medio de pago (sin anuladas). |
| `GET /ventas/{id}` | Detalle con sus líneas. 404 si es de otro negocio. |
| `POST /ventas/{id}/anular` | `{motivo}` obligatorio; solo dueño o administrador. |

El checklist del Inicio gana la regla `ventas_minimo` (paso `primera_venta`).

## App (pestaña "Vender")
1. Cuadrícula/lista de productos con buscador; un toque suma 1; barra inferior "2 platillos · Q95.00 → Cobrar".
2. Pantalla de cobro: resumen y 3 botones grandes de medio de pago (el último usado viene elegido); "Confirmar".
3. Confirmación "¡Vendiste Q95.00!" con "Otra venta" y "Deshacer" (= anular rápido, con motivo predefinido).
4. "Lo vendido hoy": lista del día con total y por medio de pago; tocar una venta muestra el detalle y permite anular.

## Orden de trabajo (me detengo tras cada paso para que pruebes)

| Paso | Contenido | Cómo lo pruebas |
|---|---|---|
| V1 | Migración `0007`, API de ventas, regla del checklist, pruebas (incluye aislamiento, precio congelado, concurrencia de numeración e idempotencia). | `pytest` + `/docs` |
| V2 | App: carrito, cobro, confirmación y "vendido hoy" con la API falsa y pruebas de navegador. | Pruebas R + recorrido visual |
| V3 | Anular desde la app, pulido en 390 px y checklist. | Recorrido en celular/navegador |
