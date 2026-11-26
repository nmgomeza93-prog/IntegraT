# Revisión para el contador: contabilidad y fiscal de IntegraT (Guatemala)

> **Dirigido a:** contador público y auditor (CPA) que validará el diseño contable y fiscal antes del piloto.
> **Preparado:** 2026-11-23, Fase 0.
>
> **Cómo usar este documento.** Cada sección explica una decisión de diseño, por qué se tomó y su fuente. Cada punto a validar tiene un código **C-xx** y una casilla.
> El contador puede responder "✅ de acuerdo", "✏️ cambiar a…" o "❓ requiere análisis".
>
> **Sobre las fuentes (importante).** Las referencias legales se citan del marco tributario guatemalteco tal como lo conocemos a la fecha de redacción.
> Al prepararlo **no pudimos consultar el portal de la SAT** (rechazó el acceso automatizado), así que **las tasas, los límites, los artículos y las reformas recientes deben confirmarse**.
> Todo lo marcado **[verificar]** tiene incertidumbre conocida. El objetivo es que el contador **corrija**, no que confíe.

---

## 1. Contexto: qué hace la app y qué ve el usuario

- IntegraT es para emprendedores **sin formación contable**. El usuario registra **hechos** (vendí, compré, gasté, cerré caja) y la app genera **automáticamente** asientos en **partida doble**.
- El usuario **nunca ve asientos ni cuentas**; ve "Lo que vendiste", "Lo que gastaste", "Lo que te queda".
- El contador del negocio recibe **exportaciones**: libro diario, mayor, balance de comprobación, estados financieros, libro de compras y ventas.
- Tipos de negocio en el MVP: **ventas en línea** (comercio) y **restaurantes**.
- La app **no emite FEL** en el MVP (está preparada; ver `PLAN_FEL.md`), pero **registra** las FEL de compra (número, serie, autorización).

---

## 2. Resumen de puntos a validar

| Código | Tema | Sección |
|---|---|---|
| C-01 | Libros por negocio (establecimiento) y libros legales por NIT (titular) | §3 |
| C-02 | Régimen fiscal definido en el titular (NIT), no en el negocio | §3 |
| C-03 | Regímenes soportados en el MVP y sus parámetros | §4 |
| C-04 | Tratamiento del pequeño contribuyente para el ISR | §4 |
| C-05 | Plan de cuentas plantilla | §5 |
| C-06 | Tratamiento del IVA (débito, crédito, requisitos, compras a pequeño contribuyente) | §6 |
| C-07 | Gastos sin factura: no deducibles y sin crédito fiscal | §6 |
| C-08 | Método de costeo: costo promedio ponderado | §7 |
| C-09 | Costo de platillos por receta y consumo teórico frente a conteo físico | §7 |
| C-10 | Mermas: tratamiento y documentación | §7 |
| C-11 | **Costo de la lectura con IA: capitalizar al inventario o gasto** | §8 |
| C-12 | Saldo IA prepagado: anticipo y momento del IVA | §8 |
| C-13 | Diferencias de caja (faltantes y sobrantes) | §9 |
| C-14 | Retiros y aportes del dueño | §9 |
| C-15 | Propinas en restaurantes | §9 |
| C-16 | Comisiones de pasarelas de pago | §9 |
| C-17 | Retención de documentos y fotos de facturas | §10 |
| C-18 | Libros obligatorios, habilitación y formato de exportación | §11 |
| C-19 | Consolidación por titular: IVA, límites y traslados entre negocios | §12 |
| C-20 | Asientos tipo de cada evento | §13 |

---

## 3. Estructura: titular (NIT) y negocios

**Decisión del dueño del producto:**
- Cada **negocio** está aislado: tiene **sus propios libros, catálogo, inventario y caja**.
- Una capa ligera de **titular** agrupa los negocios con el **mismo NIT**, solo para los **reportes fiscales consolidados** ante la SAT.

