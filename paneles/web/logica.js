/* Lógica de los paneles sin pantalla ni MQTT: textos, recomendación de la tripulación y resultados PVT.
 * Funciona en el navegador (window.Logica) y en Node (require), para poder probarla:
 * paneles/pruebas_paneles.py la compara con resumen_tripulacion() del copiloto. */
(function (raiz) {
  "use strict";

  const ORDEN_COLOR = { verde: 0, amarillo: 1, rojo: 2 };
  const TAREAS_CON_EL = ["mantenimiento", "experimento", "acoplamiento", "control"];

  // PVT-B (3 minutos): lapso = 355 ms o más; anticipada = antes del estímulo o en menos de 100 ms.
  const PVT = { LAPSO_MS: 355, ANTICIPADA_MS: 100, ISI_MIN_MS: 1000, ISI_MAX_MS: 4000, SIN_RESPUESTA_MS: 30000 };

  // Escala de somnolencia de Karolinska, con redacción sin género.
  const KSS = [
    [1, "Extremadamente alerta"],
    [2, "Muy alerta"],
    [3, "Alerta"],
    [4, "Bastante alerta"],
    [5, "Ni alerta ni con sueño"],
    [6, "Algunas señales de sueño"],
    [7, "Con sueño, pero sin esfuerzo para no dormirme"],
    [8, "Con sueño y algo de esfuerzo para no dormirme"],
    [9, "Mucho sueño: gran esfuerzo para no dormirme, luchando contra el sueño"],
  ];

  function normalizar(texto) {
    return String(texto || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  }

  /** "erick" -> "Erick" (como str.capitalize de Python). */
  function nombre(persona) {
    const p = String(persona || "");
    return p ? p.charAt(0).toUpperCase() + p.slice(1).toLowerCase() : "";
  }

  /** ["Sebas"] -> "Sebas"; ["Sebas", "Ana", "Erick"] -> "Sebas, Ana y Erick". */
  function lista(items) {
    return items.length === 1 ? items[0] : items.slice(0, -1).join(", ") + " y " + items[items.length - 1];
  }

  /** "caminata espacial" -> "la caminata espacial"; "mantenimiento externo" -> "el mantenimiento externo". */
  function conArticulo(tarea) {
    tarea = String(tarea || "").trim();
    if (!tarea) return "";
    const inicio = normalizar(tarea);
    if (["el", "la", "los", "las", "un", "una"].includes(inicio.split(/\s+/)[0])) return tarea;
    return (TAREAS_CON_EL.some((t) => inicio.startsWith(t)) ? "el " : "la ") + tarea;
  }

  function puntaje(ev) {
    const v = parseFloat(ev && ev.puntaje);
    return Number.isFinite(v) ? v : 0;
  }

  /** Primero verde, luego amarillo y rojo; dentro de cada color, mayor puntaje primero (orden estable). */
  function ordenar(evaluaciones) {
    return Object.values(evaluaciones)
      .filter((e) => e && e.color in ORDEN_COLOR)
      .sort((a, b) => ORDEN_COLOR[a.color] - ORDEN_COLOR[b.color] || puntaje(b) - puntaje(a));
  }

  /** Lo mismo que resumen_tripulacion() del copiloto, sin persona activa (nadie es «tú»).
   *  Devuelve {texto, mejor, hayVerde}. */
  function recomendacion(evaluaciones, tarea) {
    const evs = ordenar(evaluaciones);
    if (!evs.length) {
      return {
        texto: "Todavía no hay evaluaciones de la tripulación. Cada persona debe hacer su evaluación " +
          "para que pueda recomendar quién hace la tarea.",
        mejor: null, hayVerde: false,
      };
    }
    const para = tarea ? " para " + conArticulo(tarea) : "";
    const [mejor, ...resto] = evs;
    const partes = [];
    if (mejor.color === "verde") {
      partes.push(`La persona más apta${para} es ${nombre(mejor.persona)}, en verde.`);
    } else {
      partes.push(`Nadie está en verde${para}. La opción menos riesgosa es ${nombre(mejor.persona)}, ` +
        `en ${mejor.color}: conviene hacerla en pareja o posponerla.`);
    }
    const grupo = (color) => {
      const nombres = resto.filter((e) => e.color === color).map((e) => nombre(e.persona));
      return [nombres, nombres.length > 1 ? "están" : "está"];
    };
    const [verdes, verboVerde] = grupo("verde");
    if (verdes.length) partes.push(`También ${verboVerde} en verde ${lista(verdes)}.`);
    const grupos = [];
    for (const color of ["amarillo", "rojo"]) {
      const [nombres, verbo] = grupo(color);
      if (nombres.length) grupos.push([nombres, `${lista(nombres)} ${verbo} en ${color}`]);
    }
    if (grupos.length) {
      const separador = grupos.some(([n]) => n.length > 1) ? ", y " : " y ";
      const texto = grupos.map(([, frase]) => frase).join(separador);
      partes.push(texto.charAt(0).toUpperCase() + texto.slice(1) + ".");
    }
    if (evs.length === 1) partes.push("Solo tengo la evaluación de una persona; faltan las demás.");
    return { texto: partes.join(" "), mejor, hayVerde: mejor.color === "verde" };
  }

  /** Cómo cuenta una respuesta con tiempo de reacción rt (ms) después del estímulo. */
  function clasificarRespuesta(rt) {
    if (rt < PVT.ANTICIPADA_MS) return "anticipada";
    return rt >= PVT.LAPSO_MS ? "lapso" : "valida";
  }

  /** Resultado de la PVT. rts: tiempos de reacción de 100 ms o más (con los lapsos);
   *  sinRespuesta: estímulos sin respuesta en 30 s, que cuentan como lapsos pero no entran en los promedios. */
  function resumenPvt(rts, anticipadas, sinRespuesta, nEstimulos, duracionMs) {
    const v = rts.slice().sort((a, b) => a - b);
    const n = v.length;
    const media = n ? v.reduce((s, x) => s + x, 0) / n : null;
    const mediana = n ? (n % 2 ? v[(n - 1) / 2] : (v[n / 2 - 1] + v[n / 2]) / 2) : null;
    return {
      rt_media_ms: media === null ? null : Math.round(media),
      rt_mediana_ms: mediana === null ? null : Math.round(mediana),
      lapsos: v.filter((x) => x >= PVT.LAPSO_MS).length + sinRespuesta,
      anticipadas,
      n_estimulos: nEstimulos,
      duracion_s: Math.round(duracionMs / 100) / 10,
    };
  }

  /** "2026-11-13T19:30:05" (hora local, como ahora_iso() de Python) -> milisegundos; NaN si no se entiende. */
  function tsAMs(ts) {
    return ts ? Date.parse(ts) : NaN;
  }

  function dosDigitos(n) {
    return String(n).padStart(2, "0");
  }

  /** Date o milisegundos -> "19:30:05". */
  function hora(ms) {
    const d = new Date(ms);
    return Number.isNaN(d.getTime()) ? "--:--:--"
      : `${dosDigitos(d.getHours())}:${dosDigitos(d.getMinutes())}:${dosDigitos(d.getSeconds())}`;
  }

  /** Hora local en el formato de ahora_iso() de Python: "2026-11-13T19:30:05". */
  function ahoraIso(ms) {
    const d = ms === undefined ? new Date() : new Date(ms);
    return `${d.getFullYear()}-${dosDigitos(d.getMonth() + 1)}-${dosDigitos(d.getDate())}T${hora(d)}`;
  }

  /** 0.62 -> "0,62". */
  function decimal(x, cifras) {
    const v = parseFloat(x);
    return Number.isFinite(v) ? v.toFixed(cifras === undefined ? 2 : cifras).replace(".", ",") : "–";
  }

  const Logica = {
    ORDEN_COLOR, PVT, KSS, normalizar, nombre, lista, conArticulo, puntaje, ordenar, recomendacion,
    clasificarRespuesta, resumenPvt, tsAMs, hora, ahoraIso, decimal,
  };
  if (typeof module !== "undefined" && module.exports) module.exports = Logica;
  else raiz.Logica = Logica;
})(typeof window !== "undefined" ? window : globalThis);
