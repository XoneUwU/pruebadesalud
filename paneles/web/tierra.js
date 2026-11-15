/* Control de misión en Tierra (solo lectura): las evaluaciones llegan con un retraso simulado
 * (RETRASO_TIERRA_S), para mostrar que la tripulación decide a bordo antes de que Tierra se entere. */
(function () {
  "use strict";

  const { CFG, el, etiquetaSimulado, etiquetaProvisional, palabraColor } = Comun;
  const L = Logica;
  const $ = (id) => document.getElementById(id);

  const RETRASO_S = Number.isFinite(Number(CFG.retraso_tierra_s)) ? Number(CFG.retraso_tierra_s) : 2.6;
  const RETRASO_MS = RETRASO_S * 1000;
  const MAX_TRANSMISIONES = 30;

  const miembros = (CFG.tripulacion || []).slice();
  const transmisiones = [];  // {clave, persona, ev, envio, llegada, recibida}
  const conocidas = new Set();
  const enTierra = {};       // persona -> última transmisión recibida

  Comun.conectar("tierra", ["apto/+/evaluacion"], (tema, datos, retenido) => {
    const [persona] = Comun.partesTema(tema);
    if (miembros.length && !miembros.includes(persona)) return;
    const clave = [persona, datos.sesion, datos.ts, datos.color, datos.puntaje].join("|");
    if (conocidas.has(clave)) return;  // al reconectar, el broker repite las evaluaciones retenidas
    conocidas.add(clave);
    // Envío: si llegó en vivo, ahora; si estaba guardada en el broker (retenida), la hora en que se hizo.
    const ts = L.tsAMs(datos.ts);
    const envio = retenido && Number.isFinite(ts) ? Math.min(ts, Date.now()) : Date.now();
    transmisiones.unshift({ clave, persona, ev: { ...datos, persona }, envio, llegada: envio + RETRASO_MS, recibida: false });
    transmisiones.length = Math.min(transmisiones.length, MAX_TRANSMISIONES);
    actualizar();
  });

  function segundos(ms) {
    return `${Math.round(ms / 1000)} s`;
  }

  function actualizar() {
    const ahora = Date.now();
    let cambio = false;
    for (const t of transmisiones.slice().reverse()) {  // de la más vieja a la más nueva
      if (!t.recibida && ahora >= t.llegada) {
        t.recibida = true;
        cambio = true;
        if (!enTierra[t.persona] || enTierra[t.persona].envio <= t.envio) enTierra[t.persona] = t;
      }
    }
    pintarTransmisiones(ahora);
    if (cambio || !$("tarjetas").children.length) pintarTarjetas();
  }

  function pintarTransmisiones(ahora) {
    if (!transmisiones.length) return;
    $("transmisiones").replaceChildren(...transmisiones.map((t) => {
      const ev = t.ev;
      if (!t.recibida) {
        return el("li", { class: "transmision panel en-camino" },
          el("div", { class: "cabeza" }, L.nombre(t.persona), el("span", { class: "falta" },
            `En camino · llega en ${segundos(t.llegada - ahora)}`)),
          el("span", { class: "horas-tx" }, `Enviada desde la nave ${L.hora(t.envio)} · llega a Tierra ${L.hora(t.llegada)}`),
          el("span", { class: "oculto" }, "Tierra todavía no conoce el resultado."));
      }
      return el("li", { class: "transmision panel", "data-color": ev.color },
        el("div", { class: "cabeza" }, L.nombre(t.persona),
          el("span", { class: "chip-color", "data-color": ev.color }, palabraColor(ev.color)), etiquetaProvisional(ev),
          etiquetaSimulado(ev)),
        el("span", { class: "horas-tx" },
          `Enviada desde la nave ${L.hora(t.envio)} · llegó a Tierra ${L.hora(t.llegada)} (+${segundos(t.llegada - t.envio)})`),
        ev.motivos && ev.motivos.length ? el("ul", {}, ev.motivos.map((m) => el("li", {}, m))) : null,
        ev.accion ? el("span", {}, `Acción: ${ev.accion}`) : null,
        el("span", { class: "decidio" },
          `La tripulación vio este resultado a las ${L.hora(t.envio)}, ${segundos(t.llegada - t.envio)} antes que Tierra, y ya decidió a bordo.`));
    }));
  }

  function pintarTarjetas() {
    const personas = miembros.length ? miembros : Object.keys(enTierra);
    $("tarjetas").replaceChildren(...personas.map((p) => {
      const t = enTierra[p];
      const ev = t && t.ev;
      return el("article", { class: "tarjeta panel", "data-color": ev ? ev.color : "" },
        el("h3", {}, L.nombre(p), ev ? etiquetaProvisional(ev) : null, ev ? etiquetaSimulado(ev) : null),
        ev ? el("span", { class: "chip-color", "data-color": ev.color }, palabraColor(ev.color))
          : el("span", { class: "sin-evaluar" }, "Sin datos en Tierra"),
        t ? el("dl", {},
          el("dt", {}, "Puntaje"), el("dd", {}, L.decimal(ev.puntaje)),
          el("dt", {}, "A bordo"), el("dd", {}, L.hora(t.envio)),
          el("dt", {}, "En Tierra"), el("dd", {}, L.hora(t.llegada))) : null,
      );
    }));
  }

  $("retraso").textContent = `${RETRASO_S} s`;
  pintarTarjetas();
  setInterval(() => {
    $("reloj").textContent = `Hora en Tierra ${L.hora(Date.now())}`;
    actualizar();
  }, 250);
})();