**Diseño:**
- `titular` = el contribuyente (persona individual o jurídica) con su **NIT**, su **régimen de IVA y de ISR** y su afiliación.
- `negocio` = una unidad operativa (por ejemplo, "Comedor Zona 1" y "Comedor Mixco"). Para la FEL se asocia a un **establecimiento** registrado en el RTU (código de establecimiento).
- Los asientos se registran **por negocio**. Los **libros legales del contribuyente** se generan **consolidados por titular** (suma de los negocios), con la posibilidad de ver el detalle por establecimiento.

**Razonamiento:**
- Las obligaciones tributarias (IVA, ISR) y los libros del comerciante son **del contribuyente (NIT)**: Código de Comercio, Decreto 2-70, arts. 368 y siguientes; Código Tributario, Decreto 6-91.
- La separación por negocio es **contabilidad de gestión por establecimiento**, legítima y útil, pero no reemplaza los libros del contribuyente.

- [ ] **C-01** ¿Es correcto llevar asientos por negocio y generar los libros legales (Diario, Mayor, Inventarios, Estados Financieros) **consolidados por NIT**? ¿O los libros deben llevarse directamente a nivel del titular?
- [ ] **C-02** ¿Confirma que el régimen de IVA e ISR es **único por NIT**, de modo que todos los negocios de un titular comparten régimen?

---

## 4. Regímenes soportados en el MVP

| Régimen | Parámetros en la app | Fuente | Estado |
|---|---|---|---|
| **IVA – Régimen General** | Tasa **12 %**, incluida en el precio. Débito sobre ventas y crédito sobre compras con documento válido. Liquidación mensual | Ley del IVA, Decreto 27-92, art. 10 (tarifa) y arts. 14–19 (débito y crédito fiscal) | [verificar artículos] |
| **IVA – Pequeño Contribuyente** | **5 %** sobre los ingresos brutos totales del mes; **límite de Q150,000 de ingresos anuales**; sus facturas **no generan crédito fiscal** para el comprador; el IVA que paga en sus compras **forma parte del costo o gasto** | Ley del IVA, Título III, "Régimen de Pequeño Contribuyente" (arts. 45 y ss., adicionados por reforma de 2012, Decreto 4-2012) | **[verificar tasa, límite, artículos y reformas posteriores]** |
| **ISR – Régimen sobre las Utilidades de Actividades Lucrativas** | **25 %** sobre la renta imponible; pagos a cuenta trimestrales | Ley de Actualización Tributaria (LAT), Decreto 10-2012, Libro I, arts. 36 y 38 | [verificar] |
| **ISR – Régimen Opcional Simplificado sobre Ingresos** | **5 %** sobre ingresos hasta Q30,000 mensuales y **7 %** sobre el excedente; liquidación mensual; posibles retenciones por agentes | LAT, Decreto 10-2012, art. 44 y ss. | [verificar] |
| **ISO – Impuesto de Solidaridad** | No está en el MVP; se mostrará un aviso si el titular está en el régimen sobre utilidades | Decreto 73-2008 | Fuera del MVP |
| Retenciones de IVA (agentes de retención) | No está en el MVP; se registrará la constancia de retención recibida | Ley de Retenciones del IVA, Decreto 20-2006 | Fuera del MVP |

**Cómo los usa la app:**
- Al registrarse, el usuario responde "¿Das factura?":
  - *Pequeño contribuyente* → `GT_PEQ_CONTRIBUYENTE`.
  - *Régimen general* → `GT_GENERAL`, y se le pregunta el régimen de ISR.
  - *No sé / Todavía no* → modo informal, donde la app registra igual la contabilidad, pero **avisa** que debe inscribirse y lo orienta.
- El **límite del pequeño contribuyente** se vigila **consolidado por NIT**. La app avisa al 70 %, 90 % y 100 % del límite anual.

