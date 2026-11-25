# API falsa para probar la app sin base de datos: imita las respuestas de /v1 (mismas formas
# que la API real; el contrato real lo cubren las pruebas de api/tests). Corre en un proceso
# aparte con httpuv y se apaga sola al terminar la prueba.
#
# Cuentas de prueba:
#   mari@prueba.com / clave-correcta-1  -> ya tiene un restaurante
#   repetido@prueba.com                 -> el registro responde 409 (correo repetido)
# Atajos para probar la renovación de sesión:
#   token de acceso "token-vencido" -> toda llamada responde 401
#   refresh_token  "refresco-valido" -> /auth/refrescar entrega una sesión nueva
# GET /_creados devuelve cuántos negocios e ítems se crearon (para probar el doble toque) y
# cuántas veces se llamó a /v1/auth/salir.
# Catálogo (/v1/items y /v1/categorias): en memoria. Atajos:
#   ítem de nombre "Falla una vez" -> se crea, pero la primera respuesta es un error
#   ítem de nombre "Conflicto"     -> editarlo responde 409 (alguien más lo cambió)
#   la cuenta mari@prueba.com entra con 2 platillos (Pepián y Horchata)
# Gastos (/v1/gastos y /v1/gastos/categorias): en memoria. La cuenta mari@prueba.com entra con
# 2 gastos del mes (Renta Q 3,500.00 fija y Desechables Q 45.00). Atajos:
#   nota "Se pierde" -> el primer gasto con esa nota se anota, pero la respuesta es un error
#   nota "Conflicto" -> corregir ese gasto responde 409 (alguien más lo cambió)
# Ventas (/v1/ventas): en memoria; el total lo calcula la API falsa con el precio del ítem.
#   motivo de anulación "sin permiso" -> responde 403 (rol sin permiso para anular)
#   ítem de nombre "Se pierde" -> la primera venta que lo incluye se cobra, pero la respuesta es
#   un error (para probar el reintento con la misma clave)
# Impuestos y resultados: PUT /v1/negocios/{id}/impuestos guarda el régimen (empieza en "no_se");
#   GET /v1/resultados resume ventas pagadas menos gastos (sin IVA en el régimen general).
# Caja (/v1/caja) y dueño (/v1/dueno): en memoria; el efectivo esperado es la apertura más las
#   ventas en efectivo cobradas desde que se abrió.

