# Análisis: validar el inventario al vender y la base de clientes

> Pedido del dueño (2026-11-25): (1) sin inventario no se puede vender; avisar cuando un producto está por
> terminarse o ya está en cero. (2) Saber **a quién** se le vende: una base de clientes simple, con los datos
> que el negocio necesite y con validaciones.

## 1. Inventario al vender

### Cómo funciona hoy
- `PLAN_INVENTARIO.md` decidió **no bloquear**: la venta se cobra aunque falte, la existencia queda negativa y,
  ya cobrada, la app avisa "se acabó: …". Nada impide vender algo que nunca se compró.
- Solo tienen inventario los productos que lo **controlan**: la mercadería para revender (un insumo por
  producto o por variante) y los platillos con receta (sus ingredientes). Un producto sin receta ni mercadería
  no tiene existencia que revisar.
- Ya existe el mínimo por insumo (`stock_minimo_base`) y el estado "te queda poco" / "falta" en Inventario.

### Lo que hay que resolver
| Tema | Propuesta |
|---|---|
| **Dónde se valida** | En la API, al cobrar y en la misma transacción (con los insumos bloqueados): si alguna línea no alcanza, la venta **no se cobra** (409) y la respuesta dice qué falta y cuánto queda. La app no puede ser la única barrera (dos cajeros a la vez, reconexiones). |
| **Cuánto se puede vender** | Mercadería: su existencia (por variante). Platillo con receta: el mínimo entre ingredientes de `existencia ÷ lo que lleva`, redondeado hacia abajo. |
| **Productos sin control de inventario** | Hay que decidir: o se venden libres (servicios, platillos sin receta) o **no se venden hasta configurar su inventario**. En una tienda, lo natural es que todo producto nuevo **sea mercadería por defecto**: así "primero se carga el inventario" (compra o importación) y luego se vende. |
| **Restaurantes** | Bloquear un platillo porque falta registrar 10 g de sal frena la operación. Conviene que la regla sea **configurable por negocio** (bloquear / solo avisar), con "bloquear" por defecto en tiendas. |
| **Anular, compras e importaciones** | Anular una venta devuelve la existencia (ya ocurre). Lo que viene **en camino** no se puede vender hasta que llega (ya ocurre). |

### Alertas
- **En Vender:** cada producto muestra "Quedan 3"; en cero, **"Agotado"** y no se puede tocar. En el carrito no
  se puede pasar de lo que hay. Al elegir talla o color, cada variante muestra lo suyo y las agotadas aparecen
  deshabilitadas.
- **"Por terminarse":** cuando la existencia llega a su mínimo. Para la mercadería, un mínimo por defecto del
  negocio (por ejemplo 2 unidades) que se puede cambiar por producto o variante.
- **En el Inicio:** tarjeta "Por agotarse" con los productos en su mínimo o en cero, y un botón a Compras o
  Importaciones.
- **Después de vender:** "Te quedan 2 de Pijama Luxe · M" cuando la venta deja algo en su mínimo.

## 2. Clientes

### Qué dice el diseño
`MODELO_DATOS.md` prevé `ops.cliente` (nombre, teléfono, tipo e id fiscal, nombre fiscal, correo, notas) y
`venta.cliente_id`. `PLAN_FEL.md` lo necesita para el receptor de la factura (NIT, CUI o CF).
`DISENO_UX.md` lo propone **opcional y sin frenar la venta** ("+ Agregar cliente (opcional)").

### Propuesta (simple)
| Pieza | Contenido |
|---|---|
| **Datos fijos** | Nombre (obligatorio); teléfono; correo; dirección (para envíos); NIT/CUI/CF y nombre para factura; notas. |
| **Datos propios del negocio** | "Campos de cliente" que el negocio define una vez (ej. Instagram, Cumpleaños, Talla preferida), con un tipo sencillo: texto, número, fecha o sí/no. Cada cliente los llena si quiere. |
| **En la venta** | Al cobrar: "¿A quién le vendes?" con búsqueda por nombre o teléfono y "+ Nuevo cliente" (nombre y teléfono, nada más). Por defecto, **Consumidor final**. |
| **Ficha del cliente** | Sus datos, lo que ha comprado (total y últimas ventas) y desde cuándo es cliente. |
| **Después** | Fiado y cuentas por cobrar, descuentos por cliente y la factura FEL con su NIT. |

### Validaciones (las aplica la API)
- **Nombre**: 2 a 120 caracteres.
- **Teléfono**: 8 dígitos en Guatemala, con `+502` opcional; otros países con su prefijo. Se guarda normalizado.
- **Correo**: formato válido.
- **NIT**: dígito verificador módulo 11 (acepta "K"); **CUI**: 13 dígitos con su verificador; **CF** sin número
  [verificar las reglas con el contador / SAT].