- [ ] **C-03** Confirmar tasas, límites, periodicidad y artículos vigentes de cada régimen. ¿Falta algún régimen relevante para comedores o tiendas en línea pequeñas?
- [ ] **C-04** **Pequeño contribuyente e ISR**: ¿qué obligación de ISR tiene un pequeño contribuyente en la práctica actual (por ejemplo, si la cuota del 5 % es su única obligación periódica, o si debe inscribirse en un régimen de ISR)? ¿Cómo debe reflejarse en los asientos?
- [ ] ¿El modo "informal" (sin inscripción) es aceptable como etapa transitoria, o la app debe exigir el NIT y el régimen desde el inicio?

---

## 5. Plan de cuentas plantilla (Guatemala, comercio y restaurante)

**Diseño:**
- Cada negocio recibe una copia de la plantilla, que el contador puede ajustar.
- El motor contable **no usa códigos fijos**: usa **roles** (por ejemplo, `CAJA`) que apuntan a una cuenta del plan. Así el contador puede renombrar o recodificar sin romper el sistema.
- Estructura de 4 niveles: grupo, subgrupo, cuenta y subcuenta. Solo las cuentas de detalle aceptan movimientos.
- Base de presentación: NIIF para las PYMES, cuya adopción en Guatemala la promueve el Colegio de Contadores Públicos y Auditores [verificar el marco aplicable para pequeños comerciantes individuales].

| Código | Cuenta | Rol en el motor | Nombre que ve el usuario |
|---|---|---|---|
| **1** | **ACTIVO** | | |
| 1101 | Caja general | `CAJA` | Efectivo |
| 1102 | Caja chica | `CAJA_CHICA` | — |
| 1103 | Bancos | `BANCO` | Banco |
| 1104 | Pasarelas de pago por liquidar | `POR_COBRAR_PASARELA` | Pagos con tarjeta por recibir |
| 1105 | Clientes | `POR_COBRAR_CLIENTES` | Te deben |
| 1106 | Deudores diversos | `DEUDORES_DIVERSOS` | — |
| 1107 | Inventario de mercadería | `INVENTARIO_MERCADERIA` | Lo que tienes para vender |
| 1108 | Inventario de insumos (cocina) | `INVENTARIO_INSUMOS` | Ingredientes |
| 1109 | Inventario de empaques y desechables | `INVENTARIO_EMPAQUES` | Empaques |
| 1110 | IVA por cobrar (crédito fiscal) | `IVA_CREDITO` | IVA de tus compras |
| 1111 | Retenciones de IVA o ISR a favor | `RETENCIONES_A_FAVOR` | — |
| 1112 | Pagos a cuenta de ISR | `ISR_PAGOS_CUENTA` | — |
| 1113 | **Saldo de servicios prepagados (Saldo IA)** | `SALDO_IA_PREPAGADO` | Tu saldo de IA |
| 1201 | Mobiliario y equipo | `ACTIVO_FIJO_MOBILIARIO` | — (fase posterior) |
| 1202 | Equipo de cocina | `ACTIVO_FIJO_COCINA` | — (fase posterior) |
| 1209 | Depreciación acumulada (cr) | `DEPRECIACION_ACUMULADA` | — (fase posterior) |
| **2** | **PASIVO** | | |
| 2101 | Proveedores | `PROVEEDORES` | Le debes a proveedores |
| 2102 | Acreedores diversos | `ACREEDORES` | Debes (servicios) |
| 2103 | IVA por pagar (débito fiscal) | `IVA_DEBITO` | IVA de tus ventas |
| 2104 | Impuestos por pagar | `IMPUESTO_POR_PAGAR` | Impuestos por pagar |
| 2105 | Propinas por distribuir | `PROPINAS_POR_PAGAR` | Propinas del personal |
| 2106 | Anticipos de clientes | `ANTICIPOS_CLIENTES` | Te pagaron por adelantado |
| **3** | **PATRIMONIO** | | |
| 3101 | Capital | `CAPITAL` | Lo que pusiste en el negocio |
| 3102 | Retiros del propietario | `RETIROS_PROPIETARIO` | Lo que sacaste para ti |
| 3201 | Resultados acumulados | `RESULTADOS_ACUMULADOS` | — |
| 3202 | Resultado del ejercicio | `RESULTADO_EJERCICIO` | Ganancia del año |
| **4** | **INGRESOS** | | |
| 4101 | Ventas de mercadería | `VENTAS` | Lo que vendiste |
| 4102 | Ventas de alimentos y bebidas | `VENTAS` (restaurante) | Lo que vendiste |
| 4103 | Ingresos por envíos cobrados | `VENTAS_ENVIOS` | Envíos cobrados |
| 4109 | Descuentos y devoluciones sobre ventas (dr) | `DESCUENTOS_VENTAS` | Descuentos que diste |
| 4201 | Otros ingresos (incluye sobrantes de caja) | `OTROS_INGRESOS` | — |
| **5** | **COSTOS** | | |
| 5101 | Costo de ventas | `COSTO_VENTAS` | Lo que te costó lo que vendiste |
| 5102 | Mermas y desperdicios | `MERMA` | Lo que se perdió o se dañó |
| **6** | **GASTOS** | | |
| 6101 | Alquileres | `GASTO_RENTA` | Renta |
| 6102 | Energía eléctrica, agua y gas | `GASTO_SERVICIOS_BASICOS` | Luz, agua y gas |
| 6103 | Teléfono e internet | `GASTO_COMUNICACIONES` | Teléfono e internet |
| 6104 | Sueldos y salarios | `GASTO_SUELDOS` | Sueldos |
| 6105 | Publicidad | `GASTO_PUBLICIDAD` | Publicidad |
| 6106 | Envíos y fletes sobre ventas | `GASTO_ENVIOS` | Envíos |
| 6107 | Comisiones bancarias y de pasarelas | `GASTO_COMISIONES` | Comisiones |
| 6108 | Software y servicios digitales (incluye IntegraT e IA si la política es "gasto") | `GASTO_SERVICIOS_IA`, `GASTO_SOFTWARE` | Servicios digitales |
| 6109 | Mantenimiento y reparaciones | `GASTO_MANTENIMIENTO` | Reparaciones |
| 6110 | Transporte y combustible | `GASTO_TRANSPORTE` | Transporte |
| 6190 | Gastos varios | `GASTO_VARIOS` | Otros gastos |
| 6191 | Faltantes de caja | `DIFERENCIA_CAJA` | Diferencias de caja |
| 6192 | **Gastos no deducibles** | `GASTO_NO_DEDUCIBLE` | — |
| 6201 | Impuesto sobre ingresos de pequeño contribuyente | `IMPUESTO_PEQ_CONTRIBUYENTE` | Impuesto sobre ventas |
| 6202 | ISR (simplificado o del periodo) | `GASTO_ISR` | Impuesto sobre la renta |

