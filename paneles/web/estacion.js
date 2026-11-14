/* Estación de evaluación (laptop de Bri): inicio, dispositivo, cámara, voz, reacción (PVT-B), símbolos (DSST,
 * opcional), cuestionario y resultado. Cada módulo de Python avisa si está abierto (apto/control/modulos/+):
 * si falta uno, la estación lo dice en vez de esperar.
 * Atajo para probar una pantalla: estacion.html?paso=reaccion&persona=bri (&demo=1, &dsst=1). */
(function () {
  "use strict";

  const { CFG, el, etiquetaSimulado, etiquetaProvisional, palabraColor } = Comun;
  const L = Logica;
  const $ = (id) => document.getElementById(id);

  const TAREAS = ["caminata espacial", "maniobra de acoplamiento", "mantenimiento externo"];
  const PASOS = ["inicio", "dispositivo", "camara", "voz", "reaccion", "simbolos", "cuestionario", "resultado"];
  const SEGUNDOS_CAMARA = 60;
  const SEGUNDOS_VOZ = 12;
  const PREPARACION_VOZ_S = 3;        // voz_fatiga.py cuenta 3, 2, 1 antes de grabar
  const ESPERA_MODULO_VOZ_MS = 6000;  // abierto pero sin responder a la orden
  const AVISO_ESP32_MS = 10000;
  const PISTA_ANALIZANDO_MS = 25000;
  const ESPERA_COPILOTO_MS = 90000;   // la primera respuesta del modelo puede tardar un minuto
  // [nombre en apto/control/modulos/, nombre en pantalla, cómo se abre]
  const MODULOS = [
    ["voz", "Voz", "python voz\\voz_fatiga.py --servicio"],
    ["copiloto", "Copiloto", "python copiloto\\copiloto.py"],
    ["vision", "Visión", "módulo de visión (Erick)"],
    ["coordinador", "Coordinador", "python coordinador\\coordinador_provisional.py"],
    ["esp32", "ESP32", "enciendan la placa (firmware\\apto_esp32) en la misma red"],
  ];
  const COMANDO = Object.fromEntries(MODULOS.map(([m, , c]) => [m, c]));
  const modulos = {};  // nombre -> true si avisó que está activo
  const activo = (m) => modulos[m] === true;

  const estado = {
    paso: "inicio", persona: "", tarea: "", lineaBase: false, demo: false, conDsst: false, sesion: "", inicio: 0,
    esp32: null, esp32Llegada: 0, vision: null, estadoVision: "", voz: null, evaluacion: null,
    conversacion: [], pendientes: [], kss: null, horas: 7, pistaVencida: false, fraseVoz: "estandar", escuchando: false,
  };
  const temporizadores = new Set();  // se limpian al cambiar de paso

  function despues(ms, fn) {
    const id = setTimeout(() => { temporizadores.delete(id); fn(); }, ms);
    temporizadores.add(id);
    return id;
  }
  function cadaTanto(ms, fn) {
    const id = setInterval(fn, ms);
    temporizadores.add(id);
    return id;
  }
  function parar(id) {
    clearInterval(id);
    temporizadores.delete(id);
  }
  function limpiarTemporizadores() {
    for (const id of temporizadores) { clearTimeout(id); clearInterval(id); }
    temporizadores.clear();
  }

  // ------------------------------------------------------------ MQTT
  const mqttc = Comun.conectar("estacion", [
    "apto/+/esp32", "apto/+/vision", "apto/+/voz", "apto/+/evaluacion", "apto/+/copiloto",
    "apto/control/estado_voz", "apto/control/estado_vision", "apto/control/estado_escucha", "apto/control/modulos/+",
  ], alMensaje);

  function publicar(tema, datos, retener) {
    return mqttc.publicar(tema, { persona: estado.persona, sesion: estado.sesion, ...datos }, retener);
  }

  /** Un mensaje retenido (guardado en el broker) solo cuenta si es de esta sesión o posterior a su inicio. */
  function esDeEstaSesion(datos, retenido) {
    if (!retenido) return true;
    if (datos.sesion && datos.sesion === estado.sesion) return true;
    return L.tsAMs(datos.ts) >= estado.inicio - 2000;
  }

  function alMensaje(tema, datos, retenido) {
    if (tema.startsWith("apto/control/modulos/")) {
      modulos[tema.split("/")[3]] = datos.activo === true;
      alCambiarModulos();
      return;
    }
    const deLaPersona = estado.sesion && datos.persona === estado.persona;
    if (tema === "apto/control/estado_voz") { if (deLaPersona) alEstadoVoz(datos); return; }
    if (tema === "apto/control/estado_escucha") { if (deLaPersona) alEstadoEscucha(datos); return; }
    // {"estado": "midiendo", "segundos_restantes"} / "lentes" + "mensaje" / "listo" / "error" + "motivo"
    if (tema === "apto/control/estado_vision") {
      if (deLaPersona) {
        estado.estadoVision = String(datos.estado || "");
        estado.visionRestantes = datos.segundos_restantes;
        estado.visionMotivo = datos.motivo || "";
        estado.visionMensaje = datos.mensaje || "";
        pintarCamara();
      }
      return;
    }
    const [persona, tipo] = Comun.partesTema(tema);
    if (!estado.sesion || persona !== estado.persona || !esDeEstaSesion(datos, retenido)) return;
    if (tipo === "esp32") { estado.esp32 = datos; estado.esp32Llegada = Date.now(); pintarEsp32(); }
    else if (tipo === "vision") { estado.vision = datos; pintarCamara(); }
    else if (tipo === "voz") { estado.voz = datos; alResultadoVoz(); }
    else if (tipo === "evaluacion") { estado.evaluacion = datos; pintarResultado(); }
    else if (tipo === "copiloto") { agregarConversacion(datos); }
  }

  function alCambiarModulos() {
    pintarModulos();
    if (estado.paso === "camara") pintarCamara();
    if (estado.paso === "voz") pintarVozModulo();
    if (estado.paso === "resultado") { pintarResultado(); pintarCopiloto(); }
  }

  // ------------------------------------------------------------ pasos
  const entrar = {
    inicio: entrarInicio, dispositivo: entrarDispositivo, camara: entrarCamara, voz: entrarVoz, reaccion: entrarPvt,
    simbolos: entrarDsst, cuestionario: entrarCuestionario, resultado: entrarResultado,
  };

  function pasosActivos() {
    return PASOS.filter((p) => p !== "simbolos" || estado.conDsst);
  }
  function siguiente() {
    const activos = pasosActivos();
    irA(activos[Math.min(activos.indexOf(estado.paso) + 1, activos.length - 1)]);
  }

  function irA(paso) {
    limpiarTemporizadores();
    pvtDetener();
    dsstDetener();
    estado.paso = paso;
    document.querySelectorAll(".paso").forEach((s) => { s.hidden = s.dataset.paso !== paso; });
    pintarPasos();
    pintarInfoSesion();
    entrar[paso]();
    window.scrollTo(0, 0);
  }

  function pintarPasos() {
    const activos = pasosActivos();
    const actual = activos.indexOf(estado.paso);
    document.querySelectorAll("#pasos li").forEach((li) => {
      const i = activos.indexOf(li.dataset.paso);
      li.hidden = i < 0;
      li.querySelector(".numero-paso").textContent = i < 0 ? "" : i;
      li.classList.toggle("actual", i === actual);
      li.classList.toggle("hecho", i >= 0 && i < actual);
    });
  }

  function pintarInfoSesion() {
    const partes = [L.nombre(estado.persona), estado.tarea, estado.lineaBase && "línea base", estado.demo && "modo demo"];
    $("info-sesion").textContent = estado.sesion ? partes.filter(Boolean).join(" · ") : "";
  }

  // Inicio -----------------------------------------------------
  function entrarInicio() {
    Object.assign(estado, {
      persona: "", tarea: "", lineaBase: false, sesion: "", inicio: 0, esp32: null, esp32Llegada: 0, vision: null,
      estadoVision: "", voz: null, evaluacion: null, conversacion: [], pendientes: [], kss: null, horas: 7,
      pistaVencida: false, fraseVoz: "estandar", escuchando: false,
    });
    $("linea-base").checked = false;  // modo demo y símbolos se quedan como estaban
    estado.conDsst = $("con-dsst").checked;
    pintarPasos();
    pintarInfoSesion();
    pintarOpciones();
    pintarModulos();
  }

  function pintarModulos() {
    $("lista-modulos").replaceChildren(...MODULOS.map(([m, nombre, comando]) => el("li", { class: activo(m) ? "activo" : "inactivo" },
      el("span", { class: "punto" }),
      el("span", {}, el("b", {}, nombre), activo(m) ? " activo" : " no está abierto", activo(m) ? null : el("small", {}, comando)))));
  }

  function pintarOpciones() {
    const personas = CFG.tripulacion && CFG.tripulacion.length ? CFG.tripulacion : [];
    $("personas").replaceChildren(...(personas.length ? personas.map((p) => el("button", {
      class: "opcion", type: "button", "aria-pressed": String(estado.persona === p),
      onclick: () => { estado.persona = p; pintarOpciones(); },
    }, L.nombre(p))) : [el("p", { class: "estado" }, "No hay TRIPULACION en config.env.")]));
    $("tareas").replaceChildren(...TAREAS.map((t) => el("button", {
      class: "opcion", type: "button", "aria-pressed": String(estado.tarea === t),
      onclick: () => { estado.tarea = t; pintarOpciones(); },
    }, t.charAt(0).toUpperCase() + t.slice(1))));
    $("comenzar").disabled = !(estado.persona && estado.tarea);
  }

  function marcaSesion() {
    return L.ahoraIso().replace(/[-:]/g, "").replace("T", "-");  // 20261113-193005
  }

  $("con-dsst").addEventListener("change", () => { estado.conDsst = $("con-dsst").checked; pintarPasos(); });

  $("comenzar").addEventListener("click", () => {
    estado.lineaBase = $("linea-base").checked;
    estado.demo = $("modo-demo").checked;
    estado.conDsst = $("con-dsst").checked;
    estado.sesion = `${marcaSesion()}-${estado.persona}`;
    estado.inicio = Date.now();
    publicar("apto/control/sesion", { tarea: estado.tarea }, true);  // con retain: el ESP32 la sabe aunque se reinicie
    Comun.pantallaCompleta(true);
    irA("dispositivo");
  });

  // Dispositivo (ESP32: no es un módulo de Python; se sabe que está solo si llegan datos) --------
  function entrarDispositivo() {
    const llegada = Date.now();
    pintarEsp32();
    cadaTanto(1000, () => pintarEsp32(Date.now() - llegada >= AVISO_ESP32_MS));
  }

  function pintarEsp32(tarde) {
    if (estado.paso !== "dispositivo") return;
    const d = estado.esp32;
    $("v-pulso").textContent = d && d.pulso_lpm != null ? Math.round(d.pulso_lpm) : "–";
    $("v-hrv").textContent = d && d.hrv_rmssd_ms != null ? Math.round(d.hrv_rmssd_ms) : "–";
    $("v-spo2").textContent = d && d.spo2 != null ? L.decimal(d.spo2, 1) : "–";
    $("sim-esp32").replaceChildren(...[etiquetaSimulado(d)].filter(Boolean));
    if (!d) {
      $("estado-esp32").textContent = !activo("esp32") && tarde
        ? "El ESP32 no está conectado al broker. Revisen que esté encendido y en la misma red, o toquen Omitir."
        : tarde
          ? "No llegan datos del dispositivo. Revisen que el ESP32 esté encendido y conectado a la misma red, o toquen Omitir."
          : "Esperando el dispositivo...";
    } else {
      const s = Math.round((Date.now() - estado.esp32Llegada) / 1000);
      if (s > 3) $("estado-esp32").textContent = `Sin datos nuevos desde hace ${s} s.`;
      else if (d.dedo === false) $("estado-esp32").textContent = "Coloca el dedo en el sensor y quédate sin moverte.";
      else if (d.pulso_lpm == null) $("estado-esp32").textContent = "Dedo detectado: midiendo el pulso (unos segundos)…";
      else {
        const calidad = d.calidad != null ? ` · calidad ${L.decimal(d.calidad)}` : "";
        const mov = d.movimiento != null && d.movimiento > 0.05 ? " · hay movimiento: quédate quieto" : "";
        $("estado-esp32").textContent = `Datos en vivo${calidad}${mov}.`;
      }
    }
    $("continuar-dispositivo").disabled = !d || d.dedo === false;
  }
  $("continuar-dispositivo").addEventListener("click", siguiente);
  $("omitir-dispositivo").addEventListener("click", siguiente);

  // Cámara (la mide el módulo de visión; la estación no abre la cámara) -------------------------
  let camaraIniciada = false;

  function entrarCamara() {
    estado.vision = null;
    estado.estadoVision = "";
    estado.visionRestantes = null;
    estado.visionMotivo = "";
    camaraIniciada = false;
    $("continuar-camara").hidden = true;
    pintarCamara();
  }

  function iniciarCamara() {
    camaraIniciada = true;
    publicar("apto/control/orden_vision", { accion: "medir", segundos: SEGUNDOS_CAMARA });
    const inicio = Date.now();
    $("cuenta-camara").hidden = false;
    $("progreso-camara-caja").hidden = false;
    const tic = () => {
      const pasado = (Date.now() - inicio) / 1000;
      const quedan = Math.max(0, Math.ceil(SEGUNDOS_CAMARA - pasado));
      $("cuenta-camara").textContent = quedan;
      $("progreso-camara").style.width = `${Math.min(100, (pasado / SEGUNDOS_CAMARA) * 100)}%`;
      if (quedan === 0) {
        parar(reloj);
        $("continuar-camara").hidden = false;
        pintarCamara();
      }
    };
    const reloj = cadaTanto(250, tic);
    tic();
  }

  const NOMBRES_VISION = {
    pulso_rppg_lpm: ["Pulso (cámara)", "lpm", 0], calidad_rppg: ["Calidad del pulso", "de 0 a 1", 2],
    perclos: ["PERCLOS", "fracción de tiempo con los ojos cerrados", 2], parpadeos_min: ["Parpadeos", "por minuto", 1],
    ear_abierto: ["EAR ojo abierto", "", 2], bostezos: ["Bostezos", "en la medición", 0],
    bostezos_tapados: ["Bostezos tapados", "con la mano (ya incluidos)", 0],
    cara_detectada_pct: ["Cara detectada", "% del tiempo", 0],
    fps: ["Cuadros por segundo", "", 0], pulso_lpm: ["Pulso (cámara)", "lpm", 0],
  };
  const NO_MOSTRAR = new Set(["persona", "sesion", "ts", "fuente", "simulado", "linea_base", "duracion_s", "reproducido",
    "ts_original", "snr_rppg_db", "parpadeos", "brillo_piel", "bostezos_min"]);

  function pintarCamara() {
    if (estado.paso !== "camara") return;
    if (!camaraIniciada && activo("vision")) iniciarCamara();
    const d = estado.vision;
    $("sim-vision").replaceChildren(...[etiquetaSimulado(d)].filter(Boolean));
    let texto;
    if (!camaraIniciada) {
      texto = "El módulo de visión no está abierto. Pueden seguir sin la cámara (Omitir).";
      $("cuenta-camara").hidden = true;
      $("progreso-camara-caja").hidden = true;
    } else if (d) {
      texto = "Datos de la cámara recibidos.";
    } else if (estado.estadoVision === "error") {
      texto = `La medición con la cámara falló: ${estado.visionMotivo || "sin motivo"}. Pueden seguir sin ella.`;
      $("continuar-camara").hidden = false;
    } else if (!activo("vision")) {
      texto = "El módulo de visión se cerró: no llegaron datos de la cámara.";
    } else if (estado.estadoVision === "listo") {
      texto = "La medición terminó, pero no llegaron datos.";
    } else if (estado.estadoVision === "lentes") {  // la medición espera a que se quiten los lentes
      texto = estado.visionMensaje || "Se ven lentes: quítatelos para continuar con la medición.";
    } else if (estado.estadoVision === "midiendo") {
      const quedan = Number(estado.visionRestantes);
      texto = estado.visionRestantes != null && Number.isFinite(quedan) ? `Midiendo… quedan ${Math.round(quedan)} s.` : "Midiendo…";
    } else {
      texto = estado.estadoVision || "Esperando al módulo de visión…";
    }
    $("estado-camara").textContent = texto;
    $("estado-camara").classList.toggle("aviso-camara", !d && estado.estadoVision === "lentes");
    if (!d) { $("datos-vision").replaceChildren(); return; }
    if (Array.isArray(d.avisos) && d.avisos.length) {  // avisos de calidad del módulo (luz, cara, fps, pulso dudoso)
      $("estado-camara").replaceChildren(texto, el("ul", { class: "avisos-vision" }, d.avisos.map((a) => el("li", {}, a))));
    }
    const filas = Object.entries(d).filter(([k, v]) => !NO_MOSTRAR.has(k) && (typeof v === "number" || typeof v === "string"));
    $("datos-vision").replaceChildren(...filas.map(([k, v]) => {
      const [nombre, unidad, cifras] = NOMBRES_VISION[k] || [k.replace(/_/g, " "), "", 2];
      const valor = typeof v === "number" ? (cifras === 0 ? Math.round(v) : L.decimal(v, cifras)) : v;
      return el("div", { class: "medida panel" }, el("span", { class: "etiqueta" }, nombre),
        el("span", { class: "valor" }, valor), el("span", { class: "unidad" }, unidad));
    }));
  }
  $("continuar-camara").addEventListener("click", siguiente);
  $("omitir-camara").addEventListener("click", siguiente);

  // Voz --------------------------------------------------------
  let vozFase = "inicio";  // inicio, esperando, grabando, analizando, listo

  /** Frases para elegir (la estándar y, como opción, variaciones hasta un trabalenguas), desde config.js. */
  function frasesVoz() {
    return CFG.frases_voz && Object.keys(CFG.frases_voz).length
      ? CFG.frases_voz : { estandar: { titulo: "Frase estándar", texto: CFG.frase_voz || "" } };
  }

  function pintarFrases() {
    const frases = frasesVoz();
    if (!frases[estado.fraseVoz]) estado.fraseVoz = "estandar";
    const ocupado = ["esperando", "grabando", "analizando"].includes(vozFase);
    $("frases-voz").replaceChildren(...Object.entries(frases).map(([id, f]) => el("button", {
      class: "opcion", type: "button", "aria-pressed": String(estado.fraseVoz === id), disabled: ocupado,
      onclick: () => { estado.fraseVoz = id; pintarFrases(); },
    }, f.titulo)));
    $("frases-voz").hidden = Object.keys(frases).length < 2;
    $("frase-voz").textContent = frases[estado.fraseVoz].texto || "(Falta la frase: revisen voz/voz_fatiga.py)";
    $("nota-frase").textContent = estado.fraseVoz === "estandar"
      ? "La frase de siempre: se compara con tu línea base."
      : estado.fraseVoz === "trabalenguas"
        ? "La más difícil: léela clara y sin apurarte. Tiene su propia línea base."
        : "Tiene su propia línea base: se compara solo con mediciones de esta misma frase.";
  }

  function entrarVoz() {
    pintarFrases();
    vozFase = "inicio";
    estado.voz = null;
    $("resultado-voz").hidden = true;
    $("progreso-voz-caja").hidden = true;
    $("grabar").hidden = false;
    $("grabar").textContent = `Grabar (${SEGUNDOS_VOZ} s)`;
    $("continuar-voz").hidden = true;
    pintarVozModulo();
  }

  function pintarVozModulo() {
    if (estado.paso !== "voz") return;
    if (!activo("voz")) {
      if (["esperando", "grabando", "analizando"].includes(vozFase)) {
        limpiarTemporizadores();
        vozFase = "inicio";
        $("progreso-voz-caja").hidden = true;
      }
      if (vozFase === "inicio") {
        $("estado-voz").replaceChildren("El módulo de voz no está abierto. Ábranlo con ",
          el("kbd", {}, COMANDO.voz), " o toquen Omitir.");
      }
      $("grabar").disabled = true;
      return;
    }
    if (vozFase === "inicio") {
      $("estado-voz").textContent = "Presiona Grabar cuando quieras empezar.";
      $("grabar").disabled = false;
    }
  }

  $("grabar").addEventListener("click", () => {
    if (!activo("voz")) return;
    vozFase = "esperando";
    estado.voz = null;
    $("resultado-voz").hidden = true;
    $("continuar-voz").hidden = true;
    $("grabar").disabled = true;
    $("estado-voz").textContent = "Preparando la grabación…";
    publicar("apto/control/orden_voz", {
      accion: "grabar", segundos: SEGUNDOS_VOZ, linea_base: estado.lineaBase, frase: estado.fraseVoz,
    });
    pintarFrases();  // no se cambia la frase mientras se graba
    despues(ESPERA_MODULO_VOZ_MS, () => {
      if (vozFase !== "esperando") return;
      vozFase = "inicio";
      $("estado-voz").textContent = "El módulo de voz está abierto pero no respondió. Revisen su ventana y vuelvan a intentar.";
      $("grabar").disabled = false;
      $("grabar").textContent = "Reintentar";
    });
  });

  function alEstadoVoz(datos) {
    if (estado.paso !== "voz") return;
    if (datos.estado === "grabando" && vozFase === "esperando") {
      vozFase = "grabando";
      const inicio = Date.now();
      $("progreso-voz-caja").hidden = false;
      const tic = () => {
        const s = (Date.now() - inicio) / 1000;
        if (s < PREPARACION_VOZ_S) {
          $("estado-voz").textContent = `Empieza en ${Math.ceil(PREPARACION_VOZ_S - s)}…`;
          $("progreso-voz").style.width = "0%";
        } else if (s < PREPARACION_VOZ_S + SEGUNDOS_VOZ) {
          const quedan = Math.ceil(PREPARACION_VOZ_S + SEGUNDOS_VOZ - s);
          $("estado-voz").textContent = `Grabando: lee la frase en voz alta (${quedan} s)`;
          $("progreso-voz").style.width = `${((s - PREPARACION_VOZ_S) / SEGUNDOS_VOZ) * 100}%`;
        } else if (vozFase === "grabando") {
          vozFase = "analizando";
          $("progreso-voz").style.width = "100%";
          $("estado-voz").textContent = "Analizando la voz…";
        }
      };
      tic();
      cadaTanto(200, tic);
    } else if (datos.estado === "listo" && vozFase !== "listo" && vozFase !== "inicio") {
      despues(1500, () => { if (vozFase !== "listo") terminarVoz(); });
    }
  }

  function alResultadoVoz() {
    if (estado.paso === "voz" && vozFase !== "inicio") terminarVoz();
  }

  function terminarVoz() {
    vozFase = "listo";
    limpiarTemporizadores();
    $("progreso-voz-caja").hidden = true;
    const d = estado.voz;
    const caja = $("resultado-voz");
    if (!d) {
      $("estado-voz").textContent = "Listo.";
      caja.hidden = true;
    } else if (d.aviso || d.voz_detectada === false) {
      $("estado-voz").textContent = d.aviso || "No se detectó voz en la grabación.";
      caja.hidden = true;
    } else {
      $("estado-voz").textContent = "Listo.";
      const explicacion = {
        "sin línea base": "Todavía no hay línea base: hacen falta 3 mediciones marcadas como línea base.",
        "sin voz detectada": "No se detectó voz en la grabación.",
      }[d.estado_voz];
      const frase = frasesVoz()[d.frase_id || "estandar"];
      caja.replaceChildren(...[  // replaceChildren escribiría "null": se filtran las partes vacías
        el("span", { class: "etiqueta" }, `Voz comparada con la línea base · ${frase ? frase.titulo : "Frase estándar"}`,
          etiquetaSimulado(d)),
        el("p", { class: "grande" }, d.estado_voz ? d.estado_voz.charAt(0).toUpperCase() + d.estado_voz.slice(1) : "Sin comparación"),
        explicacion ? el("p", { class: "estado" }, explicacion) : null,
        d.motivos_voz && d.motivos_voz.length ? el("ul", {}, d.motivos_voz.map((m) => el("li", {}, m))) : null,
        el("p", { class: "estado" }, "Es una sugerencia, no un diagnóstico."),
      ].filter(Boolean));
      caja.hidden = false;
    }
    $("grabar").disabled = !activo("voz");
    $("grabar").textContent = "Grabar otra vez";
    $("continuar-voz").hidden = false;
    pintarFrases();
  }
  $("continuar-voz").addEventListener("click", siguiente);
  $("omitir-voz").addEventListener("click", siguiente);

  // Reacción (PVT-B) -------------------------------------------
  const pvt = {
    activo: false, inicio: 0, duracionMs: 0, estimuloEn: null, rts: [], anticipadas: 0, sinRespuesta: 0, n: 0,
    espera: null, sinResp: null, raf: null, reloj: null, borrar: null,
  };

  function segundosPvt() {
    if (estado.demo) return L.PVT.DEMO_S;
    const s = Number(CFG.pvt_segundos);
    return Number.isFinite(s) && s > 0 ? s : 180;
  }

  function entrarPvt() {
    const s = segundosPvt();
    const texto = s % 60 === 0 ? `${s / 60} ${s === 60 ? "minuto" : "minutos"}` : `${s} segundos`;
    $("pvt-duracion").textContent = estado.demo ? `${texto} (modo demo)` : texto;
    $("pvt-intro").hidden = false;
    $("pvt-area").hidden = true;
    $("pvt-fin").hidden = true;
  }

  function pvtDetener() {
    pvt.activo = false;
    clearTimeout(pvt.espera); clearTimeout(pvt.sinResp); clearTimeout(pvt.borrar); clearInterval(pvt.reloj);
    cancelAnimationFrame(pvt.raf);
    pvt.estimuloEn = null;
  }

  $("pvt-empezar").addEventListener("click", () => {
    Object.assign(pvt, { inicio: performance.now(), duracionMs: segundosPvt() * 1000, rts: [], anticipadas: 0, sinRespuesta: 0, n: 0, estimuloEn: null });
    pvt.activo = true;
    $("pvt-intro").hidden = true;
    $("pvt-fin").hidden = true;
    $("pvt-area").hidden = false;
    $("pvt-contador").textContent = "";
    $("pvt-contador").className = "pvt-contador";
    $("pvt-mensaje").textContent = "Prepárate…";
    if (document.activeElement) document.activeElement.blur();  // que la barra espaciadora no apriete un botón
    pvtReloj();
    pvt.reloj = setInterval(pvtReloj, 250);
    pvtProgramar();
  });

  function pvtReloj() {
    const quedan = Math.max(0, Math.ceil((pvt.duracionMs - (performance.now() - pvt.inicio)) / 1000));
    $("pvt-restante").textContent = `Quedan ${Math.floor(quedan / 60)}:${String(quedan % 60).padStart(2, "0")}`;
  }

  /** Espera aleatoria de 1 a 4 s; si se acaba el tiempo antes, termina la prueba. */
  function pvtProgramar() {
    clearTimeout(pvt.espera);
    cancelAnimationFrame(pvt.raf);  // un estímulo a punto de aparecer ya no aparece
    const isi = L.PVT.ISI_MIN_MS + Math.random() * (L.PVT.ISI_MAX_MS - L.PVT.ISI_MIN_MS);
    const restante = pvt.duracionMs - (performance.now() - pvt.inicio);
    if (restante <= 0) { pvtTerminar(); return; }
    pvt.espera = setTimeout(() => {
      if (performance.now() - pvt.inicio >= pvt.duracionMs) pvtTerminar();
      else pvtEstimulo();
    }, Math.min(isi, restante));
  }

  function pvtEstimulo() {
    pvt.raf = requestAnimationFrame(() => {
      if (!pvt.activo) return;
      clearTimeout(pvt.borrar);
      pvt.n += 1;
      pvt.estimuloEn = performance.now();  // el contador aparece en este cuadro
      $("pvt-mensaje").textContent = "";
      const contador = $("pvt-contador");
      contador.className = "pvt-contador";
      contador.textContent = "0";
      const animar = () => {
        if (pvt.estimuloEn === null) return;
        contador.textContent = Math.floor(performance.now() - pvt.estimuloEn);
        pvt.raf = requestAnimationFrame(animar);
      };
      pvt.raf = requestAnimationFrame(animar);
      pvt.sinResp = setTimeout(() => {  // 30 s sin respuesta: cuenta como lapso
        if (pvt.estimuloEn === null) return;
        pvt.estimuloEn = null;
        pvt.sinRespuesta += 1;
        contador.textContent = "";
        $("pvt-mensaje").textContent = "Sin respuesta.";
        pvtProgramar();
      }, L.PVT.SIN_RESPUESTA_MS);
    });
  }

  function pvtResponder(tiempo) {
    if (!pvt.activo) return;
    const contador = $("pvt-contador");
    if (pvt.estimuloEn === null) {  // antes del estímulo: anticipada, y se vuelve a esperar
      pvt.anticipadas += 1;
      $("pvt-mensaje").textContent = "¡Muy pronto! Espera al contador.";
      pvtProgramar();
      return;
    }
    const rt = tiempo - pvt.estimuloEn;
    pvt.estimuloEn = null;
    clearTimeout(pvt.sinResp);
    cancelAnimationFrame(pvt.raf);
    const tipo = L.clasificarRespuesta(rt);
    if (tipo === "anticipada") {
      pvt.anticipadas += 1;
      contador.textContent = "";
      $("pvt-mensaje").textContent = "¡Muy pronto! Espera al contador.";
    } else {
      pvt.rts.push(rt);
      contador.textContent = Math.round(rt);
      contador.className = `pvt-contador respuesta${tipo === "lapso" ? " lapso" : ""}`;
      pvt.borrar = setTimeout(() => { if (pvt.estimuloEn === null) contador.textContent = ""; }, 800);
    }
    pvtProgramar();
  }

  function tiempoDelEvento(e) {
    // timeStamp del evento (misma base que performance.now) es más exacto; si no sirve, la hora actual
    const ahora = performance.now();
    return e && e.timeStamp > 0 && Math.abs(ahora - e.timeStamp) < 1000 ? e.timeStamp : ahora;
  }

  $("pvt-area").addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;  // solo el botón principal o un toque
    e.preventDefault();
    pvtResponder(tiempoDelEvento(e));
  });

  function pvtTerminar() {
    const duracionMs = performance.now() - pvt.inicio;
    pvtDetener();
    const r = L.resumenPvt(pvt.rts, pvt.anticipadas, pvt.sinRespuesta, pvt.n, duracionMs);
    publicar(`apto/${estado.persona}/pvt`, { ...r, linea_base: estado.lineaBase, modo_demo: estado.demo });
    $("pvt-area").hidden = true;
    $("pvt-fin").hidden = false;
    $("pvt-media").textContent = r.rt_media_ms ?? "–";
    $("pvt-mediana").textContent = r.rt_mediana_ms ?? "–";
    $("pvt-lapsos").textContent = r.lapsos;
    $("pvt-lapsos-min").textContent = `${L.decimal(r.lapsos_por_min)} por minuto (355 ms o más)`;
    $("pvt-anticipadas").textContent = r.anticipadas;
    $("pvt-estimulos").textContent = `de ${r.n_estimulos} estímulos`;
  }
  $("continuar-reaccion").addEventListener("click", siguiente);
  $("omitir-reaccion").addEventListener("click", siguiente);

  // Símbolos (DSST) --------------------------------------------
  const dsst = { activo: false, inicio: 0, clave: [], actual: 0, correctas: 0, incorrectas: 0, fin: null, reloj: null };

  function svgSimbolo(i) {
    const ns = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(ns, "svg");
    svg.setAttribute("viewBox", "0 0 40 40");
    svg.setAttribute("aria-hidden", "true");
    const trazo = document.createElementNS(ns, "path");
    trazo.setAttribute("d", L.SIMBOLOS_DSST[i]);
    svg.append(trazo);
    return svg;
  }

  function entrarDsst() {
    $("dsst-intro").hidden = false;
    $("dsst-area").hidden = true;
    $("dsst-fin").hidden = true;
  }

  function dsstDetener() {
    dsst.activo = false;
    clearTimeout(dsst.fin);
    clearInterval(dsst.reloj);
  }

  $("dsst-empezar").addEventListener("click", () => {
    const orden = [...Array(9).keys()];
    for (let i = orden.length - 1; i > 0; i--) {  // clave al azar en cada sesión
      const j = Math.floor(Math.random() * (i + 1));
      [orden[i], orden[j]] = [orden[j], orden[i]];
    }
    Object.assign(dsst, { clave: orden, actual: 0, correctas: 0, incorrectas: 0, inicio: performance.now() });
    dsst.activo = true;
    $("dsst-clave").replaceChildren(...orden.map((s, i) => el("div", { class: "dsst-celda" }, svgSimbolo(s), el("span", {}, i + 1))));
    $("dsst-teclado").replaceChildren(...orden.map((_, i) => el("button", {
      class: "dsst-tecla", type: "button", "data-numero": i + 1, onclick: (e) => dsstResponder(i + 1, e.currentTarget),
    }, i + 1)));
    $("dsst-intro").hidden = true;
    $("dsst-fin").hidden = true;
    $("dsst-area").hidden = false;
    if (document.activeElement) document.activeElement.blur();
    dsstSiguiente();
    dsstReloj();
    dsst.reloj = setInterval(dsstReloj, 250);
    dsst.fin = setTimeout(dsstTerminar, L.DSST_SEGUNDOS * 1000);
  });

  function dsstReloj() {
    const quedan = Math.max(0, Math.ceil(L.DSST_SEGUNDOS - (performance.now() - dsst.inicio) / 1000));
    $("dsst-restante").textContent = `Quedan ${quedan} s`;
  }

  function dsstSiguiente() {
    let n;
    do { n = 1 + Math.floor(Math.random() * 9); } while (n === dsst.actual);  // nunca el mismo dos veces
    dsst.actual = n;
    $("dsst-simbolo").replaceChildren(svgSimbolo(dsst.clave[n - 1]));
  }

  function dsstResponder(n, boton) {
    if (!dsst.activo) return;
    if (n === dsst.actual) dsst.correctas += 1;
    else dsst.incorrectas += 1;
    const b = boton || document.querySelector(`.dsst-tecla[data-numero="${n}"]`);
    if (b) { b.classList.add("pulsada"); setTimeout(() => b.classList.remove("pulsada"), 120); }
    dsstSiguiente();
  }

  function dsstTerminar() {
    const duracionMs = performance.now() - dsst.inicio;
    dsstDetener();
    const r = L.resumenDsst(dsst.correctas, dsst.incorrectas, duracionMs);
    publicar(`apto/${estado.persona}/dsst`, { ...r, linea_base: estado.lineaBase });
    $("dsst-area").hidden = true;
    $("dsst-fin").hidden = false;
    $("dsst-correctas").textContent = r.correctas;
    $("dsst-incorrectas").textContent = r.incorrectas;
    $("dsst-por-minuto").textContent = L.decimal(r.por_minuto, 1);
  }
  $("continuar-simbolos").addEventListener("click", siguiente);
  $("omitir-simbolos").addEventListener("click", siguiente);

  document.addEventListener("keydown", (e) => {
    if (estado.paso === "reaccion" && pvt.activo && (e.code === "Space" || e.key === " ")) {
      e.preventDefault();
      if (!e.repeat) pvtResponder(tiempoDelEvento(e));
    } else if (estado.paso === "simbolos" && dsst.activo && /^[1-9]$/.test(e.key)) {
      e.preventDefault();
      if (!e.repeat) dsstResponder(Number(e.key));
    }
  });

  // Cuestionario -----------------------------------------------
  function entrarCuestionario() {
    pintarCuestionario();
  }

  function pintarCuestionario() {
    $("kss").replaceChildren(...L.KSS.map(([n, texto]) => el("button", {
      class: "opcion", type: "button", "aria-pressed": String(estado.kss === n),
      onclick: () => { estado.kss = n; pintarCuestionario(); },
    }, el("b", {}, n), texto)));
    $("horas").textContent = L.decimal(estado.horas, estado.horas % 1 ? 1 : 0);
    $("enviar-cuestionario").disabled = estado.kss === null;
  }
  $("horas-menos").addEventListener("click", () => { estado.horas = Math.max(0, estado.horas - 0.5); pintarCuestionario(); });
  $("horas-mas").addEventListener("click", () => { estado.horas = Math.min(16, estado.horas + 0.5); pintarCuestionario(); });
  $("enviar-cuestionario").addEventListener("click", () => {
    const texto = (L.KSS.find(([n]) => n === estado.kss) || [])[1];
    publicar(`apto/${estado.persona}/cuestionario`, {
      kss: estado.kss, kss_texto: texto, horas_sueno: estado.horas, linea_base: estado.lineaBase,
    });
    siguiente();
  });

  // Resultado --------------------------------------------------
  function entrarResultado() {
    estado.pistaVencida = false;
    pintarResultado();
    pintarCopiloto();
    despues(PISTA_ANALIZANDO_MS, () => { estado.pistaVencida = true; pintarResultado(); });
    cadaTanto(5000, pintarConversacion);  // para avisar si el copiloto no responde
  }

  function pintarResultado() {
    if (estado.paso !== "resultado") return;
    const ev = estado.evaluacion;
    $("analizando").hidden = Boolean(ev);
    $("resultado").hidden = !ev;
    if (!ev) {
      const simulador = el("kbd", {}, `python herramientas\\simulador.py --persona ${estado.persona}`);
      if (!activo("coordinador")) {
        $("giro").hidden = true;
        $("titulo-analizando").textContent = "Falta el coordinador";
        $("estado-analizando").replaceChildren("El módulo coordinador no está abierto. Ábranlo con ",
          el("kbd", {}, COMANDO.coordinador), ". Para probar sin él: ", simulador, " y luego 1, 2 o 3.");
      } else {
        $("giro").hidden = false;
        $("titulo-analizando").textContent = "Analizando...";
        $("estado-analizando").replaceChildren(...(estado.pistaVencida
          ? ["El coordinador todavía no envió el resultado. Para probar sin él: ", simulador, " y luego 1, 2 o 3."]
          : ["El coordinador está calculando tu resultado."]));
      }
      return;
    }
    const color = ["verde", "amarillo", "rojo"].includes(ev.color) ? ev.color : "";
    $("semaforo").dataset.color = color;
    $("palabra-color").textContent = palabraColor(color);
    $("etiquetas-resultado").replaceChildren(...[etiquetaProvisional(ev), etiquetaSimulado(ev)].filter(Boolean));
    $("puntaje").textContent = ev.puntaje != null ? `Puntaje ${L.decimal(ev.puntaje)} · ${L.hora(L.tsAMs(ev.ts))}` : "";
    // Aviso de SpO2: no cambia el color; va en amarillo debajo del semáforo y no se repite en los motivos.
    const esAvisoSpo2 = (m) => ev.aviso_spo2 && /^ox[ií]geno m[aá]s bajo/i.test(m);
    $("aviso-spo2").hidden = !ev.aviso_spo2;
    $("aviso-spo2").textContent = ev.aviso_spo2
      ? `⚠ ${(ev.motivos || []).find(esAvisoSpo2) || "Oxígeno más bajo de lo habitual: repetir la medición"}`
      : "";
    const propios = (ev.motivos || []).filter((m) => !esAvisoSpo2(m));
    const motivos = propios.length ? propios
      : [ev.aviso_spo2 ? "Sin motivos que cambien el color." : "Tus señales están en tu rango habitual."];
    $("motivos").replaceChildren(...motivos.map((m) => el("li", {}, m)));
    $("accion").textContent = ev.accion || "–";
  }

  function pintarCopiloto() {
    if (estado.paso !== "resultado") return;
    const abierto = activo("copiloto");
    $("estado-copiloto").hidden = abierto;
    if (!abierto) $("estado-copiloto").replaceChildren("El copiloto no está abierto. Ábranlo con ", el("kbd", {}, COMANDO.copiloto), ".");
    $("pregunta").disabled = !abierto;
    $("enviar-pregunta").disabled = !abierto;
    $("hablar").disabled = !abierto || estado.escuchando;
    $("hablar").classList.toggle("escuchando", estado.escuchando);
    pintarConversacion();
  }

  // Preguntar en voz alta: el copiloto escucha con el micrófono de la laptop, transcribe y responde.
  let escuchaVence = null;
  function mostrarEscucha(texto) {
    $("estado-escucha").hidden = !texto;
    $("estado-escucha").textContent = texto;
  }
  function terminarEscucha(texto) {
    estado.escuchando = false;
    clearTimeout(escuchaVence);
    mostrarEscucha(texto);
    pintarCopiloto();
  }
  $("hablar").addEventListener("click", () => {
    if (!estado.sesion || !activo("copiloto") || estado.escuchando) return;
    estado.escuchando = true;
    publicar("apto/control/escuchar", { segundos_max: 10 });
    mostrarEscucha("Pidiendo el micrófono al copiloto…");
    clearTimeout(escuchaVence);
    escuchaVence = setTimeout(() => { if (estado.escuchando) terminarEscucha("El copiloto no respondió al pedido de escuchar."); }, 25000);
    pintarCopiloto();
  });
  function alEstadoEscucha(d) {
    if (!estado.escuchando) return;
    if (d.estado === "escuchando") mostrarEscucha("Escuchando… habla ahora (se detiene cuando te callas).");
    else if (d.estado === "transcribiendo") mostrarEscucha("Transcribiendo…");
    else if (d.estado === "listo") {
      if (d.texto) estado.pendientes.push({ pregunta: d.texto, desde: Date.now() });
      terminarEscucha("");
    } else if (d.estado === "error") terminarEscucha(d.motivo || "No se pudo escuchar.");
  }

  function agregarConversacion(datos) {
    estado.conversacion.push(datos);
    const i = estado.pendientes.findIndex((p) => p.pregunta === datos.pregunta);
    if (i >= 0) estado.pendientes.splice(i, 1);
    pintarConversacion();
  }

  let cantidadPintada = 0;
  function pintarConversacion() {
    if (estado.paso !== "resultado") return;
    const items = estado.conversacion.map((d) => el("li", {},
      el("div", { class: "pregunta" }, d.pregunta === "(resumen automático)" ? "Resumen automático" : d.pregunta),
      el("div", { class: "respuesta" }, d.respuesta, el("div", { class: "meta" }, `${L.hora(L.tsAMs(d.ts))} · ${d.modo || ""}`)),
    ));
    for (const p of estado.pendientes) {
      const texto = !activo("copiloto") ? "El copiloto no está abierto."
        : Date.now() - p.desde > ESPERA_COPILOTO_MS ? "El copiloto no respondió. Revisen su ventana." : "El copiloto está pensando…";
      items.push(el("li", {}, el("div", { class: "pregunta" }, p.pregunta), el("div", { class: "pendiente" }, texto)));
    }
    if (!items.length) items.push(el("li", { class: "vacio" }, "Escribe una pregunta, por ejemplo: «¿Por qué salí en amarillo?»"));
    const lista = $("conversacion");
    lista.replaceChildren(...items);
    if (items.length !== cantidadPintada) lista.scrollTop = lista.scrollHeight;  // solo si hay algo nuevo
    cantidadPintada = items.length;
  }

  $("form-pregunta").addEventListener("submit", (e) => {
    e.preventDefault();
    const pregunta = $("pregunta").value.trim();
    if (!pregunta || !estado.sesion || !activo("copiloto")) return;
    publicar("apto/control/pregunta", { pregunta });
    estado.pendientes.push({ pregunta, desde: Date.now() });
    $("pregunta").value = "";
    pintarConversacion();
  });
  $("nueva").addEventListener("click", () => irA("inicio"));

  // ------------------------------------------------------------ arranque
  $("pantalla-completa").addEventListener("click", () => Comun.pantallaCompleta(!document.fullscreenElement));
  $("aviso-lectura").hidden = CFG.puede_publicar !== false;

  const params = new URLSearchParams(location.search);
  let pasoInicial = params.get("paso") || "";
  if (/^\d+$/.test(pasoInicial)) pasoInicial = PASOS[Number(pasoInicial)] || "";
  if (PASOS.includes(pasoInicial) && pasoInicial !== "inicio") {  // atajo de prueba: sin publicar la sesión
    entrarInicio();
    estado.persona = (params.get("persona") || (CFG.tripulacion || [])[0] || "bri").toLowerCase();
    estado.tarea = params.get("tarea") || TAREAS[0];
    estado.demo = params.get("demo") === "1";
    estado.conDsst = params.get("dsst") === "1" || pasoInicial === "simbolos";
    estado.sesion = `prueba-${marcaSesion()}-${estado.persona}`;
    estado.inicio = Date.now();
    irA(pasoInicial);
  } else {
    irA("inicio");
  }
})();
