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
  function marcarSeccion(destino) {
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
    var tam = ev.target.closest("[data-tamano-texto]");
    if (tam) {
      var t = tam.getAttribute("data-tamano-texto");
      aplicarTamano(t);
      guardarTamano(t);
    }
  });

  document.addEventListener("keydown", function (ev) {
    if (ev.key === "Escape") cerrarHojas();
  });

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
  });
})();
