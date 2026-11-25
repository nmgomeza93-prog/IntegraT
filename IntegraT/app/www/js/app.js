// Comportamiento del lado del navegador: navegación, hoja inferior, reconexión y tamaño de texto.
(function () {
  "use strict";

  // --- Tamaño de texto (preferencia del dispositivo; tolera navegadores sin almacenamiento) ---
  var CLASES_TEXTO = { normal: "", grande: "texto-grande", muy_grande: "texto-muy-grande" };
  function aplicarTamano(tamano) {
    var html = document.documentElement;
    html.classList.remove("texto-grande", "texto-muy-grande");
    if (CLASES_TEXTO[tamano]) html.classList.add(CLASES_TEXTO[tamano]);
    document.querySelectorAll("[data-tamano-texto]").forEach(function (b) {
      b.setAttribute("aria-pressed", b.getAttribute("data-tamano-texto") === tamano ? "true" : "false");
    });
  }
  function leerTamano() {
    try { return localStorage.getItem("integrat.tamano_texto") || "normal"; } catch (e) { return "normal"; }
  }
  function guardarTamano(tamano) {
    try { localStorage.setItem("integrat.tamano_texto", tamano); } catch (e) { /* sin almacenamiento */ }
  }

  // --- Hoja inferior ---
  function abrirHoja(id) {
    var hoja = document.getElementById(id);
    if (!hoja) return;
    hoja.classList.add("abierta");
    hoja.setAttribute("aria-hidden", "false");
    var primero = hoja.querySelector("button");
    if (primero) primero.focus();
  }
  function cerrarHojas() {
    document.querySelectorAll(".hoja.abierta").forEach(function (h) {
      h.classList.remove("abierta");
      h.setAttribute("aria-hidden", "true");
    });
  }

  // --- Navegación inferior: marca la sección activa ---
  // Secciones que no tienen botón propio en la barra se muestran bajo otra (Gastos vive en "Más").
  var BAJO_BOTON = { gastos: "mas", inventario: "mas", compras: "mas", impuestos: "mas" };
  function marcarSeccion(destino) {
    destino = BAJO_BOTON[destino] || destino;
    document.querySelectorAll(".nav-inferior__boton[data-destino]").forEach(function (b) {
      if (b.getAttribute("data-destino") === destino) b.setAttribute("aria-current", "page");
      else b.removeAttribute("aria-current");
    });
    window.scrollTo(0, 0);
  }

  document.addEventListener("click", function (ev) {
    var nav = ev.target.closest("[data-destino]");
    if (nav) {
      cerrarHojas();
      marcarSeccion(nav.getAttribute("data-destino"));
      if (window.Shiny) Shiny.setInputValue("nav_destino", nav.getAttribute("data-destino"), { priority: "event" });
      return;
    }
    var abre = ev.target.closest("[data-abre-hoja]");
    if (abre) { abrirHoja(abre.getAttribute("data-abre-hoja")); return; }
    if (ev.target.closest("[data-cierra-hoja]") || ev.target.classList.contains("hoja-fondo")) { cerrarHojas(); return; }
    var accion = ev.target.closest("[data-accion]");
    if (accion) {
      cerrarHojas();
      if (window.Shiny) Shiny.setInputValue("accion_rapida", accion.getAttribute("data-accion"), { priority: "event" });
      return;
    }
    // Opción de elección (onboarding): manda su valor al input indicado
    var elige = ev.target.closest("[data-elige-input]");
    if (elige) {
      var entrada = elige.getAttribute("data-elige-input");
      // En un selector segmentado (o un grupo marcado con data-elige-grupo), la opción tocada
      // queda marcada de inmediato (sin recargar)
      var grupo = elige.closest(".segmentado, [data-elige-grupo]");
      if (grupo) {
        grupo.querySelectorAll("[data-elige-input]").forEach(function (b) {
          b.setAttribute("aria-pressed", b === elige ? "true" : "false");
        });
      }
      if (window.Shiny) Shiny.setInputValue(entrada, elige.getAttribute("data-elige-valor"), { priority: "event" });
      return;
    }
    var tam = ev.target.closest("[data-tamano-texto]");
    if (tam) {
      var t = tam.getAttribute("data-tamano-texto");
      aplicarTamano(t);
      guardarTamano(t);
    }
  });

  document.addEventListener("keydown", function (ev) {
    if (ev.key === "Escape") cerrarHojas();
    // Enter en un campo de un formulario de entrada = tocar su botón principal
    if (ev.key === "Enter" && ev.target.matches && ev.target.matches(".entrada .campo input")) {
      var boton = ev.target.closest(".entrada").querySelector(".boton-primario");
      if (boton) { ev.preventDefault(); boton.click(); }
    }
  });

  // --- Campo de fecha del navegador (input type="date"): Shiny no lo conecta por sí solo ---
  if (window.Shiny && Shiny.inputBindings && window.jQuery) {
    var enlaceFecha = new Shiny.InputBinding();
    jQuery.extend(enlaceFecha, {
      find: function (alcance) { return jQuery(alcance).find('input[type="date"]'); },
      getValue: function (el) { return el.value; },
      setValue: function (el, valor) { el.value = valor; },
      subscribe: function (el, callback) {
        jQuery(el).on("change.enlaceFecha input.enlaceFecha", function () { callback(true); });
      },
      unsubscribe: function (el) { jQuery(el).off(".enlaceFecha"); }
    });
    Shiny.inputBindings.register(enlaceFecha, "integrat.fecha");
  }

  // --- Aviso amable de reconexión ---
  function aviso(visible) {
    var el = document.getElementById("aviso-conexion");
    if (el) el.classList.toggle("visible", visible);
  }
  $(document).on("shiny:disconnected", function () { aviso(true); });
  $(document).on("shiny:connected", function () { aviso(false); });

  $(document).on("shiny:sessioninitialized", function () { aplicarTamano(leerTamano()); });
  document.addEventListener("DOMContentLoaded", function () { aplicarTamano(leerTamano()); });

  // El servidor puede pedir cambiar de sección (ej. desde un estado vacío)
  $(document).one("shiny:connected", function () {
    Shiny.addCustomMessageHandler("ir_a_seccion", function (destino) { marcarSeccion(destino); });
    // Al cambiar de pantalla (registro, onboarding, app) se vuelve arriba
    Shiny.addCustomMessageHandler("subir", function (_) { window.scrollTo(0, 0); });
  });
})();
