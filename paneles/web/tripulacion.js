/* Tripulación (para proyectar y para las otras laptops; solo lectura): una tarjeta por integrante,
 * la recomendación para la tarea (misma lógica que resumen_tripulacion() del copiloto) y el copiloto. */
(function () {
  "use strict";

  const { CFG, el, etiquetaSimulado, palabraColor } = Comun;
  const L = Logica;
  const $ = (id) => document.getElementById(id);

  const MAX_COPILOTO = 12;
  const PULSO_VIGENTE_MS = 15000;

  const miembros = (CFG.tripulacion || []).slice();
  const evaluaciones = {};   // persona -> evaluación (en orden de llegada, como en el copiloto)
  const pulsos = {};         // persona -> {lpm, llegada, simulado}
  const copiloto = [];       // más nuevas primero
  let tareaSesion = "";

  function esMiembro(persona) {
    return !miembros.length || miembros.includes(persona);
  }

  Comun.conectar("tripulacion", ["apto/+/evaluacion", "apto/+/esp32", "apto/+/copiloto", "apto/control/sesion"],
    (tema, datos) => {
      if (tema === "apto/control/sesion") {
        if (datos.tarea) { tareaSesion = datos.tarea; pintarRecomendacion(); }
        return;
      }
      const [persona, tipo] = Comun.partesTema(tema);
      if (!esMiembro(persona)) return;  // p. ej. evaluaciones viejas de alguien que ya no está
      if (tipo === "evaluacion") {
        evaluaciones[persona] = { ...datos, persona };
        pintarTodo();
      } else if (tipo === "esp32" && datos.pulso_lpm != null) {
        pulsos[persona] = { lpm: datos.pulso_lpm, llegada: Date.now(), simulado: datos.simulado };
        pintarTarjetas();
      } else if (tipo === "copiloto") {
        copiloto.unshift({ ...datos, persona });
        copiloto.length = Math.min(copiloto.length, MAX_COPILOTO);
        pintarCopiloto();
      }
    });

  /** Tarea para la recomendación: la de la sesión activa o, si no, la de la evaluación más reciente. */
  function tareaActual() {
    if (tareaSesion) return tareaSesion;
    const evs = Object.values(evaluaciones).filter((e) => e.tarea);
    evs.sort((a, b) => (L.tsAMs(b.ts) || 0) - (L.tsAMs(a.ts) || 0));
    return evs.length ? evs[0].tarea : "";
  }

  function pintarRecomendacion() {
    const tarea = tareaActual();
    const { texto, mejor, hayVerde } = L.recomendacion(evaluaciones, tarea);
    const caja = $("recomendacion");
    caja.dataset.color = mejor ? mejor.color : "";
    $("rec-etiqueta").textContent = tarea ? `Recomendación para ${L.conArticulo(tarea)}` : "Recomendación";
    if (!mejor) {
      $("rec-titular").replaceChildren("Sin evaluaciones todavía");
    } else {
      $("rec-titular").replaceChildren(
        hayVerde ? L.nombre(mejor.persona) : `Nadie en verde · opción menos riesgosa: ${L.nombre(mejor.persona)}`,
        el("span", { class: "chip-color", "data-color": mejor.color }, palabraColor(mejor.color)),
      );
    }
    $("rec-texto").textContent = texto;
  }

  function pintarTarjetas() {
    const personas = miembros.length ? miembros : Object.keys(evaluaciones);
    $("tarjetas").replaceChildren(...personas.map((p) => {
      const ev = evaluaciones[p];
      const pulso = pulsos[p];
      const vigente = pulso && Date.now() - pulso.llegada < PULSO_VIGENTE_MS;
      const filas = [];
      if (ev) {
        filas.push(el("dt", {}, "Puntaje"), el("dd", {}, L.decimal(ev.puntaje)));
        filas.push(el("dt", {}, "Evaluación"), el("dd", {}, L.hora(L.tsAMs(ev.ts))));
      }
      if (pulso) {
        filas.push(el("dt", {}, "Pulso"), el("dd", { class: vigente ? "pulso-vivo" : "viejo" },
          vigente ? `${Math.round(pulso.lpm)} lpm` : "sin datos recientes", vigente ? etiquetaSimulado(pulso) : null));
      }
      return el("article", { class: "tarjeta panel", "data-color": ev ? ev.color : "" },
        el("h3", {}, L.nombre(p), ev ? etiquetaSimulado(ev) : null),
        ev ? el("span", { class: "chip-color", "data-color": ev.color }, palabraColor(ev.color))
          : el("span", { class: "sin-evaluar" }, "Sin evaluar"),
        filas.length ? el("dl", {}, filas) : null,
        ev && ev.motivos && ev.motivos.length ? el("p", { class: "motivos" }, ev.motivos.join(" · ")) : null,
      );
    }));
  }

  function pintarCopiloto() {
    $("copiloto").replaceChildren(...(copiloto.length ? copiloto.map((d) => el("li", {},
      el("span", { class: "meta" }, `${L.nombre(d.persona)} · ${L.hora(L.tsAMs(d.ts))}${d.modo ? " · " + d.modo : ""}`),
      d.pregunta ? el("span", { class: "preg" }, d.pregunta === "(resumen automático)" ? "Resumen automático" : `«${d.pregunta}»`) : null,
      el("span", { class: "resp" }, d.respuesta || ""),
    )) : [el("li", { class: "vacio" }, "Todavía no hay respuestas.")]));
  }

  function pintarTodo() {
    pintarRecomendacion();
    pintarTarjetas();
  }

  function reloj() {
    $("reloj").textContent = `Hora a bordo ${L.hora(Date.now())}`;
  }

  pintarTodo();
  reloj();
  setInterval(() => { reloj(); pintarTarjetas(); }, 1000);  // también apaga los pulsos sin datos recientes
})();
