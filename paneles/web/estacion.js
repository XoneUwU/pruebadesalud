/* Estación de evaluación (laptop de Bri): inicio, dispositivo, cámara, voz, PVT-B, cuestionario y resultado.
 * Atajo para probar una pantalla sin hacer todo el recorrido: estacion.html?paso=4&persona=bri */
(function () {
  "use strict";

  const { CFG, el, etiquetaSimulado, palabraColor } = Comun;
  const L = Logica;
  const $ = (id) => document.getElementById(id);

  const TAREAS = ["caminata espacial", "maniobra de acoplamiento", "mantenimiento externo"];
  const SEGUNDOS_CAMARA = 60;
  const SEGUNDOS_VOZ = 12;
  const PREPARACION_VOZ_S = 3;      // voz_fatiga.py cuenta 3, 2, 1 antes de grabar
  const ESPERA_MODULO_VOZ_MS = 6000; // si no llega "grabando" en este tiempo, el módulo de voz no está abierto
  const PISTA_ANALIZANDO_MS = 25000;

  const estado = {
    paso: 0, persona: "", tarea: "", lineaBase: false, sesion: "", inicio: 0,
    esp32: null, esp32Llegada: 0, vision: null, voz: null, evaluacion: null,
    conversacion: [], pendientes: [], kss: null, horas: 7,
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
  function limpiarTemporizadores() {
    for (const id of temporizadores) { clearTimeout(id); clearInterval(id); }
    temporizadores.clear();
  }

  // ------------------------------------------------------------ MQTT
  const mqttc = Comun.conectar("estacion", [
    "apto/+/esp32", "apto/+/vision", "apto/+/voz", "apto/+/evaluacion", "apto/+/copiloto", "apto/control/estado_voz",
  ], alMensaje);

  function publicar(tema, datos) {
    return mqttc.publicar(tema, { persona: estado.persona, sesion: estado.sesion, ...datos });
  }

  /** Un mensaje retenido (guardado en el broker) solo cuenta si es de esta sesión o posterior a su inicio. */
  function esDeEstaSesion(datos, retenido) {
    if (!retenido) return true;
    if (datos.sesion && datos.sesion === estado.sesion) return true;
    return L.tsAMs(datos.ts) >= estado.inicio - 2000;
  }

  function alMensaje(tema, datos, retenido) {
    if (tema === "apto/control/estado_voz") {
      if (estado.sesion && datos.persona === estado.persona) alEstadoVoz(datos);
      return;
    }
    const [persona, tipo] = Comun.partesTema(tema);
    if (!estado.sesion || persona !== estado.persona || !esDeEstaSesion(datos, retenido)) return;
    if (tipo === "esp32") { estado.esp32 = datos; estado.esp32Llegada = Date.now(); pintarEsp32(); }
    else if (tipo === "vision") { estado.vision = datos; pintarVision(); }
    else if (tipo === "voz") { estado.voz = datos; alResultadoVoz(); }
    else if (tipo === "evaluacion") { estado.evaluacion = datos; if (estado.paso === 6) pintarResultado(); }
    else if (tipo === "copiloto") { agregarConversacion(datos); }
  }

  // ------------------------------------------------------------ pasos
  const entrar = { 0: entrarInicio, 1: entrarDispositivo, 2: entrarCamara, 3: entrarVoz, 4: entrarPvt, 5: entrarCuestionario, 6: entrarResultado };

  function irA(paso) {
    limpiarTemporizadores();
    pvtDetener();
    estado.paso = paso;
    document.querySelectorAll(".paso").forEach((s) => { s.hidden = Number(s.dataset.paso) !== paso; });
    document.querySelectorAll("#pasos li").forEach((li, i) => {
      li.classList.toggle("actual", i === paso);
      li.classList.toggle("hecho", i < paso);
    });
    pintarInfoSesion();
    entrar[paso]();
    window.scrollTo(0, 0);
  }

  function pintarInfoSesion() {
    $("info-sesion").textContent = estado.sesion
      ? `${L.nombre(estado.persona)} · ${estado.tarea}${estado.lineaBase ? " · línea base" : ""}`
      : "";
  }

  // 0. Inicio --------------------------------------------------
  function entrarInicio() {
    Object.assign(estado, {
      persona: "", tarea: "", lineaBase: false, sesion: "", inicio: 0, esp32: null, esp32Llegada: 0,
      vision: null, voz: null, evaluacion: null, conversacion: [], pendientes: [], kss: null, horas: 7,
    });
    $("linea-base").checked = false;
    pintarInfoSesion();
    pintarOpciones();
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

  $("comenzar").addEventListener("click", () => {
    estado.lineaBase = $("linea-base").checked;
    estado.sesion = `${marcaSesion()}-${estado.persona}`;
    estado.inicio = Date.now();
    publicar("apto/control/sesion", { tarea: estado.tarea });
    Comun.pantallaCompleta(true);
    irA(1);
  });

  // 1. Dispositivo ---------------------------------------------
  function entrarDispositivo() {
    pintarEsp32();
    cadaTanto(1000, pintarEsp32);
  }

  function pintarEsp32() {
    if (estado.paso !== 1) return;
    const d = estado.esp32;
    $("v-pulso").textContent = d && d.pulso_lpm != null ? Math.round(d.pulso_lpm) : "–";
    $("v-hrv").textContent = d && d.hrv_rmssd_ms != null ? Math.round(d.hrv_rmssd_ms) : "–";
    $("v-spo2").textContent = d && d.spo2 != null ? L.decimal(d.spo2, 1) : "–";
    $("sim-esp32").replaceChildren(...[etiquetaSimulado(d)].filter(Boolean));
    if (!d) {
      $("estado-esp32").textContent = "Esperando el dispositivo...";
    } else {
      const s = Math.round((Date.now() - estado.esp32Llegada) / 1000);
      $("estado-esp32").textContent = s <= 3 ? "Datos en vivo." : `Sin datos nuevos desde hace ${s} s.`;
    }
    $("continuar-1").disabled = !d;
  }
  $("continuar-1").addEventListener("click", () => irA(2));
  $("omitir-1").addEventListener("click", () => irA(2));

  // 2. Cámara --------------------------------------------------
  function entrarCamara() {
    estado.vision = null;
    pintarVision();
    $("continuar-2").hidden = true;
    publicar("apto/control/orden_vision", { accion: "medir", segundos: SEGUNDOS_CAMARA });
    const inicio = Date.now();
    const tic = () => {
      const pasado = (Date.now() - inicio) / 1000;
      const quedan = Math.max(0, Math.ceil(SEGUNDOS_CAMARA - pasado));
      $("cuenta-camara").textContent = quedan;
      $("progreso-camara").style.width = `${Math.min(100, (pasado / SEGUNDOS_CAMARA) * 100)}%`;
      if (quedan === 0) {
        limpiarTemporizadores();
        $("continuar-2").hidden = false;
        if (!estado.vision) $("estado-vision").textContent = "Terminó el minuto. No llegaron datos de la cámara.";
      }
    };
    tic();
    cadaTanto(250, tic);
  }

  const NOMBRES_VISION = {
    pulso_lpm: ["Pulso (cámara)", "lpm", 0], perclos: ["PERCLOS", "", 2], parpadeos_min: ["Parpadeos", "por minuto", 0],
  };
  const NO_MOSTRAR = new Set(["persona", "sesion", "ts", "fuente", "simulado"]);

  function pintarVision() {
    if (estado.paso !== 2) return;
    const d = estado.vision;
    $("sim-vision").replaceChildren(...[etiquetaSimulado(d)].filter(Boolean));
    if (!d) {
      $("datos-vision").replaceChildren();
      $("estado-vision").textContent = "Esperando datos de la cámara…";
      return;
    }
    $("estado-vision").textContent = "Datos de la cámara recibidos.";
    const filas = Object.entries(d).filter(([k, v]) => !NO_MOSTRAR.has(k) && (typeof v === "number" || typeof v === "string"));
    $("datos-vision").replaceChildren(...filas.map(([k, v]) => {
      const [nombre, unidad, cifras] = NOMBRES_VISION[k] || [k.replace(/_/g, " "), "", 2];
      const valor = typeof v === "number" ? (cifras === 0 ? Math.round(v) : L.decimal(v, cifras)) : v;
      return el("div", { class: "medida panel" }, el("span", { class: "etiqueta" }, nombre),
        el("span", { class: "valor" }, valor), el("span", { class: "unidad" }, unidad));
    }));
  }
  $("continuar-2").addEventListener("click", () => irA(3));
  $("omitir-2").addEventListener("click", () => irA(3));

  // 3. Voz -----------------------------------------------------
  let vozFase = "inicio";  // inicio, esperando, grabando, analizando, listo

  function entrarVoz() {
    $("frase-voz").textContent = CFG.frase_voz || "(Falta la frase: revisen voz/voz_fatiga.py)";
    vozFase = "inicio";
    estado.voz = null;
    $("estado-voz").textContent = "Presiona Grabar cuando quieras empezar.";
    $("resultado-voz").hidden = true;
    $("progreso-voz-caja").hidden = true;
    $("grabar").hidden = false;
    $("grabar").disabled = false;
    $("grabar").textContent = `Grabar (${SEGUNDOS_VOZ} s)`;
    $("continuar-3").hidden = true;
  }

  $("grabar").addEventListener("click", () => {
    vozFase = "esperando";
    estado.voz = null;
    $("resultado-voz").hidden = true;
    $("continuar-3").hidden = true;
    $("grabar").disabled = true;
    $("estado-voz").textContent = "Preparando la grabación…";
    publicar("apto/control/orden_voz", { accion: "grabar", segundos: SEGUNDOS_VOZ, linea_base: estado.lineaBase });
    despues(ESPERA_MODULO_VOZ_MS, () => {
      if (vozFase !== "esperando") return;
      vozFase = "inicio";
      $("estado-voz").textContent = "El módulo de voz no responde. Revisen que esté abierto voz\\voz_fatiga.py --servicio.";
      $("grabar").disabled = false;
      $("grabar").textContent = "Reintentar";
    });
  });

  function alEstadoVoz(datos) {
    if (estado.paso !== 3) return;
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
    if (estado.paso === 3 && vozFase !== "inicio") terminarVoz();
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
      caja.replaceChildren(...[  // replaceChildren escribiría "null": se filtran las partes vacías
        el("span", { class: "etiqueta" }, "Voz comparada con la línea base", etiquetaSimulado(d)),
        el("p", { class: "grande" }, d.estado_voz ? d.estado_voz.charAt(0).toUpperCase() + d.estado_voz.slice(1) : "Sin comparación"),
        explicacion ? el("p", { class: "estado" }, explicacion) : null,
        d.motivos_voz && d.motivos_voz.length ? el("ul", {}, d.motivos_voz.map((m) => el("li", {}, m))) : null,
        el("p", { class: "estado" }, "Es una sugerencia, no un diagnóstico."),
      ].filter(Boolean));
      caja.hidden = false;
    }
    $("grabar").disabled = false;
    $("grabar").textContent = "Grabar otra vez";
    $("continuar-3").hidden = false;
  }
  $("continuar-3").addEventListener("click", () => irA(4));
  $("omitir-3").addEventListener("click", () => irA(4));

  // 4. PVT-B ---------------------------------------------------
  const pvt = {
    activo: false, inicio: 0, duracionMs: 0, estimuloEn: null, rts: [], anticipadas: 0, sinRespuesta: 0, n: 0,
    espera: null, sinResp: null, raf: null, reloj: null, borrar: null,
  };

  function segundosPvt() {
    const s = Number(CFG.pvt_segundos);
    return Number.isFinite(s) && s > 0 ? s : 180;
  }

  function entrarPvt() {
    const s = segundosPvt();
    $("pvt-duracion").textContent = s % 60 === 0 ? `${s / 60} ${s === 60 ? "minuto" : "minutos"}` : `${s} segundos`;
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
  document.addEventListener("keydown", (e) => {
    if (estado.paso !== 4 || !pvt.activo || (e.code !== "Space" && e.key !== " ")) return;
    e.preventDefault();
    if (!e.repeat) pvtResponder(tiempoDelEvento(e));
  });

  function pvtTerminar() {
    const duracionMs = performance.now() - pvt.inicio;
    pvtDetener();
    const r = L.resumenPvt(pvt.rts, pvt.anticipadas, pvt.sinRespuesta, pvt.n, duracionMs);
    publicar(`apto/${estado.persona}/pvt`, { ...r, linea_base: estado.lineaBase });
    $("pvt-area").hidden = true;
    $("pvt-fin").hidden = false;
    $("pvt-media").textContent = r.rt_media_ms ?? "–";
    $("pvt-mediana").textContent = r.rt_mediana_ms ?? "–";
    $("pvt-lapsos").textContent = r.lapsos;
    $("pvt-anticipadas").textContent = r.anticipadas;
    $("pvt-estimulos").textContent = `de ${r.n_estimulos} estímulos`;
  }
  $("continuar-4").addEventListener("click", () => irA(5));
  $("omitir-4").addEventListener("click", () => irA(5));

  // 5. Cuestionario --------------------------------------------
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
    irA(6);
  });

  // 6. Resultado -----------------------------------------------
  function entrarResultado() {
    pintarResultado();
    pintarConversacion();
    despues(PISTA_ANALIZANDO_MS, () => { if (!estado.evaluacion) $("pista-analizando").hidden = false; });
  }

  function pintarResultado() {
    const ev = estado.evaluacion;
    $("analizando").hidden = Boolean(ev);
    $("resultado").hidden = !ev;
    if (!ev) { $("pista-analizando").hidden = true; return; }
    const color = ["verde", "amarillo", "rojo"].includes(ev.color) ? ev.color : "";
    $("semaforo").dataset.color = color;
    $("palabra-color").replaceChildren(palabraColor(color), etiquetaSimulado(ev) || "");
    $("puntaje").textContent = ev.puntaje != null ? `Puntaje ${L.decimal(ev.puntaje)} · ${L.hora(L.tsAMs(ev.ts))}` : "";
    const motivos = ev.motivos && ev.motivos.length ? ev.motivos : ["Tus señales están en tu rango habitual."];
    $("motivos").replaceChildren(...motivos.map((m) => el("li", {}, m)));
    $("accion").textContent = ev.accion || "–";
  }

  function agregarConversacion(datos) {
    estado.conversacion.push(datos);
    const i = estado.pendientes.indexOf(datos.pregunta);
    if (i >= 0) estado.pendientes.splice(i, 1);
    if (estado.paso === 6) pintarConversacion();
  }

  function pintarConversacion() {
    const items = estado.conversacion.map((d) => el("li", {},
      el("div", { class: "pregunta" }, d.pregunta === "(resumen automático)" ? "Resumen automático" : d.pregunta),
      el("div", { class: "respuesta" }, d.respuesta, el("div", { class: "meta" }, `${L.hora(L.tsAMs(d.ts))} · ${d.modo || ""}`)),
    ));
    for (const p of estado.pendientes) {
      items.push(el("li", {}, el("div", { class: "pregunta" }, p), el("div", { class: "pendiente" }, "El copiloto está pensando…")));
    }
    if (!items.length) items.push(el("li", { class: "vacio" }, "Escribe una pregunta, por ejemplo: «¿Por qué salí en amarillo?»"));
    const lista = $("conversacion");
    lista.replaceChildren(...items);
    lista.scrollTop = lista.scrollHeight;
  }

  $("form-pregunta").addEventListener("submit", (e) => {
    e.preventDefault();
    const pregunta = $("pregunta").value.trim();
    if (!pregunta || !estado.sesion) return;
    publicar("apto/control/pregunta", { pregunta });
    estado.pendientes.push(pregunta);
    $("pregunta").value = "";
    pintarConversacion();
  });
  $("nueva").addEventListener("click", () => irA(0));

  // ------------------------------------------------------------ arranque
  $("pantalla-completa").addEventListener("click", () => Comun.pantallaCompleta(!document.fullscreenElement));
  $("aviso-lectura").hidden = CFG.puede_publicar !== false;

  const params = new URLSearchParams(location.search);
  const pasoInicial = Number(params.get("paso"));
  if (pasoInicial >= 1 && pasoInicial <= 6) {  // atajo de prueba: sin publicar la sesión
    entrarInicio();
    estado.persona = (params.get("persona") || (CFG.tripulacion || [])[0] || "bri").toLowerCase();
    estado.tarea = params.get("tarea") || TAREAS[0];
    estado.sesion = `prueba-${marcaSesion()}-${estado.persona}`;
    estado.inicio = Date.now();
    irA(pasoInicial);
  } else {
    irA(0);
  }
})();