- [ ] **C-05** Revisar la estructura y los nombres. ¿Faltan cuentas habituales para comedores o tiendas en línea pequeñas? ¿Conviene separar los gastos no deducibles en una cuenta aparte, como se propone, o marcarlos con un atributo?

---

## 6. IVA: tratamiento en la app

| Situación | Tratamiento propuesto | Fuente |
|---|---|---|
| Venta (régimen general), precio con IVA incluido | `base = total / 1.12`; `IVA = total − base` → débito fiscal | Ley del IVA, arts. 10 y 14 [verificar] |
| Compra con FEL a nombre del NIT del titular, de un proveedor en régimen general, vinculada al giro | Crédito fiscal = IVA del documento | Ley del IVA, arts. 15–18 (requisitos del crédito fiscal) [verificar] |
| Compra a un **pequeño contribuyente** | **Sin crédito fiscal**: el total va al costo o gasto | Régimen de Pequeño Contribuyente [verificar] |
| Compra con factura a nombre de **"CF"** (sin NIT) | **Sin crédito fiscal**; la app advierte: "Pide tu factura con tu NIT para recuperar el IVA" | [verificar] |
| Negocio en **pequeño contribuyente** | No separa IVA en compras (todo es costo o gasto) ni en ventas; provisiona el 5 % sobre los ingresos brutos del mes | [verificar] |
| Gasto **sin factura** (mercado, gas a granel) | Se registra (es real), **sin crédito fiscal** y marcado **no deducible** para el ISR (régimen sobre utilidades) | LAT, requisitos de deducibilidad (art. 21 y ss.) [verificar] |
| Liquidación mensual (general) | Débito − crédito; remanente a favor al mes siguiente | Ley del IVA [verificar] |
| Libro de compras y ventas | Se genera **por NIT** (consolidado de negocios) desde los registros | Ley del IVA, art. 37 y su reglamento [verificar] |

