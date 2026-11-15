// Vista de Houston: pide los datos al servidor (api/*.json) cada pocos segundos y los muestra. Solo lee.
// Todo el texto entra con textContent o nodos de texto (nunca como HTML), así un dato no puede inyectar HTML.
"use strict";

const CADA_MS = 5000;
const estado = { persona: "", dias: 7, seleccion: "", personasConocidas: new Set() };

// ------------------------------------------------------------ utilidades

function el(etiqueta, attrs, ...hijos) {
  const nodo = document.createElement(etiqueta);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "texto") nodo.textContent = v;
    else if (k === "al_click") nodo.addEventListener("click", v);
    else nodo.setAttribute(k, v === true ? "" : String(v));
  }
  for (const h of hijos.flat()) {
    if (h === null || h === undefined || h === false) continue;
    nodo.append(h instanceof Node ? h : document.createTextNode(String(h)));
  }
  return nodo;
}

function hora(ms) {
  if (!ms) return "–";
  const f = new Date(ms);
  const hoy = new Date();
  const mismoDia = f.toDateString() === hoy.toDateString();
  return mismoDia ? f.toLocaleTimeString("es", { hour12: false })
    : f.toLocaleString("es", { dateStyle: "short", timeStyle: "short", hour12: false });
}

function hace(ms, ahora) {
  if (!ms) return "–";
  const s = Math.max(0, Math.round((ahora - ms) / 1000));
  if (s < 60) return `hace ${s} s`;
  if (s < 3600) return `hace ${Math.round(s / 60)} min`;
  if (s < 86400) return `hace ${Math.round(s / 3600)} h`;
  return `hace ${Math.round(s / 86400)} d`;
}

function num(v, dec = 0, unidad = "") {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return "–";
  return Number(v).toLocaleString("es", { maximumFractionDigits: dec, minimumFractionDigits: dec }) + unidad;
}

function pct(v) { return v === null || v === undefined ? "–" : num(v * 100, 1, " %"); }

function nombre(p) { return p ? p.charAt(0).toUpperCase() + p.slice(1) : "–"; }

function colorTexto(c) { return { verde: "Verde", amarillo: "Amarillo", rojo: "Rojo" }[c] || "Sin dato"; }

function chipColor(c) { return el("span", { class: "color", "data-color": c || "" }, colorTexto(c)); }

function marcas(f) {
  return [
    f.aviso_spo2 && el("span", { class: "marca-dato spo2", title: "Oxígeno más bajo de lo habitual" }, "SpO₂"),
    f.provisional && el("span", { class: "marca-dato", title: "Coordinador provisional" }, "prov."),
    f.simulado && el("span", { class: "marca-dato", title: "Datos simulados" }, "sim."),
  ];
}