- **Duplicados**: el mismo teléfono o NIT en el negocio avisa ("Ya tienes a María López con ese teléfono") y
  ofrece usar el existente.
- Campos propios: un número debe ser número; una fecha, fecha válida.
- Privacidad: datos de clientes aislados por negocio; el cajero puede elegir y crear clientes, pero no exportar
  la base.

## 3. Próximos pasos propuestos
| Paso | Contenido |
|---|---|
| **V1. Validar existencia al vender** | API: revisar lo disponible antes de cobrar (con bloqueo), 409 con lo que falta; regla por negocio (bloquear / avisar); en tiendas, producto nuevo = mercadería por defecto; `disponible` en `GET /items` (por variante). |
| **V2. Alertas** | Mínimo por defecto y por producto/variante; "Agotado" y "Quedan N" en Vender; tope en el carrito; tarjeta "Por agotarse" en el Inicio; aviso después de vender. |
| **C1. Clientes (API)** | Migración `ops_cliente` y campos propios del negocio, validaciones, búsqueda y duplicados; `venta.cliente_id`. |
| **C2. Clientes (app)** | Más → Clientes (lista, buscar, ficha, nuevo, editar, campos propios); en Vender, "¿A quién le vendes?" al cobrar. |

## 4. Decisiones del dueño (2026-11-25)
- **Vender sin existencia: configurable por negocio.** Por defecto las tiendas en línea **bloquean** (no se
  cobra si no hay) y los restaurantes **avisan** pero dejan vender. Se cambia en Más.
- **Productos sin control de inventario:** en tiendas, **no se venden**: todo producto nuevo nace como
  mercadería en 0 y primero se compra o importa. En restaurantes, un platillo sin receta se vende libre (con
  aviso en su ficha).
- **Cliente en la venta: opcional**, "Consumidor final" por defecto; elegir o crear cliente es un toque extra.
- **Datos de clientes: fijos + campos propios** del negocio (texto, número, fecha o sí/no).

## 5. Estado (2026-11-25): V1 hecho
- API: migración `0019` (`core_negocio.vender_sin_existencia`), plantilla `operacion` por tipo de negocio,
  `integrat/existencias.py` (disponible por producto y variante; verificación al cobrar con los insumos
  bloqueados, antes de numerar la venta), `PUT /v1/negocios/{id}/ventas`, `disponible` y
  `controla_inventario` en los ítems; en tiendas, el producto nace como mercadería en 0 y los anteriores sin
  inventario se convierten al listar el catálogo. Pruebas en `tests/test_existencias.py` (incluye dos ventas
  a la vez por la última unidad).
- App: "Quedan N", "Agotado" y "Sin inventario" en Vender (lo agotado no se toca, también por talla), tope del
  carrito, el 409 de la API se muestra y recarga la lista; Más → "Si no hay inventario". Pruebas en
  `test-existencia.R`.

## 6. Estado (2026-11-25): V2 hecho
- API: migración `0020` (`core_negocio.minimo_defecto`: 2 en tiendas, 0 en restaurantes); la mercadería nueva
  nace con ese mínimo y se puede aplicar a la existente (`PUT /v1/negocios/{id}/ventas` con `minimo_defecto` y
  `aplicar_a_todos`). Cada ítem y variante trae `alerta_existencia` ("agotado", "poco" o nulo);
  `GET /v1/inventario/alertas` junta productos (por talla) e ingredientes; la venta devuelve `por_agotarse`.
- App: "Quedan N · por agotarse" en Vender, aviso "Te queda poco de…" al cobrar, tarjeta "Por agotarse" en el
  Inicio (con "Ver mi inventario") y el mínimo en Más → "Si no hay inventario".
- Sigue: C1 y C2 (clientes).

## 7. Estado (2026-11-25): C1 hecho
- Migración `0021`: `ops_cliente` (datos fijos y `datos` JSON con los campos propios), `ops_campo_cliente`
  (texto, número, fecha o sí/no; máximo 10) y `ops_venta.cliente_id` (nulo = Consumidor final).
- `integrat/clientes/`: `validaciones.py` (teléfono normalizado a `+502…`, correo, NIT módulo 11 con K y CUI
  con departamento y municipio, marcados [verificar]); rutas `GET/POST /v1/clientes` (búsqueda por nombre,
  teléfono o NIT), `GET/PATCH/DELETE /v1/clientes/{id}` (la ficha trae lo que ha comprado) y
  `GET/PUT /v1/clientes/campos`. Duplicado por teléfono o NIT/CUI: 409 con el nombre; `aunque_se_repita`
  guarda igual. El cajero busca, crea y corrige; archivar y los campos son del dueño o el administrador.
- Ventas: `cliente_id` opcional al cobrar; `cliente_id` y `cliente_nombre` en cada venta (también si el
  cliente se archivó). Pruebas en `api/tests/test_clientes.py`.
- Sigue: C2 (clientes en la app).