- [ ] **C-06** Validar la tabla. En particular: requisitos actuales del crédito fiscal con FEL, tratamiento de compras a pequeño contribuyente y formato del libro de compras y ventas.
- [ ] **C-07** Para un negocio en el régimen **opcional simplificado** (ISR sobre ingresos), ¿tiene sentido marcar los gastos como "no deducibles", o esa marca solo aplica al régimen sobre utilidades? ¿Afecta en algo al pequeño contribuyente?

---

## 7. Inventario, costeo y recetas

**Método de costeo: costo promedio ponderado (CPP).** Se recalcula en cada entrada: `nuevo_CPP = (existencia × CPP + cantidad_entrada × costo_unitario_entrada) / (existencia + cantidad_entrada)`.
- **Por qué:** es simple de explicar al usuario, estable ante compras frecuentes con precios variables (insumos) y compatible con un sistema automático.
- **Fuente:** la LAT admite métodos de valuación de inventarios que incluyen el promedio ponderado (Decreto 10-2012, art. 35 [verificar]); NIIF para las PYMES, Sección 13, admite el costo promedio ponderado.
- **Costo de adquisición:** precio sin el IVA acreditable + fletes y gastos directamente atribuibles, prorrateados por el valor de la línea.

**Recetas (restaurante):**
- Cada platillo tiene una receta: insumo, cantidad y % de merma estándar.
- Al vender un platillo se descargan **teóricamente** los insumos de su receta, al CPP vigente, y el costo de ventas = Σ (cantidad × (1 + merma) × CPP).
- **Conteo físico periódico** (sugerido semanal o mensual): la diferencia entre el inventario teórico y el real se registra como **merma o ajuste**.

**Mermas:** se registran contra `MERMA` (costo), con motivo y evidencia opcional (foto).

- [ ] **C-08** ¿Confirma el CPP como método único para el MVP? ¿Hace falta habilitar otro método por configuración?
- [ ] **C-09** ¿Es aceptable el consumo teórico por receta + ajuste por conteo físico? ¿Con qué frecuencia mínima recomienda el conteo?
- [ ] **C-10** Mermas: ¿qué documentación exige la ley para que una merma o destrucción sea deducible (actas, avisos a la SAT)? ¿Se debe distinguir la merma normal (de proceso) de la anormal?

---

## 8. Costo de la lectura de facturas con IA

**Contexto:**
- La lectura automática de facturas por foto es **opcional** y **tiene un costo** por página, que el usuario ve y autoriza antes de usarla.
- Se paga con un **"Saldo IA" prepagado en quetzales** que el usuario recarga. IntegraT le emite una factura (FEL) por cada recarga.
- Algunos planes incluyen *N* lecturas al mes sin costo adicional.

**Pedido del dueño del producto:** que el costo de la lectura **se reparta en los productos de esa factura, como un flete**, para que el precio sugerido lo incluya.

**Diseño:**
- **Prorrateo** por el valor de la línea, a centavos, con el residuo asignado a la línea mayor.
- Hay dos políticas, configurables por titular sin cambiar código:

  | Política | Asiento al confirmar la compra | Efecto en el precio sugerido |
  |---|---|---|
  | `capitalizar` (por defecto) | Debe `INVENTARIO_*` (incluye la IA prorrateada) / Haber `SALDO_IA_PREPAGADO` | Incluido vía CPP |
  | `gasto` | Debe `GASTO_SERVICIOS_IA` / Haber `SALDO_IA_PREPAGADO` | Incluido mediante un "recargo de gestión" **no contable** por unidad |