iniciar_api_falsa <- function(env = parent.frame()) {
  puerto <- httpuv::randomPort()
  proceso <- callr::r_bg(function(puerto) {
    `%||%` <- function(x, y) if (is.null(x)) y else x
    json <- function(estado, datos) {
      list(status = estado, headers = list("Content-Type" = "application/json"),
           body = jsonlite::toJSON(datos, auto_unbox = TRUE, null = "null"))
    }
    leer <- function(req) {
      crudo <- rawToChar(req$rook.input$read())
      if (nzchar(crudo)) jsonlite::fromJSON(crudo, simplifyVector = FALSE) else list()
    }
    usuario <- function(nombre, correo) list(id = "u-1", nombre = nombre, correo = correo)
    sesion <- function(nombre, correo, negocio_id = NULL) {
      list(token_type = "bearer", access_token = "token-valido", expira_en = 900,
           refresh_token = "refresco-valido-0123456789", negocio_id = negocio_id,
           usuario = usuario(nombre, correo))
    }
    vocab <- list(
      restaurante = list(item_singular = "platillo", item_plural = "platillos",
                         catalogo = "Menú", catalogo_icono = "journal-text"),
      ventas_en_linea = list(item_singular = "producto", item_plural = "productos",
                             catalogo = "Productos", catalogo_icono = "box-seam")
    )
    pasos <- list(
      restaurante = list(
        list(clave = "cinco_platillos", texto = "Agrega tus 5 platillos más vendidos",
             icono = "journal-text", hecho = FALSE),
        list(clave = "primeros_insumos", texto = "Anota tus insumos principales",
             icono = "basket", hecho = FALSE),
        list(clave = "primera_compra", texto = "Registra tu primera compra", icono = "receipt",
             hecho = FALSE),
        list(clave = "receta_estrella", texto = "Dinos qué lleva tu platillo estrella",
             icono = "basket", hecho = FALSE),
        list(clave = "primera_venta", texto = "Haz tu primera venta", icono = "cart",
             hecho = FALSE)),
      ventas_en_linea = list(
        list(clave = "primer_producto", texto = "Agrega tu primer producto",
             icono = "box-seam", hecho = FALSE),
        list(clave = "primera_venta", texto = "Haz tu primera venta", icono = "cart",
             hecho = FALSE),
        list(clave = "gastos_fijos", texto = "Anota tus gastos fijos", icono = "cash-coin",
             hecho = FALSE),
        list(clave = "primera_compra", texto = "Registra tu primera compra", icono = "receipt",
             hecho = FALSE))
    )
    estado <- new.env()
    # El checklist se marca solo, como en la API real: 5 platillos o 1 producto.
    pasos_al_dia <- function(tipo) {
      vivos <- length(estado$items)
      hay_fijo <- any(vapply(estado$gastos, function(g) isTRUE(g$es_fijo), NA))
      minimo <- c(cinco_platillos = 5L, primer_producto = 1L)
      vendidas <- sum(vapply(estado$ventas, function(v) identical(v$estado, "pagada"), NA))
      lapply(pasos[[tipo]], function(p) {
        p$hecho <- (!is.na(minimo[p$clave]) && vivos >= minimo[[p$clave]]) ||
          (identical(p$clave, "primera_venta") && vendidas >= 1) ||
          (identical(p$clave, "gastos_fijos") && hay_fijo) ||
          (identical(p$clave, "primeros_insumos") && length(estado$insumos) >= 1) ||
          (identical(p$clave, "primera_compra") &&
             any(vapply(estado$compras, function(co) identical(co$estado, "registrada"), NA))) ||
          (identical(p$clave, "receta_estrella") &&
             any(vapply(estado$recetas, function(r) length(r) > 0, NA)))
        p
      })
    }
    negocio <- function(id, nombre, tipo, factura) {
      list(id = id, nombre = nombre, tipo_negocio_codigo = tipo, pais_codigo = "GT",
           moneda_codigo = "GTQ", zona_horaria = "America/Guatemala", da_factura = factura,
           regimen_iva = estado$regimen, margen_objetivo = estado$margen,
           vender_sin_existencia = estado$regla_venta,
           minimo_defecto = sprintf("%.2f", estado$minimo), capacidades = list("recetas", "mesas"),
           vocabulario = vocab[[tipo]], primeros_pasos = pasos_al_dia(tipo))
    }
    estado$regimen <- "no_se"
    estado$margen <- "0.3500"
    estado$regla_venta <- "avisar"   # Mari es un restaurante: avisa y deja vender
    estado$minimo <- 2L               # "por agotarse" con 2 o menos (versión simple)
    estado$atributos <- list(
      list(id = "at-1", nombre = "Talla",
           valores = lapply(c("S", "M", "L"), function(v) list(id = paste0("va-", v), valor = v))),
      list(id = "at-2", nombre = "Color",
           valores = lapply(c("Negro", "Rosa"), function(v) list(id = paste0("va-", v), valor = v))))
    estado$variantes_creadas <- 0L
    estado$importaciones <- list()
    estado$claves_importacion <- list()
    # Vista previa fija (la API real lee el archivo): 2 productos, uno con 2 tallas.
    previa_falsa <- list(
      encabezado = list(plataforma = "shein", numero_factura = "INVPRUEBA", numero_orden = "ORD-1",
                        fecha_factura = "2026-11-03", moneda_codigo = "MXN", moneda_conocida = TRUE,
                        tipo_cambio = NULL, total_factura = "519.00", garantia_envio = "19.00",
                        costo_importacion = "100.00", otros_cobros = "0.00"),
      cuadre = list(lineas = "400.00", cargos = "119.00", total_calculado = "519.00",
                    total_factura = "519.00", diferencia = "0.00", cuadra = TRUE),
      productos = list(
        list(nombre = "SilkySpell Conjunto de pijama", categoria = "Ropa de dormir", item_id = NULL,
             existente = FALSE,
             lineas = list(list(fila = 3L, codigo = "si100", descripcion = "Pijama con encaje",
                                atributos = list(Talla = "M", Color = "Negro"), cantidad = 1L,
                                precio_unitario = "100.0000", item_variante_id = NULL))),
        list(nombre = "Dream Adore Conjunto", categoria = "Ropa de dormir", item_id = NULL,
             existente = FALSE,
             lineas = list(
               list(fila = 4L, codigo = "si200", descripcion = "Conjunto de casa",
                    atributos = list(Talla = "S", Color = "Rosa"), cantidad = 1L,
                    precio_unitario = "150.0000", item_variante_id = NULL),
               list(fila = 5L, codigo = "si200", descripcion = "Conjunto de casa",
                    atributos = list(Talla = "M", Color = "Rosa"), cantidad = 1L,
                    precio_unitario = "150.0000", item_variante_id = NULL)))),
      unidades = 3L, avisos = list())
    importacion_out <- function(i, con_lineas = TRUE) {
      if (!con_lineas) i$lineas <- list()
      i
    }
    estado$caja <- NULL          # la sesión abierta
    estado$cierres <- list()
    estado$cierres_hechos <- 0L
    estado$claves_cierre <- list()
    estado$dueno <- list()
    estado$claves_dueno <- list()
    resumen_vacio <- function() list(ventas = "0.00", gastos = "0.00", compras = "0.00",
                                     inventario = "0.00", dueno = "0.00", otros = "0.00",
                                     cantidad_ventas = 0L, ventas_tarjeta = "0.00",
                                     ventas_transferencia = "0.00")
    # Caja en vivo, versión simple: apertura + ventas en efectivo pagadas desde que se abrió.
    caja_en_vivo <- function(c) {
      ventas <- Filter(function(v) identical(v$estado, "pagada") && identical(v$medio_pago, "efectivo") &&
                         (v$creada_n %||% 0L) > c$ventas_al_abrir, estado$ventas)
      monto <- sum(vapply(ventas, function(v) as.numeric(v$total), 0))
      r <- resumen_vacio()
      r$ventas <- sprintf("%.2f", monto)
      r$cantidad_ventas <- length(ventas)
      c$resumen <- r
      c$efectivo_esperado <- sprintf("%.2f", as.numeric(c$monto_apertura) + monto)
      c$ventas_al_abrir <- NULL
      c
    }
    estado$resultados_llamadas <- 0L
    estado$creados <- 0L
    estado$salidas <- 0L
    estado$claves <- list()
    estado$items <- list()          # id -> ítem
    estado$orden_items <- character()
    estado$claves_item <- list()
    estado$items_creados <- 0L
    estado$gastos <- list()
    estado$gcats_extra <- list()
    estado$claves_gasto <- list()
    estado$gastos_creados <- 0L
    estado$gsembrado <- FALSE
    gcats_de <- function(tipo) {
      if (tipo == "restaurante") {
        nombres <- c("Renta", "Sueldos", "Luz, agua y gas", "Desechables", "Teléfono e internet", "Mantenimiento")
        fijos <- c(TRUE, TRUE, FALSE, FALSE, TRUE, FALSE)
      } else {
        nombres <- c("Publicidad", "Envíos", "Empaques", "Comisiones", "Teléfono e internet", "Renta")
        fijos <- c(FALSE, FALSE, FALSE, FALSE, TRUE, TRUE)
      }
      base <- lapply(seq_along(nombres), function(i) {
        list(id = paste0("g-", i), nombre = nombres[i], icono = NULL, es_fijo = fijos[i],
             orden = i - 1L, version = 1L)
      })
      c(base, unname(estado$gcats_extra))
    }
    gcat <- function(id) {
      for (c in gcats_de(estado$tipo)) if (identical(c$id, id)) return(c)
      NULL
    }
    gasto <- function(id, monto, cat_id, medio, fecha, nota = NULL, factura = FALSE) {
      c <- gcat(cat_id)
      list(id = id, fecha = fecha, monto = sprintf("%.2f", as.numeric(monto)), categoria_id = cat_id,
           categoria_nombre = c$nombre, medio_pago = medio, descripcion = nota,
           es_fijo = isTRUE(c$es_fijo), con_factura = isTRUE(factura), version = 1L)
    }
    estado$ventas <- list()          # en orden de creación
    estado$claves_venta <- list()
    estado$ventas_creadas <- 0L
    estado$anulaciones <- 0L
    estado$tipo <- "restaurante"
    estado$sembrado <- FALSE
    estado$cats_extra <- list()
    categorias_de <- function(tipo) {
      base <- list()
      if (tipo == "restaurante") {
        nombres <- c("Entradas", "Platos fuertes", "Bebidas", "Postres")
        base <- lapply(seq_along(nombres), function(i) {
          list(id = paste0("c-", i), nombre = nombres[i], orden = i - 1L, icono = NULL,
               cantidad_items = 0L, version = 1L)
        })
      }
      c(base, unname(estado$cats_extra))
    }
    nombre_categoria <- function(id) {
      for (c in categorias_de(estado$tipo)) if (identical(c$id, id)) return(c$nombre)
      NULL
    }
    item <- function(id, nombre, precio, categoria_id = NULL, version = 1L) {
      list(id = id, tipo_item = if (estado$tipo == "restaurante") "platillo" else "producto",
           nombre = nombre, descripcion = NULL, categoria_id = categoria_id,
           categoria_nombre = nombre_categoria(categoria_id), precio_venta = precio,
           se_vende = TRUE, archivado = FALSE, version = version, aviso = NULL,
           tiene_variantes = FALSE, variantes = list())
    }
    guardar_item <- function(it) {
      estado$items[[it$id]] <- it
      if (!it$id %in% estado$orden_items) estado$orden_items <- c(estado$orden_items, it$id)
    }
    id_de_ruta <- function(ruta) sub("^/v1/items/", "", ruta)

    # --- Inventario: insumos y movimientos en memoria (existencia y costo en la unidad de uso) ---
    estado$insumos <- list()
    estado$recetas <- list()            # id de ítem -> líneas (insumo_id, cantidad, unidad_codigo)
    # --- Compras y proveedores en memoria ---
    estado$proveedores <- list()
    estado$compras <- list()            # en orden de creación
    estado$claves_compra <- list()
    estado$compras_creadas <- 0L
    estado$anulaciones_compra <- 0L
    estado$psembrado <- FALSE
    estado$orden_insumos <- character()
    estado$movs <- list()               # id de insumo -> movimientos (el más nuevo primero)
    estado$claves_mov <- list()
    estado$insumos_creados <- 0L
    estado$movs_creados <- 0L
    estado$isembrado <- FALSE
    unidades_falsas <- list(
      list(codigo = "UN", nombre = "Unidad", tipo = "unidad"),
      list(codigo = "DOC", nombre = "Docena", tipo = "unidad"),
      list(codigo = "G", nombre = "Gramo", tipo = "masa"),
      list(codigo = "OZ", nombre = "Onza", tipo = "masa"),
      list(codigo = "LB", nombre = "Libra", tipo = "masa"),
      list(codigo = "KG", nombre = "Kilogramo", tipo = "masa"),
      list(codigo = "QQ", nombre = "Quintal", tipo = "masa"),
      list(codigo = "ML", nombre = "Mililitro", tipo = "volumen"),
      list(codigo = "L", nombre = "Litro", tipo = "volumen"),
      list(codigo = "GAL", nombre = "Galón", tipo = "volumen"))
    nombre_unidad <- function(codigo) {
      for (u in unidades_falsas) if (identical(u$codigo, codigo)) return(u$nombre)
      NULL
    }
    cant <- function(x) {
      texto <- formatC(x, format = "f", digits = 4)
      if (grepl(".", texto, fixed = TRUE)) {
        texto <- sub("0+$", "", texto)
        texto <- sub("[.]$", "", texto)
      }
      if (texto %in% c("-0", "")) "0" else texto
    }
    insumo_out <- function(i) {
      e <- i$existencia
      est <- if (e <= 0) "falta" else if (i$minimo > 0 && e <= i$minimo) "poco" else "ok"
      list(id = i$id, nombre = i$nombre, unidad_codigo = i$unidad, item_id = i$item_id,
           unidad_nombre = nombre_unidad(i$unidad), existencia = cant(e),
           costo_unitario = sprintf("%.2f", i$costo), valor = sprintf("%.2f", max(0, e * i$costo)),
           stock_minimo = cant(i$minimo), estado = est, version = i$version)
    }
    receta_out <- function(it) {
      lineas <- estado$recetas[[it$id]] %||% list()
      salidas <- lapply(lineas, function(l) {
        ins <- estado$insumos[[l$insumo_id]]
        cantidad <- as.numeric(l$cantidad)
        list(insumo_id = ins$id, insumo_nombre = ins$nombre, archivado = FALSE,
             cantidad = cant(cantidad), unidad_codigo = l$unidad_codigo,
             unidad_nombre = nombre_unidad(l$unidad_codigo),
             costo = sprintf("%.2f", cantidad * ins$costo), sin_costo = ins$costo == 0)
      })
      total <- sum(vapply(salidas, function(l) as.numeric(l$costo), 0))
      precio <- as.numeric(it$precio_venta)
      hay <- length(salidas) > 0
      list(item_id = it$id, item_nombre = it$nombre, tiene_receta = hay, lineas = salidas,
           costo_total = sprintf("%.2f", total),
           costo_completo = !any(vapply(salidas, function(l) l$sin_costo, NA)),
           precio_venta = it$precio_venta,
           margen = if (hay) sprintf("%.2f", precio - total),
           margen_porcentaje = if (hay) as.integer(round((precio - total) * 100 / precio)),
           precio_sugerido = con_precio(it)$precio_sugerido,
           aviso_precio = con_precio(it)$aviso_precio,
           margen_objetivo_porcentaje = as.integer(round(100 * as.numeric(con_precio(it)$margen_objetivo))),
           margen_propio = con_precio(it)$margen_propio)
    }
    # Precio sugerido, versión simple de integrat.precios: costo / (1 - margen), con IVA en el
    # régimen general, hacia arriba a Q0.50; aviso "pierde", "bajo" u "ok".
    costo_de <- function(it) {
      lineas <- estado$recetas[[it$id]] %||% list()
      if (length(lineas) == 0) return(NULL)
      sum(vapply(lineas, function(l) as.numeric(l$cantidad) *
                   (estado$insumos[[l$insumo_id]]$costo %||% 0), 0))
    }
    con_precio <- function(it) {
      margen <- as.numeric(it$margen_propio_valor %||% estado$margen)
      it$margen_objetivo <- sprintf("%.4f", margen)
      it$margen_propio <- !is.null(it$margen_propio_valor)
      it$margen_propio_valor <- NULL
      it$controla_inventario <- !is.null(it$stock)
      it["disponible"] <- list(it$stock)
      it["alerta_existencia"] <- list(if (is.null(it$stock)) NULL else if (it$stock <= 0) "agotado"
                                      else if (it$stock <= estado$minimo) "poco")
      it$stock <- NULL
      costo <- costo_de(it)
      it["precio_sugerido"] <- list(NULL)
      it["aviso_precio"] <- list(NULL)
      if (!is.null(costo) && costo > 0) {
        iva <- if (identical(estado$regimen, "general")) 1.12 else 1
        it$precio_sugerido <- sprintf("%.2f", ceiling(costo / (1 - margen) * iva * 2 - 1e-9) / 2)
        neto <- as.numeric(it$precio_venta) / iva
        it$aviso_precio <- if (neto < costo) "pierde" else if ((neto - costo) / neto < margen) "bajo" else "ok"
      }
      it
    }
    proveedor_por_nombre <- function(nombre) {
      for (p in estado$proveedores) if (identical(tolower(p$nombre), tolower(nombre))) return(p)
      NULL
    }
    insumo_nuevo <- function(id, nombre, unidad, existencia = 0, costo_total = 0, minimo = 0) {
      i <- list(id = id, nombre = nombre, unidad = unidad, existencia = existencia,
                costo = if (existencia > 0) costo_total / existencia else 0,
                minimo = minimo, version = 1L)
      estado$insumos[[id]] <- i
      estado$orden_insumos <- c(estado$orden_insumos, id)
      estado$movs[[id]] <- if (existencia > 0) {
        list(list(id = paste0("m-", id, "-0"), tipo = "inicial", cantidad = cant(existencia),
                  costo_unitario = sprintf("%.2f", i$costo), fecha_hora = "2026-11-24T10:00:00Z",
                  nota = NULL, insumo = NULL))
      } else list()
      i
    }
    insumos_vivos_lista <- function() {
      vivos <- unname(estado$insumos[estado$orden_insumos[estado$orden_insumos %in% names(estado$insumos)]])
      vivos[order(vapply(vivos, function(i) tolower(i$nombre), ""))]
    }
    id_insumo_de_ruta <- function(ruta) sub("/movimientos$", "", sub("^/v1/insumos/", "", ruta))

    app <- list(call = function(req) {
      ruta <- req$PATH_INFO
      metodo <- req$REQUEST_METHOD
      auth <- req$HTTP_AUTHORIZATION %||% ""

      if (ruta == "/_creados") {
        return(json(200, list(creados = estado$creados, salidas = estado$salidas,
                              items = estado$items_creados,
                              ventas = estado$ventas_creadas,
                              gastos = estado$gastos_creados,
                              gastos_vivos = length(estado$gastos),
                              anulaciones = estado$anulaciones,
                              insumos = estado$insumos_creados,
                              insumos_vivos = length(estado$insumos),
                              movimientos = estado$movs_creados,
                              compras = estado$compras_creadas,
                              anulaciones_compra = estado$anulaciones_compra,
                              proveedores = length(estado$proveedores),
                              regimen = estado$regimen,
                              margen = estado$margen,
                              regla_venta = estado$regla_venta,
                              importaciones = length(estado$importaciones),
                              importaciones_recibidas = sum(vapply(estado$importaciones,
                                function(i) i$estado %in% c("recibida", "recibida_parcial"), NA)),
                              importaciones_parciales = sum(vapply(estado$importaciones,
                                function(i) identical(i$estado, "recibida_parcial"), NA)),
                              cierres = estado$cierres_hechos,
                              caja_abierta = !is.null(estado$caja),
                              dueno = length(estado$dueno),
                              gastos_con_factura = sum(vapply(estado$gastos,
                                function(g) isTRUE(g$con_factura), NA)),
                              resultados = estado$resultados_llamadas,
                              items_vivos = length(estado$items))))
      }
      if (ruta == "/v1/auth/salir" && metodo == "POST") {
        estado$salidas <- estado$salidas + 1L
        # La API real responde 204; httpuv + curl se confunden con un 204 sin cuerpo en una
        # conexión reutilizada, y a la app solo le importa que la llamada no falle.
        return(json(200, list()))
      }
      if (ruta == "/v1/salud") {
        return(json(200, list(estado = "ok", version = "0", entorno = "dev",
                              bd = list(conectada = TRUE))))
      }
      if (ruta == "/v1/tipos-negocio") {
        return(json(200, list(
          list(codigo = "ventas_en_linea", nombre = "Vendo en línea",
               descripcion = "Vendes por WhatsApp, Instagram o tienda web.", icono = "bag"),
          list(codigo = "restaurante", nombre = "Tengo un restaurante o comedor",
               descripcion = "Vendes comida y bebida.", icono = "cup-hot"))))
      }
      if (ruta == "/v1/auth/registro" && metodo == "POST") {
        d <- leer(req)
        if (identical(d$correo, "repetido@prueba.com")) {
          return(json(409, list(detail = "Ese correo ya tiene una cuenta. Prueba iniciar sesión.")))
        }
        return(json(201, sesion(d$nombre, d$correo)))
      }
      if (ruta == "/v1/auth/login" && metodo == "POST") {
        d <- leer(req)
        if (identical(d$correo, "mari@prueba.com") && identical(d$clave, "clave-correcta-1")) {
          if (!estado$gsembrado) {
            estado$gsembrado <- TRUE
            estado$tipo <- "restaurante"
            estado$gastos[["gx-1"]] <- gasto("gx-1", "3500", "g-1", "transferencia",
                                              format(Sys.Date(), "%Y-%m-01"))
            estado$gastos[["gx-2"]] <- gasto("gx-2", "45", "g-4", "efectivo", format(Sys.Date()))
          }
          if (!estado$psembrado) {
            estado$psembrado <- TRUE
            estado$proveedores[["pr-1"]] <- list(id = "pr-1", nombre = "Don Pedro",
                                                  telefono = "5555-1234", version = 1L)
          }
          if (!estado$isembrado) {
            estado$isembrado <- TRUE
            insumo_nuevo("in-1", "Harina", "LB", 10, 150, minimo = 3)
            insumo_nuevo("in-2", "Aceite", "L", 1, 40, minimo = 2)
          }
          if (!estado$sembrado) {
            estado$sembrado <- TRUE
            guardar_item(item("i-1", "Pepián", "45.00", "c-2"))
            guardar_item(item("i-2", "Horchata", "10.00", "c-3"))
          }
          return(json(200, sesion("Mari", d$correo, negocio_id = "n-mari")))
        }
        return(json(401, list(detail = "Correo o contraseña incorrectos.")))
      }
      if (ruta == "/v1/auth/refrescar" && metodo == "POST") {
        d <- leer(req)
        if (identical(d$refresh_token, "refresco-valido")) {
          return(json(200, sesion("Mari", "mari@prueba.com", negocio_id = "n-mari")))
        }
        return(json(401, list(detail = "Tu sesión venció. Inicia sesión otra vez.")))
      }

      # Desde aquí todo exige token
      if (!startsWith(auth, "Bearer ") || grepl("token-vencido", auth)) {
        return(json(401, list(detail = "Tu sesión venció. Inicia sesión otra vez.")))
      }
      if (ruta == "/v1/negocios" && metodo == "POST") {
        d <- leer(req)
        if (!d$tipo_negocio_codigo %in% names(vocab)) {
          return(json(422, list(detail = "Ese tipo de negocio no existe.")))
        }
        Sys.sleep(0.4)  # para que un doble toque llegue antes de terminar
        clave <- req$HTTP_IDEMPOTENCY_KEY %||% NULL
        if (!is.null(clave) && !is.null(estado$claves[[clave]])) {
          return(json(201, estado$claves[[clave]]))  # misma clave: mismo negocio, no se crea otro
        }
        estado$creados <- estado$creados + 1L
        estado$tipo <- d$tipo_negocio_codigo
        estado$nombre_nuevo <- d$nombre
        estado$factura_nueva <- d$da_factura
        n <- negocio("n-nuevo", d$nombre, d$tipo_negocio_codigo, d$da_factura)
        n$acceso <- list(token_type = "bearer", access_token = "token-con-negocio",
                         expira_en = 900, negocio_id = "n-nuevo")
        if (!is.null(clave)) estado$claves[[clave]] <- n
        # "Falla una vez": se crea, pero la respuesta se pierde (la primera vez responde 503).
        if (identical(d$nombre, "Falla una vez") && estado$creados == 1L) {
          return(json(503, list(detail = "El servicio no está listo. Intenta más tarde.")))
        }
        return(json(201, n))
      }
      # Atajo de las pruebas: fija la existencia de un ítem (no existe en la API real).
      if (ruta == "/_stock" && metodo == "POST") {
        d <- leer(req)
        it <- estado$items[[d$item_id]]
        it["stock"] <- list(if (is.null(d$n)) NULL else as.integer(d$n))
        estado$items[[d$item_id]] <- it
        return(json(200, list()))
      }
      if (grepl("^/v1/negocios/[^/]+/ventas$", ruta) && metodo == "PUT") {
        d <- leer(req)
        if (!(d$vender_sin_existencia %||% "") %in% c("bloquear", "avisar")) {
          return(json(422, list(detail = "Revisa los datos e intenta de nuevo.")))
        }
        estado$regla_venta <- d$vender_sin_existencia
        if (!is.null(d$minimo_defecto)) estado$minimo <- as.integer(d$minimo_defecto)
        return(json(200, list()))
      }
      if (ruta == "/v1/inventario/alertas" && metodo == "GET") {
        productos <- list()
        for (it in estado$items) {
          if (is.null(it$stock) || it$stock > estado$minimo) next
          productos[[length(productos) + 1L]] <- list(
            item_id = it$id, item_variante_id = paste0(it$id, "-u"), nombre = it$nombre,
            disponible = it$stock, estado = if (it$stock <= 0) "agotado" else "poco")
        }
        return(json(200, list(productos = productos, ingredientes = list())))
      }
      if (ruta == "/v1/categorias/sugeridas" && metodo == "GET") {
        return(json(200, list(list(nombre = "Ropa de dormir", icono = "moon-stars",
                                   atributos = list("Talla", "Color"), palabras_clave = list("pijama")))))
      }
      if (ruta == "/v1/importaciones/vista-previa" && metodo == "POST") {
        crudo <- req$rook.input$read()
        cabeza <- rawToChar(crudo[seq_len(min(400L, length(crudo)))][crudo[seq_len(min(400L, length(crudo)))] != as.raw(0)])
        if (grepl("filename=\"[^\"]*\\.pdf\"", cabeza)) {
          return(json(422, list(detail = "Sube la plantilla en Excel (.xlsx) o CSV.")))
        }
        return(json(200, previa_falsa))
      }
      if (ruta == "/v1/importaciones" && metodo == "POST") {
        d <- leer(req)
        clave <- req$HTTP_IDEMPOTENCY_KEY %||% NULL
        if (!is.null(clave) && !is.null(estado$claves_importacion[[clave]])) {
          return(json(201, estado$claves_importacion[[clave]]))
        }
        if (is.null(d$cobro_q)) return(json(422, list(detail = "Dinos cuánto te cobró la tarjeta en quetzales.")))
        id <- paste0("imp-", length(estado$importaciones) + 1L)
        k <- 0L
        lineas <- list()
        for (prod in d$productos) for (l in prod$lineas) {
          k <- k + 1L
          valores <- paste(unlist(l$atributos), collapse = " \u00b7 ")
          lineas[[k]] <- list(id = paste0(id, "-l", k),
                              nombre = if (nzchar(valores)) paste(prod$nombre, "\u00b7", valores) else prod$nombre,
                              codigo = l$codigo, atributos = l$atributos, item_id = NULL,
                              item_variante_id = NULL, cantidad = l$cantidad,
                              precio_unitario = sprintf("%.2f", as.numeric(l$precio_unitario)),
                              costo_pedido_q = "50.00", cantidad_recibida = NULL, courier_q = NULL,
                              pendiente = l$cantidad, cantidad_perdida = NULL, peso = l$peso,
                              costo_unitario_q = NULL, precio_sugerido = NULL)
        }
        imp <- list(id = id, plataforma = d$plataforma, numero_factura = d$numero_factura,
                    numero_orden = d$numero_orden, fecha_factura = d$fecha_factura,
                    moneda_codigo = d$moneda_codigo, total_factura = "519.00",
                    tipo_cambio = sprintf("%.6f", as.numeric(d$cobro_q) / 519),
                    total_q = sprintf("%.2f", as.numeric(d$cobro_q)), medio_pago = d$medio_pago,
                    estado = "en_camino", creada_en = "2026-11-25T10:00:00Z", recibida_en = NULL,
                    guia = NULL, courier_q = NULL, envio_local_q = NULL, nota = NULL,
                    motivo_anulacion = NULL, unidades = sum(vapply(lineas, function(l) l$cantidad, 0L)),
                    dias_en_camino = 2L, lineas = lineas, entregas = list(),
                    pendientes = sum(vapply(lineas, function(l) l$cantidad, 0L)), productos_nombres = vapply(d$productos, function(x) x$nombre, ""))
        estado$importaciones[[id]] <- imp
        if (!is.null(clave)) estado$claves_importacion[[clave]] <- imp
        return(json(201, imp))
      }
      if (ruta == "/v1/importaciones" && metodo == "GET") {
        todas <- rev(unname(estado$importaciones))
        en_camino <- Filter(function(i) i$estado %in% c("en_camino", "llegando"), todas)
        recibidas <- Filter(function(i) i$estado %in% c("recibida", "recibida_parcial"), todas)
        return(json(200, list(en_camino = lapply(en_camino, importacion_out, FALSE),
                              recibidas = lapply(recibidas, importacion_out, FALSE))))
      }
      if (grepl("^/v1/importaciones/[^/]+/recibir$", ruta) && metodo == "POST") {
        id <- sub("/recibir$", "", sub("^/v1/importaciones/", "", ruta))
        imp <- estado$importaciones[[id]]
        if (is.null(imp)) return(json(404, list(detail = "No encontramos esa importación.")))
        if (!imp$estado %in% c("en_camino", "llegando")) return(json(409, list(detail = "Esta importación ya no está en camino.")))
        d <- leer(req)
        unidades <- 0L
        imp$lineas <- lapply(imp$lineas, function(l) {
          pend <- l$cantidad - (l$cantidad_recibida %||% 0L) - (l$cantidad_perdida %||% 0L)
          n <- if (is.null(d$lineas)) pend else {
            r <- Filter(function(x) identical(x$linea_id, l$id), d$lineas)
            if (length(r)) r[[1]]$cantidad else 0L
          }
          if (n > 0) {
            l$cantidad_recibida <- (l$cantidad_recibida %||% 0L) + n
            l$courier_q <- "10.00"
            l$costo_unitario_q <- "60.00000000"
            l$precio_sugerido <- "92.50"
            unidades <<- unidades + n
          }
          if (isTRUE(d$cerrar) && pend - n > 0) l$cantidad_perdida <- pend - n
          l$pendiente <- l$cantidad - (l$cantidad_recibida %||% 0L) - (l$cantidad_perdida %||% 0L)
          l
        })
        imp$pendientes <- sum(vapply(imp$lineas, function(l) l$pendiente, 0L))
        perdidas <- any(vapply(imp$lineas, function(l) isTRUE(l$cantidad_perdida > 0), NA))
        imp$estado <- if (imp$pendientes > 0) "llegando" else if (perdidas) "recibida_parcial" else "recibida"
        imp$entregas <- c(imp$entregas %||% list(), list(list(
          numero = length(imp$entregas %||% list()) + 1L, recibida_en = "2026-11-27T10:00:00Z",
          guia = d$guia, courier_q = sprintf("%.2f", as.numeric(d$courier_q %||% 0)),
          envio_local_q = "0.00", reparto = d$reparto %||% "valor", cierra = isTRUE(d$cerrar),
          unidades = unidades)))
        imp$recibida_en <- "2026-11-27T10:00:00Z"
        imp$guia <- d$guia
        imp$courier_q <- sprintf("%.2f", as.numeric(d$courier_q %||% 0))
        estado$importaciones[[id]] <- imp
        return(json(200, imp))
      }
      if (grepl("^/v1/importaciones/[^/]+/anular$", ruta) && metodo == "POST") {
        id <- sub("/anular$", "", sub("^/v1/importaciones/", "", ruta))
        imp <- estado$importaciones[[id]]
        if (is.null(imp)) return(json(404, list(detail = "No encontramos esa importación.")))
        imp$estado <- "anulada"
        estado$importaciones[[id]] <- imp
        return(json(200, imp))
      }
      if (startsWith(ruta, "/v1/importaciones/") && metodo == "GET") {
        imp <- estado$importaciones[[sub("^/v1/importaciones/", "", ruta)]]
        if (is.null(imp)) return(json(404, list(detail = "No encontramos esa importación.")))
        return(json(200, imp))
      }
      if (ruta == "/v1/atributos" && metodo == "GET") {
        return(json(200, estado$atributos))
      }
      if (startsWith(ruta, "/v1/items/") && endsWith(ruta, "/variantes") && metodo == "PUT") {
        id <- sub("/variantes$", "", sub("^/v1/items/", "", ruta))
        it <- estado$items[[id]]
        if (is.null(it)) return(json(404, list(detail = "No encontramos eso.")))
        d <- leer(req)
        combos <- vapply(d$variantes, function(x) paste(tolower(unlist(x$atributos)), collapse = "|"), "")
        if (any(duplicated(combos))) return(json(422, list(detail = "Hay dos variantes iguales.")))
        if (any(vapply(d$variantes, function(x) length(x$atributos) == 0, NA))) {
          return(json(422, list(detail = "Revisa los datos e intenta de nuevo.")))
        }
        it$variantes <- lapply(d$variantes, function(x) {
          if (is.null(x$id)) {
            estado$variantes_creadas <- estado$variantes_creadas + 1L
            x$id <- paste0("var-", estado$variantes_creadas)
          }
          # valores nuevos se agregan al atributo
          for (n in names(x$atributos)) {
            for (k in seq_along(estado$atributos)) {
              a <- estado$atributos[[k]]
              if (identical(a$nombre, n) && !x$atributos[[n]] %in% vapply(a$valores, function(v) v$valor, "")) {
                a$valores[[length(a$valores) + 1L]] <- list(id = paste0("va-", x$atributos[[n]]),
                                                            valor = x$atributos[[n]])
                estado$atributos[[k]] <- a
              }
            }
          }
          list(id = x$id, nombre = paste(unlist(x$atributos), collapse = " · "),
               atributos = x$atributos, codigo = x$codigo,
               precio_venta = sprintf("%.2f", as.numeric(x$precio_venta)),
               precio_sugerido = NULL, aviso_precio = NULL)
        })
        it$tiene_variantes <- length(it$variantes) > 0
        if (it$tiene_variantes) {
          it$precio_venta <- sprintf("%.2f", min(vapply(it$variantes, function(x) as.numeric(x$precio_venta), 0)))
        }
        it$version <- it$version + 1L
        guardar_item(it)
        return(json(200, con_precio(it)))
      }
      if (grepl("^/v1/negocios/[^/]+/precios$", ruta) && metodo == "PUT") {
        d <- leer(req)
        m <- suppressWarnings(as.numeric(d$margen_objetivo))
        if (is.na(m) || m < 0 || m > 0.9) return(json(422, list(detail = "Revisa los datos e intenta de nuevo.")))
        estado$margen <- sprintf("%.4f", m)
        return(json(200, list()))
      }
      if (grepl("^/v1/negocios/[^/]+/impuestos$", ruta) && metodo == "PUT") {
        d <- leer(req)
        if (!(d$regimen_iva %||% "") %in% c("general", "pequeno", "no_se")) {
          return(json(422, list(detail = "Revisa los datos e intenta de nuevo.")))
        }
        estado$regimen <- d$regimen_iva
        # La API real responde 204; aquí 200 con {} porque un 204 de httpuv sin cuerpo deja
        # la conexión en mal estado para la siguiente petición (para la app, ambos son "ok").
        return(json(200, list()))
      }
      if (ruta == "/v1/caja" && metodo == "GET") {
        ultimo <- if (length(estado$cierres) > 0) estado$cierres[[1]] else NULL
        abierta <- if (is.null(estado$caja)) NULL else caja_en_vivo(estado$caja)
        return(json(200, list(abierta = abierta, ultimo_cierre = ultimo)))
      }
      if (ruta == "/v1/caja/abrir" && metodo == "POST") {
        d <- leer(req)
        if (!is.null(estado$caja)) return(json(409, list(detail = "La caja ya está abierta.")))
        monto <- suppressWarnings(as.numeric(d$monto_apertura))
        if (is.na(monto) || monto < 0) return(json(422, list(detail = "Revisa los datos e intenta de nuevo.")))
        estado$caja <- list(id = paste0("caja-", estado$cierres_hechos + 1L),
                            fecha = format(Sys.Date()),
                            abierta_en = format(Sys.time(), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC"),
                            monto_apertura = sprintf("%.2f", monto), estado = "abierta",
                            efectivo_contado = NULL, diferencia = NULL, cerrada_en = NULL,
                            nota = NULL, ventas_al_abrir = estado$ventas_creadas)
        return(json(201, caja_en_vivo(estado$caja)))
      }
      if (ruta == "/v1/caja/cerrar" && metodo == "POST") {
        d <- leer(req)
        clave <- req$HTTP_IDEMPOTENCY_KEY %||% NULL
        if (!is.null(clave) && !is.null(estado$claves_cierre[[clave]])) {
          return(json(200, estado$claves_cierre[[clave]]))
        }
        if (is.null(estado$caja)) return(json(409, list(detail = "La caja no está abierta. Ábrela primero.")))
        c <- caja_en_vivo(estado$caja)
        contado <- as.numeric(d$efectivo_contado)
        c$estado <- "cerrada"
        c$efectivo_contado <- sprintf("%.2f", contado)
        c$diferencia <- sprintf("%.2f", contado - as.numeric(c$efectivo_esperado))
        c$cerrada_en <- format(Sys.time(), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
        c$nota <- d$nota
        estado$caja <- NULL
        estado$cierres <- c(list(c), estado$cierres)
        estado$cierres_hechos <- estado$cierres_hechos + 1L
        if (!is.null(clave)) estado$claves_cierre[[clave]] <- c
        return(json(200, c))
      }
      if (ruta == "/v1/caja/cierres" && metodo == "GET") {
        return(json(200, list(mes = format(Sys.Date(), "%Y-%m"), cierres = estado$cierres)))
      }
      if (ruta == "/v1/dueno" && metodo == "GET") {
        movs <- rev(unname(estado$dueno))
        total <- function(t) sprintf("%.2f", sum(vapply(Filter(function(m) m$tipo == t, movs),
                                                       function(m) as.numeric(m$monto), 0)))
        return(json(200, list(mes = format(Sys.Date(), "%Y-%m"), total_aportes = total("aporte"),
                              total_retiros = total("retiro"), movimientos = movs)))
      }
      if (ruta == "/v1/dueno" && metodo == "POST") {
        d <- leer(req)
        monto <- suppressWarnings(as.numeric(d$monto))
        if (!(d$tipo %||% "") %in% c("aporte", "retiro") || is.na(monto) || monto <= 0 ||
            !(d$medio %||% "") %in% c("efectivo", "banco")) {
          return(json(422, list(detail = "Revisa los datos e intenta de nuevo.")))
        }
        Sys.sleep(0.4)  # para que un doble toque llegue antes de terminar
        clave <- req$HTTP_IDEMPOTENCY_KEY %||% NULL
        if (!is.null(clave) && !is.null(estado$claves_dueno[[clave]])) {
          return(json(201, estado$claves_dueno[[clave]]))
        }
        m <- list(id = paste0("d-", length(estado$dueno) + 1L), tipo = d$tipo,
                  monto = sprintf("%.2f", monto), medio = d$medio,
                  fecha = d$fecha %||% format(Sys.Date()), nota = d$nota)
        estado$dueno[[m$id]] <- m
        if (!is.null(clave)) estado$claves_dueno[[clave]] <- m
        return(json(201, m))
      }
      if (startsWith(ruta, "/v1/dueno/") && metodo == "DELETE") {
        id <- sub("^/v1/dueno/", "", ruta)
        if (is.null(estado$dueno[[id]])) return(json(404, list(detail = "No encontramos ese movimiento.")))
        estado$dueno[[id]] <- NULL
        return(json(200, list()))
      }
      # Resultados del mes: versión simple de lo que calcula la API real desde los asientos
      # (ventas pagadas menos gastos; en el régimen general, sin el 12 % de IVA de las ventas).
      if (ruta == "/v1/resultados" && metodo == "GET") {
        estado$resultados_llamadas <- estado$resultados_llamadas + 1L
        if (identical(auth, "Bearer token-cajero")) {
          return(json(403, list(detail = "No tienes permiso para ver esto.")))
        }
        ventas <- sum(vapply(Filter(function(v) identical(v$estado, "pagada"), estado$ventas),
                             function(v) as.numeric(v$total), 0))
        if (identical(estado$regimen, "general")) ventas <- round(ventas / 1.12, 2)
        gastos <- sum(vapply(estado$gastos, function(g) as.numeric(g$monto), 0))
        return(json(200, list(
          mes = format(Sys.Date(), "%Y-%m"), vendiste = sprintf("%.2f", ventas),
          costo_de_lo_vendido = "0.00", se_perdio = "0.00", gastaste = sprintf("%.2f", gastos),
          otros_ingresos = "0.00", te_queda = sprintf("%.2f", ventas - gastos),
          sin_iva = identical(estado$regimen, "general"),
          gastos_fijos = sprintf("%.2f", sum(vapply(Filter(function(g) isTRUE(g$es_fijo), estado$gastos),
                                                    function(g) as.numeric(g$monto), 0))),
          margen_objetivo = "0.3500")))
      }
      if (ruta == "/v1/negocios/n-nuevo" && metodo == "GET") {
        return(json(200, negocio("n-nuevo", estado$nombre_nuevo, estado$tipo, estado$factura_nueva)))
      }
      if (ruta == "/v1/negocios/n-mari") {
        return(json(200, negocio("n-mari", "Comedor Doña Mari", "restaurante", "no")))
      }
      if (ruta == "/v1/categorias" && metodo == "GET") {
        return(json(200, categorias_de(estado$tipo)))
      }
      if (ruta == "/v1/categorias" && metodo == "POST") {
        d <- leer(req)
        nombre <- trimws(d$nombre %||% "")
        if (nchar(nombre) < 2) return(json(422, list(detail = "Revisa los datos e intenta de nuevo.")))
        if (any(vapply(categorias_de(estado$tipo), function(c) identical(tolower(c$nombre), tolower(nombre)), NA))) {
          return(json(409, list(detail = "Ya tienes una categoría con ese nombre.")))
        }
        id <- paste0("c-x", length(estado$cats_extra) + 1L)
        nueva <- list(id = id, nombre = nombre, orden = length(categorias_de(estado$tipo)),
                      icono = NULL, cantidad_items = 0L, version = 1L)
        estado$cats_extra[[id]] <- nueva
        return(json(201, nueva))
      }
      if (ruta == "/v1/items" && metodo == "GET") {
        vivos <- unname(estado$items[estado$orden_items[estado$orden_items %in% names(estado$items)]])
        vivos <- vivos[order(vapply(vivos, function(i) tolower(i$nombre), ""))]
        return(json(200, list(total = length(vivos), items = lapply(vivos, con_precio))))
      }
      if (ruta == "/v1/items" && metodo == "POST") {
        d <- leer(req)
        if (is.null(d$nombre) || nchar(trimws(d$nombre)) < 2 ||
            !grepl("^[0-9]+([.][0-9]{1,2})?$", d$precio_venta %||% "")) {
          return(json(422, list(detail = "Revisa los datos e intenta de nuevo.")))
        }
        Sys.sleep(0.4)  # para que un doble toque llegue antes de terminar
        clave <- req$HTTP_IDEMPOTENCY_KEY %||% NULL
        if (!is.null(clave) && !is.null(estado$claves_item[[clave]])) {
          return(json(201, estado$claves_item[[clave]]))
        }
        estado$items_creados <- estado$items_creados + 1L
        id <- paste0("i-n", estado$items_creados + 10L)
        repetido <- any(vapply(estado$items, function(i) identical(tolower(i$nombre), tolower(d$nombre)), NA))
        it <- item(id, trimws(d$nombre), sprintf("%.2f", as.numeric(d$precio_venta)), d$categoria_id)
        guardar_item(it)
        if (repetido) it$aviso <- "Ya tienes un platillo con ese nombre."
        if (!is.null(clave)) estado$claves_item[[clave]] <- it
        if (identical(d$nombre, "Falla una vez") && estado$items_creados == 1L) {
          return(json(503, list(detail = "El servicio no está listo. Intenta más tarde.")))
        }
        return(json(201, it))
      }
      if (ruta == "/v1/gastos/categorias" && metodo == "GET") {
        return(json(200, gcats_de(estado$tipo)))
      }
      if (ruta == "/v1/gastos/categorias" && metodo == "POST") {
        d <- leer(req)
        nombre <- trimws(d$nombre %||% "")
        if (nchar(nombre) < 2) return(json(422, list(detail = "Revisa los datos e intenta de nuevo.")))
        if (any(vapply(gcats_de(estado$tipo), function(c) identical(tolower(c$nombre), tolower(nombre)), NA))) {
          return(json(409, list(detail = "Ya tienes una categoría con ese nombre.")))
        }
        id <- paste0("g-x", length(estado$gcats_extra) + 1L)
        nueva <- list(id = id, nombre = nombre, icono = NULL, es_fijo = isTRUE(d$es_fijo),
                      orden = length(gcats_de(estado$tipo)), version = 1L)
        estado$gcats_extra[[id]] <- nueva
        return(json(201, nueva))
      }
      if (ruta == "/v1/gastos" && metodo == "GET") {
        consulta <- req$QUERY_STRING %||% ""
        mes <- sub(".*mes=([0-9-]+).*", "\\1", consulta)
        if (!grepl("^[0-9]{4}-[0-9]{2}$", mes)) mes <- format(Sys.Date(), "%Y-%m")
        todos <- unname(estado$gastos)
        del_mes <- Filter(function(g) startsWith(g$fecha, mes), todos)
        del_mes <- del_mes[order(vapply(del_mes, function(g) g$fecha, ""), decreasing = TRUE)]
        total <- sum(vapply(del_mes, function(g) as.numeric(g$monto), 0))
        fijos <- sum(vapply(Filter(function(g) isTRUE(g$es_fijo), del_mes), function(g) as.numeric(g$monto), 0))
        nombres <- unique(vapply(del_mes, function(g) g$categoria_nombre, ""))
        por_cat <- lapply(nombres, function(n) {
          propios <- Filter(function(g) identical(g$categoria_nombre, n), del_mes)
          monto <- sum(vapply(propios, function(g) as.numeric(g$monto), 0))
          list(categoria_id = propios[[1]]$categoria_id, nombre = n, total = sprintf("%.2f", monto),
               porcentaje = as.integer(round(monto * 100 / total)))
        })
        por_cat <- por_cat[order(-vapply(por_cat, function(c) as.numeric(c$total), 0))]
        resumen <- list(cantidad = length(del_mes), total = sprintf("%.2f", total),
                        total_fijos = sprintf("%.2f", fijos),
                        total_variables = sprintf("%.2f", total - fijos), por_categoria = por_cat)
        return(json(200, list(mes = mes, resumen = resumen, gastos = del_mes)))
      }
      if (ruta == "/v1/gastos" && metodo == "POST") {
        d <- leer(req)
        monto <- suppressWarnings(as.numeric(d$monto))
        if (is.na(monto) || monto <= 0 || is.null(gcat(d$categoria_id))) {
          return(json(422, list(detail = "Revisa los datos e intenta de nuevo.")))
        }
        fecha <- d$fecha %||% format(Sys.Date())
        if (fecha > format(Sys.Date())) {
          return(json(422, list(detail = "La fecha no puede ser de mañana en adelante.")))
        }
        Sys.sleep(0.4)  # para que un doble toque llegue antes de terminar
        clave <- req$HTTP_IDEMPOTENCY_KEY %||% NULL
        if (!is.null(clave) && !is.null(estado$claves_gasto[[clave]])) {
          return(json(201, estado$claves_gasto[[clave]]))
        }
        estado$gastos_creados <- estado$gastos_creados + 1L
        g <- gasto(paste0("gx-n", estado$gastos_creados + 10L), d$monto, d$categoria_id,
                   d$medio_pago, fecha, d$descripcion, isTRUE(d$con_factura))
        estado$gastos[[g$id]] <- g
        if (!is.null(clave)) estado$claves_gasto[[clave]] <- g
        if (identical(d$descripcion, "Se pierde") && estado$gastos_creados == 1L) {
          return(json(503, list(detail = "El servicio no está listo. Intenta más tarde.")))
        }
        return(json(201, g))
      }
      if (startsWith(ruta, "/v1/gastos/")) {
        id <- sub("^/v1/gastos/", "", ruta)
        g <- estado$gastos[[id]]
        if (is.null(g)) return(json(404, list(detail = "No encontramos ese gasto.")))
        if (metodo == "GET") return(json(200, g))
        if (metodo == "DELETE") {
          estado$gastos[[id]] <- NULL
          return(json(200, list()))
        }
        if (metodo == "PATCH") {
          d <- leer(req)
          if (identical(g$descripcion, "Conflicto") || !identical(as.integer(d$version), g$version)) {
            return(json(409, list(detail = "Alguien más cambió esto. Ábrelo de nuevo e inténtalo otra vez.")))
          }
          nuevo <- gasto(id, d$monto %||% g$monto, d$categoria_id %||% g$categoria_id,
                         d$medio_pago %||% g$medio_pago, d$fecha %||% g$fecha, d$descripcion,
                         d$con_factura %||% g$con_factura)
          nuevo$version <- g$version + 1L
          estado$gastos[[id]] <- nuevo
          return(json(200, nuevo))
        }
      }
      if (ruta == "/v1/proveedores" && metodo == "GET") {
        lista <- unname(estado$proveedores)
        lista <- lista[order(vapply(lista, function(p) tolower(p$nombre), ""))]
        return(json(200, lista))
      }
      if (ruta == "/v1/proveedores" && metodo == "POST") {
        d <- leer(req)
        nombre <- trimws(d$nombre %||% "")
        if (nchar(nombre) < 2) return(json(422, list(detail = "Revisa los datos e intenta de nuevo.")))
        if (!is.null(proveedor_por_nombre(nombre))) {
          return(json(409, list(detail = "Ya tienes un proveedor con ese nombre.")))
        }
        id <- paste0("pr-n", length(estado$proveedores) + 10L)
        nuevo <- list(id = id, nombre = nombre, telefono = d$telefono, version = 1L)
        estado$proveedores[[id]] <- nuevo
        return(json(201, nuevo))
      }
      if (ruta == "/v1/compras" && metodo == "POST") {
        d <- leer(req)
        if (length(d$lineas) == 0 || !(d$medio_pago %in% c("efectivo", "tarjeta", "transferencia"))) {
          return(json(422, list(detail = "Revisa los datos e intenta de nuevo.")))
        }
        fecha <- d$fecha %||% format(Sys.Date())
        if (fecha > format(Sys.Date())) {
          return(json(422, list(detail = "La fecha no puede ser de mañana en adelante.")))
        }
        for (l in d$lineas) {
          if (is.null(estado$insumos[[l$insumo_id]])) {
            return(json(422, list(detail = "Uno de los insumos no existe.")))
          }
        }
        Sys.sleep(0.4)  # para que un doble toque llegue antes de terminar
        clave <- req$HTTP_IDEMPOTENCY_KEY %||% NULL
        if (!is.null(clave) && !is.null(estado$claves_compra[[clave]])) {
          return(json(201, estado$claves_compra[[clave]]))
        }
        estado$compras_creadas <- estado$compras_creadas + 1L
        proveedor <- NULL
        if (!is.null(d$proveedor_id)) proveedor <- estado$proveedores[[d$proveedor_id]]
        if (!is.null(d$proveedor_nuevo)) {
          proveedor <- proveedor_por_nombre(d$proveedor_nuevo$nombre)
          if (is.null(proveedor)) {
            id <- paste0("pr-n", length(estado$proveedores) + 10L)
            proveedor <- list(id = id, nombre = trimws(d$proveedor_nuevo$nombre),
                              telefono = d$proveedor_nuevo$telefono, version = 1L)
            estado$proveedores[[id]] <- proveedor
          }
        }
        armadas <- list()
        total <- 0
        for (l in d$lineas) {
          ins <- estado$insumos[[l$insumo_id]]
          q <- as.numeric(l$cantidad)
          costo_linea <- as.numeric(l$costo_total)
          ins$costo <- if (ins$existencia <= 0) costo_linea / q else (ins$existencia * ins$costo + costo_linea) / (ins$existencia + q)
          ins$existencia <- ins$existencia + q
          estado$insumos[[ins$id]] <- ins
          total <- total + costo_linea
          armadas[[length(armadas) + 1L]] <- list(
            insumo_id = ins$id, nombre = ins$nombre, cantidad = cant(q),
            unidad_codigo = l$unidad_codigo %||% ins$unidad, costo_total = sprintf("%.2f", costo_linea))
        }
        compra <- list(
          id = paste0("co-", estado$compras_creadas), fecha = fecha,
          proveedor_id = proveedor$id, proveedor_nombre = proveedor$nombre,
          numero_factura = d$numero_factura, medio_pago = d$medio_pago,
          total = sprintf("%.2f", total), estado = "registrada", nota = NULL, lineas = armadas,
          anulada_en = NULL, motivo_anulacion = NULL)
        estado$compras[[compra$id]] <- compra
        if (!is.null(clave)) estado$claves_compra[[clave]] <- compra
        if (identical(d$numero_factura, "Se pierde") && estado$compras_creadas == 1L) {
          return(json(503, list(detail = "El servicio no está listo. Intenta más tarde.")))
        }
        return(json(201, compra))
      }
      if (ruta == "/v1/compras" && metodo == "GET") {
        consulta <- req$QUERY_STRING %||% ""
        mes <- sub(".*mes=([0-9-]+).*", "\\1", consulta)
        if (!grepl("^[0-9]{4}-[0-9]{2}$", mes)) mes <- format(Sys.Date(), "%Y-%m")
        del_mes <- Filter(function(co) startsWith(co$fecha, mes), unname(estado$compras))
        del_mes <- rev(del_mes)
        vigentes <- Filter(function(co) identical(co$estado, "registrada"), del_mes)
        total <- sum(vapply(vigentes, function(co) as.numeric(co$total), 0))
        return(json(200, list(mes = mes,
                              resumen = list(cantidad = length(vigentes), total = sprintf("%.2f", total)),
                              compras = del_mes)))
      }
      if (startsWith(ruta, "/v1/compras/")) {
        resto <- sub("^/v1/compras/", "", ruta)
        anular <- endsWith(resto, "/anular")
        id <- sub("/anular$", "", resto)
        co <- estado$compras[[id]]
        if (is.null(co)) return(json(404, list(detail = "No encontramos esa compra.")))
        if (!anular && metodo == "GET") return(json(200, co))
        if (anular && metodo == "POST") {
          d <- leer(req)
          motivo <- trimws(d$motivo %||% "")
          if (nchar(motivo) < 3) return(json(422, list(detail = "Revisa los datos e intenta de nuevo.")))
          if (identical(co$estado, "anulada")) {
            return(json(409, list(detail = "Esa compra ya estaba anulada.")))
          }
          Sys.sleep(0.3)  # para que un doble toque llegue antes de terminar
          for (l in co$lineas) {
            ins <- estado$insumos[[l$insumo_id]]
            if (is.null(ins)) next
            q <- as.numeric(l$cantidad)
            queda <- ins$existencia - q
            if (queda > 0) ins$costo <- max(0, (ins$existencia * ins$costo - as.numeric(l$costo_total)) / queda)
            ins$existencia <- queda
            estado$insumos[[ins$id]] <- ins
          }
          co$estado <- "anulada"
          co$anulada_en <- format(Sys.time(), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
          co$motivo_anulacion <- motivo
          estado$compras[[id]] <- co
          estado$anulaciones_compra <- estado$anulaciones_compra + 1L
          return(json(200, co))
        }
      }
      if (ruta == "/v1/unidades" && metodo == "GET") return(json(200, unidades_falsas))
      if (ruta == "/v1/insumos" && metodo == "GET") {
        salidas <- lapply(insumos_vivos_lista(), insumo_out)
        valor <- sum(vapply(salidas, function(i) as.numeric(i$valor), 0))
        reponer <- sum(vapply(salidas, function(i) i$estado != "ok", NA))
        return(json(200, list(total = length(salidas), valor_inventario = sprintf("%.2f", valor),
                              por_reponer = reponer, insumos = salidas)))
      }
      if (ruta == "/v1/insumos" && metodo == "POST") {
        d <- leer(req)
        nombre <- trimws(d$nombre %||% "")
        if (nchar(nombre) < 2 || is.null(nombre_unidad(d$unidad_codigo %||% ""))) {
          return(json(422, list(detail = "Revisa los datos e intenta de nuevo.")))
        }
        if (any(vapply(insumos_vivos_lista(), function(i) identical(tolower(i$nombre), tolower(nombre)), NA))) {
          return(json(409, list(detail = "Ya tienes un insumo con ese nombre.")))
        }
        Sys.sleep(0.4)  # para que un doble toque llegue antes de terminar
        estado$insumos_creados <- estado$insumos_creados + 1L
        i <- insumo_nuevo(paste0("in-n", estado$insumos_creados + 10L), nombre, d$unidad_codigo,
                          as.numeric(d$existencia_inicial %||% 0),
                          as.numeric(d$costo_total_inicial %||% 0),
                          as.numeric(d$stock_minimo %||% 0))
        return(json(201, insumo_out(i)))
      }
      if (startsWith(ruta, "/v1/insumos/")) {
        id <- id_insumo_de_ruta(ruta)
        i <- estado$insumos[[id]]
        if (is.null(i)) return(json(404, list(detail = "No encontramos ese insumo.")))
        if (endsWith(ruta, "/movimientos") && metodo == "GET") {
          return(json(200, list(movimientos = estado$movs[[id]])))
        }
        if (endsWith(ruta, "/movimientos") && metodo == "POST") {
          d <- leer(req)
          q <- suppressWarnings(as.numeric(d$cantidad))
          if (is.na(q) || !(d$tipo %in% c("entrada", "merma", "ajuste")) ||
              (d$tipo != "ajuste" && q <= 0) || (d$tipo == "entrada" && is.null(d$costo_total))) {
            return(json(422, list(detail = "Revisa los datos e intenta de nuevo.")))
          }
          Sys.sleep(0.4)  # para que un doble toque llegue antes de terminar
          clave <- req$HTTP_IDEMPOTENCY_KEY %||% NULL
          if (!is.null(clave) && !is.null(estado$claves_mov[[clave]])) {
            return(json(201, estado$claves_mov[[clave]]))
          }
          estado$movs_creados <- estado$movs_creados + 1L
          e <- i$existencia
          costo <- i$costo
          if (d$tipo == "entrada") {
            total <- as.numeric(d$costo_total)
            costo_mov <- total / q
            i$costo <- if (e <= 0) costo_mov else (e * i$costo + total) / (e + q)
            delta <- q
          } else if (d$tipo == "merma") {
            costo_mov <- costo
            delta <- -q
          } else {
            costo_mov <- costo
            delta <- q - e
          }
          i$existencia <- e + delta
          estado$insumos[[id]] <- i
          mov <- list(id = paste0("m-", estado$movs_creados + 100L), tipo = d$tipo,
                      cantidad = cant(delta), costo_unitario = sprintf("%.2f", costo_mov),
                      fecha_hora = format(Sys.time(), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC"),
                      nota = d$nota)
          estado$movs[[id]] <- c(list(c(mov, list(insumo = NULL))), estado$movs[[id]])
          respuesta <- c(mov, list(insumo = insumo_out(i)))
          if (!is.null(clave)) estado$claves_mov[[clave]] <- respuesta
          if (identical(d$nota, "Se pierde") && estado$movs_creados == 1L) {
            return(json(503, list(detail = "El servicio no está listo. Intenta más tarde.")))
          }
          return(json(201, respuesta))
        }
        if (metodo == "GET") return(json(200, insumo_out(i)))
        if (metodo == "DELETE") {
          estado$insumos[[id]] <- NULL
          return(json(200, list()))
        }
        if (metodo == "PATCH") {
          d <- leer(req)
          if (identical(i$nombre, "Conflicto") || !identical(as.integer(d$version), i$version)) {
            return(json(409, list(detail = "Alguien más cambió esto. Ábrelo de nuevo e inténtalo otra vez.")))
          }
          if (!is.null(d$nombre)) i$nombre <- trimws(d$nombre)
          if (!is.null(d$stock_minimo)) i$minimo <- as.numeric(d$stock_minimo)
          i$version <- i$version + 1L
          estado$insumos[[id]] <- i
          return(json(200, insumo_out(i)))
        }
      }
      if (ruta == "/v1/ventas" && metodo == "POST") {
        d <- leer(req)
        lineas <- d$lineas
        if (length(lineas) == 0 || !(d$medio_pago %in% c("efectivo", "tarjeta", "transferencia"))) {
          return(json(422, list(detail = "Revisa los datos e intenta de nuevo.")))
        }
        Sys.sleep(0.4)  # para que un doble toque llegue antes de terminar
        clave <- req$HTTP_IDEMPOTENCY_KEY %||% NULL
        if (!is.null(clave) && !is.null(estado$claves_venta[[clave]])) {
          return(json(201, estado$claves_venta[[clave]]))
        }
        if (identical(estado$regla_venta, "bloquear")) {
          for (l in lineas) {
            it <- estado$items[[l$item_id]]
            if (is.null(it)) next
            if (is.null(it$stock)) {
              return(json(409, list(detail = paste0("No te alcanza para vender: ", it$nombre,
                                                    " (aún no tiene inventario: cómpralo o impórtalo primero)."))))
            }
            if (l$cantidad > it$stock) {
              return(json(409, list(detail = paste0("No te alcanza para vender: ", it$nombre,
                                                    if (it$stock == 0) " (agotado)." else paste0(" (solo quedan ", it$stock, ").")))))
            }
          }
        }
        # Con cualquier regla, lo vendido sale del inventario (con "avisar" puede quedar en negativo).
        for (l in lineas) {
          it <- estado$items[[l$item_id]]
          if (!is.null(it) && !is.null(it$stock)) {
            it$stock <- it$stock - l$cantidad
            estado$items[[l$item_id]] <- it
          }
        }
        armadas <- list()
        total <- 0
        for (l in lineas) {
          it <- estado$items[[l$item_id]]
          if (is.null(it)) {
            return(json(422, list(detail = "Alguno de los productos ya no está disponible. Revisa tu carrito.")))
          }
          precio <- it$precio_venta
          nombre <- it$nombre
          if (isTRUE(it$tiene_variantes)) {
            v <- Filter(function(x) identical(x$id, l$item_variante_id), it$variantes)
            if (length(v) == 0) {
              return(json(422, list(detail = "Elige la talla o el color de cada producto.")))
            }
            precio <- v[[1]]$precio_venta
            nombre <- paste(it$nombre, "·", v[[1]]$nombre)
          }
          subtotal <- as.numeric(precio) * l$cantidad
          total <- total + subtotal
          armadas[[length(armadas) + 1L]] <- list(
            item_id = it$id, item_variante_id = l$item_variante_id, nombre = nombre,
            cantidad = l$cantidad, precio_unitario = precio, total = sprintf("%.2f", subtotal))
        }
        estado$ventas_creadas <- estado$ventas_creadas + 1L
        venta <- list(
          id = paste0("v-", estado$ventas_creadas), numero = length(estado$ventas) + 1L,
          fecha_hora = format(Sys.time(), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC"),
          estado = "pagada", total = sprintf("%.2f", total), moneda_codigo = "GTQ",
          medio_pago = d$medio_pago, lineas = armadas, anulada_en = NULL, motivo_anulacion = NULL,
          creada_n = estado$ventas_creadas)
        # Los insumos de las recetas se descuentan; si alguno se acaba, se avisa (la venta se cobra)
        sin_existencia <- character()
        for (l in lineas) {
          for (r in estado$recetas[[l$item_id]] %||% list()) {
            ins <- estado$insumos[[r$insumo_id]]
            if (is.null(ins)) next
            ins$existencia <- ins$existencia - as.numeric(r$cantidad) * l$cantidad
            estado$insumos[[ins$id]] <- ins
            if (ins$existencia <= 0) sin_existencia <- c(sin_existencia, ins$nombre)
          }
        }
        quedan_poco <- character()
        for (l in lineas) {
          it <- estado$items[[l$item_id]]
          if (!is.null(it$stock) && it$stock <= estado$minimo) quedan_poco <- c(quedan_poco, it$nombre)
        }
        venta_resp <- c(venta, list(insumos_en_falta = as.list(sort(unique(sin_existencia))),
                                    por_agotarse = as.list(sort(unique(quedan_poco)))))
        estado$ventas[[venta$id]] <- venta
        if (!is.null(clave)) estado$claves_venta[[clave]] <- venta_resp
        se_pierde <- any(vapply(armadas, function(a) identical(a$nombre, "Se pierde"), NA))
        if (se_pierde && estado$ventas_creadas == 1L) {
          return(json(503, list(detail = "El servicio no está listo. Intenta más tarde.")))
        }
        return(json(201, venta_resp))
      }
      if (ruta == "/v1/ventas" && metodo == "GET") {
        todas <- unname(estado$ventas)
        todas <- todas[order(-vapply(todas, function(v) v$numero, 1))]
        vigentes <- Filter(function(v) identical(v$estado, "pagada"), todas)
        suma <- function(medio) {
          sum(vapply(Filter(function(v) identical(v$medio_pago, medio), vigentes),
                     function(v) as.numeric(v$total), 0))
        }
        resumen <- list(
          cantidad = length(vigentes),
          total = sprintf("%.2f", sum(vapply(vigentes, function(v) as.numeric(v$total), 0))),
          por_medio = list(efectivo = sprintf("%.2f", suma("efectivo")),
                           tarjeta = sprintf("%.2f", suma("tarjeta")),
                           transferencia = sprintf("%.2f", suma("transferencia"))))
        return(json(200, list(fecha = format(Sys.Date()), resumen = resumen, ventas = todas)))
      }
      if (startsWith(ruta, "/v1/ventas/")) {
        resto <- sub("^/v1/ventas/", "", ruta)
        anular <- endsWith(resto, "/anular")
        id <- sub("/anular$", "", resto)
        v <- estado$ventas[[id]]
        if (is.null(v)) return(json(404, list(detail = "No encontramos esa venta.")))
        if (!anular && metodo == "GET") return(json(200, v))
        if (anular && metodo == "POST") {
          d <- leer(req)
          motivo <- trimws(d$motivo %||% "")
          if (nchar(motivo) < 3) return(json(422, list(detail = "Revisa los datos e intenta de nuevo.")))
          if (identical(motivo, "sin permiso")) {
            return(json(403, list(detail = "No tienes permiso para hacer esto.")))
          }
          if (identical(v$estado, "anulada")) {
            return(json(409, list(detail = "Esa venta ya estaba anulada.")))
          }
          Sys.sleep(0.3)  # para que un doble toque llegue antes de terminar
          v$estado <- "anulada"
          v$anulada_en <- format(Sys.time(), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
          v$motivo_anulacion <- motivo
          estado$ventas[[id]] <- v
          estado$anulaciones <- estado$anulaciones + 1L
          return(json(200, v))
        }
      }
      if (startsWith(ruta, "/v1/items/") && endsWith(ruta, "/mercaderia")) {
        id <- sub("/mercaderia$", "", id_de_ruta(ruta))
        it <- estado$items[[id]]
        if (is.null(it)) return(json(404, list(detail = "No encontramos eso.")))
        ligado <- NULL
        for (ins in estado$insumos) if (identical(ins$item_id, id)) ligado <- ins
        if (metodo == "PUT") {
          d <- leer(req)
          if (isTRUE(d$activa) && is.null(ligado)) {
            if (length(estado$recetas[[id]]) > 0) {
              return(json(409, list(detail = "Este producto ya tiene una receta. Quítala primero para comprarlo hecho.")))
            }
            estado$insumos_creados <- estado$insumos_creados + 1L
            ligado <- insumo_nuevo(paste0("in-m", estado$insumos_creados + 10L), it$nombre, "UN")
            ligado$item_id <- id
            estado$insumos[[ligado$id]] <- ligado
            estado$recetas[[id]] <- list(list(insumo_id = ligado$id, cantidad = "1", unidad_codigo = "UN"))
          } else if (!isTRUE(d$activa) && !is.null(ligado)) {
            estado$insumos[[ligado$id]] <- NULL
            estado$recetas[[id]] <- NULL
            ligado <- NULL
          }
        }
        return(json(200, list(activa = !is.null(ligado),
                              insumo = if (!is.null(ligado)) insumo_out(ligado))))
      }
      if (startsWith(ruta, "/v1/items/") && endsWith(ruta, "/receta")) {
        id <- sub("/receta$", "", id_de_ruta(ruta))
        it <- estado$items[[id]]
        if (is.null(it)) return(json(404, list(detail = "No encontramos eso.")))
        if (metodo == "GET") return(json(200, receta_out(it)))
        if (metodo == "PUT") {
          d <- leer(req)
          ids <- vapply(d$lineas, function(l) l$insumo_id, "")
          if (any(duplicated(ids))) {
            return(json(422, list(detail = "Un insumo aparece dos veces en la receta.")))
          }
          for (l in d$lineas) {
            ins <- estado$insumos[[l$insumo_id]]
            if (is.null(ins)) return(json(422, list(detail = "Uno de los insumos no existe.")))
            tipo_de <- function(codigo) for (u in unidades_falsas) if (identical(u$codigo, codigo)) return(u$tipo)
            if (!is.null(l$unidad_codigo) && !identical(tipo_de(l$unidad_codigo), tipo_de(ins$unidad))) {
              return(json(422, list(detail = "Esa unidad no sirve aquí. Usa una del mismo tipo (peso con peso, líquido con líquido).")))
            }
          }
          estado$recetas[[id]] <- lapply(d$lineas, function(l) {
            ins <- estado$insumos[[l$insumo_id]]
            list(insumo_id = l$insumo_id, cantidad = l$cantidad,
                 unidad_codigo = l$unidad_codigo %||% ins$unidad)
          })
          return(json(200, receta_out(it)))
        }
      }
      if (startsWith(ruta, "/v1/items/")) {
        id <- id_de_ruta(ruta)
        it <- estado$items[[id]]
        if (is.null(it)) return(json(404, list(detail = "No encontramos eso.")))
        if (metodo == "GET") return(json(200, con_precio(it)))
        if (metodo == "DELETE") {
          estado$items[[id]] <- NULL
          return(json(200, list()))
        }
        if (metodo == "PATCH") {
          d <- leer(req)
          if (identical(it$nombre, "Conflicto") || !identical(as.integer(d$version), it$version)) {
            return(json(409, list(detail = "Alguien más cambió esto. Ábrelo de nuevo e inténtalo otra vez.")))
          }
          if (!is.null(d$nombre)) it$nombre <- trimws(d$nombre)
          if (!is.null(d$precio_venta)) it$precio_venta <- sprintf("%.2f", as.numeric(d$precio_venta))
          if ("margen_objetivo" %in% names(d)) it["margen_propio_valor"] <- list(d$margen_objetivo)
          if ("categoria_id" %in% names(d)) {
            it["categoria_id"] <- list(d$categoria_id)
            it["categoria_nombre"] <- list(nombre_categoria(d$categoria_id))
          }
          it$version <- it$version + 1L
          guardar_item(it)
          return(json(200, con_precio(it)))
        }
      }
      json(404, list(detail = "No encontramos eso."))
    })
    httpuv::runServer("127.0.0.1", puerto, app)
  }, args = list(puerto = puerto), supervise = TRUE)

  url <- sprintf("http://127.0.0.1:%d", puerto)
  withr::defer(proceso$kill(), envir = env)

  # Esperar a que responda (máx. 10 s)
  for (i in 1:100) {
    listo <- tryCatch({
      httr2::req_perform(httr2::request(paste0(url, "/v1/salud")))
      TRUE
    }, error = function(e) FALSE)
    if (listo) break
    Sys.sleep(0.1)
  }
  if (!listo) stop("La API falsa no arrancó: ", paste(proceso$read_all_error(), collapse = " "))
  url
}

negocios_creados <- function(url) {
  httr2::request(paste0(url, "/_creados")) |> httr2::req_perform() |>
    httr2::resp_body_json() |> (\(x) x$creados)()
}

items_creados <- function(url) {
  httr2::request(paste0(url, "/_creados")) |> httr2::req_perform() |>
    httr2::resp_body_json() |> (\(x) x$items)()
}

ventas_creadas <- function(url) {
  httr2::request(paste0(url, "/_creados")) |> httr2::req_perform() |>
    httr2::resp_body_json() |> (\(x) x$ventas)()
}

gastos_creados <- function(url) {
  httr2::request(paste0(url, "/_creados")) |> httr2::req_perform() |>
    httr2::resp_body_json() |> (\(x) x$gastos)()
}

contadores_api <- function(url) {
  httr2::request(paste0(url, "/_creados")) |> httr2::req_perform() |> httr2::resp_body_json()
}

gastos_vivos <- function(url) {
  httr2::request(paste0(url, "/_creados")) |> httr2::req_perform() |>
    httr2::resp_body_json() |> (\(x) x$gastos_vivos)()
}

anulaciones <- function(url) {
  httr2::request(paste0(url, "/_creados")) |> httr2::req_perform() |>
    httr2::resp_body_json() |> (\(x) x$anulaciones)()
}

items_vivos <- function(url) {
  httr2::request(paste0(url, "/_creados")) |> httr2::req_perform() |>
    httr2::resp_body_json() |> (\(x) x$items_vivos)()
}

sesiones_cerradas <- function(url) {
  httr2::request(paste0(url, "/_creados")) |> httr2::req_perform() |>
    httr2::resp_body_json() |> (\(x) x$salidas)()
}

abrir_app <- function(url, nombre, env = parent.frame()) {
  withr::local_envvar(API_BASE_URL = url, NOT_CRAN = "true", .local_envir = env)
  app <- shinytest2::AppDriver$new(
    testthat::test_path("..", ".."),
    name = nombre, width = 390, height = 844, load_timeout = 30000
  )
  withr::defer(app$stop(), envir = env)
  app
}

visible <- function(app, selector) {
  app$get_js(sprintf(
    "(function(){var e=document.querySelector(\"%s\"); return !!e && e.getClientRects().length > 0 && getComputedStyle(e).visibility !== 'hidden';})()",
    selector
  ))
}

# Repite una comprobación hasta que se cumpla (los pasos del asistente tardan un instante).
esperar_visible <- function(app, selector, intentos = 50) {
  for (i in seq_len(intentos)) {
    if (isTRUE(visible(app, selector))) return(invisible(TRUE))
    Sys.sleep(0.2)
  }
  FALSE
}

# Recorre registro + onboarding de un restaurante hasta llegar a la app.
crear_cuenta_y_negocio <- function(app, tipo = "restaurante", nombre_negocio = "Comedor Doña Mari",
                                   correo = "nuevo@prueba.com") {
  app$click(selector = "#bienvenida-crear")
  app$set_inputs("registro-nombre" = "Mari", "registro-correo" = correo,
                 "registro-clave" = "una-clave-larga-1")
  app$click(selector = "#registro-crear")
  esperar_visible(app, sprintf("[data-elige-valor='%s']", tipo))
  app$click(selector = sprintf("[data-elige-valor='%s']", tipo))
  esperar_visible(app, "#onboarding-seguir_nombre")
  app$set_inputs("onboarding-nombre" = nombre_negocio)
  app$click(selector = "#onboarding-seguir_nombre")
  esperar_visible(app, "[data-elige-valor='no_se']")
  app$click(selector = "[data-elige-valor='no_se']")
  esperar_visible(app, "#onboarding-ir_app")
  app$click(selector = "#onboarding-ir_app")
  esperar_visible(app, ".nav-inferior")
  invisible(app)
}

# --- Ayudas comunes de las pruebas con navegador ---------------------------------------------

entrar_como_mari <- function(app) {
  app$click(selector = "#bienvenida-entrar")
  app$set_inputs("login-correo" = "mari@prueba.com", "login-clave" = "clave-correcta-1")
  app$click(selector = "#login-entrar")
  esperar_visible(app, ".nav-inferior")
}

# Repite una condición de JavaScript hasta que se cumpla (la lista llega un instante después).
esperar_js <- function(app, expresion, intentos = 50) {
  for (i in seq_len(intentos)) {
    if (isTRUE(app$get_js(expresion))) return(invisible(TRUE))
    Sys.sleep(0.2)
  }
  FALSE
}

esperar_texto <- function(app, selector, patron, intentos = 50) {
  for (i in seq_len(intentos)) {
    texto <- app$get_js(sprintf("(document.querySelector('%s') || {}).textContent || ''", selector))
    if (grepl(patron, texto)) return(invisible(TRUE))
    Sys.sleep(0.2)
  }
  FALSE
}

llenar_item <- function(app, nombre, precio, categoria = NULL) {
  app$set_inputs("productos-nombre" = nombre, "productos-precio" = precio)
  if (!is.null(categoria)) app$set_inputs("productos-categoria" = categoria)
}

insumos_vivos <- function(url) {
  httr2::request(paste0(url, "/_creados")) |> httr2::req_perform() |>
    httr2::resp_body_json() |> (\(x) x$insumos_vivos)()
}

insumos_creados <- function(url) {
  httr2::request(paste0(url, "/_creados")) |> httr2::req_perform() |>
    httr2::resp_body_json() |> (\(x) x$insumos)()
}

movimientos_creados <- function(url) {
  httr2::request(paste0(url, "/_creados")) |> httr2::req_perform() |>
    httr2::resp_body_json() |> (\(x) x$movimientos)()
}

compras_creadas <- function(url) {
  httr2::request(paste0(url, "/_creados")) |> httr2::req_perform() |>
    httr2::resp_body_json() |> (\(x) x$compras)()
}

proveedores_vivos <- function(url) {
  httr2::request(paste0(url, "/_creados")) |> httr2::req_perform() |>
    httr2::resp_body_json() |> (\(x) x$proveedores)()
}

anulaciones_compra <- function(url) {
  httr2::request(paste0(url, "/_creados")) |> httr2::req_perform() |>
    httr2::resp_body_json() |> (\(x) x$anulaciones_compra)()
}
