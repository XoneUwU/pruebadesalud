/* Plantillas sin frameworks: h`...` arma HTML escapando todo lo que se interpola, y morph() actualiza el DOM
 * cambiando solo lo distinto (así no se pierden el foco, el video ni las animaciones al volver a pintar).
 * Los eventos van por atributos data-click, data-change, data-submit y data-pointer: Plantilla.acciones(...)
 * los atiende con un solo oyente por tipo. */
(function () {
  "use strict";

  class Crudo {
    constructor(s) { this.s = s; }
    toString() { return this.s; }
  }

  const ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ESC[c]);

  function valor(v) {
    if (v === null || v === undefined || v === false) return "";
    if (v instanceof Crudo) return v.s;
    if (Array.isArray(v)) return v.map(valor).join("");
    return esc(v);
  }

  /** h`<p>${texto}</p>`: los textos se escapan; lo que ya es h`...` (o una lista de h`...`) entra tal cual. */
  function h(partes, ...vals) {
    let s = partes[0];
    for (let i = 0; i < vals.length; i++) s += valor(vals[i]) + partes[i + 1];
    return new Crudo(s);
  }

  /** Atributo booleano: si(cond, "disabled") -> "disabled" o nada. */
  const si = (cond, nombre) => new Crudo(cond ? nombre : "");

  // ------------------------------------------------------------------ morph
  const clave = (n) => (n.nodeType === 1 ? n.getAttribute("data-k") : null);

  function mismo(a, b) {
    return a.nodeType === b.nodeType && a.nodeName === b.nodeName && clave(a) === clave(b);
  }

  function atributos(viejo, nuevo) {
    for (const { name } of Array.from(viejo.attributes)) {
      if (!nuevo.hasAttribute(name)) viejo.removeAttribute(name);
    }
    for (const { name, value } of Array.from(nuevo.attributes)) {
      if (viejo.getAttribute(name) !== value) viejo.setAttribute(name, value);
    }
    const tag = viejo.nodeName;
    if (tag === "INPUT") {
      if (viejo.type === "checkbox" || viejo.type === "radio") viejo.checked = nuevo.hasAttribute("checked");
      else if (!viejo.hasAttribute("data-libre") && document.activeElement !== viejo) viejo.value = nuevo.getAttribute("value") || "";
    } else if (tag === "OPTION") {
      viejo.selected = nuevo.hasAttribute("selected");
    }
  }

  function morphNodo(viejo, nuevo) {
    if (viejo.nodeType !== 1) {
      if (viejo.nodeValue !== nuevo.nodeValue) viejo.nodeValue = nuevo.nodeValue;
      return;
    }
    // data-congelar: el contenido lo maneja otro código (logo animado, video). Solo se cambia si cambia la marca.
    const congelar = viejo.getAttribute("data-congelar");
    if (congelar !== null && congelar === nuevo.getAttribute("data-congelar")) return;
    atributos(viejo, nuevo);
    morphHijos(viejo, nuevo);
    if (viejo.nodeName === "SELECT") {
      const elegida = nuevo.querySelector("option[selected]");
      if (elegida) viejo.value = elegida.getAttribute("value");
    }
  }

  function morphHijos(viejo, nuevo) {
    const a = Array.from(viejo.childNodes);
    const b = Array.from(nuevo.childNodes);
    for (let i = 0; i < b.length; i++) {
      const nb = b[i];
      const na = a[i];
      if (!na) viejo.appendChild(nb);
      else if (mismo(na, nb)) morphNodo(na, nb);
      else viejo.replaceChild(nb, na);
    }
    for (let i = b.length; i < a.length; i++) viejo.removeChild(a[i]);
  }

  /** Deja dentro de destino el HTML nuevo, tocando solo lo que cambió. */
  function morph(destino, html) {
    const t = document.createElement("template");
    t.innerHTML = String(html);
    morphHijos(destino, t.content);
  }

  // ------------------------------------------------------------------ eventos
  /** acciones: {nombre: (arg, evento, elemento) => ...}. Un oyente por tipo de evento, en document. */
  function acciones(mapa) {
    const atender = (tipo, atributo, filtro) => document.addEventListener(tipo, (e) => {
      const el = e.target.closest && e.target.closest(`[${atributo}]`);
      if (!el || el.disabled || (filtro && !filtro(e))) return;
      const fn = mapa[el.getAttribute(atributo)];
      if (!fn) return;
      if (tipo === "submit") e.preventDefault();
      fn(el.getAttribute("data-arg"), e, el);
    });
    atender("click", "data-click");
    atender("change", "data-change");
    atender("input", "data-input");
    atender("submit", "data-submit");
    atender("pointerdown", "data-pointer", (e) => e.button === 0);
  }

  const Plantilla = { h, si, esc, crudo: (s) => new Crudo(s), morph, acciones };
  if (typeof module !== "undefined" && module.exports) module.exports = Plantilla;  // para probar h`` con Node
  else window.Plantilla = Plantilla;
})();