- **Recarga del saldo**, con factura de IntegraT en régimen general:

  | | Debe | Haber |
  |---|---|---|
  | Recarga de Q100 | `SALDO_IA_PREPAGADO` 89.29 · `IVA_CREDITO` 10.71 | `BANCO` 100 |

- **Lecturas incluidas en el plan:** no tienen costo incremental, así que no se prorratea nada. La suscripción a IntegraT se registra como `GASTO_SOFTWARE`.

**Opinión técnica (para su criterio):**
- La NIIF para las PYMES, Sección 13, incluye en el costo del inventario los costos de compra **directamente atribuibles** (precio, aranceles, transporte, manipulación) y excluye los **costos indirectos de administración**.
- La lectura de una factura con IA se parece más a un costo administrativo de procesamiento que a un costo para llevar el inventario a su ubicación y condición actuales.
- Por eso, la política técnicamente más defendible podría ser **`gasto`**, manteniendo el objetivo comercial (precio sugerido) con el recargo de gestión no contable.
- Los montos son mínimos (centavos por producto), así que el impacto en los estados financieros es inmaterial.

- [ ] **C-11** ¿Qué política debe usarse por defecto: `capitalizar` o `gasto`?
- [ ] **C-12** Saldo prepagado: ¿es correcto tratarlo como **anticipo** (activo) que se consume con cada lectura? Para IntegraT como emisor, ¿cuándo se genera el **IVA por un servicio prepagado**: al cobrar la recarga o al prestar el servicio (Ley del IVA, art. 4, momento de la generación del impuesto en servicios [verificar])? ¿Puede el usuario tomar el crédito fiscal completo al recargar?

---

## 9. Caja, dueño, propinas y pasarelas

| Situación | Tratamiento propuesto |
|---|---|
| **Faltante de caja** | Debe `DIFERENCIA_CAJA` / Haber `CAJA`. Si se atribuye a un empleado: `DEUDORES_DIVERSOS` |
| **Sobrante de caja** | Debe `CAJA` / Haber `OTROS_INGRESOS` |
| **Aporte del dueño** | Debe `CAJA` o `BANCO` / Haber `CAPITAL` |
| **Retiro del dueño** (persona individual: "saqué para mi casa") | Debe `RETIROS_PROPIETARIO` / Haber `CAJA`. No es gasto |
| **Propinas** (restaurante, fase posterior) | Cobradas con la cuenta: Debe `CAJA` / Haber `PROPINAS_POR_PAGAR`. No son ingreso ni base de IVA del negocio. Se liquidan a los empleados contra el pasivo |
| **Venta con tarjeta** | Debe `POR_COBRAR_PASARELA` (neto) + `GASTO_COMISIONES` (comisión) / Haber `VENTAS`, `IVA_DEBITO`. Al acreditarse: Debe `BANCO` / Haber `POR_COBRAR_PASARELA`. El IVA de la comisión, si la pasarela factura, va a crédito fiscal |

- [ ] **C-13** ¿Los faltantes de caja son deducibles? ¿Hay un tratamiento preferido para los faltantes atribuibles a empleados?
- [ ] **C-14** ¿Es correcta la cuenta de retiros del propietario para personas individuales? ¿Aplica igual a sociedades (donde serían dividendos o préstamos)?
- [ ] **C-15** Propinas: confirmar que no son base del IVA ni ingreso del negocio cuando se distribuyen íntegramente, y si existe alguna regla laboral o tributaria vigente al respecto [verificar].
- [ ] **C-16** Comisiones de pasarelas: ¿se registran por venta (estimadas) o al liquidar la pasarela (con su factura)? La app propone el registro por venta con un ajuste al liquidar.

---

## 10. Retención de documentos y fotos de facturas

