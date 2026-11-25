# Plan: catálogo de productos y platillos (Fase 2, primera entrega)

> Decisiones del dueño (2026-11-24): alcance básico, variante implícita desde ya, categorías
> sugeridas por tipo de negocio y editables, y solo **nombre + precio de venta** obligatorios.
> Modelo de referencia: `MODELO_DATOS.md` (catálogo e inventario) y `CONVENCIONES_BD.md`.

## Qué incluye
Crear, ver, editar y archivar **productos** (ventas en línea) y **platillos** (restaurante), con
nombre, precio de venta, categoría opcional y descripción opcional.

## Qué NO incluye (entregas siguientes)
Fotos (R2) · variantes visibles (talla, color) · recetas e insumos · inventario y costo ·
precio sugerido · precios por canal · impuestos y datos FEL. Las columnas de esas funciones **no**
se crean todavía: se agregan con su migración cuando llegue su turno.

## Modelo de datos (migración `0006`)

| Tabla | Columnas | Notas |
|---|---|---|
| `ops_categoria` | id, negocio_id, nombre, orden, icono, auditoría | Único por (negocio, nombre). |
| `ops_item` | id, negocio_id, categoria_id (nulo), tipo_item (`producto`/`platillo`), nombre, descripcion, se_vende, auditoría | El tipo sale del tipo de negocio, no lo elige la persona. |
| `ops_item_variante` | id, negocio_id, item_id, nombre, precio_venta (DECIMAL 14,2), auditoría | Todo ítem tiene **una** variante implícita ("Única"); la app aún no la muestra. |

- Prefijo `ops_` (operación diaria), como indica `CONVENCIONES_BD.md`. Todas llevan `negocio_id`
  y se leen/escriben solo con el repositorio de aislamiento (`db/aislamiento.py`).
- Dinero como `DECIMAL(14,2)` y texto decimal en la API (nunca float).
- Borrado = archivar (`eliminado_en`), nunca borrar filas. Edición con `version` (si dos
  pestañas editan lo mismo, la segunda recibe un aviso amable en vez de pisar la primera).
- Categorías sugeridas: nueva plantilla `catalogo` en `db/semillas/04_tipos_negocio.yaml` (también fija el tipo de ítem: `platillo` o `producto`)
  (restaurante: Platos fuertes, Bebidas, Postres, Entradas; en línea: sin categorías por ahora,
  se crean al agregar). Se copian al negocio al crearlo.

## API (`/v1`, el negocio siempre sale del token)

| Método y ruta | Qué hace |
|---|---|
| `GET /items` | Lista del negocio (filtros: `categoria_id`, `buscar`, `archivados`). Paginada. |
| `POST /items` | Crea (nombre + precio; `Idempotency-Key` opcional). |
| `GET /items/{id}` | Detalle. 404 si es de otro negocio. |
| `PATCH /items/{id}` | Edita nombre, precio, categoría, descripción (con `version`). |
| `DELETE /items/{id}` | Archiva. |
| `GET/POST /categorias`, `PATCH/DELETE /categorias/{id}` | Categorías del negocio. |

Reglas: nombre 2–120 caracteres, precio ≥ 0 con 2 decimales, nombre repetido en el mismo negocio
→ aviso (no error duro: puede haber "Pollo" en dos categorías). Los textos de error van en
lenguaje cotidiano. Cada acción de escritura registra `creado_por`/`actualizado_por`.

## App (pestaña "Productos" / "Menú")
1. Lista vacía con el botón principal "Agregar mi primer platillo/producto" (ya diseñada en
   `DISENO_UX.md`) y, con datos, lista por categoría con buscador y precio.
2. Agregar y editar en una pantalla propia dentro de la sección (no en hoja inferior: una pantalla, una tarea): nombre → precio → (categoría opcional) → Guardar. Máximo 3 toques. Crear categorías desde la app queda para C3.
3. Ficha: editar y "Archivar" (con confirmación).
4. El checklist del Inicio marca "hecho" automáticamente (ej. 5 platillos agregados).
5. Vocabulario del tipo de negocio en todo ("platillo" / "producto"); sin jerga.

## Orden de trabajo (me detengo tras cada paso para que pruebes)

| Paso | Contenido | Cómo lo pruebas |
|---|---|---|
| C1 | Migración `0006`, tablas, semilla de categorías, endpoints, pruebas de API (incluye aislamiento entre negocios). | `pytest` + `curl` contra la API local. |
| C2 | App: lista, agregar y editar con la API falsa y pruebas de navegador. | Pruebas R + recorrido visual. |
| C3 | Checklist del Inicio con avance real (reglas en la plantilla del tipo de negocio), crear categorías desde el formulario y pulido en 390 px. | Recorrido en celular/navegador. |

Commit por paso, solo con tu confirmación y **sin push** (ver memoria del proyecto).