async function pedir(ruta) {
  const r = await fetch(ruta, { cache: "no-store" });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

function aviso(texto) {
  const a = document.getElementById("aviso");
  a.hidden = !texto;
  a.textContent = texto || "";
}

// ------------------------------------------------------------ tablero

function pintarSenal(enlace, ahora) {
  const s = document.getElementById("senal");
  let est = "esperando", texto = "Esperando el enlace…";
  if (enlace.error) { est = "error"; texto = enlace.error; }
  else if (enlace.con_senal) { est = "ok"; texto = "Enlace con la nave activo"; }
  else if (enlace.actualizado) { est = "sin_senal"; texto = `Sin señal de la nave (${hace(enlace.actualizado, ahora)})`; }
  s.dataset.estado = est;
  s.querySelector(".texto").textContent = texto;
  document.getElementById("retraso").textContent = `${enlace.retraso_s} s`;
  document.getElementById("ultimo").textContent = hace(enlace.ultimo_dato_nave, ahora);
  document.getElementById("copiados").textContent = num(enlace.copiados);
  document.getElementById("en-camino").textContent = num(enlace.en_camino);
}

function tarjeta(t, ahora) {
  const f = t.ultima;
  if (!f) {
    return el("article", { class: "tarjeta", "data-vacia": true },
      el("h3", { texto: nombre(t.persona) }), el("div", { class: "meta" }, "Sin evaluaciones en Tierra"));
  }
  return el("article", {
    class: "tarjeta", "data-color": f.color || "", tabindex: 0,
    al_click: () => seleccionar(f.id),
  },
  el("h3", { texto: nombre(t.persona) }),
  el("div", {}, chipColor(f.color), marcas(f)),
  el("div", { class: "meta" }, `${f.tarea || "Sin tarea"} · llegó ${hace(f.llego || f.fecha, ahora)}`),
  el("dl", {},
    el("dt", {}, "Puntaje"), el("dd", {}, num(f.puntaje)),
    el("dt", {}, "KSS"), el("dd", {}, num(f.kss)),
    el("dt", {}, "PVT"), el("dd", {}, num(f.pvt_mediana, 0, " ms")),
    el("dt", {}, "Pulso"), el("dd", {}, num(f.pulso_lpm, 0, " lpm"))));
}

function pintarTablero(t) {
  pintarSenal(t.enlace, t.ahora);
  const c = t.conteo;
  document.getElementById("conteo").replaceChildren(
    el("span", { class: "chip" }, el("b", { class: "color", "data-color": "verde" }), `${c.verde} verde`),
    el("span", { class: "chip" }, el("b", { class: "color", "data-color": "amarillo" }), `${c.amarillo} amarillo`),
    el("span", { class: "chip" }, el("b", { class: "color", "data-color": "rojo" }), `${c.rojo} rojo`),
    el("span", { class: "chip" }, `${c.sin_dato} sin dato`));
  document.getElementById("tarjetas").replaceChildren(...t.tripulacion.map((x) => tarjeta(x, t.ahora)));
  for (const x of t.tripulacion) estado.personasConocidas.add(x.persona);
  pintarFiltroPersonas();

  const lista = document.getElementById("copiloto");
  if (!t.copiloto.length) lista.replaceChildren(el("li", { class: "vacio" }, "Sin conversaciones recibidas."));
  else lista.replaceChildren(...t.copiloto.map((m) => el("li", {},
    el("div", { class: "quien" }, `${nombre(m.persona)} · ${hora(m.fecha)}`),
    el("div", { class: "p" }, m.pregunta || "(resumen automático)"),
    el("div", {}, m.respuesta))));
}

function pintarFiltroPersonas() {
  const sel = document.getElementById("f-persona");
  const ya = new Set([...sel.options].map((o) => o.value));
  for (const p of estado.personasConocidas) {
    if (!ya.has(p)) sel.append(el("option", { value: p }, nombre(p)));
  }
}

// ------------------------------------------------------------ evaluaciones

function pintarFilas(filas) {
  const cuerpo = document.getElementById("filas");
  if (!filas.length) {
    cuerpo.replaceChildren(el("tr", {}, el("td", { colspan: 8, class: "vacio" }, "Ninguna evaluación en este período.")));
    return;
  }
  cuerpo.replaceChildren(...filas.slice().reverse().map((f) => el("tr", {
    "aria-selected": f.id === estado.seleccion ? "true" : "false", al_click: () => seleccionar(f.id),
  },
  el("td", {}, hora(f.llego || f.fecha)),
  el("td", {}, nombre(f.persona)),
  el("td", {}, chipColor(f.color), marcas(f)),
  el("td", {}, f.tarea || "–"),
  el("td", { class: "num" }, num(f.kss)),
  el("td", { class: "num" }, num(f.pvt_mediana, 0, " ms")),
  el("td", { class: "num" }, num(f.pulso_lpm, 0, " lpm")),
  el("td", { class: "num" }, f.llego && f.fecha ? num((f.llego - f.fecha) / 1000, 0, " s") : "–"))));
}

function rutaEvaluaciones(ext) {
  const q = new URLSearchParams({ dias: estado.dias });
  if (estado.persona) q.set("persona", estado.persona);
  return `api/evaluaciones.${ext}?${q}`;
}

// ------------------------------------------------------------ detalle

const GRUPOS = {
  cuestionario: ["Cuestionario", [["kss", "KSS (1 a 9)"], ["kss_texto", "Somnolencia"], ["horas_sueno", "Horas de sueño"]]],
  pvt: ["Reacción (PVT-B)", [["rt_mediana_ms", "Mediana (ms)"], ["rt_media_ms", "Media (ms)"], ["lapsos", "Lapsos"],
    ["anticipadas", "Anticipadas"], ["n_estimulos", "Estímulos"], ["modo_demo", "Modo demo"]]],
  dsst: ["Símbolos (DSST)", [["correctas", "Correctas"], ["incorrectas", "Incorrectas"], ["por_minuto", "Por minuto"]]],
  vision: ["Cámara", [["perclos", "PERCLOS"], ["parpadeos_min", "Parpadeos/min"], ["bostezos", "Bostezos"],
    ["pulso_rppg_lpm", "Pulso rPPG (lpm)"], ["calidad_rppg", "Calidad rPPG"], ["lentes", "Con lentes"]]],
  voz: ["Voz", [["estado_voz", "Estado"], ["indice_cansancio", "Índice de cansancio"], ["motivos_voz", "Motivos"]]],
};

function valor(v) {
  if (v === null || v === undefined || v === "") return "–";
  if (typeof v === "boolean") return v ? "Sí" : "No";
  if (Array.isArray(v)) return v.length ? v.join("; ") : "–";
  if (typeof v === "number") return v.toLocaleString("es", { maximumFractionDigits: 2 });
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

function grupo(titulo, pares) {
  return el("div", { class: "grupo" }, el("strong", {}, titulo),
    el("dl", {}, pares.flatMap(([k, v]) => [el("dt", {}, k), el("dd", {}, valor(v))])));
}

function pintarDetalle(s) {
  const caja = document.getElementById("detalle");
  if (!s.disponible) { caja.replaceChildren(el("p", { class: "vacio" }, s.motivo)); return; }
  const ultimo = {};
  for (const m of s.mensajes) ultimo[m.tipo] = m;
  const ev = ultimo.evaluacion;
  const partes = [];
  if (ev) {
    const d = ev.datos;
    partes.push(
      el("h3", {}, nombre(ev.persona)),
      el("div", {}, chipColor(d.color), marcas({ aviso_spo2: d.aviso_spo2, provisional: d.provisional, simulado: d.simulado })),
      el("p", { class: "vacio" }, `Sesión ${s.sesion} · en la nave ${hora(ev.fecha)} · en Tierra ${hora(ev.llego)}`),
      d.accion ? el("p", {}, d.accion) : null,
      (d.motivos || []).length ? el("ul", {}, d.motivos.map((m) => el("li", {}, m))) : el("p", { class: "vacio" }, "Sin motivos."));
  } else {
    partes.push(el("p", { class: "vacio" }, `Sesión ${s.sesion}: la evaluación todavía no llegó a Tierra.`));
  }
  for (const [tipo, [titulo, campos]] of Object.entries(GRUPOS)) {
    const m = ultimo[tipo];
    if (!m) continue;
    partes.push(grupo(titulo, campos.map(([k, etiqueta]) => [etiqueta, tipo === "vision" && k === "perclos" ? pct(m.datos[k] > 1 ? m.datos[k] / 100 : m.datos[k]) : m.datos[k]])));
  }
  if (s.esp32) {
    const e = s.esp32;
    partes.push(grupo(`Sensor ESP32${e.simulado ? " (simulado)" : ""}`, [
      ["Lecturas válidas", `${e.validas} de ${e.lecturas}`], ["Pulso (lpm)", e.pulso_lpm], ["HRV RMSSD (ms)", e.hrv_rmssd_ms],
      ["SpO₂ mediana", e.spo2], ["SpO₂ mínimo", e.spo2_min]]));
  }
  caja.replaceChildren(...partes.filter(Boolean));
}

async function seleccionar(id) {
  estado.seleccion = id;
  document.querySelectorAll("#filas tr").forEach((tr) => tr.setAttribute("aria-selected", "false"));
  try {
    pintarDetalle(await pedir(`api/sesion.json?sesion=${encodeURIComponent(id)}`));
  } catch (e) {
    pintarDetalle({ disponible: false, motivo: `No se pudo leer la sesión (${e.message}).` });
  }
  actualizarEvaluaciones();
}

// ------------------------------------------------------------ ciclo

async function actualizarEvaluaciones() {
  document.getElementById("csv").href = rutaEvaluaciones("csv");
  try {
    const r = await pedir(rutaEvaluaciones("json"));
    if (r.disponible) pintarFilas(r.filas);
  } catch (e) { /* el tablero ya muestra el aviso */ }
}

async function actualizar() {
  try {
    const t = await pedir("api/tablero.json");
    if (!t.disponible) {
      aviso(t.motivo);
      const s = document.getElementById("senal");
      s.dataset.estado = "error";
      s.querySelector(".texto").textContent = "Sin base de Houston";
    } else {
      aviso("");
      pintarTablero(t);
    }
  } catch (e) {
    aviso(`No responde el servidor de Houston (${e.message}).`);
  }
  await actualizarEvaluaciones();
}

function reloj() {
  document.getElementById("reloj").textContent =
    new Date().toLocaleString("es", { dateStyle: "medium", timeStyle: "medium", hour12: false }) + " · Tierra";
}

document.getElementById("f-persona").addEventListener("change", (e) => { estado.persona = e.target.value; actualizarEvaluaciones(); });
document.getElementById("f-dias").addEventListener("change", (e) => { estado.dias = Number(e.target.value); actualizarEvaluaciones(); });

reloj();
setInterval(reloj, 1000);
actualizar();
setInterval(actualizar, CADA_MS);