**Diseño:**
- Las fotos de las facturas de compra, las plantillas cargadas y, en el futuro, los XML de la FEL se guardan en un **almacenamiento privado** (Cloudflare R2), vinculadas a su compra y su asiento.
- **No se borran automáticamente.** La app conservará los registros y documentos **por al menos 5 años** después del cierre del ejercicio (más que el plazo de prescripción, como margen) y nunca los borrará sin una acción explícita del titular, fuera de ese plazo.
- **Aviso al usuario:** "La foto es una copia de respaldo. Si tu factura **no es electrónica (FEL)**, guarda también el papel original".

**Fuentes:**
- Código Tributario, Decreto 6-91: prescripción de **4 años** para las facultades de la Administración Tributaria (art. 47 [verificar]) y obligación de conservar libros, registros y documentos mientras no prescriban (art. 112 [verificar]).
- Código de Comercio, Decreto 2-70: obligación de conservar la contabilidad, la correspondencia y la documentación (art. 382 [verificar el plazo]).

- [ ] **C-17** Confirmar el plazo mínimo de conservación aplicable (tributario y mercantil) y si una **fotografía** de un documento en papel tiene algún valor probatorio o es solo un respaldo de gestión.

---

## 11. Libros obligatorios y exportaciones

**Diseño (MVP + fase fiscal):** exportaciones por **titular** (consolidado) y por negocio, en PDF y Excel:

1. Libro Diario.
2. Libro Mayor.
3. Balance de comprobación.
4. Estado de resultados y balance general (por periodo).
5. Libro de compras y servicios recibidos, y libro de ventas y servicios prestados.
6. Detalle de inventario valorizado (para el libro de inventarios).
7. Detalle de gastos no deducibles.

**Fuentes:**
- Código de Comercio, Decreto 2-70, arts. 368 y siguientes: el comerciante con activo mayor al umbral legal debe llevar contabilidad completa con los libros de Inventarios, Diario, Mayor y Estados Financieros [verificar el umbral vigente y la obligación según el tipo de comerciante].
- Ley del IVA, art. 37 (libros de compras y ventas) [verificar].
- Habilitación de libros ante la SAT [verificar el procedimiento vigente y si admite libros generados por un sistema o electrónicos].

- [ ] **C-18** ¿Qué libros debe llevar cada tipo de usuario (pequeño contribuyente, régimen general con o sin la obligación de contabilidad completa)? ¿Qué **formato** necesita el contador para transcribir o imprimir los libros habilitados? ¿Algún formato de archivo es preferido para el libro de compras y ventas?

---

## 12. Consolidación por titular

| Tema | Diseño |
|---|---|
| IVA mensual | Se suma el débito y el crédito de todos los negocios del NIT y se presenta **un solo resumen** para la declaración |
| Límite anual del pequeño contribuyente | Se suman los ingresos de todos los negocios del NIT y se avisa al 70 %, 90 % y 100 % |
| ISR | Se consolidan los ingresos, costos y gastos del NIT |
| Traslados entre negocios del mismo titular (por ejemplo, insumos de una sucursal a otra) | **Fuera del MVP.** No son ventas: se propone registrarlos como traslado entre establecimientos (sin IVA), con una cuenta puente que se elimina en el consolidado |

- [ ] **C-19** ¿Es correcto este tratamiento consolidado? ¿Cómo deben documentarse los traslados de inventario entre establecimientos del mismo NIT (por ejemplo, con una nota de envío o un documento FEL específico)?

---

## 13. Asientos tipo (el motor los genera automáticamente)

**Régimen general (IVA 12 % incluido):**

| Evento | Debe | Haber |
|---|---|---|
| Venta en efectivo Q112 (costo Q60) | Caja 112; Costo de ventas 60 | Ventas 100; IVA por pagar 12; Inventario 60 |
| Venta al crédito o contra entrega | Clientes 112; Costo de ventas 60 | Ventas 100; IVA por pagar 12; Inventario 60 |
| Cobro a cliente | Caja o Bancos | Clientes |
| Venta de platillo Q56 (receta Q18) | Caja 56; Costo de ventas 18 | Ventas A&B 50; IVA por pagar 6; Inventario insumos 18 |
| Envío cobrado al cliente Q28 | Caja 28 | Ingresos por envíos 25; IVA por pagar 3 |
| Compra al crédito Q1,120 (+ IA Q0.80, capitalizar) | Inventario 1,000.80; IVA por cobrar 120 | Proveedores 1,120; Saldo IA 0.80 |
| Pago a proveedor | Proveedores | Caja o Bancos |
| Gasto con factura (renta Q2,240) | Alquileres 2,000; IVA por cobrar 240 | Bancos 2,240 |
| Gasto sin factura (gas Q50) | Gastos no deducibles 50 | Caja 50 |
| Merma de insumos Q35 | Mermas 35 | Inventario insumos 35 |
| Faltante de caja Q20 | Faltantes de caja 20 | Caja 20 |
| Depósito de efectivo | Bancos | Caja |
| Aporte del dueño | Caja o Bancos | Capital |
| Retiro del dueño | Retiros del propietario | Caja |
| Recarga de Saldo IA Q100 | Saldo IA 89.29; IVA por cobrar 10.71 | Bancos 100 |
| Liquidación de IVA del mes | IVA por pagar | IVA por cobrar; Impuestos por pagar (o remanente) |
| Anulación de una venta | Reverso exacto del asiento original + reingreso de inventario | |

**Pequeño contribuyente (5 % sobre ingresos [verificar]):**

| Evento | Debe | Haber |
|---|---|---|
| Venta en efectivo Q112 (costo Q60) | Caja 112; Costo de ventas 60 | Ventas 112; Inventario 60 |
| Compra Q1,120 | Inventario 1,120 | Proveedores o Caja 1,120 |
| Provisión mensual del impuesto (ventas del mes Q20,000) | Impuesto pequeño contribuyente 1,000 | Impuestos por pagar 1,000 |
| Pago del impuesto | Impuestos por pagar | Bancos |

- [ ] **C-20** Validar cada asiento tipo. ¿Falta algún evento frecuente en estos negocios?

---

## 14. Fuentes citadas

| Norma | Para qué se usa | Estado |
|---|---|---|
| Ley del Impuesto al Valor Agregado, Decreto 27-92 y sus reformas | Tarifa, débito y crédito fiscal, régimen de pequeño contribuyente, libros, generación del impuesto | Citada de memoria; **[verificar artículos y reformas vigentes]** |
| Decreto 4-2012 (reformas tributarias de 2012) | Régimen de pequeño contribuyente | [verificar] |
| Ley de Actualización Tributaria, Decreto 10-2012 | ISR: regímenes, tasas, deducibilidad, valuación de inventarios | [verificar] |
| Ley del Impuesto de Solidaridad, Decreto 73-2008 | ISO (fuera del MVP) | [verificar] |
| Ley de Retenciones del IVA, Decreto 20-2006 | Retenciones (fuera del MVP) | [verificar] |
| Código Tributario, Decreto 6-91 | Prescripción, conservación de documentos | [verificar] |
| Código de Comercio, Decreto 2-70 | Obligación de contabilidad y libros, conservación | [verificar] |
| Régimen de Factura Electrónica en Línea (FEL), acuerdos de Directorio de la SAT | Documentos tributarios electrónicos (ver `PLAN_FEL.md`) | [verificar los acuerdos y el esquema vigente] |
| Reglas del NIT (dígito verificador módulo 11, "K" = 10) y del CUI del DPI (13 dígitos: 8 + verificador + departamento + municipio) | Validar el NIT o CUI del cliente (`api/src/integrat/validaciones.py`) | [verificar los algoritmos y la tabla de municipios] |
| NIIF para las PYMES (IASB), Sección 13 Inventarios | Costo de inventarios, costeo promedio | Marco contable de referencia [verificar la aplicabilidad local] |

**Nota final:** IntegraT **no presenta declaraciones** en el MVP. Prepara la información para que el usuario o su contador las presenten. El contenido de este documento **no constituye asesoría legal**; requiere la validación profesional que aquí se solicita.
