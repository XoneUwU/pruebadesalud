/* Estación de monitoreo Becspace (diseño «Apto Hoy» de Claude Design) con los servicios reales del proyecto.
 *
 *  Panel           evaluaciones de apto/+/evaluacion (retenidas), recomendación de logica.js, módulos activos,
 *                  aviso de SpO2 y últimas respuestas del copiloto
 *  Evaluación      inicio, dispositivo (ESP32), cámara (orden al módulo de visión), voz (orden al módulo de voz),
 *                  reacción PVT-B, símbolos DSST (opcional), cuestionario de Karolinska y espera del coordinador
 *  Pruebas         cámara y micrófono de este navegador (getUserMedia), sin guardar imagen ni audio
 *  Resultados      semáforo, motivos, aviso de SpO2, copiloto (pregunta escrita o por voz) e indicadores
 *  Historial       /historial.json de servidor.py (MongoDB del registrador)
 *  Configuración   íconos, tema, preferencias visuales y datos de config.env
 *
 * Atajos para probar: estacion.html?pantalla=historial · estacion.html?paso=reaccion&persona=bri (&demo=1, &dsst=1).
 * Con ?paso= no se publica la sesión. */
(function () {
  "use strict";

  const { h, si, morph } = Plantilla;
  const { CFG } = Comun;
  const L = Logica;
  const raiz = document.getElementById("app");
  const PAGINA = document.body.dataset.pagina || "estacion";
  const PUEDE = CFG.puede_publicar !== false && Boolean(window.APTO);

  // ================================================================== constantes del diseño
  const ST = {
    verde: { fg: "var(--st-verde)", bg: "var(--st-verde-bg)", icon: "ph-check-circle", word: "VERDE", label: "Condición favorable para la tarea" },
    amarillo: { fg: "var(--st-amarillo)", bg: "var(--st-amarillo-bg)", icon: "ph-warning-circle", word: "AMARILLO", label: "Precaución: en pareja o posponer" },
    rojo: { fg: "var(--st-rojo)", bg: "var(--st-rojo-bg)", icon: "ph-x-circle", word: "ROJO", label: "No recomendado hoy" },
    sin: { fg: "var(--color-neutral-400)", bg: "var(--color-neutral-900)", icon: "ph-minus-circle", word: "SIN EVALUAR", label: "Falta la evaluación" },
  };
  const TIPOS = {
    medido: { label: "Medido", icon: "ph-target", fg: "var(--color-accent-300)", help: "Lo calcula un sensor o una prueba con un método definido." },
    estimado: { label: "Estimado", icon: "ph-approximate-equals", fg: "var(--color-neutral-300)", help: "Aproximación sin validación clínica; se muestra con su calidad." },
    reportado: { label: "Reportado", icon: "ph-chat-centered-text", fg: "var(--color-neutral-300)", help: "Lo responde la persona en el cuestionario." },
    no_disponible: { label: "No disponible", icon: "ph-prohibit", fg: "var(--color-neutral-500)", help: "No se calcula o la calidad no alcanzó; nunca se muestra un número." },
  };
  const THEME_DARK = { "--color-bg": "#060913", "--color-surface": "rgba(22,28,48,0.82)", "--color-text": "#F4F6FF", "--color-neutral-300": "#A7B3CC", "--color-divider": "rgba(125,145,210,0.16)", "--nav-bg": "rgba(8,14,34,0.74)", "--card-edge": "rgba(125,145,210,0.18)", "--shadow-sm": "0 0 0 1px rgba(125,145,210,0.18), 0 12px 36px rgba(0,0,0,0.22)", "--st-verde": "oklch(0.80 0.10 160)", "--st-verde-bg": "oklch(0.32 0.045 160)", "--st-amarillo": "oklch(0.85 0.10 85)", "--st-amarillo-bg": "oklch(0.34 0.05 80)", "--st-rojo": "oklch(0.76 0.11 25)", "--st-rojo-bg": "oklch(0.32 0.06 22)", "--ink": "black" };
  const THEME_LIGHT = {
    "--color-bg": "#e9ebf5", "--color-surface": "#f7f7fc", "--color-text": "#1c1e2b", "--color-accent": "#6a5cc4", "--color-divider": "color-mix(in srgb, #1c1e2b 14%, transparent)",
    "--color-neutral-100": "#1f2129", "--color-neutral-200": "#2f3240", "--color-neutral-300": "#454857", "--color-neutral-400": "#5a5e6e", "--color-neutral-500": "#6e7285", "--color-neutral-600": "#9397ab", "--color-neutral-700": "#b2b6ca", "--color-neutral-800": "#d3d6e4", "--color-neutral-900": "#e2e4ef",
    "--color-accent-100": "#1e1a3a", "--color-accent-200": "#2b2560", "--color-accent-300": "#4a3f99", "--color-accent-400": "#5d50b5", "--color-accent-500": "#6a5cc4", "--color-accent-600": "#8a7ed6", "--color-accent-700": "#c4bdf5", "--color-accent-800": "#ddd8fb", "--color-accent-900": "#ecebfd",
    "--shadow-sm": "0 0 0 1px #d3d6e4, 0 1px 3px rgba(30,30,70,0.06)", "--shadow-md": "0 0 0 1px #c9cde0, 0 6px 18px rgba(30,30,70,0.12)", "--shadow-lg": "0 0 0 1px #b2b6ca, 0 16px 40px rgba(30,30,70,0.18)",
    "--st-verde": "oklch(0.45 0.10 160)", "--st-verde-bg": "oklch(0.92 0.04 160)", "--st-amarillo": "oklch(0.48 0.09 70)", "--st-amarillo-bg": "oklch(0.93 0.05 85)", "--st-rojo": "oklch(0.50 0.14 25)", "--st-rojo-bg": "oklch(0.93 0.035 22)", "--ink": "#d9dcea", "--nav-bg": "rgba(240,242,250,0.78)", "--card-edge": "rgba(90,100,160,0.16)",
  };
  const ICONOS = [["ph-star-four", "Estrella"], ["ph-rocket-launch", "Cohete"], ["ph-triangle", "Triángulo"], ["ph-moon-stars", "Luna"], ["ph-diamond", "Diamante"], ["ph-hexagon", "Hexágono"], ["ph-heart", "Corazón"], ["ph-lightning", "Rayo"], ["ph-crown-simple", "Corona"], ["ph-square", "Cuadrado"]];
  const ICONOS_DEF = { bri: "ph-star-four", danilo: "ph-rocket-launch", sebas: "ph-triangle", erick: "ph-moon-stars", adrian: "ph-diamond" };
  const NAV = [
    ["dashboard", "Panel", "ph-squares-four", "Tripulación", "Panel de la misión"],
    ["evaluacion", "Evaluación", "ph-scan", "Estación", "Evaluación en curso"],
    ["pruebas", "Pruebas", "ph-faders", "Cámara y micrófono", "Pruebas de dispositivos"],
    ["resultados", "Resultados", "ph-clipboard-text", "Resultado", "Resultado de la evaluación"],
    ["historial", "Historial", "ph-chart-line-up", "Registrador", "Historial de monitoreo"],
    ["config", "Configuración", "ph-gear-six", "Sistema", "Configuración"],
    ["sistema", "Sistema de diseño", "ph-swatches", "Nocturne + Apto", "Sistema de diseño"],
  ];
  const LANDMARKS = [[30, 38], [36, 36], [42, 38], [58, 38], [64, 36], [70, 38], [33, 40], [39, 41], [61, 41], [67, 40], [50, 48], [50, 56], [46, 60], [54, 60], [40, 72], [45, 75], [50, 76], [55, 75], [60, 72], [50, 71], [20, 45], [22, 62], [30, 80], [50, 92], [70, 80], [78, 62], [80, 45], [50, 18], [32, 22], [68, 22]];
  const TAREAS = ["caminata espacial", "maniobra de acoplamiento", "mantenimiento externo"];
  // [nombre en apto/control/modulos/, nombre en pantalla, cómo se abre]
  const MODULOS = [
    ["voz", "Voz", "python voz\\voz_fatiga.py --servicio"],
    ["copiloto", "Copiloto", "python copiloto\\copiloto.py"],
    ["vision", "Visión", "python vision\\vision.py --servicio"],
    ["coordinador", "Coordinador", "python coordinador\\coordinador_provisional.py"],
    ["esp32", "ESP32", "enciendan la placa (firmware\\apto_esp32) en la misma red"],
  ];
  const COMANDO = Object.fromEntries(MODULOS.map(([m, , c]) => [m, c]));
  const PASOS = ["inicio", "dispositivo", "camara", "voz", "reaccion", "simbolos", "cuestionario", "resultado"];
  const PASO_INFO = { inicio: ["Inicio", "ph-user"], dispositivo: ["Dispositivo", "ph-heartbeat"], camara: ["Cámara", "ph-webcam"], voz: ["Voz", "ph-microphone"], reaccion: ["Reacción", "ph-timer"], simbolos: ["Símbolos", "ph-shapes"], cuestionario: ["Cuestionario", "ph-list-checks"], resultado: ["Resultado", "ph-flag-checkered"] };
  const SEGUNDOS_CAMARA = Number(CFG.vision_segundos) > 0 ? Number(CFG.vision_segundos) : 60;
  const SEGUNDOS_VOZ = 12;
  const PREPARACION_VOZ_S = 3;        // voz_fatiga.py cuenta 3, 2, 1 antes de grabar
  const ESPERA_MODULO_VOZ_MS = 6000;  // abierto pero sin responder a la orden
  const AVISO_ESP32_MS = 10000;
  const PISTA_ANALIZANDO_MS = 25000;
  const ESPERA_COPILOTO_MS = 90000;   // la primera respuesta del modelo puede tardar un minuto
  const PULSO_VIGENTE_MS = 15000;
  const POR_PAGINA = 20;

  const MONO = "font-family:ui-monospace,Menlo,monospace";
  const ETQ = `font-size:11px;letter-spacing:0.12em;text-transform:uppercase;color:var(--color-neutral-400);${MONO}`;
  const TARJ = "border-radius:var(--radius-md);background:var(--color-surface);box-shadow:inset 0 0 0 1px var(--card-edge)";
  const SECC = "display:flex;flex-direction:column;gap:12px;padding:18px;border-radius:var(--radius-lg);background:var(--color-surface);box-shadow:var(--shadow-sm);backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px)";

  // ================================================================== utilidades
  const cap = (s) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : "");
  const num = (x) => (x === null || x === undefined || x === "" || !Number.isFinite(Number(x)) ? null : Number(x));
  const fmt = (x, c = 2) => (num(x) === null ? "–" : Number(x).toFixed(c).replace(".", ","));
  const entero = (x) => (num(x) === null ? "–" : String(Math.round(Number(x))));
  const dd = (n) => String(n).padStart(2, "0");
  const fechaCorta = (ms) => { const d = new Date(ms); return `${dd(d.getDate())}/${dd(d.getMonth() + 1)}`; };
  const horaCorta = (ms) => { const d = new Date(ms); return Number.isNaN(d.getTime()) ? "--:--" : `${dd(d.getHours())}:${dd(d.getMinutes())}`; };
  const esHoy = (ms) => new Date(ms).toDateString() === new Date().toDateString();
  const cuando = (ms) => (!Number.isFinite(ms) ? "" : esHoy(ms) ? `hoy ${horaCorta(ms)}` : `${fechaCorta(ms)} ${horaCorta(ms)}`);
  const mediana = (vals) => {
    const v = vals.filter((x) => x !== null).sort((a, b) => a - b);
    if (!v.length) return null;
    return v.length % 2 ? v[(v.length - 1) / 2] : (v[v.length / 2 - 1] + v[v.length / 2]) / 2;
  };
  const reducido = () => S.prefs.movimiento || Boolean(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  function leer(clave, defecto) {
    try { const v = localStorage.getItem(clave); return v === null ? defecto : JSON.parse(v); } catch (e) { return defecto; }
  }
  function guardar(clave, valor) {
    try { localStorage.setItem(clave, JSON.stringify(valor)); } catch (e) { /* sin almacenamiento */ }
  }

  // ================================================================== estado
  const params = new URLSearchParams(location.search);
  const S = {
    pantalla: document.body.dataset.inicio || "dashboard",
    w: window.innerWidth,
    tema: leer("becspace-tema", "oscuro"),
    prefs: Object.assign({ proyector: false, movimiento: false, alto: false }, leer("becspace-prefs", {})),
    iconos: Object.assign({}, ICONOS_DEF, leer("becspace-iconos-v2", {})),
    conexion: "conectando", conexionTexto: "Conectando…",
    modulos: {},
    evaluaciones: {},     // persona -> última evaluación (en orden de llegada, como el copiloto)
    ultimas: {},          // persona -> {pulso, pulsoLlegada, kss, pvt}
    sesiones: {},         // id de sesión -> {esp32: [...], vision, voz, pvt, dsst, cuestionario}
    copiloto: [],         // respuestas del copiloto, la más nueva primero
    pendientes: [],       // preguntas sin respuesta todavía: {persona, pregunta, desde}
    tareaSesion: "", tareaElegida: "",
    // evaluación
    paso: "inicio", persona: "", tarea: "", lineaBase: false, demo: false, conDsst: false, sesion: "", inicio: 0,
    esp32: null, esp32Llegada: 0, esp32Tarde: false, ppg: [], latido: 0,
    vision: null, estadoVision: "", visionRestantes: null, visionMotivo: "", visionMensaje: "", camFase: "lista", camInicio: 0, camT: SEGUNDOS_CAMARA, vista: "ventana",
    fraseVoz: "estandar", vozFase: "inicio", vozMsg: "", vozInicio: 0, vozPct: 0, voz: null,
    pvt: { fase: "intro", msg: "", cont: "", contColor: "", res: null },
    dsst: { fase: "intro", res: null, clave: [], actual: 0 },
    kss: null, horas: 7,
    anal: { t0: 0, comparando: false, vencida: false, listo: false },
    // resultados
    resPersona: "", chat: { persona: "", sesion: "" }, escuchando: false, escuchaTexto: "",
    // historial
    hist: { estado: "nada", filas: [], motivo: "" }, periodo: "30", hPersona: "todos", serie: "puntaje", hSel: null, hPag: 0, hComando: "",
    // pruebas
    pCam: "off", camErr: null, camDevs: [], camDev: "", camRes: "", camFps: null, luz: null,
    pMic: "off", micErr: null, micDevs: [], micDev: "", level: 0, peakMax: 0, noise: null, wave: [], recFase: "no", recUrl: null,
    // configuración
    permisos: { camera: "", microphone: "" }, verComandoCamaras: false,
    modal: false,
    splash: !params.get("paso") && !params.get("pantalla") && PAGINA === "estacion"
      && !(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) && !leer("becspace-prefs", {}).movimiento,
    splashFuera: false, splashVa: false,
  };
  // Un SVG por lugar (barra, carga, sistema de diseño): se arma una vez, así no se repiten los id de sus degradados.
  const logos = new Map();
  function logo(lugar, variante, tono) {
    const k = `${lugar}-${variante}-${tono}`;
    if (!logos.has(k)) logos.set(k, Plantilla.crudo(Logo.html(variante, tono)));
    return logos.get(k);
  }
  const TRIPULACION = () => (CFG.tripulacion && CFG.tripulacion.length ? CFG.tripulacion : Object.keys(S.evaluaciones));
  const activo = (m) => S.modulos[m] === true;
  const icono = (p) => S.iconos[p] || "ph-user";

  // ================================================================== pintar
  let pedido = false;
  let ultimaVista = "";
  function pintar() {
    pedido = false;
    morph(raiz, vistaApp());
    const vistaActual = S.pantalla + ":" + (S.pantalla === "evaluacion" ? S.paso : "");
    if (vistaActual !== ultimaVista) { ultimaVista = vistaActual; animarEntrada(); }
    pvtContadorVivo();
  }
  function pedirPintar() {
    if (!pedido) { pedido = true; requestAnimationFrame(pintar); }
  }
  function animarEntrada() {
    const m = document.getElementById("principal");
    if (!m || !m.animate || reducido()) return;
    Array.from(m.children).forEach((c, i) => c.animate && c.animate(
      [{ opacity: 0, transform: "translateY(12px)" }, { opacity: 1, transform: "none" }],
      { duration: 460, delay: Math.min(i, 8) * 55, easing: "cubic-bezier(.2,.7,.2,1)", fill: "backwards" }));
  }

  function aplicarTema() {
    const r = document.documentElement.style;
    const claro = S.tema === "claro";
    Object.keys(THEME_DARK).concat(Object.keys(THEME_LIGHT)).forEach((k) => r.removeProperty(k));
    Object.entries(claro ? THEME_LIGHT : THEME_DARK).forEach(([k, v]) => r.setProperty(k, v));
    r.colorScheme = claro ? "light" : "dark";
    document.documentElement.dataset.tema = claro ? "claro" : "oscuro";
  }
  function aplicarPrefs() {
    const d = document.documentElement.dataset;
    d.proyector = S.prefs.proyector ? "1" : "0";
    d.quieto = S.prefs.movimiento ? "1" : "0";
    d.contraste = S.prefs.alto ? "1" : "0";
  }

  function irPantalla(p) {
    if (S.pantalla === "evaluacion" && p !== "evaluacion") cortarPruebasEnCurso();
    if (S.pantalla === "pruebas" && p !== "pruebas") { pararCamara(); pararMic(); }
    S.pantalla = p;
    if (p === "historial" && S.hist.estado !== "cargando") cargarHistorial();
    if (p === "config") revisarPermisos();
    if (p === "resultados") completarSesion(evaluacionVista());
    window.scrollTo(0, 0);
    pedirPintar();
  }

  // ================================================================== MQTT
  const mqttc = Comun.conectar(PAGINA, [
    "apto/+/esp32", "apto/+/vision", "apto/+/voz", "apto/+/pvt", "apto/+/dsst", "apto/+/cuestionario",
    "apto/+/evaluacion", "apto/+/copiloto", "apto/control/sesion", "apto/control/estado_voz",
    "apto/control/estado_vision", "apto/control/estado_escucha", "apto/control/modulos/+",
  ], alMensaje, (estado, texto) => { S.conexion = estado; S.conexionTexto = texto; pedirPintar(); });

  function publicar(tema, datos, retener) {
    if (!PUEDE) return false;
    return mqttc.publicar(tema, { persona: S.persona, sesion: S.sesion, ...datos }, retener);
  }

  /** Un mensaje retenido (guardado en el broker) solo cuenta si es de esta sesión o posterior a su inicio. */
  function esDeEstaSesion(datos, retenido) {
    if (!retenido) return true;
    if (datos.sesion && datos.sesion === S.sesion) return true;
    return L.tsAMs(datos.ts) >= S.inicio - 2000;
  }

  function datosSesion(id) {
    if (!S.sesiones[id]) S.sesiones[id] = { esp32: [] };
    return S.sesiones[id];
  }

  function alMensaje(tema, datos, retenido) {
    if (tema.startsWith("apto/control/modulos/")) {
      S.modulos[tema.split("/")[3]] = datos.activo === true;
      alCambiarModulos();
      return pedirPintar();
    }
    if (tema === "apto/control/sesion") {
      if (datos.tarea) S.tareaSesion = datos.tarea;
      return pedirPintar();
    }
    const deLaPersona = S.sesion && datos.persona === S.persona;
    if (tema === "apto/control/estado_voz") { if (deLaPersona) alEstadoVoz(datos); return pedirPintar(); }
    if (tema === "apto/control/estado_escucha") { if (datos.persona === S.chat.persona) alEstadoEscucha(datos); return pedirPintar(); }
    if (tema === "apto/control/estado_vision") {
      if (deLaPersona) alEstadoVision(datos);
      return pedirPintar();
    }
    const [persona, tipo] = Comun.partesTema(tema);
    if (!persona || persona === "control") return;
    const miembros = CFG.tripulacion || [];
    if (miembros.length && !miembros.includes(persona)) return;  // p. ej. evaluaciones viejas de alguien que ya no está

    // Caché por sesión (para los indicadores de Resultados) y últimos valores por persona (para el Panel).
    if (datos.sesion) {
      const d = datosSesion(datos.sesion);
      if (tipo === "esp32") { d.esp32.push(datos); if (d.esp32.length > 900) d.esp32.shift(); }
      else if (["vision", "voz", "pvt", "dsst", "cuestionario"].includes(tipo)) d[tipo] = datos;
    }
    const u = S.ultimas[persona] || (S.ultimas[persona] = {});
    if (tipo === "esp32" && num(datos.pulso_lpm) !== null) { u.pulso = num(datos.pulso_lpm); u.pulsoLlegada = Date.now(); u.pulsoSimulado = datos.simulado; }
    if (tipo === "cuestionario" && num(datos.kss) !== null) u.kss = num(datos.kss);
    if (tipo === "pvt" && num(datos.rt_mediana_ms) !== null) u.pvt = num(datos.rt_mediana_ms);

    if (tipo === "evaluacion") {
      S.evaluaciones[persona] = { ...datos, persona };
      if (S.paso === "resultado" && S.sesion && persona === S.persona && esDeEstaSesion(datos, retenido)) alLlegarEvaluacion();
    } else if (tipo === "copiloto") {
      S.copiloto.unshift({ ...datos, persona, llegada: Date.now() });
      S.copiloto.length = Math.min(S.copiloto.length, 60);
      const i = S.pendientes.findIndex((p) => p.persona === persona && p.pregunta === datos.pregunta);
      if (i >= 0) S.pendientes.splice(i, 1);
    } else if (S.sesion && persona === S.persona && esDeEstaSesion(datos, retenido)) {
      if (tipo === "esp32") { S.esp32 = datos; S.esp32Llegada = Date.now(); }
      else if (tipo === "vision") { S.vision = datos; if (S.camFase === "midiendo") S.camFase = "listo"; }
      else if (tipo === "voz") { S.voz = datos; if (S.paso === "voz" && S.vozFase !== "inicio") terminarVoz(); }
    }
    pedirPintar();
  }

  function alCambiarModulos() {
    if (S.pantalla !== "evaluacion") return;
    if (S.paso === "voz" && !activo("voz") && ["esperando", "grabando", "analizando"].includes(S.vozFase)) {
      limpiarTemporizadores();
      S.vozFase = "inicio";
    }
  }

  // ================================================================== evaluación: pasos
  const temporizadores = new Set();  // se limpian al cambiar de paso
  function despues(ms, fn) {
    const id = setTimeout(() => { temporizadores.delete(id); fn(); pedirPintar(); }, ms);
    temporizadores.add(id);
    return id;
  }
  function cadaTanto(ms, fn) {
    const id = setInterval(() => { fn(); pedirPintar(); }, ms);
    temporizadores.add(id);
    return id;
  }
  function parar(id) { clearInterval(id); temporizadores.delete(id); }
  function limpiarTemporizadores() {
    for (const id of temporizadores) { clearTimeout(id); clearInterval(id); }
    temporizadores.clear();
  }

  function pasosActivos() { return PASOS.filter((p) => p !== "simbolos" || S.conDsst); }
  function mover(d) {
    const l = pasosActivos();
    const i = l.indexOf(S.paso);
    irA(l[Math.max(0, Math.min(l.length - 1, i + d))]);
  }

  const entrar = {
    inicio: entrarInicio, dispositivo: entrarDispositivo, camara: entrarCamara, voz: entrarVoz, reaccion: entrarPvt,
    simbolos: entrarDsst, cuestionario: () => {}, resultado: entrarAnalizando,
  };

  function irA(paso) {
    limpiarTemporizadores();
    pvtDetener();
    dsstDetener();
    S.paso = paso;
    entrar[paso]();
    window.scrollTo(0, 0);
    pedirPintar();
  }

  /** Al salir de la pantalla de Evaluación en medio de una prueba, la prueba se corta y vuelve a su inicio. */
  function cortarPruebasEnCurso() {
    if (S.paso === "reaccion" && S.pvt.fase === "activa") { pvtDetener(); S.pvt = { fase: "intro", msg: "", cont: "", contColor: "", res: null }; }
    if (S.paso === "simbolos" && S.dsst.fase === "activa") { dsstDetener(); S.dsst = { fase: "intro", res: null, clave: [], actual: 0 }; }
  }

  // Inicio -----------------------------------------------------
  function entrarInicio() {
    Object.assign(S, {
      persona: "", tarea: "", lineaBase: false, sesion: "", inicio: 0, esp32: null, esp32Llegada: 0, esp32Tarde: false,
      vision: null, estadoVision: "", visionRestantes: null, visionMotivo: "", visionMensaje: "", camFase: "lista", camT: SEGUNDOS_CAMARA,
      voz: null, vozFase: "inicio", vozMsg: "", vozPct: 0, fraseVoz: "estandar", kss: null, horas: 7,
      pvt: { fase: "intro", msg: "", cont: "", contColor: "", res: null }, dsst: { fase: "intro", res: null, clave: [], actual: 0 },
      anal: { t0: 0, comparando: false, vencida: false, listo: false },
    });
  }

  function marcaSesion() {
    return L.ahoraIso().replace(/[-:]/g, "").replace("T", "-");  // 20261113-193005
  }

  function comenzar() {
    if (!S.persona || !S.tarea || !PUEDE) return;
    S.sesion = `${marcaSesion()}-${S.persona}`;
    S.inicio = Date.now();
    datosSesion(S.sesion).meta = { modo_demo: S.demo, linea_base: S.lineaBase, tarea: S.tarea };
    publicar("apto/control/sesion", { tarea: S.tarea }, true);  // con retain: el ESP32 la sabe aunque se reinicie
    Comun.pantallaCompleta(true);
    irA("dispositivo");
  }

  // Dispositivo (ESP32: se sabe que está porque llegan datos) ---------
  function entrarDispositivo() {
    const llegada = Date.now();
    S.esp32Tarde = false;
    S.ppg = [];
    cadaTanto(1000, () => { S.esp32Tarde = Date.now() - llegada >= AVISO_ESP32_MS; });
    let fase = 0;
    cadaTanto(50, () => {  // onda ilustrativa al ritmo del pulso medido (el ESP32 manda un resumen por segundo)
      const d = S.esp32;
      const lpm = d && d.dedo !== false && num(d.pulso_lpm) !== null ? num(d.pulso_lpm) : null;
      let v = 0.04 + (Math.random() - 0.5) * 0.01;
      if (lpm) {
        fase += 0.05 * lpm / 60;
        if (fase >= 1) { fase -= 1; S.latido = performance.now(); }
        v = 0.95 * Math.exp(-(((fase - 0.16) / 0.065) ** 2)) + 0.36 * Math.exp(-(((fase - 0.43) / 0.09) ** 2)) + 0.05 * Math.sin(performance.now() / 1900) + (Math.random() - 0.5) * 0.025;
      }
      S.ppg.push(v);
      if (S.ppg.length > 160) S.ppg.shift();
    });
  }

  function estadoEsp32() {
    const d = S.esp32;
    if (!d) {
      if (!S.esp32Tarde) return ["espera", "Esperando el dispositivo…"];
      return ["aviso", !activo("esp32")
        ? "El ESP32 no está conectado al broker (si tiene los tres LED encendidos, no llega al broker). Revisen que " +
          "esté encendido y en la misma red, o toquen Omitir."
        : "No llegan datos del dispositivo. Revisen que el ESP32 esté encendido y conectado a la misma red, o toquen Omitir."];
    }
    const s = Math.round((Date.now() - S.esp32Llegada) / 1000);
    if (s > 3) return ["aviso", `Sin datos nuevos desde hace ${s} s.`];
    if (d.dedo === false) return ["aviso", "Coloca el dedo en el sensor y quédate sin moverte."];
    if (d.pulso_lpm == null) return ["espera", "Dedo detectado: midiendo el pulso (unos segundos)…"];
    const calidad = d.calidad != null ? ` · calidad ${L.decimal(d.calidad)}` : "";
    const mov = d.movimiento != null && d.movimiento > 0.05 ? " · hay movimiento: quédate quieto" : "";
    return ["ok", `Dedo detectado${calidad} · lecturas cada segundo${mov}`];
  }

  // Cámara (la mide el módulo de visión; la estación no abre la cámara) -------
  function entrarCamara() {
    Object.assign(S, { vision: null, estadoVision: "", visionRestantes: null, visionMotivo: "", visionMensaje: "", camFase: "lista", camT: SEGUNDOS_CAMARA });
  }

  function iniciarCamara() {
    if (!activo("vision") || S.camFase === "midiendo") return;
    Object.assign(S, { vision: null, estadoVision: "", visionRestantes: null, visionMotivo: "", visionMensaje: "", camFase: "midiendo", camInicio: Date.now(), camT: SEGUNDOS_CAMARA });
    publicar("apto/control/orden_vision", { accion: "medir", segundos: SEGUNDOS_CAMARA, linea_base: S.lineaBase });
    const reloj = cadaTanto(250, () => {
      // Mientras el módulo espera a que se quiten los lentes, la cuenta de la medición no corre.
      if (S.camFase === "midiendo" && S.estadoVision === "lentes") { S.camInicio = Date.now(); S.camT = SEGUNDOS_CAMARA; return; }
      const local = Math.max(0, SEGUNDOS_CAMARA - (Date.now() - S.camInicio) / 1000);
      const remoto = num(S.visionRestantes);
      S.camT = remoto !== null && S.estadoVision === "midiendo" ? Math.min(local, remoto) : local;
      if (S.camFase !== "midiendo") { parar(reloj); return; }
      if (local <= 0) { S.camFase = "listo"; parar(reloj); }
    });
  }

  function alEstadoVision(d) {
    S.estadoVision = String(d.estado || "");
    S.visionRestantes = d.segundos_restantes;
    S.visionMotivo = d.motivo || "";
    S.visionMensaje = d.mensaje || "";  // con "lentes": el pedido de quitárselos
    if (S.estadoVision === "error" && S.camFase === "midiendo") S.camFase = "error";
    if (S.estadoVision === "listo" && S.camFase === "midiendo") despues(2000, () => { if (S.camFase === "midiendo") S.camFase = "listo"; });
  }

  // Voz --------------------------------------------------------
  function frasesVoz() {
    return CFG.frases_voz && Object.keys(CFG.frases_voz).length
      ? CFG.frases_voz : { estandar: { titulo: "Frase estándar", texto: CFG.frase_voz || "" } };
  }

  function entrarVoz() {
    Object.assign(S, { voz: null, vozFase: "inicio", vozMsg: "", vozPct: 0 });
  }

  function grabarVoz() {
    if (!activo("voz")) return;
    Object.assign(S, { vozFase: "esperando", voz: null, vozMsg: "Preparando la grabación…", vozPct: 0 });
    publicar("apto/control/orden_voz", { accion: "grabar", segundos: SEGUNDOS_VOZ, linea_base: S.lineaBase, frase: S.fraseVoz });
    despues(ESPERA_MODULO_VOZ_MS, () => {
      if (S.vozFase !== "esperando") return;
      S.vozFase = "inicio";
      S.vozMsg = "El módulo de voz está abierto pero no respondió. Revisen su ventana y vuelvan a intentar.";
    });
  }

  function alEstadoVoz(datos) {
    if (S.paso !== "voz") return;
    if (datos.estado === "grabando" && S.vozFase === "esperando") {
      S.vozFase = "grabando";
      S.vozInicio = Date.now();
      const tic = () => {
        const s = (Date.now() - S.vozInicio) / 1000;
        if (s < PREPARACION_VOZ_S) { S.vozMsg = `Empieza en ${Math.ceil(PREPARACION_VOZ_S - s)}…`; S.vozPct = 0; }
        else if (s < PREPARACION_VOZ_S + SEGUNDOS_VOZ) {
          S.vozMsg = `Grabando… lee la frase (${Math.ceil(PREPARACION_VOZ_S + SEGUNDOS_VOZ - s)} s)`;
          S.vozPct = ((s - PREPARACION_VOZ_S) / SEGUNDOS_VOZ) * 100;
        } else if (S.vozFase === "grabando") { S.vozFase = "analizando"; S.vozPct = 100; S.vozMsg = "Analizando tu voz…"; }
      };
      tic();
      cadaTanto(200, tic);
    } else if (datos.estado === "listo" && S.vozFase !== "listo" && S.vozFase !== "inicio") {
      despues(1500, () => { if (S.vozFase !== "listo") terminarVoz(); });
    }
  }

  function terminarVoz() {
    limpiarTemporizadores();
    S.vozFase = "listo";
    S.vozPct = 100;
    const d = S.voz;
    S.vozMsg = !d ? "Listo." : d.aviso || (d.voz_detectada === false ? "No se detectó voz en la grabación." : "Voz lista: tono, jitter, shimmer y pausas");
  }

  // Reacción (PVT-B) -------------------------------------------
  const pvt = { activo: false, inicio: 0, duracionMs: 0, estimuloEn: null, rts: [], anticipadas: 0, sinRespuesta: 0, n: 0, espera: null, sinResp: null, raf: null, reloj: null, borrar: null };

  function segundosPvt() {
    if (S.demo) return L.PVT.DEMO_S;
    const s = Number(CFG.pvt_segundos);
    return Number.isFinite(s) && s > 0 ? s : 180;
  }
  function textoDuracion(s) {
    return s % 60 === 0 ? `${s / 60} ${s === 60 ? "minuto" : "minutos"}` : `${s} segundos`;
  }

  function entrarPvt() { S.pvt = { fase: "intro", msg: "", cont: "", contColor: "", res: null }; }

  function pvtDetener() {
    pvt.activo = false;
    clearTimeout(pvt.espera); clearTimeout(pvt.sinResp); clearTimeout(pvt.borrar); clearInterval(pvt.reloj);
    cancelAnimationFrame(pvt.raf);
    pvt.estimuloEn = null;
  }

  function pvtEmpezar() {
    Object.assign(pvt, { inicio: performance.now(), duracionMs: segundosPvt() * 1000, rts: [], anticipadas: 0, sinRespuesta: 0, n: 0, estimuloEn: null });
    pvt.activo = true;
    S.pvt = { fase: "activa", msg: "Prepárate…", cont: "", contColor: "", res: null };
    if (document.activeElement) document.activeElement.blur();  // que la barra espaciadora no apriete un botón
    pvt.reloj = setInterval(pedirPintar, 250);
    pvtProgramar();
    pedirPintar();
  }

  function pvtRestante() {
    const quedan = Math.max(0, Math.ceil((pvt.duracionMs - (performance.now() - pvt.inicio)) / 1000));
    return `Quedan ${Math.floor(quedan / 60)}:${dd(quedan % 60)}`;
  }

  /** Espera aleatoria de 1 a 4 s; si se acaba el tiempo antes, termina la prueba. */
  function pvtProgramar() {
    clearTimeout(pvt.espera);
    cancelAnimationFrame(pvt.raf);
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
      Object.assign(S.pvt, { msg: "", cont: "0", contColor: ST.amarillo.fg });
      pintar();
      const animar = () => {
        if (pvt.estimuloEn === null) return;
        pvtContadorVivo();
        pvt.raf = requestAnimationFrame(animar);
      };
      pvt.raf = requestAnimationFrame(animar);
      pvt.sinResp = setTimeout(() => {  // 30 s sin respuesta: cuenta como lapso
        if (pvt.estimuloEn === null) return;
        pvt.estimuloEn = null;
        pvt.sinRespuesta += 1;
        Object.assign(S.pvt, { cont: "", msg: "Sin respuesta." });
        pedirPintar();
        pvtProgramar();
      }, L.PVT.SIN_RESPUESTA_MS);
    });
  }

  /** El contador corre en cada cuadro sin volver a pintar toda la pantalla. */
  function pvtContadorVivo() {
    if (pvt.estimuloEn === null) return;
    const c = document.getElementById("pvt-cont");
    if (c) c.textContent = String(Math.floor(performance.now() - pvt.estimuloEn));
  }

  function pvtResponder(tiempo) {
    if (!pvt.activo) return;
    if (pvt.estimuloEn === null) {  // antes del estímulo: anticipada, y se vuelve a esperar
      pvt.anticipadas += 1;
      Object.assign(S.pvt, { cont: "", msg: "Te adelantaste: cuenta como anticipada" });
      pvtProgramar();
      return pedirPintar();
    }
    const rt = tiempo - pvt.estimuloEn;
    pvt.estimuloEn = null;
    clearTimeout(pvt.sinResp);
    cancelAnimationFrame(pvt.raf);
    const tipo = L.clasificarRespuesta(rt);
    if (tipo === "anticipada") {
      pvt.anticipadas += 1;
      Object.assign(S.pvt, { cont: "", msg: "Te adelantaste: cuenta como anticipada" });
    } else {
      pvt.rts.push(rt);
      Object.assign(S.pvt, { cont: String(Math.round(rt)), contColor: tipo === "lapso" ? ST.rojo.fg : "var(--color-text)", msg: tipo === "lapso" ? "Lapso: 355 ms o más" : "Bien" });
      pvt.borrar = setTimeout(() => { if (pvt.estimuloEn === null && pvt.activo) { S.pvt.cont = ""; S.pvt.msg = ""; pedirPintar(); } }, 800);
    }
    pvtProgramar();
    pedirPintar();
  }

  function tiempoDelEvento(e) {
    // timeStamp del evento (misma base que performance.now) es más exacto; si no sirve, la hora actual
    const ahora = performance.now();
    return e && e.timeStamp > 0 && Math.abs(ahora - e.timeStamp) < 1000 ? e.timeStamp : ahora;
  }

  function pvtTerminar() {
    const duracionMs = performance.now() - pvt.inicio;
    pvtDetener();
    const r = L.resumenPvt(pvt.rts, pvt.anticipadas, pvt.sinRespuesta, pvt.n, duracionMs);
    publicar(`apto/${S.persona}/pvt`, { ...r, linea_base: S.lineaBase, modo_demo: S.demo });
    S.pvt = { fase: "fin", msg: "Prueba terminada", cont: "", contColor: "", res: r };
    pedirPintar();
  }

  // Símbolos (DSST) --------------------------------------------
  const dsst = { activo: false, inicio: 0, correctas: 0, incorrectas: 0, fin: null, reloj: null };

  function entrarDsst() { S.dsst = { fase: "intro", res: null, clave: [], actual: 0 }; }

  function dsstDetener() {
    dsst.activo = false;
    clearTimeout(dsst.fin);
    clearInterval(dsst.reloj);
  }

  function dsstEmpezar() {
    const orden = [...Array(9).keys()];
    for (let i = orden.length - 1; i > 0; i--) {  // clave al azar en cada sesión
      const j = Math.floor(Math.random() * (i + 1));
      [orden[i], orden[j]] = [orden[j], orden[i]];
    }
    Object.assign(dsst, { correctas: 0, incorrectas: 0, inicio: performance.now() });
    dsst.activo = true;
    S.dsst = { fase: "activa", res: null, clave: orden, actual: 0 };
    if (document.activeElement) document.activeElement.blur();
    dsstSiguiente();
    dsst.reloj = setInterval(pedirPintar, 250);
    dsst.fin = setTimeout(dsstTerminar, L.DSST_SEGUNDOS * 1000);
    pedirPintar();
  }

  function dsstSiguiente() {
    let n;
    do { n = 1 + Math.floor(Math.random() * 9); } while (n === S.dsst.actual);  // nunca el mismo dos veces
    S.dsst.actual = n;
  }

  function dsstResponder(n) {
    if (!dsst.activo) return;
    if (n === S.dsst.actual) dsst.correctas += 1;
    else dsst.incorrectas += 1;
    const b = document.querySelector(`.tecla-dsst[data-arg="${n}"]`);
    if (b) { b.classList.add("pulsada"); setTimeout(() => b.classList.remove("pulsada"), 120); }
    dsstSiguiente();
    pedirPintar();
  }

  function dsstTerminar() {
    const duracionMs = performance.now() - dsst.inicio;
    dsstDetener();
    const r = L.resumenDsst(dsst.correctas, dsst.incorrectas, duracionMs);
    publicar(`apto/${S.persona}/dsst`, { ...r, linea_base: S.lineaBase });
    S.dsst = { ...S.dsst, fase: "fin", res: r };
    pedirPintar();
  }

  // Cuestionario y espera del coordinador ----------------------
  function enviarCuestionario() {
    if (S.kss === null) return;
    const texto = (L.KSS.find(([n]) => n === S.kss) || [])[1];
    publicar(`apto/${S.persona}/cuestionario`, { kss: S.kss, kss_texto: texto, horas_sueno: S.horas, linea_base: S.lineaBase });
    irA("resultado");
  }

  function entrarAnalizando() {
    S.anal = { t0: Date.now(), comparando: false, vencida: false, listo: false };
    despues(1200, () => { S.anal.comparando = true; });
    despues(PISTA_ANALIZANDO_MS, () => { S.anal.vencida = true; });
    const ev = S.evaluaciones[S.persona];
    if (ev && ev.sesion === S.sesion) alLlegarEvaluacion();
  }

  function alLlegarEvaluacion() {
    if (S.anal.listo) return;
    S.anal.listo = true;
    S.anal.comparando = true;
    const persona = S.persona, sesion = S.sesion;
    despues(700, () => {
      limpiarTemporizadores();
      abrirResultado(persona, sesion);
      const demo = S.demo, dsstOn = S.conDsst;
      entrarInicio();  // la próxima vez, Evaluación empieza de cero (modo demo y símbolos quedan como estaban)
      S.paso = "inicio";
      S.demo = demo;
      S.conDsst = dsstOn;
    });
  }

  // ================================================================== resultados y copiloto
  function evaluacionVista() {
    const p = S.resPersona || ultimaEvaluada();
    return p ? S.evaluaciones[p] : null;
  }
  function ultimaEvaluada() {
    const evs = Object.values(S.evaluaciones);
    evs.sort((a, b) => (L.tsAMs(b.ts) || 0) - (L.tsAMs(a.ts) || 0));
    return evs.length ? evs[0].persona : "";
  }

  function abrirResultado(persona, sesion) {
    S.resPersona = persona;
    const ev = S.evaluaciones[persona];
    S.chat = { persona, sesion: sesion || (ev && ev.sesion) || "" };
    irPantalla("resultados");
  }

  /** Si la sesión no está en esta pantalla (se abrió después), se pide al registrador. */
  const pedidas = new Set();
  function completarSesion(ev) {
    if (!ev || !ev.sesion || pedidas.has(ev.sesion)) return;
    const d = S.sesiones[ev.sesion];
    if (d && (d.cuestionario || d.pvt)) return;
    pedidas.add(ev.sesion);
    fetch(`sesion.json?sesion=${encodeURIComponent(ev.sesion)}`).then((r) => (r.ok ? r.json() : null)).then((j) => {
      if (!j || !j.disponible) return;
      const d2 = datosSesion(ev.sesion);
      for (const m of j.mensajes || []) {
        if (m.tipo === "esp32") d2.esp32.push(m.datos);
        else if (m.tipo !== "evaluacion") d2[m.tipo] = m.datos;  // vienen de la más vieja a la más nueva
      }
      pedirPintar();
    }).catch(() => {});
  }

  function preguntar(texto) {
    const pregunta = String(texto || "").trim();
    const { persona, sesion } = S.chat;
    if (!pregunta || !persona || !activo("copiloto") || !PUEDE) return;
    mqttc.publicar("apto/control/pregunta", { persona, sesion, pregunta });
    S.pendientes.push({ persona, pregunta, desde: Date.now() });
    pedirPintar();
  }

  let escuchaVence = null;
  function hablar() {
    const { persona, sesion } = S.chat;
    if (!persona || !activo("copiloto") || S.escuchando || !PUEDE) return;
    S.escuchando = true;
    S.escuchaTexto = "Pidiendo el micrófono al copiloto…";
    mqttc.publicar("apto/control/escuchar", { persona, sesion, segundos_max: 10 });
    clearTimeout(escuchaVence);
    escuchaVence = setTimeout(() => { if (S.escuchando) terminarEscucha("El copiloto no respondió al pedido de escuchar."); }, 25000);
    pedirPintar();
  }
  function terminarEscucha(texto) {
    S.escuchando = false;
    clearTimeout(escuchaVence);
    S.escuchaTexto = texto;
    pedirPintar();
  }
  function alEstadoEscucha(d) {
    if (!S.escuchando) return;
    if (d.estado === "escuchando") S.escuchaTexto = "Escuchando… habla ahora (se detiene cuando te callas).";
    else if (d.estado === "transcribiendo") S.escuchaTexto = "Transcribiendo…";
    else if (d.estado === "listo") {
      if (d.texto) S.pendientes.push({ persona: S.chat.persona, pregunta: d.texto, desde: Date.now() });
      terminarEscucha("");
    } else if (d.estado === "error") terminarEscucha(d.motivo || "No se pudo escuchar.");
  }

  // ================================================================== historial (servidor.py -> MongoDB)
  function cargarHistorial() {
    S.hist = { ...S.hist, estado: "cargando" };
    fetch("historial.json?dias=0").then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`)))).then((j) => {
      S.hist = j.disponible ? { estado: "ok", filas: j.filas || [], motivo: "" } : { estado: "error", filas: [], motivo: j.motivo || "MongoDB no responde." };
      completarUltimas(S.hist.filas);
      pedirPintar();
    }).catch((e) => {
      S.hist = { estado: "error", filas: [], motivo: `El servidor no respondió el historial (${e.message}).` };
      pedirPintar();
    });
  }

  /** Con el historial, el Panel muestra pulso, KSS y PVT de la última evaluación aunque la página se haya abierto después. */
  function completarUltimas(filas) {
    const porPersona = {};
    for (const f of filas) if (!porPersona[f.persona] || porPersona[f.persona].fecha < f.fecha) porPersona[f.persona] = f;
    for (const [p, f] of Object.entries(porPersona)) {
      const u = S.ultimas[p] || (S.ultimas[p] = {});
      if (u.kss == null && f.kss != null) u.kss = f.kss;
      if (u.pvt == null && f.pvt_mediana != null) u.pvt = f.pvt_mediana;
      if (u.pulso == null && f.pulso_lpm != null) u.pulso = f.pulso_lpm;
    }
  }

  async function copiar(texto) {
    S.hComando = texto;
    try { await navigator.clipboard.writeText(texto); } catch (e) { /* se muestra igual */ }
    pedirPintar();
  }

  // ================================================================== pruebas de cámara y micrófono (este navegador)
  let camStream = null, micStream = null, lumaIv = null, ac = null, an = null, micRaf = null;

  function errTxt(e, q) {
    const n = e && e.name; const Q = cap(q);
    if (!navigator.mediaDevices) return "Este navegador no permite usar " + q + " aquí. Abre la estación desde localhost o https.";
    if (n === "NotAllowedError" || n === "SecurityError") return "Permiso denegado. Permite el acceso a " + q + " desde el candado de la barra de direcciones y vuelve a intentar.";
    if (n === "NotFoundError" || n === "OverconstrainedError") return "No se encontró " + (q === "la cámara" ? "ninguna cámara" : "ningún micrófono") + ". Conéctalo y vuelve a intentar.";
    if (n === "NotReadableError") return Q + " está en uso por otro programa, por ejemplo vision.py o DroidCam. Ciérralo y vuelve a intentar.";
    return "No se pudo abrir " + q + ". " + ((e && e.message) || n || "");
  }
  async function listarDispositivos() {
    try {
      const ds = await navigator.mediaDevices.enumerateDevices();
      const m = (k, n) => ds.filter((d) => d.kind === k).map((d, i) => ({ id: d.deviceId, label: d.label || n + " " + (i + 1) }));
      S.camDevs = m("videoinput", "Cámara"); S.micDevs = m("audioinput", "Micrófono"); pedirPintar();
    } catch (e) { /* sin lista */ }
  }
  async function iniciarCamaraPrueba() {
    pararCamara(); S.pCam = "pidiendo"; S.camErr = null; pedirPintar();
    try {
      const st = await navigator.mediaDevices.getUserMedia({ video: S.camDev ? { deviceId: { exact: S.camDev } } : { width: { ideal: 1280 }, height: { ideal: 720 } } });
      camStream = st;
      const v = document.getElementById("pru-video");
      if (v) { v.muted = true; v.playsInline = true; v.srcObject = st; await v.play().catch(() => {}); }
      const se = st.getVideoTracks()[0].getSettings();
      S.pCam = "on"; S.camRes = (se.width || "?") + "×" + (se.height || "?"); S.camFps = se.frameRate ? Math.round(se.frameRate) : null;
      const c = document.createElement("canvas"); c.width = 64; c.height = 48; const x = c.getContext("2d", { willReadFrequently: true });
      lumaIv = setInterval(() => {
        const vv = document.getElementById("pru-video"); if (!vv || vv.readyState < 2) return;
        x.drawImage(vv, 0, 0, 64, 48); const d = x.getImageData(0, 0, 64, 48).data; let lum = 0;
        for (let i = 0; i < d.length; i += 4) lum += 0.2126 * d[i] + 0.7152 * d[i + 1] + 0.0722 * d[i + 2];
        S.luz = lum / (d.length / 4); pedirPintar();
      }, 500);
      listarDispositivos();
    } catch (e) { S.pCam = "error"; S.camErr = errTxt(e, "la cámara"); }
    revisarPermisos();
    pedirPintar();
  }
  function pararCamara() {
    clearInterval(lumaIv);
    if (camStream) { camStream.getTracks().forEach((t) => t.stop()); camStream = null; }
    const v = document.getElementById("pru-video"); if (v) v.srcObject = null;
    if (S.pCam === "on" || S.pCam === "pidiendo") { S.pCam = "off"; S.luz = null; pedirPintar(); }
  }
  async function iniciarMic() {
    pararMic(); S.pMic = "pidiendo"; S.micErr = null; S.peakMax = 0; S.noise = null; pedirPintar();
    try {
      const st = await navigator.mediaDevices.getUserMedia({ audio: S.micDev ? { deviceId: { exact: S.micDev } } : true });
      micStream = st; const AC = window.AudioContext || window.webkitAudioContext; ac = new AC();
      const src = ac.createMediaStreamSource(st); an = ac.createAnalyser(); an.fftSize = 1024; src.connect(an);
      const buf = new Float32Array(an.fftSize); let last = 0, sm = 0, floor = 1;
      const loop = (t) => {
        if (!an) return; an.getFloatTimeDomainData(buf); let sum = 0, pk = 0;
        for (let i = 0; i < buf.length; i++) { sum += buf[i] * buf[i]; pk = Math.max(pk, Math.abs(buf[i])); }
        const rms = Math.sqrt(sum / buf.length); sm = sm * 0.75 + rms * 0.25; floor = Math.min(floor * 1.003 + 0.000005, Math.max(sm, 0.00001));
        if (t - last > 60) {
          last = t; const wave = []; for (let i = 0; i < 64; i++) wave.push(buf[i * 16]);
          Object.assign(S, { level: sm, peakMax: Math.max(S.peakMax, pk), noise: floor, wave, pMic: "on" }); pedirPintar();
        }
        micRaf = requestAnimationFrame(loop);
      };
      micRaf = requestAnimationFrame(loop); listarDispositivos();
    } catch (e) { S.pMic = "error"; S.micErr = errTxt(e, "el micrófono"); }
    revisarPermisos();
    pedirPintar();
  }
  function pararMic() {
    cancelAnimationFrame(micRaf); an = null; if (ac) { ac.close(); ac = null; }
    if (micStream) { micStream.getTracks().forEach((t) => t.stop()); micStream = null; }
    if (S.pMic === "on" || S.pMic === "pidiendo") { S.pMic = "off"; S.level = 0; S.wave = []; pedirPintar(); }
  }
  function grabarPrueba() {
    if (!micStream || S.recFase === "grabando" || !window.MediaRecorder) return;
    const ch = []; const mr = new MediaRecorder(micStream);
    mr.ondataavailable = (e) => ch.push(e.data);
    mr.onstop = () => { if (S.recUrl) URL.revokeObjectURL(S.recUrl); S.recFase = "listo"; S.recUrl = URL.createObjectURL(new Blob(ch, { type: mr.mimeType })); pedirPintar(); };
    mr.start(); S.recFase = "grabando"; setTimeout(() => mr.state !== "inactive" && mr.stop(), 3000);
    pedirPintar();
  }

  async function revisarPermisos() {
    if (!navigator.permissions || !navigator.permissions.query) return;
    for (const nombre of ["camera", "microphone"]) {
      try { const r = await navigator.permissions.query({ name: nombre }); S.permisos[nombre] = r.state; } catch (e) { S.permisos[nombre] = ""; }
    }
    pedirPintar();
  }

  // ================================================================== acciones (data-click, data-change, ...)
  Plantilla.acciones({
    nada: () => {},
    ir: (p) => irPantalla(p),
    ocultarSplash: () => { S.splashFuera = true; pedirPintar(); setTimeout(() => { S.splash = false; pedirPintar(); }, 600); },
    abrirModal: () => { S.modal = true; pedirPintar(); },
    cerrarModal: () => { S.modal = false; pedirPintar(); },
    // panel
    tareaPanel: (t) => { S.tareaElegida = t; pedirPintar(); },
    nuevaEvaluacion: () => { if (S.paso !== "inicio") irA("inicio"); irPantalla("evaluacion"); },
    ultimoResultado: () => abrirResultado(ultimaEvaluada()),
    abrirTripulante: (p) => {
      if (S.evaluaciones[p]) abrirResultado(p);
      else { if (S.paso !== "inicio") irA("inicio"); S.persona = p; irPantalla("evaluacion"); }
    },
    // evaluación
    persona: (p) => { S.persona = p; pedirPintar(); },
    tarea: (t) => { S.tarea = t; pedirPintar(); },
    opcion: (k, e, el) => { S[k] = el.checked; pedirPintar(); },
    comenzar,
    siguiente: () => mover(1),
    anterior: () => mover(-1),
    vista: (v) => { S.vista = v; pedirPintar(); },
    camIniciar: iniciarCamara,
    camReiniciar: () => { if (S.camFase !== "midiendo") { entrarCamara(); pedirPintar(); } },
    frase: (f) => { if (!["esperando", "grabando", "analizando"].includes(S.vozFase)) { S.fraseVoz = f; pedirPintar(); } },
    grabar: grabarVoz,
    pvtEmpezar,
    pvt: (a, e) => { e.preventDefault(); pvtResponder(tiempoDelEvento(e)); },
    dsstEmpezar,
    dsst: (n) => dsstResponder(Number(n)),
    kss: (n) => { S.kss = Number(n); pedirPintar(); },
    horas: (d) => { S.horas = Math.max(0, Math.min(16, S.horas + Number(d))); pedirPintar(); },
    enviarCuestionario,
    // resultados
    preguntar: (a, e, form) => { const i = form.querySelector("input"); preguntar(i.value); i.value = ""; },
    hablar,
    // historial
    periodo: (k) => { S.periodo = k; S.hPag = 0; pedirPintar(); },
    hPersona: (p) => { S.hPersona = p; S.hSel = null; S.hPag = 0; pedirPintar(); },
    serie: (k) => { S.serie = k; pedirPintar(); },
    hSel: (id) => { S.hSel = id; S.hComando = ""; pedirPintar(); },
    hPag: (p) => { S.hPag = Number(p); pedirPintar(); },
    recargarHistorial: cargarHistorial,
    reproducir: (id) => {
      const f = S.hist.filas.find((x) => x.id === id);
      if (f) copiar(`python registrador\\reproducir.py --persona ${f.persona} --sesion ${f.id}`);
    },
    verResultadoHist: (id) => {
      const f = S.hist.filas.find((x) => x.id === id);
      if (f && S.evaluaciones[f.persona] && S.evaluaciones[f.persona].sesion === f.id) abrirResultado(f.persona);
    },
    // pruebas
    pruCam: iniciarCamaraPrueba, pruCamStop: pararCamara, pruMic: iniciarMic, pruMicStop: pararMic, pruGrabar: grabarPrueba,
    camDev: (a, e, el) => { S.camDev = el.value; if (S.pCam === "on") iniciarCamaraPrueba(); },
    micDev: (a, e, el) => { S.micDev = el.value; if (S.pMic === "on") iniciarMic(); },
    // configuración
    icono: (arg) => { const [p, i] = arg.split("|"); S.iconos = { ...S.iconos, [p]: i }; guardar("becspace-iconos-v2", S.iconos); pedirPintar(); },
    tema: (k) => { S.tema = k; guardar("becspace-tema", k); aplicarTema(); Fondo.reconstruir(); pedirPintar(); },
    pref: (k) => {
      S.prefs = { ...S.prefs, [k]: !S.prefs[k] }; guardar("becspace-prefs", S.prefs); aplicarPrefs();
      if (k === "movimiento") Fondo.despertar();
      pedirPintar();
    },
    buscarCamaras: () => { S.verComandoCamaras = !S.verComandoCamaras; pedirPintar(); },
  });

  document.addEventListener("keydown", (e) => {
    if (S.pantalla !== "evaluacion") return;
    if (S.paso === "reaccion" && pvt.activo && (e.code === "Space" || e.key === " ")) {
      e.preventDefault();
      if (!e.repeat) pvtResponder(tiempoDelEvento(e));
    } else if (S.paso === "simbolos" && dsst.activo && /^[1-9]$/.test(e.key)) {
      e.preventDefault();
      if (!e.repeat) dsstResponder(Number(e.key));
    }
  });
  window.addEventListener("resize", () => { S.w = window.innerWidth; pedirPintar(); });
  setInterval(() => { if (S.pantalla === "dashboard" || (S.pantalla === "resultados" && S.pendientes.length)) pedirPintar(); }, 5000);

  // ================================================================== vistas: piezas comunes
  const etq = (texto, extra = "") => h`<span style="${ETQ}${extra}">${texto}</span>`;
  const pildora = (st, texto, extra = "") => h`<span style="display:inline-flex;align-items:center;gap:6px;padding:3px 9px;border-radius:5px;background:${st.bg};color:${st.fg};${MONO};font-size:12px;font-weight:600;letter-spacing:0.06em;white-space:nowrap;${extra}"><i class="ph-fill ${st.icon}"></i>${texto || st.word}</span>`;
  const tagMono = (texto, clase = "tag-neutral") => h`<span class="tag ${clase}" style="${MONO};font-size:10px">${texto}</span>`;
  const alerta = (st, icono, titulo, texto, rol = "status") => h`<div role="${rol}" style="display:flex;gap:10px;align-items:flex-start;padding:10px 14px;border-radius:var(--radius-md);background:${st.bg}">
      <i class="ph ${icono}" style="font-size:18px;color:${st.fg};flex:none"></i>
      <span style="display:flex;flex-direction:column;gap:2px"><b style="font-weight:500;color:${st.fg}">${titulo}</b><span style="font-size:13px;color:var(--color-neutral-200)">${texto}</span></span></div>`;
  const nota = (icono, texto) => h`<div style="display:flex;gap:10px;align-items:center;padding:14px 16px;border-radius:var(--radius-md);box-shadow:inset 0 0 0 1px var(--color-neutral-800)"><i class="ph ${icono}" style="font-size:18px;color:var(--color-neutral-400);flex:none"></i><span style="font-size:13px;color:var(--color-neutral-300);text-wrap:pretty">${texto}</span></div>`;
  const cmd = (texto) => h`<code style="${MONO};font-size:11px;color:var(--color-neutral-500);word-break:break-all">${texto}</code>`;
  const segOpciones = (nombre, aria, opciones, accion, extra = "") => h`<div class="seg" role="radiogroup" aria-label="${aria}" style="flex-wrap:wrap;${extra}">
      ${opciones.map(([valor, label, on, icono]) => h`<label class="seg-opt"><input type="radio" name="${nombre}" ${si(on, "checked")} data-change="${accion}" data-arg="${valor}">${icono ? h`<i class="ph ${icono}"></i>` : ""}<span>${label}</span></label>`)}
    </div>`;
  const tarjetaDato = (label, valor, unidad, tamano = 28, extra = "") => h`<div style="display:flex;flex-direction:column;gap:4px;padding:14px;${TARJ}"><span style="font-size:12px;color:var(--color-neutral-300)">${label}</span><span style="${MONO};font-size:${tamano}px;font-variant-numeric:tabular-nums;${extra}">${valor}</span><span style="font-size:11px;color:var(--color-neutral-400)">${unidad}</span></div>`;

  function estadoBroker() {
    const e = S.conexion;
    if (!window.APTO) return { st: ST.rojo, corto: "SIN CONFIG", largo: "Falta config.js: abran la página desde paneles/servidor.py", icon: "ph-plugs" };
    if (e === "ok") return { st: ST.verde, corto: "CONECTADO", largo: "Broker conectado", icon: "ph-plugs-connected" };
    if (e === "conectando") return { st: ST.amarillo, corto: "CONECTANDO", largo: "Conectando al broker…", icon: "ph-plugs" };
    if (e === "reconectando") return { st: ST.amarillo, corto: "SIN CONEXIÓN", largo: "Broker sin conexión: reintentando", icon: "ph-plugs" };
    return { st: ST.rojo, corto: "SIN CONECTAR", largo: S.conexionTexto || "Broker sin conectar", icon: "ph-plugs" };
  }

  // ================================================================== vista: armazón
  function vistaApp() {
    const wide = S.w >= 900;
    const meta = NAV.find((n) => n[0] === S.pantalla) || NAV[0];
    const broker = estadoBroker();
    let kicker = meta[3];
    if (S.pantalla === "resultados") {
      const ev = evaluacionVista();
      kicker = ev ? `${L.nombre(ev.persona)} · ${cuando(L.tsAMs(ev.ts))}` : "Sin evaluación";
    }
    const personaCab = S.pantalla === "resultados" ? (evaluacionVista() || {}).persona : S.pantalla === "evaluacion" ? S.persona : "";
    return h`
<div style="position:relative;z-index:1;display:flex;min-height:100vh;flex-direction:${wide ? "row" : "column"}">
  <nav aria-label="Navegación principal" style="flex:none;display:flex;flex-direction:${wide ? "column" : "row"};align-items:${wide ? "stretch" : "center"};gap:4px;padding:${wide ? "18px 12px" : "8px 12px"};width:${wide ? "232px" : "100%"};background:var(--nav-bg);backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);position:sticky;top:0;z-index:20;overflow-x:auto;box-shadow:${wide ? "inset -1px 0 0 var(--color-neutral-900)" : "inset 0 -1px 0 var(--color-neutral-900)"};height:${wide ? "100vh" : "auto"}">
    <div style="display:flex;align-items:center;gap:10px;padding:10px 8px 26px;flex:none">
      <div style="display:flex;flex-direction:column;gap:10px;padding:6px 0 4px">
        <div style="width:196px" data-congelar="logo-compact-${S.tema}">${logo("barra", "compact", S.tema === "claro" ? "light" : "dark")}</div>
        <span style="padding-left:6px;margin-top:0;font-size:9.5px;letter-spacing:0.16em;text-transform:uppercase;color:var(--color-neutral-400);${MONO}">Estación de monitoreo</span>
      </div>
    </div>
    ${NAV.map(([id, label, icon]) => {
      const on = S.pantalla === id;
      return h`<button type="button" class="hv-nav" data-click="ir" data-arg="${id}" aria-current="${on ? "page" : "false"}" style="display:flex;align-items:center;gap:10px;padding:8px 10px;border:0;border-radius:var(--radius-md);background:${on ? "var(--color-accent-900)" : "transparent"};color:${on ? "var(--color-accent-200)" : "var(--color-neutral-300)"};box-shadow:${on ? "inset 2px 0 0 var(--color-accent)" : "none"};cursor:pointer;text-align:left;font-size:14px;white-space:nowrap;flex:none">
        <i class="ph ${icon}" style="font-size:18px"></i><span>${label}</span></button>`;
    })}
    ${wide ? h`<div style="margin-top:auto;padding:12px 10px;display:flex;flex-direction:column;gap:8px;font-size:12px;color:var(--color-neutral-400)">
        <div style="display:flex;align-items:center;gap:8px"><i class="ph ph-broadcast" style="font-size:15px;color:${broker.st.fg}"></i><span>${broker.largo}</span></div>
        <div style="display:flex;align-items:center;gap:8px"><i class="ph ${PUEDE ? "ph-pencil-simple" : "ph-eye"}" style="font-size:15px;color:var(--color-accent-300)"></i><span>${PUEDE ? "Estación: puede publicar" : "Solo lectura"}</span></div>
      </div>` : ""}
  </nav>
  <div style="flex:1;min-width:0;display:flex;flex-direction:column">
    <header style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;padding:14px 24px;background:linear-gradient(to right, transparent, var(--color-divider) 48px, var(--color-divider) calc(100% - 48px), transparent) no-repeat bottom / 100% 1px;background-color:color-mix(in srgb, var(--color-bg) 35%, transparent);backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px)">
      <div style="display:flex;flex-direction:column;gap:2px;margin-right:auto;min-width:0">
        <span style="font-size:11px;letter-spacing:0.12em;text-transform:uppercase;color:var(--color-neutral-400);${MONO}">${kicker}</span>
        <h1 style="font-size:22px;margin:0">${meta[4]}</h1>
      </div>
      ${PUEDE ? "" : h`<span title="Desde otra laptop solo se puede mirar: el usuario de solo lectura no publica" style="display:inline-flex;align-items:center;gap:6px;padding:3px 9px;border:1px dashed var(--color-accent-500);border-radius:6px;${MONO};font-size:11px;letter-spacing:0.1em;color:var(--color-accent-300)"><i class="ph ph-eye"></i>SOLO LECTURA</span>`}
      <span title="${broker.largo}" style="display:inline-flex;align-items:center;gap:6px;padding:3px 10px;border-radius:999px;box-shadow:inset 0 0 0 1px var(--color-neutral-700);${MONO};font-size:11px;letter-spacing:0.08em;color:${S.conexion === "ok" ? broker.st.fg : "var(--color-neutral-300)"}"><i class="ph ${broker.icon}"></i>BROKER · ${broker.corto}</span>
      ${personaCab ? h`<span style="display:inline-flex;align-items:center;gap:6px;font-size:13px;color:var(--color-neutral-300)"><i class="ph ph-user-circle" style="font-size:18px"></i>${L.nombre(personaCab)}</span>` : ""}
    </header>
    <main id="principal" style="flex:1;padding:24px;display:flex;flex-direction:column;gap:20px;max-width:1360px;width:100%;box-sizing:border-box">
      ${{ dashboard: vistaPanel, evaluacion: vistaEvaluacion, pruebas: vistaPruebas, resultados: vistaResultados, historial: vistaHistorial, config: vistaConfig, sistema: vistaSistema }[S.pantalla]()}
    </main>
  </div>
</div>
${S.splash ? vistaSplash() : ""}
${S.modal ? vistaModal() : ""}`;
  }

  function vistaSplash() {
    return h`<div role="status" aria-label="Cargando la estación" data-click="ocultarSplash" style="position:fixed;inset:0;z-index:80;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:18px;background:radial-gradient(80% 70% at 50% 45%, #0B1430, #060913);opacity:${S.splashFuera ? "0" : "1"};transition:opacity .6s;cursor:pointer">
    <div style="width:min(78vw,560px)" data-congelar="logo-splash">${logo("carga", "full", "dark")}</div>
    <div style="display:flex;flex-direction:column;align-items:center;gap:8px"><span style="${MONO};font-size:11px;letter-spacing:0.18em;text-transform:uppercase;color:#A7B3CC">Cargando estación de monitoreo</span><div style="width:180px;height:2px;border-radius:1px;background:rgba(125,145,210,0.2);overflow:hidden"><div style="height:100%;width:${S.splashVa ? "100%" : "0%"};background:#00C896;transition:width 1.8s ease-out"></div></div></div>
  </div>`;
  }

  function vistaModal() {
    return h`<div class="dialog-backdrop" data-click="cerrarModal" style="z-index:50">
    <div class="dialog" role="dialog" aria-modal="true" aria-labelledby="dlg-t" data-click="nada">
      <div id="dlg-t" class="dialog-title">¿Borrar tu historial?</div>
      <div class="dialog-body">Se borran tus evaluaciones guardadas en esta laptop. Tu línea base también se reinicia y las próximas mediciones no tendrán con qué compararse.</div>
      <div style="font-size:12px;color:var(--color-neutral-400)">Pendiente: el borrado todavía no está conectado al registrador. Por ahora se hace en MongoDB (colección mensajes) y en datos\\coordinador\\linea_base.jsonl.</div>
      <div class="dialog-actions"><button class="btn btn-ghost" type="button" data-click="cerrarModal">Cancelar</button><button class="btn btn-primary" type="button" disabled title="Todavía no está conectado al registrador">Borrar</button></div>
    </div>
  </div>`;
  }

  // ================================================================== vista: Panel
  function tareaPanel() {
    if (S.tareaElegida) return S.tareaElegida;
    if (S.tareaSesion) return S.tareaSesion;
    const evs = Object.values(S.evaluaciones).filter((e) => e.tarea);
    evs.sort((a, b) => (L.tsAMs(b.ts) || 0) - (L.tsAMs(a.ts) || 0));
    return evs.length ? evs[0].tarea : TAREAS[0];
  }

  function vistaPanel() {
    const tarea = tareaPanel();
    const evs = S.evaluaciones;
    const r = L.recomendacion(evs, tarea);
    const rst = ST[r.mejor ? r.mejor.color : "sin"] || ST.sin;
    const crew = TRIPULACION();
    const cnt = { verde: 0, amarillo: 0, rojo: 0, sin: 0 };
    crew.forEach((p) => { cnt[evs[p] && ST[evs[p].color] ? evs[p].color : "sin"]++; });
    const tareas = TAREAS.includes(tarea) ? TAREAS : TAREAS.concat([tarea]);
    const provisional = Object.values(evs).some((e) => e.provisional);
    const conSpo2 = crew.filter((p) => evs[p] && evs[p].aviso_spo2);
    const resp = S.copiloto.slice(0, 6);
    return h`<div data-k="panel" style="display:contents">
  <section style="position:relative;overflow:hidden;display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,340px),1fr));gap:20px;padding:22px;border-radius:var(--radius-lg);background:linear-gradient(135deg, var(--color-surface), color-mix(in srgb, var(--color-surface) 40%, var(--color-bg)));box-shadow:var(--shadow-sm)">
    <svg aria-hidden="true" viewBox="0 0 600 300" style="position:absolute;right:-120px;top:-90px;width:560px;opacity:.5;pointer-events:none"><ellipse cx="300" cy="150" rx="280" ry="90" fill="none" stroke="var(--color-accent-800)" stroke-width="1" transform="rotate(-14 300 150)"></ellipse><ellipse cx="300" cy="150" rx="200" ry="60" fill="none" stroke="var(--color-neutral-800)" stroke-width="1" transform="rotate(-14 300 150)"></ellipse><circle cx="528" cy="88" r="3" fill="var(--color-accent)"></circle></svg>
    <div style="position:relative;display:flex;flex-direction:column;gap:12px">
      <span style="font-size:11px;letter-spacing:0.12em;text-transform:uppercase;color:var(--color-accent-300);${MONO}">Recomendación · ${cap(tarea)}</span>
      <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">
        <span style="display:inline-flex;align-items:center;gap:7px;padding:5px 12px;border-radius:6px;background:${rst.bg};color:${rst.fg};${MONO};font-size:13px;font-weight:600;letter-spacing:0.08em"><i class="ph-fill ${rst.icon}" style="font-size:16px"></i>${rst.word}</span>
        <h2 style="font-size:30px;margin:0">${r.mejor ? L.nombre(r.mejor.persona) : "Sin datos"}</h2>
      </div>
      <p style="margin:0;font-size:15px;line-height:1.55;color:var(--color-neutral-200);max-width:60ch;text-wrap:pretty" aria-live="polite">${r.texto}</p>
      <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:4px">
        <button class="btn btn-primary" type="button" data-click="nuevaEvaluacion" style="padding:9px 16px"><i class="ph ph-play"></i>Nueva evaluación</button>
        <button class="btn btn-secondary" type="button" data-click="ultimoResultado" ${si(!r.mejor, "disabled")} style="padding:9px 16px">Ver último resultado</button>
      </div>
    </div>
    <div style="position:relative;display:flex;flex-direction:column;gap:10px">
      ${etq("Tarea a asignar")}
      ${segOpciones("tarea-dash", "Tarea", tareas.map((t) => [t, cap(t), t === tarea]), "tareaPanel")}
      <div style="display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin-top:6px">
        ${["verde", "amarillo", "rojo", "sin"].map((c) => h`<div style="display:flex;flex-direction:column;gap:2px;padding:10px;border-radius:var(--radius-md);background:color-mix(in srgb, var(--color-bg) 55%, transparent)">
            <span style="display:flex;align-items:center;gap:5px;font-size:11px;color:${ST[c].fg}"><i class="ph-fill ${ST[c].icon}"></i>${c === "sin" ? "Pendiente" : cap(c)}</span>
            <span style="${MONO};font-size:24px;font-variant-numeric:tabular-nums">${cnt[c]}</span></div>`)}
      </div>
    </div>
  </section>

  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,420px),1fr));gap:20px;align-items:start">
    <section style="display:flex;flex-direction:column;gap:10px">
      <div style="display:flex;align-items:baseline;gap:10px"><h2 style="font-size:17px;margin:0">Tripulación</h2><span style="font-size:12px;color:var(--color-neutral-400)">Última evaluación de cada integrante</span></div>
      <div style="display:flex;flex-direction:column;gap:8px">
        ${crew.length ? crew.map((p) => {
          const e = evs[p]; const u = S.ultimas[p] || {}; const st = (e && ST[e.color]) || ST.sin;
          const vivo = u.pulsoLlegada && Date.now() - u.pulsoLlegada < PULSO_VIGENTE_MS;
          return h`<button type="button" class="hv-crew" data-click="abrirTripulante" data-arg="${p}" style="display:flex;flex-direction:column;gap:8px;padding:12px 16px;border:0;border-radius:var(--radius-md);background:var(--color-surface);box-shadow:inset 3px 0 0 ${st.fg}, inset 0 0 0 1px var(--card-edge);text-align:left;cursor:pointer;transition:transform .2s, background-color .2s;width:100%;min-width:0">
            <span style="display:flex;align-items:center;gap:10px 14px;flex-wrap:wrap;width:100%">
              <span style="display:flex;align-items:center;gap:7px;font-size:16px;font-weight:500"><i class="ph-fill ${icono(p)}" style="font-size:18px;color:var(--color-accent-300)"></i>${L.nombre(p)}</span>
              <span style="${MONO};font-size:11px;color:var(--color-neutral-400)">${e ? cuando(L.tsAMs(e.ts)) : "sin evaluación"}</span>
              ${pildora(st)}
              ${e && e.simulado ? tagMono("SIMULADO") : ""}
              <span style="margin-left:auto;display:flex;gap:16px;flex-wrap:wrap;${MONO};font-size:13px;color:var(--color-neutral-200);font-variant-numeric:tabular-nums">
                <span title="${vivo ? "Pulso en vivo" : "Pulso"}">${vivo ? h`<i class="ph-fill ph-heart" style="color:var(--st-rojo);font-size:11px;animation:pulso 1.4s ease-in-out infinite"></i> ` : ""}${entero(u.pulso)}<span style="color:var(--color-neutral-500);font-size:11px"> lpm</span></span>
                <span title="Somnolencia KSS">KSS ${entero(u.kss)}</span>
                <span title="Mediana PVT">${entero(u.pvt)}<span style="color:var(--color-neutral-500);font-size:11px"> ms</span></span>
              </span>
            </span>
            <span style="font-size:13px;line-height:1.45;color:var(--color-neutral-300);text-wrap:pretty;max-width:80ch">${e ? ((e.motivos || []).length ? e.motivos.join(" · ") : "Sin motivos de alerta") : "Pendiente de evaluar"}</span>
          </button>`;
        }) : nota("ph-users-three", "No hay TRIPULACION en config.env.")}
      </div>
    </section>
    <div style="display:flex;flex-direction:column;gap:20px">
      <section style="display:flex;flex-direction:column;gap:10px;padding:16px;${TARJ}">
        <div style="display:flex;align-items:center;gap:8px"><h2 style="font-size:15px;margin:0;margin-right:auto">Módulos</h2><span style="font-size:12px;color:var(--color-neutral-400)">${MODULOS.filter(([m]) => activo(m)).length} de ${MODULOS.length} activos</span></div>
        ${MODULOS.map(([m, nombre, comando]) => h`<div style="display:flex;align-items:flex-start;gap:10px;padding:6px 0">
            <i class="ph-fill ${activo(m) ? "ph-check-circle" : "ph-x-circle"}" style="font-size:16px;margin-top:1px;color:${activo(m) ? ST.verde.fg : ST.rojo.fg}"></i>
            <div style="display:flex;flex-direction:column;gap:1px;min-width:0;flex:1">
              <span style="font-size:13px"><b style="font-weight:500">${nombre}</b> <span style="color:var(--color-neutral-400)">${activo(m) ? "activo" : "no está abierto"}</span></span>
              ${activo(m) ? "" : cmd(comando)}
            </div>
            ${m === "coordinador" && provisional ? tagMono("PROVISIONAL") : ""}
          </div>`)}
      </section>
      ${conSpo2.length ? h`<section role="status" style="display:flex;gap:12px;padding:14px 16px;border-radius:var(--radius-md);background:${ST.amarillo.bg};box-shadow:inset 0 0 0 1px color-mix(in srgb, ${ST.amarillo.fg} 40%, transparent)">
        <i class="ph ph-warning" style="font-size:20px;color:${ST.amarillo.fg};flex:none"></i>
        <div style="display:flex;flex-direction:column;gap:4px">
          <b style="font-weight:500;color:${ST.amarillo.fg}">Oxígeno más bajo de lo habitual en ${L.lista(conSpo2.map(L.nombre))}</b>
          <span style="font-size:13px;color:var(--color-neutral-200)">Es un aviso, no cambia el color. Repetir la medición con el sensor antes de la tarea.</span>
        </div>
      </section>` : ""}
      <section style="display:flex;gap:12px;padding:14px 16px;border-radius:var(--radius-md);box-shadow:inset 0 0 0 1px var(--color-neutral-800)">
        <i class="ph ph-info" style="font-size:20px;color:var(--color-neutral-400);flex:none"></i>
        <span style="font-size:13px;color:var(--color-neutral-300);text-wrap:pretty">Indicadores orientativos para apoyar la decisión. No es un diagnóstico médico ni una certificación de aptitud.</span>
      </section>
      <section style="display:flex;flex-direction:column;gap:10px;padding:16px;${TARJ}">
        <div style="display:flex;align-items:center;gap:8px"><h2 style="font-size:15px;margin:0;margin-right:auto">Becspace AI · últimas respuestas</h2>${activo("copiloto") ? "" : h`<span style="font-size:12px;color:var(--color-neutral-400)">copiloto sin abrir</span>`}</div>
        ${resp.length ? resp.map((d) => h`<div style="display:flex;flex-direction:column;gap:4px;padding:6px 0">
            <span style="${MONO};font-size:10px;color:var(--color-neutral-500)">${L.nombre(d.persona)} · ${L.hora(L.tsAMs(d.ts))}${d.modo ? " · " + d.modo : ""}</span>
            ${d.pregunta ? h`<span style="font-size:13px;color:var(--color-neutral-300)">${d.pregunta === "(resumen automático)" ? "Resumen automático" : `«${d.pregunta}»`}</span>` : ""}
            <span style="font-size:13px;line-height:1.5">${d.respuesta || ""}</span></div>`)
          : h`<span style="font-size:13px;color:var(--color-neutral-400)">Todavía no hay respuestas.</span>`}
      </section>
    </div>
  </div>
</div>`;
  }

  // ================================================================== vista: Evaluación
  function botonera(primario, opciones = {}) {
    return h`<div style="display:flex;gap:8px;justify-content:flex-end;flex-wrap:wrap">
      <button class="btn btn-ghost" type="button" data-click="anterior" style="margin-right:auto"><i class="ph ph-arrow-left"></i>Atrás</button>
      ${opciones.sinOmitir ? "" : h`<button class="btn btn-secondary" type="button" data-click="siguiente" style="padding:9px 16px">Omitir</button>`}
      ${opciones.extra || ""}
      ${primario}
    </div>`;
  }
  const botonPrimario = (texto, accion, deshabilitado, icono = "ph-arrow-right", antes = false) => h`<button class="btn btn-primary" type="button" data-click="${accion}" ${si(deshabilitado, "disabled")} style="padding:9px 18px">${antes ? h`<i class="ph ${icono}"></i>` : ""}${texto}${antes ? "" : h`<i class="ph ${icono}"></i>`}</button>`;
  const titulo = (t, texto, ancho = "") => h`<div style="display:flex;flex-direction:column;gap:6px"><h2 style="font-size:26px;margin:0">${t}</h2><p style="margin:0;color:var(--color-neutral-300);${ancho}">${texto}</p></div>`;

  function vistaEvaluacion() {
    const pl = pasosActivos();
    const cur = pl.indexOf(S.paso);
    const wide = S.w >= 900;
    const vistas = { inicio: vInicio, dispositivo: vDispositivo, camara: vCamara, voz: vVoz, reaccion: vPvt, simbolos: vDsst, cuestionario: vKss, resultado: vAnalizando };
    return h`<div data-k="eval-${S.paso}" style="display:contents">
  <ol aria-label="Pasos de la evaluación" style="display:flex;gap:4px;margin:0;padding:0;list-style:none;overflow-x:auto;scrollbar-width:none">
    ${pl.map((p, i) => h`<li aria-current="${i === cur ? "step" : "false"}" style="flex:1 0 auto;display:flex;align-items:center;gap:7px;padding:8px 10px 0;border-top:2px solid ${i === cur ? "var(--color-accent)" : i < cur ? "var(--color-accent-700)" : "var(--color-neutral-800)"};color:${i === cur ? "var(--color-text)" : i < cur ? "var(--color-neutral-300)" : "var(--color-neutral-500)"};font-size:12px;white-space:nowrap">
        <i class="ph ${i < cur ? "ph-check" : PASO_INFO[p][1]}" style="font-size:15px"></i><span style="${MONO};font-size:11px">${dd(i + 1)}</span><span style="display:${wide || i === cur ? "inline" : "none"}">${PASO_INFO[p][0]}</span></li>`)}
  </ol>
  ${vistas[S.paso]()}
</div>`;
  }

  function vInicio() {
    const broker = estadoBroker();
    const listo = S.persona && S.tarea && PUEDE;
    const checks = [
      { label: "Broker", st: broker.st, estado: broker.corto.toLowerCase(), help: S.conexion === "ok" ? `WebSocket en ${location.hostname || "localhost"}:${CFG.mqtt_puerto_ws || 9001}.` : broker.largo },
      ...MODULOS.map(([m, nombre, comando]) => ({ label: nombre, st: activo(m) ? ST.verde : ST.rojo, estado: activo(m) ? "activo" : "no está abierto",
        help: activo(m) ? (m === "coordinador" ? "Calcula el semáforo al terminar el cuestionario." : "Listo para medir.") : comando })),
    ];
    const opciones = [
      ["lineaBase", "Medición de línea base", "Márcala si hoy descansaste bien: esta medición servirá para comparar las siguientes."],
      ["demo", "Modo demo (1 min)", "La prueba de reacción dura 1 minuto en vez de 3. Queda anotado en el resultado."],
      ["conDsst", "Prueba de símbolos (90 s)", "Además de la de reacción: emparejar símbolos con números lo más rápido posible."],
    ];
    const crew = CFG.tripulacion || [];
    return h`<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,380px),1fr));gap:24px;align-items:start">
      <div style="display:flex;flex-direction:column;gap:18px">
        ${titulo("Nueva evaluación", "Elige quién se evalúa y para qué tarea. Luego el sistema mide con el sensor, la cámara y la voz, y hace dos pruebas cortas.", "max-width:56ch")}
        ${PUEDE ? "" : alerta(ST.amarillo, "ph-eye", "Solo lectura", "Abriste la estación desde otra laptop: el usuario de solo lectura no puede publicar. Para evaluar, usen la laptop de la estación (http://localhost:8080/estacion.html).")}
        <div style="display:flex;flex-direction:column;gap:8px">
          ${etq("¿Quién se evalúa?")}
          <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(110px,1fr));gap:8px">
            ${crew.length ? crew.map((p) => h`<button type="button" class="hv-acc" aria-pressed="${String(S.persona === p)}" data-click="persona" data-arg="${p}" style="min-height:56px;padding:10px;border:0;border-radius:var(--radius-md);background:${S.persona === p ? "var(--color-accent-900)" : "var(--color-surface)"};box-shadow:${S.persona === p ? "inset 0 0 0 1px var(--color-accent)" : "inset 0 0 0 1px transparent"};font-size:17px;font-weight:500;cursor:pointer"><span style="display:inline-flex;align-items:center;gap:8px"><i class="ph-fill ${icono(p)}" style="font-size:20px;color:var(--color-accent-300)"></i>${L.nombre(p)}</span></button>`)
              : h`<span style="font-size:13px;color:var(--color-neutral-400)">No hay TRIPULACION en config.env.</span>`}
          </div>
        </div>
        <div style="display:flex;flex-direction:column;gap:8px">
          ${etq("Tarea")}
          ${segOpciones("tarea-ev", "Tarea", TAREAS.map((t) => [t, cap(t), S.tarea === t]), "tarea", "align-self:flex-start")}
        </div>
        <div style="display:flex;flex-direction:column;gap:8px">
          ${opciones.map(([k, label, help]) => h`<label style="display:flex;gap:12px;align-items:flex-start;padding:12px 14px;border-radius:var(--radius-md);background:var(--color-surface);cursor:pointer;box-shadow:inset 0 0 0 1px var(--card-edge)">
              <input type="checkbox" ${si(S[k], "checked")} data-change="opcion" data-arg="${k}" style="width:18px;height:18px;margin:1px 0 0;accent-color:var(--color-accent);flex:none">
              <span style="display:flex;flex-direction:column;gap:2px"><span style="font-weight:500">${label}</span><span style="font-size:12px;color:var(--color-neutral-400)">${help}</span></span>
            </label>`)}
        </div>
      </div>
      <div style="display:flex;flex-direction:column;gap:12px;padding:18px;${TARJ}">
        ${etq("Verificación de condiciones")}
        ${checks.map((ck) => h`<div style="display:flex;gap:10px;align-items:flex-start">
            <i class="ph-fill ${ck.st.icon}" style="font-size:17px;color:${ck.st.fg};margin-top:1px"></i>
            <div style="display:flex;flex-direction:column;gap:1px"><span style="font-size:13px"><b style="font-weight:500">${ck.label}</b> <span style="color:${ck.st.fg}">${ck.estado}</span></span><span style="font-size:12px;color:var(--color-neutral-400)">${ck.help}</span></div>
          </div>`)}
        <div style="display:flex;gap:8px;justify-content:flex-end;align-items:center;margin-top:8px">
          ${listo ? "" : h`<span style="font-size:12px;color:var(--color-neutral-400);margin-right:auto">${PUEDE ? "Elige persona y tarea para comenzar." : "Solo lectura: no se puede comenzar aquí."}</span>`}
          ${botonPrimario("Comenzar", "comenzar", !listo)}
        </div>
      </div>
    </div>`;
  }

  function vDispositivo() {
    const d = S.esp32;
    const [tipoEstado, textoEstado] = estadoEsp32();
    const tag = d ? (d.simulado ? "SIMULADO" : "EN VIVO") : "";
    const tarjetas = [
      { label: "Pulso", icon: "ph-heartbeat", valor: d ? entero(d.pulso_lpm) : "–", unidad: "latidos por minuto" },
      { label: "HRV", icon: "ph-wave-sine", valor: d ? entero(d.hrv_rmssd_ms) : "–", unidad: "ms (RMSSD de 30 s)" },
      { label: "SpO₂", icon: "ph-drop", valor: d && num(d.spo2) !== null ? L.decimal(d.spo2, 0) : "–", unidad: "% de oxígeno en sangre" },
      { label: "Movimiento", icon: "ph-hand", valor: d ? fmt(d.movimiento) : "–", unidad: d && num(d.movimiento) !== null ? (d.movimiento > 0.05 ? "g · en movimiento" : "g · quieto") : "g" },
    ];
    const n = S.ppg.length;
    const px = (i) => ((160 - n + i) * 600) / 159;
    const py = (v) => Math.round((110 - v * 88) * 10) / 10;
    const pts = S.ppg.map((v, i) => px(i).toFixed(1) + "," + py(v)).join(" ");
    const cab = n ? { x: px(n - 1), y: py(S.ppg[n - 1]) } : { x: -10, y: -10 };
    const late = performance.now() - S.latido < 170;
    const iconoEstado = { ok: ["ph-check-circle", ST.verde.fg], aviso: ["ph-warning-circle", ST.amarillo.fg], espera: ["ph-circle-notch", "var(--color-accent-300)"] }[tipoEstado];
    return h`${titulo("Dispositivo", "Colócate el sensor en el dedo y quédate sin moverte.")}
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,200px),1fr));gap:12px">
      ${tarjetas.map((t) => h`<div style="display:flex;flex-direction:column;gap:6px;padding:16px;${TARJ}">
          <span style="display:flex;align-items:center;gap:6px;font-size:12px;color:var(--color-neutral-300)"><i class="ph ${t.icon}" style="font-size:16px;color:var(--color-accent)"></i>${t.label}<span style="margin-left:auto;${MONO};font-size:10px;color:var(--color-accent-300)">${tag}</span></span>
          <span style="${MONO};font-size:40px;line-height:1.05;font-variant-numeric:tabular-nums">${t.valor}</span>
          <span style="font-size:12px;color:var(--color-neutral-400)">${t.unidad}</span>
        </div>`)}
    </div>
    <div style="display:flex;flex-direction:column;gap:8px;padding:16px;border-radius:var(--radius-md);background:var(--color-surface);box-shadow:var(--shadow-sm)">
      <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
        <i class="ph-fill ph-heart" style="font-size:17px;color:var(--st-rojo);transform:scale(${late ? "1.3" : "1"});transition:transform .12s ease-out"></i>
        <span style="font-size:13px;font-weight:500">Pulso en tiempo real</span>
        <span style="font-size:12px;color:var(--color-neutral-400)">fotopletismografía · sensor del dedo</span>
        <span style="margin-left:auto;${MONO};font-size:15px;font-variant-numeric:tabular-nums">${d ? entero(d.pulso_lpm) : "–"}<span style="font-size:11px;color:var(--color-neutral-400)"> lpm</span></span>
        <span style="${MONO};font-size:10px;color:var(--color-accent-300)" title="El ESP32 envía un resumen por segundo, no la señal cruda">ILUSTRATIVA</span>
      </div>
      <div style="position:relative;border-radius:var(--radius-sm);overflow:hidden;background:color-mix(in srgb, var(--color-bg) 60%, var(--ink))">
        <div style="position:absolute;inset:0;background-image:linear-gradient(color-mix(in srgb, var(--color-accent) 8%, transparent) 1px, transparent 1px),linear-gradient(90deg, color-mix(in srgb, var(--color-accent) 8%, transparent) 1px, transparent 1px);background-size:100% 25%, 12.5% 100%"></div>
        <svg viewBox="0 0 600 120" style="position:relative;width:100%;height:auto;display:block" role="img" aria-label="Onda del pulso, ilustrativa al ritmo medido">
          <polyline points="${pts}" style="fill:none;stroke:var(--color-accent);stroke-width:2;stroke-linejoin:round;stroke-linecap:round;filter:drop-shadow(0 0 4px color-mix(in srgb, var(--color-accent) 55%, transparent))"></polyline>
          <circle cx="${cab.x}" cy="${cab.y}" r="4" style="fill:var(--color-accent-200)"></circle>
        </svg>
      </div>
      <span style="font-size:12px;color:var(--color-neutral-400)">Onda ilustrativa al ritmo del pulso medido: el ESP32 envía un resumen por segundo (pulso, HRV de 30 s, SpO₂), no la señal cruda. Cuadrícula de 1 segundo.</span>
    </div>
    <div style="display:flex;align-items:center;gap:10px;font-size:14px;color:var(--color-neutral-200)" aria-live="polite"><i class="ph-fill ${iconoEstado[0]}" style="color:${iconoEstado[1]};font-size:18px"></i>${textoEstado}${d && d.simulado ? h` ${tagMono("SIMULADO")}` : ""}</div>
    ${botonera(botonPrimario("Continuar", "siguiente", !d || d.dedo === false))}`;
  }

  function vCamara() {
    const d = S.vision;
    const abierto = activo("vision");
    const mid = S.camFase === "midiendo";
    const listo = S.camFase === "listo" || S.camFase === "error" || Boolean(d);
    const avisos = d && Array.isArray(d.avisos) ? d.avisos : [];
    const avisoLuz = avisos.find((a) => /luz|brill|reflej/i.test(a));
    const cara = d ? num(d.cara_detectada_pct) : null;
    const chips = [{ icon: "ph-webcam", label: `CÁMARA ${CFG.camara != null && CFG.camara !== "" ? String(CFG.camara).replace(/^https?:\/\/([^/:]+).*$/, "droidcam $1") : "0"}`, fg: abierto ? ST.verde.fg : ST.rojo.fg }];
    if (d && cara !== null) chips.push(cara >= 80 ? { icon: "ph-check-circle", label: `ROSTRO ${Math.round(cara)} %`, fg: ST.verde.fg } : { icon: "ph-warning-circle", label: `ROSTRO ${Math.round(cara)} %`, fg: ST.amarillo.fg });
    if (d) chips.push(avisoLuz ? { icon: "ph-warning-circle", label: "REVISAR LUZ", fg: ST.amarillo.fg } : { icon: "ph-sun", label: "LUZ OK", fg: ST.verde.fg });
    // El módulo de visión vio lentes y espera a que se los quiten antes de empezar a medir.
    const lentes = mid && !d && S.estadoVision === "lentes";
    const textoLentes = S.visionMensaje || "Se ven lentes: quítatelos para continuar con la medición.";
    if (lentes) chips.push({ icon: "ph-eyeglasses", label: "QUÍTATE LOS LENTES", fg: ST.amarillo.fg });
    else if (mid) chips.push({ icon: "ph-record", label: "MIDIENDO", fg: "var(--color-accent-300)" });
    const estado = !abierto && !mid && !d ? "Módulo sin abrir" : lentes ? "Se ven lentes"
      : { lista: "Listo para medir", midiendo: "Midiendo", listo: d ? "Medición lista" : "Terminó sin datos", error: "Error" }[S.camFase];
    const sub = !abierto && !mid && !d ? "Pueden seguir sin la cámara (Omitir)." : lentes ? textoLentes
      : { lista: `Cámara ${CFG.camara ?? 0} · ${SEGUNDOS_CAMARA} s de medición`, midiendo: `Quedan ${Math.ceil(S.camT)} s · el módulo avisa cada 5 s`,
        listo: d ? "Datos enviados al coordinador" : (abierto ? "La medición terminó, pero no llegaron datos." : "El módulo de visión se cerró: no llegaron datos."),
        error: S.visionMotivo || "La medición con la cámara falló." }[S.camFase];
    const ventanaTexto = !abierto && !mid ? "El módulo de visión no está abierto." : lentes ? textoLentes : mid ? "Tu rostro se ve en la ventana del módulo de visión. Mírala de frente."
      : S.camFase === "listo" ? "Medición terminada. La ventana de visión ya se cerró." : "Al iniciar, el módulo de visión abre su ventana con tu rostro.";
    const cards = [
      { label: "Parpadeos", valor: d ? fmt(d.parpadeos_min, 1) : "–", unidad: "por minuto", tipo: TIPOS.medido },
      { label: "PERCLOS", valor: d ? fmt(num(d.perclos) > 1 ? num(d.perclos) / 100 : d.perclos) : "–", unidad: "fracción con ojos casi cerrados", tipo: TIPOS.estimado },
      { label: "Bostezos", valor: d ? entero(d.bostezos) : "–", unidad: "boca abierta ≥ 1,5 s", tipo: TIPOS.medido },
      { label: "Bostezos tapados", valor: d && d.bostezos_tapados != null ? entero(d.bostezos_tapados) : "–", unidad: "con la mano (ya incluidos)", tipo: TIPOS.medido },
    ];
    const restante = S.camFase === "listo" || S.camFase === "error" ? 0 : Math.max(0, Math.min(SEGUNDOS_CAMARA, S.camT));
    return h`<div style="display:flex;align-items:flex-end;gap:12px;flex-wrap:wrap">
      <div style="display:flex;flex-direction:column;gap:6px;margin-right:auto"><h2 style="font-size:26px;margin:0">Monitoreo con cámara</h2><p style="margin:0;color:var(--color-neutral-300);max-width:60ch">Mira a la cámara de frente durante ${SEGUNDOS_CAMARA} segundos. Mide parpadeos, ojos cerrados y bostezos.</p></div>
      ${segOpciones("vista", "Vista de la cámara", [["ventana", "Ventana de visión", S.vista === "ventana", "ph-app-window"], ["web", "Vista web · pendiente", S.vista === "web", "ph-browser"]], "vista")}
    </div>
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,420px),1fr));gap:20px;align-items:start">
      <div style="display:flex;flex-direction:column;gap:10px">
        <div style="position:relative;aspect-ratio:4/3;border-radius:var(--radius-lg);overflow:hidden;background:radial-gradient(120% 90% at 50% 40%, color-mix(in srgb, var(--color-surface) 70%, var(--color-bg)), color-mix(in srgb, var(--color-bg) 60%, var(--ink)));box-shadow:var(--shadow-sm)">
          <div style="position:absolute;inset:0;background-image:linear-gradient(color-mix(in srgb, var(--color-accent) 7%, transparent) 1px, transparent 1px),linear-gradient(90deg, color-mix(in srgb, var(--color-accent) 7%, transparent) 1px, transparent 1px);background-size:40px 40px"></div>
          ${esquinas(14, 22)}
          <div style="position:absolute;left:50%;top:48%;width:38%;aspect-ratio:3/4;transform:translate(-50%,-50%);border-radius:50%;border:1.5px dashed ${cara !== null && cara < 80 ? ST.amarillo.fg : mid ? "var(--color-accent)" : "var(--color-neutral-600)"}"></div>
          ${S.vista === "web" ? h`<div style="position:absolute;left:50%;top:48%;width:38%;aspect-ratio:3/4;transform:translate(-50%,-50%)">
              ${LANDMARKS.map(([x, y]) => h`<span style="position:absolute;left:${x}%;top:${y}%;width:4px;height:4px;margin:-2px;border-radius:50%;background:var(--color-accent-300);opacity:.85"></span>`)}
            </div>
            <span style="position:absolute;left:50%;bottom:44px;transform:translateX(-50%);padding:4px 10px;border-radius:5px;background:color-mix(in srgb, var(--color-bg) 80%, transparent);font-size:12px;color:var(--color-neutral-200);white-space:nowrap">Vista previa simulada · la transmisión web aún no existe</span>`
          : h`<div style="position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;padding:24px;text-align:center">
              <i class="ph ph-app-window" style="font-size:36px;color:var(--color-accent-400)"></i>
              <span style="font-size:15px;max-width:34ch;color:var(--color-neutral-100)">${ventanaTexto}</span>
              <span style="font-size:12px;color:var(--color-neutral-400);${MONO}">${abierto || mid ? `vision.py --servicio · cámara ${CFG.camara ?? 0}` : COMANDO.vision}</span>
            </div>`}
          ${mid ? h`<div style="position:absolute;left:0;right:0;top:0;height:100%;background:linear-gradient(to bottom, transparent 85%, color-mix(in srgb, var(--color-accent) 14%, transparent));animation:barrido 3s linear infinite;pointer-events:none"></div>` : ""}
          <div style="position:absolute;left:14px;right:14px;top:44px;display:flex;gap:6px;flex-wrap:wrap;padding:0 30px">
            ${chips.map((c) => h`<span style="display:inline-flex;align-items:center;gap:5px;padding:3px 8px;border-radius:5px;background:color-mix(in srgb, var(--color-bg) 82%, transparent);color:${c.fg};${MONO};font-size:11px"><i class="ph-fill ${c.icon}"></i>${c.label}</span>`)}
          </div>
        </div>
        ${lentes ? h`<div class="aviso-camara">${alerta(ST.amarillo, "ph-eyeglasses", "Se ven lentes", textoLentes, "alert")}</div>` : ""}
        ${S.camFase === "error" ? alerta(ST.rojo, "ph-x-circle", "La medición con la cámara falló", `${S.visionMotivo || "Sin motivo"}. Pueden seguir sin ella.`, "alert") : ""}
        ${avisos.map((a) => alerta(ST.amarillo, "ph-warning", "Aviso de calidad", a, "alert"))}
        <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
          <button class="btn btn-primary" type="button" data-click="camIniciar" ${si(mid || !abierto || !PUEDE, "disabled")} style="padding:9px 16px"><i class="ph ph-play"></i>${listo ? "Medir otra vez" : "Iniciar"}</button>
          <button class="btn btn-ghost" type="button" data-click="camReiniciar" ${si(mid, "disabled")} style="padding:9px 10px"><i class="ph ph-arrow-counter-clockwise"></i>Reiniciar</button>
          ${abierto ? "" : h`<span style="margin-left:auto;font-size:12px;color:var(--color-neutral-400)">Abran el módulo: ${cmd(COMANDO.vision)}</span>`}
        </div>
      </div>
      <div style="display:flex;flex-direction:column;gap:14px">
        <div style="display:flex;align-items:center;gap:16px;padding:16px;${TARJ}">
          <div style="position:relative;width:84px;height:84px;flex:none">
            <svg viewBox="0 0 84 84" width="84" height="84" style="transform:rotate(-90deg)"><circle cx="42" cy="42" r="37" fill="none" stroke="var(--color-neutral-800)" stroke-width="4"></circle><circle cx="42" cy="42" r="37" fill="none" stroke="var(--color-accent)" stroke-width="4" stroke-linecap="round" stroke-dasharray="232.5" stroke-dashoffset="${String(232.5 * (restante / SEGUNDOS_CAMARA))}" style="transition:stroke-dashoffset .25s linear;filter:drop-shadow(0 0 4px color-mix(in srgb, var(--color-accent) 60%, transparent))"></circle></svg>
            <span style="position:absolute;inset:0;display:grid;place-items:center;${MONO};font-size:24px;font-variant-numeric:tabular-nums">${String(Math.ceil(restante))}</span>
          </div>
          <div style="display:flex;flex-direction:column;gap:3px" aria-live="polite">
            ${etq("Estado")}
            <span style="font-size:18px;font-weight:500">${estado}${mid && avisos.length ? " con avisos" : ""}</span>
            <span style="font-size:13px;color:var(--color-neutral-400)">${sub}</span>
          </div>
        </div>
        <div style="display:flex;flex-direction:column;gap:8px;padding:16px;${TARJ}">
          <div style="display:flex;align-items:center;gap:8px"><i class="ph ph-eye" style="font-size:16px;color:var(--color-accent)"></i><span style="font-size:13px;font-weight:500">EAR · apertura de ojos</span><span style="margin-left:auto;${MONO};font-size:13px;font-variant-numeric:tabular-nums" title="EAR de ojo abierto (mediana de los primeros 5 s)">${d ? fmt(d.ear_abierto) : "–"}</span></div>
          <svg viewBox="0 0 400 90" style="width:100%;height:auto;display:block" role="img" aria-label="Umbral de parpadeo">
            <line x1="0" y1="54" x2="400" y2="54" stroke="var(--color-neutral-700)" stroke-dasharray="3 4" stroke-width="1"></line>
            ${d && num(d.ear_abierto) !== null ? h`<line x1="0" y1="${Math.round(88 - num(d.ear_abierto) * 230)}" x2="400" y2="${Math.round(88 - num(d.ear_abierto) * 230)}" stroke="var(--color-accent)" stroke-width="1.5"></line>` : ""}
          </svg>
          <span style="font-size:12px;color:var(--color-neutral-400)">La señal EAR en vivo se ve en la ventana del módulo de visión; aquí llega el EAR de ojo abierto al terminar. Línea punteada: umbral de parpadeo, 60 % del ojo abierto, durante 2 cuadros o más.</span>
        </div>
        <div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px">
          ${cards.map((v) => h`<div style="display:flex;flex-direction:column;gap:4px;padding:12px 14px;${TARJ}">
              <span style="display:flex;align-items:center;gap:6px;font-size:12px;color:var(--color-neutral-300)">${v.label}<span style="margin-left:auto;display:inline-flex;align-items:center;gap:4px;font-size:10px;color:${v.tipo.fg}"><i class="ph ${v.tipo.icon}"></i>${v.tipo.label.toUpperCase()}</span></span>
              <span style="${MONO};font-size:24px;font-variant-numeric:tabular-nums;color:${v.gris && d ? "var(--color-neutral-400)" : "var(--color-text)"}">${v.valor}</span>
              <span style="font-size:11px;color:var(--color-neutral-400)">${v.unidad}</span>
            </div>`)}
        </div>
        ${d && d.simulado ? h`<span>${tagMono("SIMULADO")}</span>` : ""}
      </div>
    </div>
    ${botonera(botonPrimario("Continuar", "siguiente", !listo))}`;
  }

  function esquinas(m, t) {
    const b = "1.5px solid var(--color-accent-500)";
    return h`<div style="position:absolute;left:${m}px;top:${m}px;width:${t}px;height:${t}px;border-left:${b};border-top:${b}"></div>
      <div style="position:absolute;right:${m}px;top:${m}px;width:${t}px;height:${t}px;border-right:${b};border-top:${b}"></div>
      <div style="position:absolute;left:${m}px;bottom:${m}px;width:${t}px;height:${t}px;border-left:${b};border-bottom:${b}"></div>
      <div style="position:absolute;right:${m}px;bottom:${m}px;width:${t}px;height:${t}px;border-right:${b};border-bottom:${b}"></div>`;
  }

  function vVoz() {
    const frases = frasesVoz();
    if (!frases[S.fraseVoz]) S.fraseVoz = "estandar";
    const ocupado = ["esperando", "grabando", "analizando"].includes(S.vozFase);
    const abierto = activo("voz");
    const grabando = S.vozFase === "grabando" && S.vozPct > 0;
    const t = Date.now() / 1000;
    const notaFrase = S.fraseVoz === "estandar" ? "La frase de siempre: se compara con tu línea base."
      : S.fraseVoz === "trabalenguas" ? "La más difícil: léela clara y sin apurarte. Tiene su propia línea base."
        : "Tiene su propia línea base: se compara solo con mediciones de esta misma frase.";
    const estado = S.vozMsg || (abierto ? `Listo para grabar ${SEGUNDOS_VOZ} segundos` : "El módulo de voz no está abierto.");
    const d = S.voz;
    const explicacion = d && { "sin línea base": "Todavía no hay línea base: hacen falta 3 mediciones marcadas como línea base.", "sin voz detectada": "No se detectó voz en la grabación." }[d.estado_voz];
    const fraseRes = d && frases[d.frase_id || "estandar"];
    const primario = S.vozFase === "listo"
      ? botonPrimario("Continuar", "siguiente", false)
      : h`<button class="btn btn-primary" type="button" data-click="grabar" ${si(ocupado || !abierto || !PUEDE, "disabled")} style="padding:9px 18px"><i class="ph ph-record"></i>${S.vozMsg && S.vozFase === "inicio" && abierto ? "Reintentar" : `Grabar (${SEGUNDOS_VOZ} s)`}</button>`;
    const extra = S.vozFase === "listo" ? h`<button class="btn btn-secondary" type="button" data-click="grabar" ${si(!abierto || !PUEDE, "disabled")} style="padding:9px 16px"><i class="ph ph-record"></i>Grabar otra vez</button>` : "";
    return h`${titulo("Voz", "Cuando empiece la grabación, lee esta frase en voz alta, con tono normal.")}
    ${Object.keys(frases).length > 1 ? segOpciones("frase", "Frase a leer", Object.entries(frases).map(([k, f]) => [k, f.titulo, S.fraseVoz === k]), "frase", "align-self:flex-start") : ""}
    <blockquote style="margin:0;padding:22px 26px;border-radius:var(--radius-lg);background:var(--color-surface);font-size:22px;line-height:1.5;max-width:46ch;text-wrap:pretty;box-shadow:inset 2px 0 0 var(--color-accent);backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px)">${frases[S.fraseVoz].texto || "(Falta la frase: revisen voz/voz_fatiga.py)"}</blockquote>
    <span style="font-size:12px;color:var(--color-neutral-400);margin-top:-10px">${notaFrase}</span>
    <div style="display:flex;align-items:center;gap:14px;max-width:640px">
      <div style="display:flex;align-items:flex-end;gap:3px;height:36px;flex:none" aria-hidden="true">
        ${Array.from({ length: 14 }, (_, i) => h`<span style="width:4px;border-radius:2px;height:${grabando ? 8 + Math.round(Math.abs(Math.sin(t * 3 + i)) * 26) : 6}px;background:${grabando ? "var(--color-accent)" : "var(--color-neutral-700)"};transition:height .2s"></span>`)}
      </div>
      <div style="flex:1;display:flex;flex-direction:column;gap:6px">
        <span style="font-size:15px;font-weight:500" aria-live="polite">${estado}</span>
        <div style="height:4px;border-radius:2px;background:var(--color-neutral-800);overflow:hidden"><div style="height:100%;width:${S.vozPct}%;background:var(--color-accent);transition:width .25s linear"></div></div>
      </div>
    </div>
    ${!abierto && S.vozFase === "inicio" ? h`<span style="font-size:13px;color:var(--color-neutral-300)">Ábranlo con ${cmd(COMANDO.voz)} o toquen Omitir.</span>` : ""}
    ${d && !d.aviso && d.voz_detectada !== false ? h`<div style="display:flex;flex-direction:column;gap:6px;padding:14px 16px;max-width:640px;${TARJ}">
        <span style="${ETQ}">Voz comparada con la línea base · ${fraseRes ? fraseRes.titulo : "Frase estándar"}${d.simulado ? " · simulado" : ""}</span>
        <span style="font-size:17px;font-weight:500">${d.estado_voz ? cap(d.estado_voz) : "Sin comparación"}</span>
        ${explicacion ? h`<span style="font-size:13px;color:var(--color-neutral-300)">${explicacion}</span>` : ""}
        ${(d.motivos_voz || []).map((m) => h`<span style="display:flex;gap:8px;font-size:13px"><i class="ph ph-caret-right" style="color:var(--color-accent);margin-top:3px"></i>${m}</span>`)}
        <span style="font-size:12px;color:var(--color-neutral-400)">Es una sugerencia, no un diagnóstico.</span>
      </div>` : ""}
    ${botonera(primario, { extra })}`;
  }

  function vPvt() {
    const P = S.pvt;
    const seg = segundosPvt();
    const dur = textoDuracion(seg) + (S.demo ? " (modo demo)" : "");
    const prog = P.fase === "intro" ? `PVT-B · ${dur}` : P.fase === "activa" ? pvtRestante() : `${(P.res && P.res.n_estimulos) || 0} estímulos`;
    const msg = P.fase === "intro" ? "Toca Empezar cuando estés listo" : P.msg;
    const cont = pvt.estimuloEn !== null ? String(Math.floor(performance.now() - pvt.estimuloEn)) : P.cont;
    const r = P.res;
    const primario = P.fase === "intro" ? botonPrimario("Empezar la prueba", "pvtEmpezar", false)
      : P.fase === "fin" ? botonPrimario("Continuar", "siguiente", false) : botonPrimario("En curso…", "nada", true);
    return h`${titulo("Prueba de reacción", `Cuando aparezca el contador, presiona la barra espaciadora o toca el recuadro lo más rápido que puedas. No te adelantes: si respondes antes, cuenta como anticipada. Dura ${dur}.`, "max-width:62ch")}
    <div class="zona-prueba" role="button" tabindex="0" aria-label="Área de la prueba de reacción" data-pointer="pvt" style="position:relative;min-height:340px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px;border-radius:var(--radius-lg);background:color-mix(in srgb, var(--color-bg) 55%, var(--ink));box-shadow:var(--shadow-sm);cursor:pointer">
      <span style="position:absolute;top:14px;right:16px;${MONO};font-size:12px;color:var(--color-neutral-400)">${prog}</span>
      <span id="pvt-cont" style="${MONO};font-size:clamp(64px,12vw,140px);line-height:1;font-variant-numeric:tabular-nums;color:${P.contColor || "var(--color-text)"};min-height:1em">${cont}</span>
      <span style="font-size:17px;color:var(--color-neutral-300);text-align:center" aria-live="polite">${msg}</span>
      <span style="position:absolute;bottom:14px;font-size:12px;color:var(--color-neutral-500)">Barra espaciadora o toca aquí</span>
    </div>
    ${P.fase === "fin" && r ? h`<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px">
        ${tarjetaDato("Reacción media", r.rt_media_ms ?? "–", "ms")}
        ${tarjetaDato("Mediana", r.rt_mediana_ms ?? "–", "ms")}
        ${tarjetaDato("Lapsos", r.lapsos, `${L.decimal(r.lapsos_por_min)} por minuto (355 ms o más)`)}
        ${tarjetaDato("Anticipadas", r.anticipadas, `de ${r.n_estimulos} estímulos`)}
      </div>` : ""}
    ${botonera(primario, { sinOmitir: P.fase === "activa" })}`;
  }

  function celdaSimbolo(d, n, extra = "") {
    return h`<div style="display:flex;flex-direction:column;align-items:center;gap:2px;padding:8px 2px;${TARJ};${extra}">
      <svg viewBox="0 0 40 40" style="width:100%;max-width:40px;aspect-ratio:1"><path d="${d}" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"></path></svg>
      <span style="${MONO};font-size:16px;color:var(--color-accent)">${n}</span></div>`;
  }

  function vDsst() {
    const D = S.dsst;
    const clave = D.fase === "activa" || D.fase === "fin" ? D.clave : [...Array(9).keys()];
    const quedan = Math.max(0, Math.ceil(L.DSST_SEGUNDOS - (performance.now() - dsst.inicio) / 1000));
    const grid = "display:grid;grid-template-columns:repeat(9,minmax(0,1fr));gap:6px;max-width:720px";
    const primario = D.fase === "intro" ? botonPrimario("Empezar la prueba", "dsstEmpezar", false)
      : D.fase === "fin" ? botonPrimario("Continuar", "siguiente", false) : botonPrimario("En curso…", "nada", true);
    return h`${titulo("Prueba de símbolos", "Arriba está la clave: cada símbolo tiene su número. Cuando aparezca un símbolo en el centro, toca su número lo más rápido que puedas, sin equivocarte. También puedes usar las teclas del 1 al 9. Dura 90 segundos.", "max-width:62ch")}
    <div style="${grid}" aria-label="Clave de símbolos y números">${clave.map((s, i) => celdaSimbolo(L.SIMBOLOS_DSST[s], i + 1))}</div>
    ${D.fase === "activa" ? h`<div class="zona-prueba" style="position:relative;max-width:720px;min-height:220px;display:flex;align-items:center;justify-content:center;border-radius:var(--radius-lg);background:color-mix(in srgb, var(--color-bg) 55%, var(--ink));box-shadow:var(--shadow-sm)">
        <span style="position:absolute;top:14px;right:16px;${MONO};font-size:12px;color:var(--color-neutral-400)">Quedan ${quedan} s</span>
        <svg viewBox="0 0 40 40" style="width:120px;height:120px" aria-hidden="true"><path d="${L.SIMBOLOS_DSST[D.clave[D.actual - 1]]}" fill="none" stroke="var(--color-text)" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"></path></svg>
      </div>
      <div class="zona-prueba" style="${grid}">
        ${clave.map((_, i) => h`<button type="button" class="tecla-dsst" data-click="dsst" data-arg="${i + 1}" style="min-height:56px;border:0;${TARJ};${MONO};font-size:22px;color:var(--color-accent);cursor:pointer">${i + 1}</button>`)}
      </div>` : ""}
    ${D.fase === "intro" ? h`<div style="max-width:720px">${nota("ph-info", "Al empezar, la clave se mezcla: cada sesión tiene su propio orden.")}</div>` : ""}
    ${D.fase === "fin" && D.res ? h`<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;max-width:720px">
        ${tarjetaDato("Correctas", D.res.correctas, "en 90 s")}
        ${tarjetaDato("Incorrectas", D.res.incorrectas, "errores")}
        ${tarjetaDato("Por minuto", L.decimal(D.res.por_minuto, 1), "correctas")}
      </div>` : ""}
    ${botonera(primario, { sinOmitir: D.fase === "activa" })}`;
  }

  function vKss() {
    return h`${titulo("Cuestionario", "Dos preguntas rápidas sobre cómo te sientes ahora.")}
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,380px),1fr));gap:24px;align-items:start">
      <div style="display:flex;flex-direction:column;gap:6px">
        ${etq("¿Cuánto sueño tienes ahora? · Karolinska")}
        ${L.KSS.map(([n, label]) => h`<button type="button" class="hv-acc6" aria-pressed="${String(S.kss === n)}" data-click="kss" data-arg="${n}" style="display:flex;align-items:center;gap:14px;min-height:44px;padding:6px 14px;border:0;border-radius:var(--radius-md);background:${S.kss === n ? "var(--color-accent-900)" : "var(--color-surface)"};box-shadow:${S.kss === n ? "inset 0 0 0 1px var(--color-accent)" : "none"};text-align:left;cursor:pointer;font-size:14px">
            <b style="${MONO};font-size:18px;font-weight:500;width:20px;text-align:center;color:var(--color-accent)">${n}</b><span>${label}</span></button>`)}
      </div>
      <div style="display:flex;flex-direction:column;gap:10px">
        ${etq("¿Cuántas horas dormiste anoche?")}
        <div style="display:flex;align-items:center;gap:14px;padding:16px;${TARJ}">
          <button class="btn btn-secondary btn-icon" type="button" aria-label="Media hora menos" data-click="horas" data-arg="-0.5" style="width:48px;height:48px;font-size:20px"><i class="ph ph-minus"></i></button>
          <output aria-live="polite" style="${MONO};font-size:44px;min-width:100px;text-align:center;font-variant-numeric:tabular-nums">${fmt(S.horas, 1)}</output>
          <button class="btn btn-secondary btn-icon" type="button" aria-label="Media hora más" data-click="horas" data-arg="0.5" style="width:48px;height:48px;font-size:20px"><i class="ph ph-plus"></i></button>
          <span style="color:var(--color-neutral-300)">horas</span>
        </div>
      </div>
    </div>
    ${botonera(botonPrimario("Ver resultado", "enviarCuestionario", S.kss === null || !PUEDE), { sinOmitir: true })}`;
  }

  function vAnalizando() {
    const sinCoord = !activo("coordinador") && !S.anal.listo;
    const pasos = [["Juntando reacción, cuestionario y sensor", true], ["Comparando con tu línea base", S.anal.comparando], ["Esperando al coordinador", S.anal.listo]];
    const simulador = `python herramientas\\simulador.py --persona ${S.persona}`;
    return h`<div style="display:flex;flex-direction:column;align-items:flex-start;gap:16px;padding:48px 0">
      ${sinCoord ? h`<i class="ph ph-warning-circle" style="font-size:56px;color:${ST.amarillo.fg}"></i>` : h`<div style="width:56px;height:56px;border-radius:50%;border:3px solid var(--color-neutral-800);border-top-color:var(--color-accent);animation:${S.prefs.movimiento ? "none" : "spin 1s linear infinite"}"></div>`}
      <h2 style="font-size:26px;margin:0">${sinCoord ? "Falta el coordinador" : S.anal.listo ? "Resultado listo" : "Analizando…"}</h2>
      ${pasos.map(([label, ok]) => h`<span style="display:flex;align-items:center;gap:8px;font-size:14px;color:${ok ? "var(--color-text)" : "var(--color-neutral-500)"}"><i class="ph ${ok ? "ph-check" : "ph-circle-dashed"}"></i>${label}</span>`)}
      ${sinCoord ? h`<span style="font-size:13px;color:var(--color-neutral-300);max-width:70ch" aria-live="polite">El módulo coordinador no está abierto. Ábranlo con ${cmd(COMANDO.coordinador)}. Para probar sin él: ${cmd(simulador)} y luego 1, 2 o 3.</span>`
        : S.anal.vencida && !S.anal.listo ? h`<span style="font-size:13px;color:var(--color-neutral-300);max-width:70ch" aria-live="polite">El coordinador todavía no envió el resultado. Para probar sin él: ${cmd(simulador)} y luego 1, 2 o 3.</span>` : ""}
    </div>
    <div style="display:flex;gap:8px"><button class="btn btn-ghost" type="button" data-click="anterior"><i class="ph ph-arrow-left"></i>Volver al cuestionario</button></div>`;
  }

  // ================================================================== vista: Resultados
  // Qué motivo del coordinador corresponde a cada indicador (los puntos llegan por fuente, no por indicador).
  const MOTIVO_DE = { "Pulso": /^pulso/i, "HRV (RMSSD)": /variabilidad/i, "Reacción PVT-B": /pvt/i, "Símbolos DSST": /símbolos/i,
    "Parpadeos": /parpadeos/i, "PERCLOS": /ojos cerrados/i, "Bostezos": /bostezo/i, "Fatiga por visión": /ojos cerrados|parpadeos|bostezo/i,
    "Cansancio en la voz": /voz/i, "Somnolencia KSS": /karolinska/i, "Horas de sueño": /horas de sueño/i };
  const FUENTE_DE = { "Pulso": "esp32", "HRV (RMSSD)": "esp32", "Reacción PVT-B": "pvt", "Símbolos DSST": "dsst", "Parpadeos": "vision",
    "PERCLOS": "vision", "Bostezos": "vision", "Fatiga por visión": "vision", "Cansancio en la voz": "voz", "Somnolencia KSS": "cuestionario", "Horas de sueño": "cuestionario" };

  function indicadoresDe(ev) {
    const d = S.sesiones[ev.sesion] || { esp32: [] };
    const sen = ev.senales || {};
    const motivos = ev.motivos || [];
    // Puntos de un indicador: 0 si su fuente no sumó; los de la fuente si su motivo está entre los del coordinador;
    // si la fuente sumó pero el motivo no aparece (el coordinador manda hasta 3), no se muestra un número.
    const ptsDe = (nombre) => {
      const f = FUENTE_DE[nombre];
      if (!f || !(f in sen)) return null;
      if (!sen[f]) return 0;
      return motivos.some((m) => MOTIVO_DE[nombre].test(m)) ? sen[f] : null;
    };
    const nd = (nombre, fuente, notaTxt, calidad) => ({ tipo: "no_disponible", nombre, fuente, valor: "", unidad: "", puntos: null, nota: notaTxt, calidad });
    const out = [];
    const validas = (d.esp32 || []).filter((m) => m.dedo === true && num(m.calidad) !== null && num(m.calidad) >= 0.5);
    const calE = mediana(validas.map((m) => num(m.calidad)));
    if (validas.length) {
      const p = mediana(validas.map((m) => num(m.pulso_lpm)));
      const hrv = mediana(validas.map((m) => num(m.hrv_rmssd_ms)));
      const spo2 = mediana(validas.map((m) => num(m.spo2)));
      out.push(p !== null ? { tipo: "medido", nombre: "Pulso", fuente: "ESP32", valor: entero(p), unidad: "lpm", calidad: calE, puntos: null, nota: "Mediana de las lecturas con el dedo puesto y calidad de 0,5 o más. Manda sobre el pulso de la cámara." } : nd("Pulso", "ESP32", "Sin pulso en las lecturas válidas."));
      out.push(hrv !== null ? { tipo: "medido", nombre: "HRV (RMSSD)", fuente: "ESP32", valor: entero(hrv), unidad: "ms", calidad: calE, puntos: null, nota: "Variación entre latidos en 30 s, comparada con la línea base." } : nd("HRV (RMSSD)", "ESP32", "Sin HRV en las lecturas válidas."));
      out.push(spo2 !== null ? { tipo: "medido", nombre: "SpO₂", fuente: "ESP32", valor: entero(spo2), unidad: "%", calidad: calE, puntos: null, aviso: Boolean(ev.aviso_spo2),
        nota: ev.aviso_spo2 ? "Aviso, no puntaje: estuvo bajo 30 s seguidos. Repetir la medición." : "Aviso, no puntaje: solo avisa si está bajo 30 s seguidos." } : nd("SpO₂", "ESP32", "Sin SpO₂ en las lecturas válidas."));
    } else {
      const motivo = (d.esp32 || []).length ? "Ninguna lectura con el dedo puesto y calidad de 0,5 o más." : "Sin lecturas del sensor en esta sesión.";
      out.push(nd("Pulso", "ESP32", motivo), nd("HRV (RMSSD)", "ESP32", motivo));
      if (ev.aviso_spo2) out.push({ tipo: "medido", nombre: "SpO₂", fuente: "ESP32", valor: "", unidad: "", puntos: null, aviso: true, nota: "Aviso, no puntaje: estuvo bajo 30 s seguidos. Repetir la medición." });
    }
    const pv = d.pvt;
    if (pv) {
      const min = Math.max(1, Math.round((num(pv.duracion_s) || 0) / 60));
      const durPvt = num(pv.duracion_s) !== null ? `${min} ${min === 1 ? "minuto" : "minutos"}` : "la prueba";
      out.push({ tipo: "medido", nombre: "Reacción PVT-B", fuente: "Estación", valor: entero(pv.rt_mediana_ms), unidad: "ms mediana", puntos: null,
        nota: `${pv.lapsos ?? 0} lapsos de 355 ms o más y ${pv.anticipadas ?? 0} anticipadas en ${durPvt}${pv.modo_demo ? " (modo demo)" : ""}.` });
    } else out.push(nd("Reacción PVT-B", "Estación", "Se omitió o no llegó a esta pantalla."));
    if (d.dsst) {
      out.push({ tipo: "medido", nombre: "Símbolos DSST", fuente: "Estación", valor: fmt(d.dsst.por_minuto, 1), unidad: "correctas por min", puntos: null,
        nota: `${d.dsst.correctas ?? 0} correctas y ${d.dsst.incorrectas ?? 0} errores en 90 s.` });
    }
    const vi = d.vision;
    if (vi) {
      const cara = num(vi.cara_detectada_pct);
      const caraTxt = cara !== null ? ` Cara visible el ${Math.round(cara)} % del tiempo.` : "";
      out.push({ tipo: "medido", nombre: "Parpadeos", fuente: "Visión", valor: fmt(vi.parpadeos_min, 1), unidad: "por min", puntos: null, nota: "EAR por debajo del 60 % del ojo abierto durante 2 cuadros o más." + caraTxt });
      const pc = num(vi.perclos) !== null && num(vi.perclos) > 1 ? num(vi.perclos) / 100 : vi.perclos;
      out.push({ tipo: "estimado", nombre: "PERCLOS", fuente: "Visión", valor: fmt(pc), unidad: "fracción", puntos: null, nota: "Tiempo con los ojos casi cerrados. Aproximación P80, sin validación clínica." });
      out.push({ tipo: "medido", nombre: "Bostezos", fuente: "Visión", valor: entero(vi.bostezos), unidad: "en la medición", puntos: null, nota: "Boca muy abierta 1,5 s o más. Uno suelto no cuenta." });
      // Fatiga por visión: el resumen del coordinador para la cámara (los puntos de su peor indicador: PERCLOS,
      // parpadeos o bostezos). Si no está en las señales, la visión no se evaluó (por ejemplo, se vio poco la cara).
      const fv = num(sen.vision);
      const lentesTxt = vi.lentes ? " Con lentes puestos: solo cuentan los bostezos." : "";
      out.push(fv !== null
        ? { tipo: "estimado", nombre: "Fatiga por visión", fuente: "Visión", valor: ["Sin signos", "Leve", "Marcada"][Math.min(2, Math.max(0, Math.round(fv)))], unidad: "", puntos: null,
            nota: "Resumen de ojos cerrados, parpadeos y bostezos: vale lo que su peor indicador." + lentesTxt }
        : nd("Fatiga por visión", "Visión", cara !== null && cara < 50 ? "No se evaluó: la cara se vio menos del 50 % del tiempo." : "El coordinador no la evaluó en esta sesión."));
    } else out.push(nd("Visión", "Visión", "Sin medición de la cámara en esta sesión."));
    const vz = d.voz;
    if (vz && num(vz.indice_cansancio) !== null) {
      const v = num(vz.indice_cansancio);
      out.push({ tipo: "estimado", nombre: "Cansancio en la voz", fuente: "Voz", valor: (v > 0 ? "+" : "") + fmt(v, 1), unidad: "índice z", puntos: null, nota: `Señal débil: pesa como máximo 1 punto.${vz.estado_voz ? " " + cap(vz.estado_voz) + "." : ""}` });
    } else out.push(nd("Cansancio en la voz", "Voz", vz ? (vz.estado_voz === "sin línea base" ? "Sin línea base de voz: hacen falta 3 mediciones." : "No se pudo comparar.") : "Se omitió o no llegó a esta pantalla."));
    const cu = d.cuestionario;
    if (cu) {
      out.push({ tipo: "reportado", nombre: "Somnolencia KSS", fuente: "Cuestionario", valor: entero(cu.kss), unidad: "de 9", puntos: null, nota: cu.kss_texto ? `${cu.kss_texto}.` : "Escala de Karolinska." });
      out.push({ tipo: "reportado", nombre: "Horas de sueño", fuente: "Cuestionario", valor: fmt(cu.horas_sueno, 1), unidad: "h", puntos: null, nota: "Se compara con tu línea base (sin línea base: menos de 6 h marca)." });
    } else out.push(nd("Cuestionario", "Cuestionario", "No llegó a esta pantalla."));
    for (const it of out) if (it.tipo !== "no_disponible") it.puntos = ptsDe(it.nombre);
    return out;
  }

  function vistaResultados() {
    const ev = evaluacionVista();
    if (!ev) {
      return h`<div data-k="res-vacio" style="display:flex;flex-direction:column;align-items:flex-start;gap:12px;padding:48px 0">
        <i class="ph ph-clipboard-text" style="font-size:36px;color:var(--color-neutral-500)"></i>
        <h2 style="font-size:22px;margin:0">Todavía no hay resultados</h2>
        <span style="color:var(--color-neutral-300)">Los resultados llegan del coordinador (apto/{persona}/evaluacion) al terminar una evaluación.</span>
        <button class="btn btn-primary" type="button" data-click="nuevaEvaluacion" style="padding:9px 16px"><i class="ph ph-play"></i>Nueva evaluación</button>
      </div>`;
    }
    const st = ST[ev.color] || ST.sin;
    const p = Math.max(0, Math.min(1, num(ev.puntaje) ?? 0));
    const meta = (S.sesiones[ev.sesion] || {}).meta || {};
    const pv = (S.sesiones[ev.sesion] || {}).pvt;
    const modoDemo = meta.modo_demo || (pv && pv.modo_demo);
    const esAvisoSpo2 = (m) => ev.aviso_spo2 && /^ox[ií]geno m[aá]s bajo/i.test(m);
    const propios = (ev.motivos || []).filter((m) => !esAvisoSpo2(m));
    const motivos = propios.length ? propios : [ev.aviso_spo2 ? "Sin motivos que cambien el color." : "Tus señales están en tu rango habitual."];
    const textoSpo2 = (ev.motivos || []).find(esAvisoSpo2) || "Oxígeno más bajo de lo habitual: repetir la medición";
    const conv = S.copiloto.filter((c) => c.persona === ev.persona).slice(0, 12).reverse();
    const pend = S.pendientes.filter((x) => x.persona === ev.persona);
    const abierto = activo("copiloto");
    if (S.chat.persona !== ev.persona) S.chat = { persona: ev.persona, sesion: ev.sesion || "" };
    completarSesion(ev);
    const indicadores = indicadoresDe(ev);
    const chatOk = abierto && PUEDE;
    return h`<div data-k="res-${ev.persona}" style="display:contents">
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,300px),1fr));gap:20px;align-items:stretch">
    <section style="position:relative;overflow:hidden;display:flex;flex-direction:column;align-items:flex-start;gap:14px;padding:22px;border-radius:var(--radius-lg);background:var(--color-surface);box-shadow:var(--shadow-sm);backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px)">
      <div style="position:relative;width:140px;height:140px">
        <svg viewBox="0 0 140 140" width="140" height="140"><circle cx="70" cy="70" r="62" fill="none" stroke="var(--color-neutral-800)" stroke-width="1"></circle><circle cx="70" cy="70" r="50" fill="${st.bg}" stroke="${st.fg}" stroke-width="2"></circle><circle cx="70" cy="70" r="62" fill="none" stroke="${st.fg}" stroke-width="3" stroke-linecap="round" stroke-dasharray="${p * 389.6} 389.6" transform="rotate(-90 70 70)"></circle></svg>
        <i class="ph-fill ${st.icon}" style="position:absolute;inset:0;display:grid;place-items:center;font-size:44px;color:${st.fg}"></i>
      </div>
      <span style="${MONO};font-size:30px;font-weight:600;letter-spacing:0.08em;color:${st.fg}">${st.word}</span>
      <span style="font-size:15px;color:var(--color-neutral-200)">${st.label}</span>
      <div style="display:flex;gap:6px;flex-wrap:wrap">
        ${ev.provisional ? tagMono("PROVISIONAL") : ""}
        ${ev.simulado ? tagMono("SIMULADO", "tag-outline") : ""}
        ${ev.reproducido ? tagMono("REPRODUCIDO", "tag-outline") : ""}
        ${modoDemo ? tagMono("MODO DEMO 1 MIN") : ""}
        ${meta.linea_base ? h`<span class="tag tag-accent">Línea base</span>` : ""}
      </div>
      <span style="${MONO};font-size:12px;color:var(--color-neutral-400)">Puntaje ${fmt(ev.puntaje)} · ${ev.sesion ? `sesión ${ev.sesion}` : L.hora(L.tsAMs(ev.ts))}</span>
    </section>
    <section style="display:flex;flex-direction:column;gap:14px;padding:22px;border-radius:var(--radius-lg);background:var(--color-surface);grid-column:span ${S.w >= 1100 ? 2 : 1};box-shadow:var(--shadow-sm);backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px)">
      <div style="display:flex;flex-direction:column;gap:6px">
        ${etq("Recomendación")}
        <p style="margin:0;font-size:20px;line-height:1.35;font-weight:500;text-wrap:pretty">${ev.accion || "–"}</p>
      </div>
      <div style="display:flex;flex-direction:column;gap:6px">
        ${etq("Motivos")}
        ${motivos.map((m) => h`<span style="display:flex;gap:8px;align-items:flex-start;font-size:15px"><i class="ph ph-caret-right" style="color:var(--color-accent);margin-top:3px"></i>${m}</span>`)}
      </div>
      ${ev.aviso_spo2 ? h`<div role="status" style="display:flex;gap:10px;align-items:flex-start;padding:10px 14px;border-radius:var(--radius-md);background:${ST.amarillo.bg}">
        <i class="ph ph-drop" style="font-size:18px;color:${ST.amarillo.fg}"></i>
        <span style="display:flex;flex-direction:column;gap:2px"><b style="font-weight:500;color:${ST.amarillo.fg}">${textoSpo2}</b><span style="font-size:13px;color:var(--color-neutral-200)">Es un aviso y no cambia el color del resultado.</span></span>
      </div>` : ""}
      <span style="display:flex;gap:8px;align-items:flex-start;font-size:12px;color:var(--color-neutral-400);margin-top:auto"><i class="ph ph-info" style="font-size:15px"></i>Resultado orientativo para apoyar la decisión. No es un diagnóstico médico ni una certificación de aptitud.</span>
    </section>
  </div>

  <section style="${SECC}">
    <div style="display:flex;align-items:center;gap:8px"><span aria-hidden="true" style="position:relative;width:30px;height:30px;flex:none;display:grid;place-items:center;border-radius:9px;background:linear-gradient(135deg, var(--color-accent-800), var(--color-accent-900));box-shadow:inset 0 0 0 1px var(--color-accent-600), 0 0 16px color-mix(in srgb, var(--color-accent) 30%, transparent)"><svg viewBox="0 0 24 24" width="18" height="18"><path d="M12 3C12.7 8.6 15.4 11.3 21 12C15.4 12.7 12.7 15.4 12 21C11.3 15.4 8.6 12.7 3 12C8.6 11.3 11.3 8.6 12 3Z" style="fill:var(--color-accent-200)"></path><circle cx="18.6" cy="5.4" r="1.5" style="fill:var(--color-accent-300)"><animate attributeName="opacity" values="1;.25;1" dur="2.4s" repeatCount="indefinite"></animate></circle></svg></span><span style="display:flex;flex-direction:column;gap:1px"><h2 style="font-size:16px;margin:0">Becspace AI</h2><span style="font-size:12px;color:var(--color-neutral-400)">Asistente de la estación · responde con las fichas de protocolos</span></span></div>
    ${abierto ? "" : h`<span style="font-size:13px;color:var(--color-neutral-300)">El copiloto no está abierto. Ábranlo con ${cmd(COMANDO.copiloto)}.</span>`}
    ${S.escuchaTexto ? h`<span style="font-size:13px;color:var(--color-accent-300)" aria-live="polite">${S.escuchaTexto}</span>` : ""}
    ${conv.map((c) => h`<div style="display:flex;flex-direction:column;gap:8px">
        ${c.pregunta ? h`<span style="align-self:flex-end;max-width:80%;padding:8px 12px;border-radius:10px 10px 2px 10px;background:var(--color-neutral-800);font-size:14px">${c.pregunta === "(resumen automático)" ? "Resumen automático" : c.pregunta}</span>` : ""}
        <span style="max-width:90%;padding:10px 14px;border-radius:10px 10px 10px 2px;background:var(--color-accent-900);box-shadow:inset 0 0 0 1px var(--color-accent-800);font-size:14px;line-height:1.5">${c.respuesta || ""}</span>
        <span style="${MONO};font-size:10px;color:var(--color-neutral-500)">becspace ai · ${c.modo || ""} · ${L.hora(L.tsAMs(c.ts))}</span>
      </div>`)}
    ${pend.map((x) => h`<div style="display:flex;flex-direction:column;gap:8px">
        <span style="align-self:flex-end;max-width:80%;padding:8px 12px;border-radius:10px 10px 2px 10px;background:var(--color-neutral-800);font-size:14px">${x.pregunta}</span>
        <span style="max-width:90%;padding:10px 14px;border-radius:10px 10px 10px 2px;box-shadow:inset 0 0 0 1px var(--color-accent-800);font-size:14px;color:var(--color-neutral-300)">${!abierto ? "El copiloto no está abierto." : Date.now() - x.desde > ESPERA_COPILOTO_MS ? "El copiloto no respondió. Revisen su ventana." : "Becspace AI está pensando…"}</span>
      </div>`)}
    ${!conv.length && !pend.length ? h`<span style="font-size:13px;color:var(--color-neutral-400)">Escribe una pregunta, por ejemplo: «¿Por qué salí en ${ev.color || "amarillo"}?»</span>` : ""}
    <form data-submit="preguntar" autocomplete="off" style="display:flex;gap:8px">
      <input class="input" data-libre placeholder="Pregunta a Becspace AI o toca Hablar" aria-label="Pregunta para Becspace AI" ${si(!chatOk, "disabled")}>
      <button class="btn btn-secondary" type="button" data-click="hablar" ${si(!chatOk || S.escuchando, "disabled")} title="Preguntar en voz alta: el copiloto escucha con el micrófono de la laptop" style="padding:0 12px;flex:none"><i class="ph ph-microphone"></i>${S.escuchando ? "Escuchando…" : "Hablar"}</button>
      <button class="btn btn-primary" type="submit" ${si(!chatOk, "disabled")} style="padding:0 14px;flex:none"><i class="ph ph-paper-plane-tilt"></i>Enviar</button>
    </form>
  </section>

  <section style="display:flex;flex-direction:column;gap:12px">
    <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">
      <h2 style="font-size:17px;margin:0;margin-right:auto">Indicadores analizados</h2>
      ${Object.values(TIPOS).map((tl) => h`<span style="display:inline-flex;align-items:center;gap:5px;font-size:12px;color:${tl.fg}"><i class="ph ${tl.icon}"></i>${tl.label}</span>`)}
    </div>
    <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,260px),1fr));gap:10px">
      ${indicadores.map((it) => {
        const T = TIPOS[it.tipo]; const nada = it.tipo === "no_disponible";
        const ptsTxt = it.puntos == null ? (it.aviso ? "AVISO" : "") : "+" + it.puntos + " pt";
        const calOk = num(it.calidad) !== null;
        return h`<article class="hv-sube" style="display:flex;flex-direction:column;gap:6px;padding:14px;border-radius:var(--radius-md);background:${nada ? "transparent" : "var(--color-surface)"};box-shadow:${nada ? "inset 0 0 0 1px var(--color-neutral-800)" : "none"};transition:transform .2s">
          <div style="display:flex;align-items:center;gap:6px">
            <span style="font-size:13px;font-weight:500">${it.nombre}</span>
            <span style="margin-left:auto;display:inline-flex;align-items:center;gap:4px;font-size:11px;color:${T.fg}"><i class="ph ${T.icon}"></i>${T.label}</span>
          </div>
          <div style="display:flex;align-items:baseline;gap:6px;min-height:34px">
            <span style="${MONO};font-size:${nada || !it.valor ? 22 : 28}px;font-variant-numeric:tabular-nums;color:${nada ? "var(--color-neutral-500)" : it.aviso ? ST.amarillo.fg : "var(--color-text)"}">${nada ? "No disponible" : it.valor || "Aviso"}</span>
            <span style="font-size:12px;color:var(--color-neutral-400)">${it.unidad}</span>
            <span title="${it.puntos == null ? "" : "Puntos de la fuente (cada fuente vale lo de su peor indicador)"}" style="margin-left:auto;${MONO};font-size:11px;color:${it.aviso || it.puntos ? ST.amarillo.fg : "var(--color-neutral-500)"}">${ptsTxt}</span>
          </div>
          ${calOk ? h`<div style="display:flex;align-items:center;gap:8px"><span style="font-size:11px;color:var(--color-neutral-400);width:52px">Calidad</span><div style="flex:1;height:3px;border-radius:2px;background:var(--color-neutral-800)"><div style="height:100%;width:${Math.round(num(it.calidad) * 100)}%;border-radius:2px;background:${num(it.calidad) < 0.5 ? ST.amarillo.fg : "var(--color-accent)"}"></div></div><span style="${MONO};font-size:11px;color:var(--color-neutral-300)">${fmt(it.calidad)}</span></div>` : ""}
          <p style="margin:0;font-size:12px;line-height:1.45;color:var(--color-neutral-300);text-wrap:pretty">${it.nota}</p>
          <span style="font-size:11px;color:var(--color-neutral-500);${MONO}">Fuente · ${it.fuente}</span>
        </article>`;
      })}
    </div>
  </section>

  <div style="display:flex;gap:8px;flex-wrap:wrap">
    <button class="btn btn-primary" type="button" data-click="nuevaEvaluacion" style="padding:9px 16px"><i class="ph ph-arrow-counter-clockwise"></i>Nueva evaluación</button>
    <button class="btn btn-secondary" type="button" data-click="ir" data-arg="historial" style="padding:9px 16px"><i class="ph ph-chart-line-up"></i>Ver historial</button>
  </div>
</div>`;
  }

  // ================================================================== vista: Historial
  function serieDe(k, filas) {
    const vals = filas.map((f) => num(f[k])).filter((v) => v !== null);
    const lo = vals.length ? Math.min(...vals) : null, hi = vals.length ? Math.max(...vals) : null;
    if (k === "puntaje") return ["Puntaje", 0, 1, 0.25, ""];
    if (k === "kss") return ["Somnolencia KSS", 1, 9, 2, ""];
    if (k === "pvt_mediana") return ["Reacción mediana", Math.min(200, lo === null ? 200 : Math.floor(lo / 50) * 50), Math.max(450, hi === null ? 450 : Math.ceil(hi / 50) * 50), 50, " ms"];
    return ["Horas de sueño", Math.min(3, lo === null ? 3 : Math.floor(lo)), Math.max(9, hi === null ? 9 : Math.ceil(hi)), 2, " h"];
  }

  function vistaHistorial() {
    const H = S.hist;
    const dias = S.periodo === "7" ? 7 : S.periodo === "30" ? 30 : 99999;
    const ahora = Date.now();
    const crew = CFG.tripulacion && CFG.tripulacion.length ? CFG.tripulacion : Array.from(new Set(H.filas.map((f) => f.persona)));
    const rows = H.filas.filter((f) => (S.hPersona === "todos" || f.persona === S.hPersona) && ahora - f.fecha <= dias * 864e5).sort((a, b) => b.fecha - a.fecha);
    const [sl, mn, mx, stp, un] = serieDe(S.serie, rows);
    const asc = rows.slice().reverse();
    const x0 = 50, x1 = 780;
    const y = (v) => 190 - ((Math.max(mn, Math.min(mx, v)) - mn) / (mx - mn)) * 170;
    const xs = (i) => (asc.length > 1 ? x0 + (i / (asc.length - 1)) * (x1 - x0) : (x0 + x1) / 2);
    const conValor = asc.map((f, i) => [f, i]).filter(([f]) => num(f[S.serie]) !== null);
    const sel = rows.find((f) => f.id === S.hSel);
    const nPag = Math.max(1, Math.ceil(rows.length / POR_PAGINA)); const pag = Math.min(S.hPag, nPag - 1);
    const nums = []; for (let i = 0; i < nPag; i++) if (i === 0 || i === nPag - 1 || Math.abs(i - pag) <= 1) nums.push(i); else if (nums[nums.length - 1] !== -1) nums.push(-1);
    const todos = S.hPersona === "todos";
    const claro = S.tema === "claro";
    const SER = ["puntaje", "pvt_mediana", "kss", "horas_sueno"];
    const grid = Array.from({ length: Math.floor((mx - mn) / stp + 1e-9) + 1 }, (_, i) => mn + i * stp);
    const estadoReg = H.estado === "cargando" ? ["ph-circle-notch", "Cargando desde MongoDB…"] : H.estado === "ok" ? ["ph-database", `MongoDB · ${H.filas.length} evaluaciones`] : ["ph-database", "Requiere el registrador (MongoDB local)"];
    const vacio = H.estado === "error" ? h`<div style="display:flex;flex-direction:column;align-items:flex-start;gap:8px;padding:32px 8px"><i class="ph ph-plugs" style="font-size:28px;color:var(--color-neutral-500)"></i><b style="font-weight:500">No se pudo leer el historial</b><span style="font-size:13px;color:var(--color-neutral-400)">${H.motivo}</span><span style="font-size:13px;color:var(--color-neutral-400)">Abran MongoDB y el registrador: ${cmd("python registrador\\mongo_local.py")} y ${cmd("python registrador\\registrador.py")}.</span><button class="btn btn-secondary" type="button" data-click="recargarHistorial" style="margin-top:4px"><i class="ph ph-arrow-clockwise"></i>Reintentar</button></div>`
      : h`<div style="display:flex;flex-direction:column;align-items:flex-start;gap:8px;padding:32px 8px"><i class="ph ph-tray" style="font-size:28px;color:var(--color-neutral-500)"></i><b style="font-weight:500">${H.estado === "cargando" ? "Cargando…" : "Sin evaluaciones en este periodo"}</b><span style="font-size:13px;color:var(--color-neutral-400)">${H.estado === "cargando" ? "Leyendo el registrador." : "Prueba con un periodo más largo u otra persona."}</span></div>`;
    const csv = `historial.csv?dias=${S.periodo === "todo" ? 0 : S.periodo}${todos ? "" : `&persona=${encodeURIComponent(S.hPersona)}`}`;
    return h`<div data-k="historial" style="display:contents">
  <div style="display:flex;gap:12px;flex-wrap:wrap;align-items:center">
    ${segOpciones("periodo", "Periodo", [["7", "7 días", S.periodo === "7"], ["30", "30 días", S.periodo === "30"], ["todo", "Todo", S.periodo === "todo"]], "periodo", "flex-wrap:nowrap")}
    ${segOpciones("hpersona", "Persona", ["todos"].concat(crew).map((p) => [p, p === "todos" ? "Todos" : L.nombre(p), S.hPersona === p]), "hPersona")}
    <span style="margin-left:auto;display:inline-flex;align-items:center;gap:6px;font-size:12px;color:var(--color-neutral-400)"><i class="ph ${estadoReg[0]}"></i>${estadoReg[1]}
      <button class="btn btn-ghost" type="button" data-click="recargarHistorial" aria-label="Volver a cargar" title="Volver a cargar" style="padding:4px 6px"><i class="ph ph-arrow-clockwise"></i></button></span>
  </div>
  <section style="${SECC}">
    <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">
      <h2 style="font-size:15px;margin:0;margin-right:auto">Evolución · ${sl}${todos ? " · toda la tripulación" : " · " + L.nombre(S.hPersona)}</h2>
      <div role="tablist" aria-label="Indicador" style="display:flex;gap:2px;flex-wrap:wrap">
        ${SER.map((k) => h`<button role="tab" type="button" class="hv-tab" aria-selected="${String(S.serie === k)}" data-click="serie" data-arg="${k}" style="padding:6px 10px;border:0;background:transparent;border-radius:var(--radius-sm);color:${S.serie === k ? "var(--color-accent-200)" : "var(--color-neutral-400)"};box-shadow:${S.serie === k ? "inset 0 -2px 0 var(--color-accent)" : "none"};font-size:13px;cursor:pointer">${serieDe(k, rows)[0]}</button>`)}
      </div>
    </div>
    ${todos ? h`<div style="display:flex;flex-wrap:wrap;gap:6px 16px;align-items:center">
        ${crew.map((p) => h`<span style="display:inline-flex;align-items:center;gap:6px;font-size:13px;color:var(--color-neutral-200)"><i class="ph-fill ${icono(p)}" style="font-size:22px;color:var(--color-neutral-100)"></i>${L.nombre(p)}</span>`)}
        <span style="font-size:12px;color:var(--color-neutral-400)">El color del icono es el resultado de esa evaluación</span>
      </div>` : ""}
    <div style="position:relative">
      <svg viewBox="0 0 800 220" style="width:100%;height:auto;display:block" role="img" aria-label="Gráfico de evolución">
        ${grid.map((v) => h`<line x1="40" x2="790" y1="${y(v)}" y2="${y(v)}" style="stroke:var(--color-neutral-800);stroke-width:1"></line>`)}
        ${todos ? "" : h`<polyline points="${conValor.map(([f, i]) => xs(i) + "," + y(num(f[S.serie]))).join(" ")}" style="fill:none;stroke:var(--color-accent);stroke-width:1.5;stroke-linejoin:round"></polyline>
          ${conValor.map(([f, i]) => h`<circle cx="${xs(i)}" cy="${y(num(f[S.serie]))}" r="${f.id === S.hSel ? 6 : 4}" style="fill:${(ST[f.color] || ST.sin).fg};stroke:var(--color-surface);stroke-width:1.5"></circle>`)}`}
      </svg>
      ${grid.map((v) => h`<span style="position:absolute;left:0;width:4.5%;top:${(y(v) / 220) * 100}%;transform:translateY(-50%);text-align:right;${MONO};font-size:10px;color:var(--color-neutral-500)">${S.serie === "puntaje" ? fmt(v) : v}${un}</span>`)}
      ${todos ? conValor.map(([f, i]) => {
        const fg = claro ? { verde: "oklch(0.72 0.15 158)", amarillo: "oklch(0.80 0.15 80)", rojo: "oklch(0.70 0.17 25)" }[f.color] || ST.sin.fg : (ST[f.color] || ST.sin).fg;
        const sombra = claro ? "drop-shadow(0 0 1px rgba(255,255,255,1)) drop-shadow(0 1px 2px rgba(40,40,90,.35))" : "drop-shadow(0 0 1.5px rgba(6,9,19,.95)) drop-shadow(0 1px 2px rgba(6,9,19,.8))";
        const titulo2 = `${L.nombre(f.persona)} · ${fechaCorta(f.fecha)} · ${(ST[f.color] || ST.sin).word}`;
        return h`<button type="button" class="hv-icono" data-click="hSel" data-arg="${f.id}" title="${titulo2}" aria-label="${titulo2}" style="position:absolute;left:${(xs(i) / 800) * 100}%;top:${(y(num(f[S.serie])) / 220) * 100}%;transform:translate(-50%,-50%) scale(${f.id === S.hSel ? "1.35" : "1"});width:28px;height:28px;padding:0;border:0;background:transparent;display:grid;place-items:center;color:${fg};cursor:pointer;filter:${sombra};transition:transform .15s"><i class="ph-fill ${icono(f.persona)}" style="font-size:24px"></i></button>`;
      }) : ""}
      ${asc.filter((_, i) => i % Math.max(1, Math.ceil(asc.length / 8)) === 0).map((f) => h`<span style="position:absolute;bottom:0;left:${(xs(asc.indexOf(f)) / 800) * 100}%;transform:translateX(-50%);${MONO};font-size:10px;color:var(--color-neutral-500)">${fechaCorta(f.fecha)}</span>`)}
    </div>
    <span style="font-size:12px;color:var(--color-neutral-400)">Cada punto es una evaluación, con el color de su resultado. ${todos ? "Cada icono es un tripulante. Toca uno para ver el detalle, o elige una persona para ver su línea." : "Los datos vienen del registrador (MongoDB)."}</span>
  </section>
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,460px),1fr));gap:20px;align-items:start">
    <section style="overflow-x:auto;grid-column:span ${S.w >= 1200 ? 2 : 1}">
      <table class="table" style="min-width:560px">
        <thead><tr><th>Fecha</th><th>Persona</th><th>Estado</th><th style="text-align:right">Puntaje</th><th style="text-align:right">KSS</th><th style="text-align:right">Sueño</th><th style="text-align:right">PVT</th></tr></thead>
        <tbody>
          ${rows.slice(pag * POR_PAGINA, pag * POR_PAGINA + POR_PAGINA).map((f) => { const st = ST[f.color] || ST.sin; return h`<tr data-click="hSel" data-arg="${f.id}" style="cursor:pointer;background-color:${f.id === S.hSel ? "color-mix(in srgb, var(--color-accent) 10%, transparent)" : "transparent"}">
              <td style="${MONO};font-size:12px;white-space:nowrap">${fechaCorta(f.fecha)} ${horaCorta(f.fecha)}</td>
              <td>${L.nombre(f.persona)}${f.simulado ? h` <span class="tag tag-neutral" style="${MONO};font-size:9px;padding:1px 6px">SIM</span>` : ""}</td>
              <td><span style="display:inline-flex;align-items:center;gap:5px;padding:2px 8px;border-radius:5px;background:${st.bg};color:${st.fg};${MONO};font-size:11px;font-weight:600"><i class="ph-fill ${st.icon}"></i>${st.word}</span></td>
              <td style="text-align:right;${MONO}">${fmt(f.puntaje)}</td>
              <td style="text-align:right;${MONO}">${entero(f.kss)}</td>
              <td style="text-align:right;${MONO}">${fmt(f.horas_sueno, 1)}</td>
              <td style="text-align:right;${MONO}">${entero(f.pvt_mediana)}</td>
            </tr>`; })}
        </tbody>
      </table>
      ${nPag > 1 ? h`<nav aria-label="Paginación del historial" style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;padding:12px 4px 0">
          <span style="${MONO};font-size:12px;color:var(--color-neutral-400);margin-right:auto">${pag * POR_PAGINA + 1}–${Math.min(rows.length, pag * POR_PAGINA + POR_PAGINA)} de ${rows.length} evaluaciones</span>
          <button class="btn btn-ghost" type="button" data-click="hPag" data-arg="${pag - 1}" ${si(pag === 0, "disabled")} aria-label="Página anterior" style="padding:6px 8px"><i class="ph ph-caret-left"></i></button>
          ${nums.map((i) => (i === -1 ? h`<span style="padding:0 4px;color:var(--color-neutral-500)">…</span>`
            : h`<button type="button" class="hv-acc6" data-click="hPag" data-arg="${i}" aria-current="${i === pag ? "page" : "false"}" style="min-width:32px;height:32px;padding:0 8px;border:0;border-radius:var(--radius-sm);background:${i === pag ? "var(--color-accent-900)" : "transparent"};box-shadow:${i === pag ? "inset 0 0 0 1px var(--color-accent)" : "inset 0 0 0 1px var(--color-neutral-800)"};color:${i === pag ? "var(--color-accent-200)" : "var(--color-neutral-300)"};${MONO};font-size:12px;cursor:pointer">${i + 1}</button>`))}
          <button class="btn btn-ghost" type="button" data-click="hPag" data-arg="${pag + 1}" ${si(pag >= nPag - 1, "disabled")} aria-label="Página siguiente" style="padding:6px 8px"><i class="ph ph-caret-right"></i></button>
        </nav>` : ""}
      ${rows.length ? "" : vacio}
    </section>
    <aside style="${SECC};position:sticky;top:20px">
      ${sel ? h`${etq("Detalle de la evaluación")}
        <div style="display:flex;align-items:center;gap:10px"><span style="font-size:20px;font-weight:500">${L.nombre(sel.persona)}</span>${pildora(ST[sel.color] || ST.sin, "", "font-size:11px;padding:2px 8px")}${sel.simulado ? tagMono("SIMULADO") : ""}</div>
        <span style="${MONO};font-size:12px;color:var(--color-neutral-400);word-break:break-all">${new Date(sel.fecha).toLocaleString("es", { dateStyle: "medium", timeStyle: "short" })} · sesión ${sel.id}</span>
        <dl style="display:grid;grid-template-columns:auto 1fr;gap:8px 16px;margin:0;font-size:13px">
          <dt style="color:var(--color-neutral-400)">Puntaje</dt><dd style="margin:0;${MONO}">${fmt(sel.puntaje)}</dd>
          <dt style="color:var(--color-neutral-400)">Tarea</dt><dd style="margin:0">${sel.tarea ? cap(sel.tarea) : "–"}</dd>
          <dt style="color:var(--color-neutral-400)">KSS</dt><dd style="margin:0;${MONO}">${entero(sel.kss)} de 9</dd>
          <dt style="color:var(--color-neutral-400)">Sueño</dt><dd style="margin:0;${MONO}">${fmt(sel.horas_sueno, 1)} h</dd>
          <dt style="color:var(--color-neutral-400)">PVT mediana</dt><dd style="margin:0;${MONO}">${entero(sel.pvt_mediana)} ms</dd>
          <dt style="color:var(--color-neutral-400)">Pulso</dt><dd style="margin:0;${MONO}">${entero(sel.pulso_lpm)} lpm</dd>
          <dt style="color:var(--color-neutral-400)">PERCLOS</dt><dd style="margin:0;${MONO}">${fmt(sel.perclos)}</dd>
        </dl>
        ${(sel.motivos || []).length ? h`<div style="display:flex;flex-direction:column;gap:4px">${sel.motivos.map((m) => h`<span style="display:flex;gap:6px;font-size:12px;color:var(--color-neutral-300)"><i class="ph ph-caret-right" style="color:var(--color-accent);margin-top:2px"></i>${m}</span>`)}</div>` : ""}
        <div style="display:flex;gap:8px;flex-wrap:wrap"><a class="btn btn-secondary" href="${csv}" download style="font-size:13px"><i class="ph ph-download-simple"></i>Exportar CSV</a><button class="btn btn-ghost" type="button" data-click="reproducir" data-arg="${sel.id}" style="font-size:13px"><i class="ph ph-play-circle"></i>Reproducir sesión</button></div>
        ${S.hComando ? h`<div style="display:flex;flex-direction:column;gap:4px"><span style="font-size:12px;color:var(--color-neutral-400)">Copiado. Pégalo en una terminal de la laptop de la estación:</span>${cmd(S.hComando)}</div>` : ""}`
      : h`<div style="display:flex;flex-direction:column;gap:8px;align-items:flex-start;padding:12px 0"><i class="ph ph-cursor-click" style="font-size:24px;color:var(--color-neutral-500)"></i><b style="font-weight:500">Elige una evaluación</b><span style="font-size:13px;color:var(--color-neutral-400)">El detalle aparece aquí.</span>${rows.length ? h`<a class="btn btn-secondary" href="${csv}" download style="font-size:13px;margin-top:4px"><i class="ph ph-download-simple"></i>Exportar CSV del periodo</a>` : ""}</div>`}
    </aside>
  </div>
</div>`;
  }

  // ================================================================== vista: Pruebas
  function vistaPruebas() {
    const PILL = { off: { ...ST.sin, word: "SIN PROBAR" }, pidiendo: { fg: "var(--color-accent-300)", bg: "var(--color-accent-900)", icon: "ph-circle-notch", word: "PIDIENDO PERMISO" }, on: { ...ST.verde, word: "FUNCIONANDO" }, error: { ...ST.rojo, word: "ERROR" } };
    const db = (x) => (x > 0 ? Math.max(-90, Math.round(20 * Math.log10(x))) : -90);
    const lv = Math.max(0, Math.min(1, (db(S.level) + 60) / 60));
    const luzK = S.luz == null ? null : S.luz < 50 ? "baja" : S.luz > 210 ? "alta" : "ok";
    const micOn = S.pMic === "on"; const pkDb = db(S.peakMax); const nDb = S.noise == null ? null : db(S.noise);
    const chk = (st, estado, help) => ({ st, estado, help });
    const checks = [
      { label: "Cámara", ...(S.pCam === "on" ? chk(ST.verde, "hay imagen", S.camRes + " · " + (S.camFps ? S.camFps + " fps" : "fps sin dato")) : S.pCam === "error" ? chk(ST.rojo, "sin imagen", "Revisa el aviso de la tarjeta Cámara.") : chk(ST.sin, "sin probar", "Toca Probar cámara.")) },
      { label: "Iluminación", ...(luzK === "ok" ? chk(ST.verde, "adecuada", "La piel se ve con buena luz.") : luzK === "baja" ? chk(ST.amarillo, "poca luz", "Busca una luz frontal o acércate a una ventana.") : luzK === "alta" ? chk(ST.amarillo, "demasiada luz", "Evita la luz directa detrás o sobre la cámara.") : chk(ST.sin, "sin medir", "Se mide con la cámara encendida.")) },
      { label: "Micrófono", ...(micOn ? (pkDb > -30 ? chk(ST.verde, "se escucha la voz", "Nivel máximo " + pkDb + " dBFS.") : chk(ST.amarillo, "habla para comprobar", "Lee la frase en voz alta.")) : S.pMic === "error" ? chk(ST.rojo, "sin señal", "Revisa el aviso de la tarjeta Micrófono.") : chk(ST.sin, "sin probar", "Toca Probar micrófono.")) },
      { label: "Ruido de fondo", ...(micOn && nDb != null ? (nDb < -55 ? chk(ST.verde, "silencioso", nDb + " dBFS en silencio.") : nDb < -42 ? chk(ST.amarillo, "algo de ruido", "Cierra puertas o aleja ventiladores.") : chk(ST.rojo, "mucho ruido", "La voz no se podrá analizar bien aquí.")) : chk(ST.sin, "sin medir", "Se mide con el micrófono encendido.")) },
      { label: "Saturación", ...(micOn ? (S.peakMax > 0.98 ? chk(ST.amarillo, "satura", "Aleja el micrófono o baja la ganancia.") : chk(ST.verde, "sin saturación", "La voz no se recorta.")) : chk(ST.sin, "sin medir", "Se mide al hablar.")) },
    ];
    const okN = checks.filter((c) => c.st === ST.verde).length;
    const camDevs = S.camDevs.length ? S.camDevs : [{ id: "", label: "Cámara predeterminada" }];
    const micDevs = S.micDevs.length ? S.micDevs : [{ id: "", label: "Micrófono predeterminado" }];
    const chipVivo = `display:inline-flex;align-items:center;gap:5px;padding:3px 8px;border-radius:5px;background:color-mix(in srgb, var(--color-bg) 82%, transparent);${MONO};font-size:11px;color:var(--color-text)`;
    const pill = (P) => h`<span style="display:inline-flex;align-items:center;gap:6px;padding:3px 9px;border-radius:5px;background:${P.bg};color:${P.fg};${MONO};font-size:11px;font-weight:600;letter-spacing:0.06em;white-space:nowrap"><i class="ph-fill ${P.icon}"></i>${P.word}</span>`;
    return h`<div data-k="pruebas" style="display:contents">
  <div style="display:flex;flex-direction:column;gap:6px;max-width:72ch"><h2 style="font-size:26px;margin:0">Prueba de cámara y micrófono</h2><p style="margin:0;color:var(--color-neutral-300);line-height:1.55;text-wrap:pretty">Comprueba que la estación vea y escuche bien a la tripulación antes de evaluar. Usa los dispositivos reales de este equipo y no guarda imagen ni audio. Ciérrala antes de medir: la cámara y el micrófono los usan después los módulos de visión y de voz.</p></div>
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,420px),1fr));gap:20px;align-items:start">
    <section style="${SECC}">
      <div style="display:flex;align-items:center;gap:8px"><i class="ph ph-webcam" style="font-size:18px;color:var(--color-accent)"></i><h3 style="font-size:16px;font-weight:500;margin:0;margin-right:auto">Cámara</h3>${pill(PILL[S.pCam])}</div>
      <div class="field"><label for="pcam">Dispositivo</label><select id="pcam" class="input" data-change="camDev">${camDevs.map((c) => h`<option value="${c.id}" ${si(c.id === S.camDev, "selected")}>${c.label}</option>`)}</select></div>
      <div style="position:relative;aspect-ratio:4/3;border-radius:var(--radius-md);overflow:hidden;background:radial-gradient(120% 90% at 50% 40%, color-mix(in srgb, var(--color-surface) 70%, var(--color-bg)), color-mix(in srgb, var(--color-bg) 60%, var(--ink)))">
        <div style="position:absolute;inset:0;background-image:linear-gradient(color-mix(in srgb, var(--color-accent) 7%, transparent) 1px, transparent 1px),linear-gradient(90deg, color-mix(in srgb, var(--color-accent) 7%, transparent) 1px, transparent 1px);background-size:40px 40px"></div>
        <div style="position:absolute;inset:0;opacity:${S.pCam === "on" ? "1" : "0"};transition:opacity .5s"><div data-congelar="video" style="position:absolute;inset:0"><video id="pru-video" muted playsinline style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover;transform:scaleX(-1)"></video></div></div>
        ${esquinas(12, 20)}
        <div style="position:absolute;left:50%;top:48%;width:38%;aspect-ratio:3/4;transform:translate(-50%,-50%);border-radius:50%;border:1.5px dashed ${S.pCam === "on" ? (luzK === "ok" ? "var(--st-verde)" : "var(--st-amarillo)") : "var(--color-neutral-600)"};transition:border-color .3s"></div>
        ${S.pCam !== "on" ? h`<div style="position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;padding:24px;text-align:center"><i class="ph ph-video-camera" style="font-size:34px;color:var(--color-accent-400)"></i><span style="font-size:14px;color:var(--color-neutral-200);max-width:30ch">${{ off: "Toca Probar cámara para ver la imagen.", pidiendo: "Esperando el permiso del navegador…", error: "No hay imagen." }[S.pCam] || ""}</span></div>`
          : h`<div style="position:absolute;left:40px;right:40px;top:14px;display:flex;gap:6px;flex-wrap:wrap">
            <span style="${chipVivo}"><span style="width:7px;height:7px;border-radius:50%;background:var(--st-rojo);animation:pulso 1.4s ease-in-out infinite"></span>EN VIVO</span>
            <span style="${chipVivo}">${S.camRes}</span><span style="${chipVivo}">${S.camFps ? S.camFps + " fps" : "fps sin dato"}</span>
          </div>
          <span style="position:absolute;left:50%;bottom:16px;transform:translateX(-50%);padding:4px 10px;border-radius:5px;background:color-mix(in srgb, var(--color-bg) 80%, transparent);font-size:12px;color:var(--color-text);white-space:nowrap">Centra el rostro en el óvalo</span>`}
      </div>
      ${S.camErr ? h`<div role="alert" style="display:flex;gap:10px;align-items:flex-start;padding:10px 14px;border-radius:var(--radius-md);background:var(--st-rojo-bg)"><i class="ph ph-x-circle" style="font-size:18px;color:var(--st-rojo);flex:none"></i><span style="font-size:13px;color:var(--color-text)">${S.camErr}</span></div>` : ""}
      <div style="display:flex;flex-direction:column;gap:6px">
        <div style="display:flex;align-items:center;gap:8px;font-size:13px"><i class="ph ph-sun" style="font-size:16px;color:var(--color-neutral-300)"></i><span>Iluminación</span><span style="margin-left:auto;color:${luzK === "ok" ? ST.verde.fg : luzK == null ? "var(--color-neutral-400)" : ST.amarillo.fg}">${luzK == null ? "Sin medir" : { baja: "Poca luz", ok: "Adecuada", alta: "Demasiada luz" }[luzK]}</span><span style="${MONO};font-size:12px;color:var(--color-neutral-400);min-width:28px;text-align:right">${S.luz == null ? "–" : String(Math.round(S.luz))}</span></div>
        <div style="position:relative;height:6px;border-radius:3px;background:linear-gradient(to right, color-mix(in srgb, var(--st-amarillo) 35%, transparent) 0 20%, color-mix(in srgb, var(--st-verde) 30%, transparent) 20% 82%, color-mix(in srgb, var(--st-amarillo) 35%, transparent) 82%)"><span style="position:absolute;top:-3px;left:${S.luz == null ? "0%" : Math.round((S.luz / 255) * 100) + "%"};width:3px;height:12px;margin-left:-1.5px;border-radius:2px;background:var(--color-text);transition:left .4s"></span></div>
        <span style="font-size:11px;color:var(--color-neutral-500)">Brillo medio de la imagen. La zona central es la adecuada para medir los ojos y la boca.</span>
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <button class="btn btn-primary" type="button" data-click="pruCam" ${si(S.pCam === "pidiendo", "disabled")} style="padding:9px 16px"><i class="ph ph-play"></i>${S.pCam === "on" ? "Reiniciar" : "Probar cámara"}</button>
        <button class="btn btn-secondary" type="button" data-click="pruCamStop" ${si(S.pCam !== "on", "disabled")} style="padding:9px 16px"><i class="ph ph-stop"></i>Detener</button>
      </div>
    </section>
    <section style="${SECC}">
      <div style="display:flex;align-items:center;gap:8px"><i class="ph ph-microphone" style="font-size:18px;color:var(--color-accent)"></i><h3 style="font-size:16px;font-weight:500;margin:0;margin-right:auto">Micrófono</h3>${pill(PILL[S.pMic])}</div>
      <div class="field"><label for="pmic">Dispositivo</label><select id="pmic" class="input" data-change="micDev">${micDevs.map((m) => h`<option value="${m.id}" ${si(m.id === S.micDev, "selected")}>${m.label}</option>`)}</select></div>
      <div style="display:flex;flex-direction:column;gap:12px;padding:16px;border-radius:var(--radius-md);background:color-mix(in srgb, var(--color-bg) 60%, var(--ink))">
        <div style="display:flex;align-items:flex-end;gap:3px;height:52px" aria-hidden="true">
          ${Array.from({ length: 32 }, (_, i) => { const on = micOn && i / 32 < lv; const c = i >= 28 ? ST.rojo.fg : i >= 22 ? ST.amarillo.fg : "var(--color-accent)"; return h`<span style="flex:1;height:${14 + i * 1.2}px;border-radius:2px;background:${on ? c : "var(--color-neutral-800)"};box-shadow:${on ? `0 0 6px color-mix(in srgb, ${c} 50%, transparent)` : "none"};transition:background-color .08s"></span>`; })}
        </div>
        <svg viewBox="0 0 400 80" style="width:100%;height:auto;display:block" role="img" aria-label="Forma de onda del micrófono"><line x1="0" y1="40" x2="400" y2="40" style="stroke:var(--color-neutral-800);stroke-width:1"></line><polyline points="${S.wave.length ? S.wave.map((v, i) => ((i * 400) / 63).toFixed(1) + "," + (40 - Math.max(-1, Math.min(1, v * 4)) * 36).toFixed(1)).join(" ") : "0,40 400,40"}" style="fill:none;stroke:var(--color-accent);stroke-width:1.5;stroke-linejoin:round"></polyline></svg>
      </div>
      <div style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px">
        ${[["Nivel", micOn ? String(db(S.level)) : "–", "dBFS ahora"], ["Pico", micOn ? String(pkDb) : "–", "dBFS máximo"], ["Ruido de fondo", micOn && nDb != null ? String(nDb) : "–", "dBFS en silencio"]].map(([label, valor, unidad]) => h`<div style="display:flex;flex-direction:column;gap:2px;padding:10px 12px;border-radius:var(--radius-md);box-shadow:inset 0 0 0 1px var(--color-neutral-800)"><span style="font-size:11px;color:var(--color-neutral-400)">${label}</span><span style="${MONO};font-size:22px;font-variant-numeric:tabular-nums">${valor}</span><span style="font-size:10px;color:var(--color-neutral-500)">${unidad}</span></div>`)}
      </div>
      <div style="display:flex;gap:10px;align-items:flex-start;padding:12px 14px;border-radius:var(--radius-md);box-shadow:inset 2px 0 0 var(--color-accent);background:color-mix(in srgb, var(--color-accent) 6%, transparent)"><i class="ph ph-quotes" style="font-size:18px;color:var(--color-accent)"></i><span style="display:flex;flex-direction:column;gap:2px"><span style="font-size:12px;color:var(--color-neutral-400)">Di en voz alta, con tono normal</span><span style="font-size:15px">Estación lista para la evaluación de la tripulación.</span></span></div>
      ${S.micErr ? h`<div role="alert" style="display:flex;gap:10px;align-items:flex-start;padding:10px 14px;border-radius:var(--radius-md);background:var(--st-rojo-bg)"><i class="ph ph-x-circle" style="font-size:18px;color:var(--st-rojo);flex:none"></i><span style="font-size:13px;color:var(--color-text)">${S.micErr}</span></div>` : ""}
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <button class="btn btn-primary" type="button" data-click="pruMic" ${si(S.pMic === "pidiendo", "disabled")} style="padding:9px 16px"><i class="ph ph-play"></i>${micOn ? "Reiniciar" : "Probar micrófono"}</button>
        <button class="btn btn-secondary" type="button" data-click="pruMicStop" ${si(!micOn, "disabled")} style="padding:9px 16px"><i class="ph ph-stop"></i>Detener</button>
        <button class="btn btn-ghost" type="button" data-click="pruGrabar" ${si(!micOn || S.recFase === "grabando", "disabled")} style="padding:9px 12px"><i class="ph ph-record"></i>${S.recFase === "grabando" ? "Grabando 3 s…" : "Grabar 3 s y escuchar"}</button>
      </div>
      ${S.recUrl ? h`<div style="display:flex;flex-direction:column;gap:4px"><span style="font-size:12px;color:var(--color-neutral-400)">Escucha la grabación: la voz debe oírse clara y sin eco.</span><audio controls src="${S.recUrl}" style="width:100%;height:36px"></audio></div>` : ""}
    </section>
  </div>
  <section style="${SECC}">
    <div style="display:flex;align-items:baseline;gap:10px"><h2 style="font-size:15px;margin:0">Resumen</h2><span style="font-size:12px;color:var(--color-neutral-400)">${okN} de ${checks.length} en orden</span></div>
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,220px),1fr));gap:12px">
      ${checks.map((c) => h`<div style="display:flex;gap:10px;align-items:flex-start"><i class="ph-fill ${c.st.icon}" style="font-size:18px;color:${c.st.fg};margin-top:1px;transition:color .3s"></i><span style="display:flex;flex-direction:column;gap:1px"><span style="font-size:13px"><b style="font-weight:500">${c.label}</b> <span style="color:${c.st.fg}">${c.estado}</span></span><span style="font-size:12px;color:var(--color-neutral-400);text-wrap:pretty">${c.help}</span></span></div>`)}
    </div>
    <div style="display:flex;gap:8px;justify-content:flex-end;flex-wrap:wrap"><button class="btn btn-primary" type="button" data-click="ir" data-arg="evaluacion" style="padding:9px 18px">Ir a la evaluación<i class="ph ph-arrow-right"></i></button></div>
  </section>
</div>`;
  }

  // ================================================================== vista: Configuración
  function vistaConfig() {
    const camara = CFG.camara == null || CFG.camara === "" ? "0" : String(CFG.camara);
    const esDroid = /^https?:/i.test(camara);
    const opcionesCam = [["0", "0 · Cámara de la laptop"], ["1", "1 · Cámara USB"], ["droidcam", "DroidCam · celular por Wi-Fi"]];
    if (!esDroid && !["0", "1"].includes(camara)) opcionesCam.push([camara, `${camara} · otra cámara`]);
    const valorCam = esDroid ? "droidcam" : camara;
    const permiso = (estado) => ({ granted: ["Concedido", ST.verde], denied: ["Denegado", ST.rojo], prompt: ["Sin pedir todavía", ST.sin] }[estado] || ["Sin dato", ST.sin]);
    const broker = estadoBroker();
    const sw = (on) => ({ track: on ? "var(--color-accent-800)" : "var(--color-neutral-900)", edge: on ? "var(--color-accent)" : "var(--color-neutral-700)", knob: on ? "19px" : "3px", knobBg: on ? "var(--color-accent-200)" : "var(--color-neutral-500)" });
    const prefs = [["proyector", "Texto grande para proyector", "Para leerse a 3 m en la pantalla de tripulación."], ["movimiento", "Reducir movimiento", "Quita el fondo animado, el barrido de la cámara y los giros de carga."], ["alto", "Alto contraste", "Sube el contraste de bordes y textos secundarios."]];
    const sistema = [
      ["Broker", `${location.hostname || "localhost"} · ws ${CFG.mqtt_puerto_ws || 9001}${CFG.mqtt_host ? ` · módulos en ${CFG.mqtt_host}:${CFG.mqtt_puerto || 1883}` : ""}`],
      ["Tripulación", (CFG.tripulacion || []).join(", ") || "–"],
      ["Visión", `MediaPipe FaceLandmarker · ${SEGUNDOS_CAMARA} s`],
      ["Becspace AI", `${CFG.ollama_model || "–"} · Whisper ${CFG.whisper_model || "–"}`],
      ["PVT", `${segundosPvtConfig()} s (demo ${L.PVT.DEMO_S} s)`],
      ["Base de datos", `MongoDB ${CFG.mongo_host || "127.0.0.1"} · ${CFG.mongo_db || "apto_hoy"}`],
      ["Tierra", `retraso simulado de ${CFG.retraso_tierra_s ?? 20} s · tierra.html`],
    ];
    const privacidad = ["Todo corre en la laptop de la estación, sin internet.", "La imagen de la cámara no se guarda: solo los números calculados.", "MongoDB escucha solo en 127.0.0.1 y no se abre a la red.", "Las otras laptops entran con un usuario de solo lectura."];
    const temas = [["oscuro", "Oscuro", "ph-moon", "#161826", "#10121c", "#232532", "#e9e9ed", "#9184d9"], ["claro", "Claro", "ph-sun", "#e9ebf5", "#dcdff0", "#f7f7fc", "#1c1e2b", "#6a5cc4"]];
    return h`<div data-k="config" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,380px),1fr));gap:20px;align-items:start">
    <section style="${SECC}">
      <h2 style="font-size:15px;margin:0;display:flex;align-items:center;gap:8px"><i class="ph ph-users-three" style="color:var(--color-accent)"></i>Icono de cada tripulante</h2>
      <span style="font-size:12px;color:var(--color-neutral-400)">Identifica a cada persona en las gráficas del historial y en la evaluación. Se guarda en este navegador.</span>
      ${TRIPULACION().map((p) => h`<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
          <span style="width:64px;font-size:14px">${L.nombre(p)}</span>
          <div role="radiogroup" aria-label="Icono de ${L.nombre(p)}" style="display:flex;gap:4px;flex-wrap:wrap">
            ${ICONOS.map(([ic, label]) => { const on = icono(p) === ic; return h`<button type="button" class="hv-acc6" role="radio" aria-checked="${String(on)}" aria-label="${label}" data-click="icono" data-arg="${p}|${ic}" style="width:30px;height:30px;padding:0;border:0;border-radius:7px;display:grid;place-items:center;background:${on ? "var(--color-accent-900)" : "transparent"};box-shadow:${on ? "inset 0 0 0 1px var(--color-accent)" : "inset 0 0 0 1px var(--color-neutral-800)"};color:${on ? "var(--color-accent-200)" : "var(--color-neutral-300)"};cursor:pointer"><i class="ph-fill ${ic}" style="font-size:18px"></i></button>`; })}
          </div>
        </div>`)}
    </section>
    <section style="${SECC};gap:14px">
      <h2 style="font-size:15px;margin:0;display:flex;align-items:center;gap:8px"><i class="ph ph-circle-half" style="color:var(--color-accent)"></i>Apariencia</h2>
      <div role="radiogroup" aria-label="Modo de color" style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px">
        ${temas.map(([k, label, ic, bg, nav, card, ink, acc]) => { const on = S.tema === k; return h`<button type="button" class="hv-acc6" role="radio" aria-checked="${String(on)}" data-click="tema" data-arg="${k}" style="display:flex;flex-direction:column;gap:8px;padding:10px;border:0;border-radius:var(--radius-md);background:transparent;box-shadow:${on ? "inset 0 0 0 1.5px var(--color-accent)" : "inset 0 0 0 1px var(--color-neutral-800)"};cursor:pointer;text-align:left;transition:box-shadow .2s">
            <span style="position:relative;display:block;height:64px;border-radius:6px;overflow:hidden;background:${bg}">
              <span style="position:absolute;left:0;top:0;bottom:0;width:26%;background:${nav}"></span>
              <span style="position:absolute;left:34%;top:12px;width:40%;height:8px;border-radius:3px;background:${ink}"></span>
              <span style="position:absolute;left:34%;top:28px;right:10px;height:24px;border-radius:4px;background:${card}"></span>
              <span style="position:absolute;left:40%;top:37px;width:22%;height:6px;border-radius:3px;background:${acc}"></span>
            </span>
            <span style="display:flex;align-items:center;gap:6px;font-size:13px"><i class="ph ${ic}"></i>${label}${on ? h`<i class="ph-fill ph-check-circle" style="margin-left:auto;color:var(--color-accent)"></i>` : ""}</span>
          </button>`; })}
      </div>
      <span style="font-size:12px;color:var(--color-neutral-400)">Misma paleta en los dos modos. El modo oscuro es el recomendado para el proyector de la tripulación.</span>
    </section>
    <section style="${SECC};gap:14px">
      <h2 style="font-size:15px;margin:0;display:flex;align-items:center;gap:8px"><i class="ph ph-webcam" style="color:var(--color-accent)"></i>Cámara</h2>
      <div class="field"><label for="cam">Fuente de video (CAMARA)</label>
        <select id="cam" class="input" disabled title="Se cambia en config.local.env">${opcionesCam.map(([v, t]) => h`<option value="${v}" ${si(v === valorCam, "selected")}>${t}</option>`)}</select>
      </div>
      ${esDroid ? h`<div class="field"><label for="url">URL de DroidCam</label><input id="url" class="input" value="${camara}" readonly style="${MONO}"></div>
        <span style="font-size:12px;color:var(--color-neutral-400)">La app del celular muestra la IP. Solo un programa a la vez puede recibir la imagen.</span>` : ""}
      <div class="field"><label for="dur">Duración de la medición</label><input id="dur" class="input" value="${SEGUNDOS_CAMARA} s" readonly style="${MONO}"></div>
      <span style="font-size:12px;color:var(--color-neutral-400)">Se cambian en config.local.env (CAMARA y VISION_SEGUNDOS); luego reinicien el módulo de visión y servidor.py.</span>
      <div style="display:flex;gap:8px;flex-wrap:wrap"><button class="btn btn-secondary" type="button" data-click="buscarCamaras"><i class="ph ph-magnifying-glass"></i>Buscar cámaras</button><button class="btn btn-ghost" type="button" data-click="ir" data-arg="pruebas"><i class="ph ph-faders"></i>Probar cámara y micrófono</button></div>
      ${S.verComandoCamaras ? h`<span style="font-size:12px;color:var(--color-neutral-400)">Las lista el módulo de visión: ${cmd("python vision\\vision.py --listar")}</span>` : ""}
    </section>
    <section style="${SECC}">
      <h2 style="font-size:15px;margin:0;display:flex;align-items:center;gap:8px"><i class="ph ph-shield-check" style="color:var(--color-accent)"></i>Permisos</h2>
      ${[["ph-webcam", "Cámara (este navegador)", ...permiso(S.permisos.camera)], ["ph-microphone", "Micrófono (este navegador)", ...permiso(S.permisos.microphone)], ["ph-broadcast", "Broker MQTT", cap(broker.corto.toLowerCase()), broker.st]]
        .map(([ic, label, estado, st]) => h`<div style="display:flex;align-items:center;gap:10px"><i class="ph ${ic}" style="font-size:18px;color:var(--color-neutral-300)"></i><span style="flex:1;font-size:14px">${label}</span><span style="display:inline-flex;align-items:center;gap:5px;font-size:12px;color:${st.fg}"><i class="ph-fill ${st.icon}"></i>${estado}</span></div>`)}
    </section>
    <section style="${SECC};gap:14px">
      <h2 style="font-size:15px;margin:0;display:flex;align-items:center;gap:8px"><i class="ph ph-sliders-horizontal" style="color:var(--color-accent)"></i>Preferencias visuales</h2>
      ${prefs.map(([k, label, help]) => { const on = S.prefs[k]; const s = sw(on); return h`<label style="display:flex;align-items:center;gap:12px;cursor:pointer">
          <span style="flex:1;display:flex;flex-direction:column;gap:1px"><span style="font-size:14px">${label}</span><span style="font-size:12px;color:var(--color-neutral-400)">${help}</span></span>
          <input type="checkbox" role="switch" ${si(on, "checked")} data-change="pref" data-arg="${k}" style="position:absolute;opacity:0;width:0;height:0">
          <span aria-hidden="true" style="width:36px;height:20px;border-radius:10px;flex:none;position:relative;background:${s.track};box-shadow:inset 0 0 0 1px ${s.edge};transition:background .15s"><span style="position:absolute;top:3px;left:${s.knob};width:14px;height:14px;border-radius:50%;background:${s.knobBg};transition:left .15s"></span></span>
        </label>`; })}
    </section>
    <section style="${SECC};gap:10px">
      <h2 style="font-size:15px;margin:0;display:flex;align-items:center;gap:8px"><i class="ph ph-cpu" style="color:var(--color-accent)"></i>Información del sistema</h2>
      <dl style="display:grid;grid-template-columns:auto 1fr;gap:6px 16px;margin:0;font-size:13px">
        ${sistema.map(([k, v]) => h`<dt style="color:var(--color-neutral-400)">${k}</dt><dd style="margin:0;${MONO};font-size:12px;word-break:break-all">${v}</dd>`)}
      </dl>
    </section>
    <section style="${SECC};gap:10px">
      <h2 style="font-size:15px;margin:0;display:flex;align-items:center;gap:8px"><i class="ph ph-lock-simple" style="color:var(--color-accent)"></i>Privacidad y datos</h2>
      ${privacidad.map((pv) => h`<span style="display:flex;gap:8px;align-items:flex-start;font-size:13px;color:var(--color-neutral-200);text-wrap:pretty"><i class="ph ph-check" style="color:var(--color-accent);margin-top:2px"></i>${pv}</span>`)}
      <button class="btn btn-secondary" type="button" data-click="abrirModal" style="align-self:flex-start;margin-top:4px"><i class="ph ph-trash"></i>Borrar mi historial</button>
    </section>
    <section style="display:flex;flex-direction:column;gap:10px;padding:18px;border-radius:var(--radius-lg);box-shadow:inset 0 0 0 1px var(--color-neutral-800)">
      <h2 style="font-size:15px;margin:0;display:flex;align-items:center;gap:8px"><i class="ph ph-info" style="color:var(--color-neutral-300)"></i>Cómo funciona la evaluación</h2>
      <p style="margin:0;font-size:13px;line-height:1.55;color:var(--color-neutral-200);text-wrap:pretty">Cada fuente da 0, 1 o 2 puntos frente a tu línea base. Rojo si una fuente tiene 2 puntos o tres fuentes tienen puntos; amarillo si alguna tiene puntos; verde si ninguna. La voz pesa como máximo 1 punto y el oxígeno solo genera un aviso.</p>
      <p style="margin:0;font-size:13px;line-height:1.55;color:var(--color-neutral-300);text-wrap:pretty">Es un prototipo de apoyo a la decisión. No es un dispositivo médico y no diagnostica.</p>
    </section>
  </div>`;
  }
  function segundosPvtConfig() {
    const s = Number(CFG.pvt_segundos);
    return Number.isFinite(s) && s > 0 ? s : 180;
  }

  // ================================================================== vista: Sistema de diseño
  function vistaSistema() {
    const ramp = (rol) => [100, 200, 300, 400, 500, 600, 700, 800, 900].map((n) => h`<div style="aspect-ratio:1;border-radius:4px;background:var(--color-${rol}-${n})"></div>`);
    const alertas = [
      ["ph-circle-notch", "var(--color-accent-300)", "var(--color-accent-900)", "Cargando", "Esperando la evaluación del coordinador…"],
      ["ph-check-circle", ST.verde.fg, ST.verde.bg, "Listo", "Medición enviada. Puedes continuar."],
      ["ph-warning", ST.amarillo.fg, ST.amarillo.bg, "Aviso", "Datos insuficientes de la cámara: repetir con más luz."],
      ["ph-x-circle", ST.rojo.fg, ST.rojo.bg, "Error", "No se encontró la cámara. Revisa CAMARA en config.env."],
    ];
    const brillo = "background:linear-gradient(90deg, var(--color-neutral-800), var(--color-neutral-700), var(--color-neutral-800));background-size:400px 100%;animation:brillo 1.4s linear infinite";
    return h`<div data-k="sistema" style="display:contents">
  <section style="display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,300px),1fr));gap:20px;align-items:center;padding:22px;border-radius:var(--radius-lg);background:radial-gradient(90% 90% at 40% 50%, #0b1f22, #080C12);box-shadow:var(--shadow-sm)">
    <div style="grid-column:span ${S.w >= 700 ? 2 : 1};min-width:0;max-width:620px" data-congelar="logo-full">${logo("ds", "full", "dark")}</div>
    <div style="display:flex;flex-direction:column;gap:12px">
      <span style="font-size:11px;letter-spacing:0.12em;text-transform:uppercase;color:#A7B3CC;${MONO}">Logotipo animado</span>
      <p style="margin:0;font-size:14px;line-height:1.55;color:#F4F6FF;text-wrap:pretty">La Tierra gira despacio y el cohete da una vuelta cada 8 segundos: pasa por detrás del planeta y cruza las letras con un destello verde en el punto de entrada.</p>
      <div style="width:196px;padding:8px;border-radius:8px;box-shadow:inset 0 0 0 1px rgba(125,145,210,0.18)" data-congelar="logo-mini">${logo("ds", "compact", "dark")}</div>
      <span style="font-size:12px;color:#A7B3CC">Versión compacta para la barra lateral. Pantalla de carga al abrir la estación.</span>
    </div>
  </section>
  <section style="display:flex;flex-direction:column;gap:10px;max-width:72ch">
    <h2 style="font-size:26px;margin:0">Identidad: una estación personal de monitoreo</h2>
    <p style="margin:0;color:var(--color-neutral-300);line-height:1.6;text-wrap:pretty">Nocturne aporta el fondo azul grisáceo, Inter a peso 500 y el acento violeta usado como línea y brillo. Encima sumamos tres piezas propias: datos en monoespaciada, un semáforo desaturado que siempre lleva palabra e icono, y una instrumentación discreta con retículas, órbitas y trazos de señal solo donde hay medición.</p>
  </section>
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,340px),1fr));gap:20px;align-items:start">
    <section style="${SECC}">
      ${etq("Color · base Nocturne")}
      <div style="display:grid;grid-template-columns:repeat(9,1fr);gap:3px">${ramp("neutral")}${ramp("accent")}</div>
      ${etq("Estados · OKLCH desaturado", ";margin-top:6px")}
      ${["verde", "amarillo", "rojo", "sin"].map((k) => h`<div style="display:flex;align-items:center;gap:10px">${pildora(ST[k], "", "min-width:120px")}<span style="font-size:12px;color:var(--color-neutral-300)">${ST[k].label}</span></div>`)}
    </section>
    <section style="${SECC};gap:10px">
      ${etq("Tipografía")}
      <span style="font-size:42px;font-weight:500;line-height:1.1;letter-spacing:-0.015em">Display 42</span>
      <span style="font-size:26px;font-weight:500">Título de pantalla 26</span>
      <span style="font-size:17px;font-weight:500">Sección 17</span>
      <span style="font-size:14px">Texto 14 · Inter 400 para descripciones y formularios.</span>
      ${etq("Etiqueta mono 11")}
      <span style="${MONO};font-size:40px;font-variant-numeric:tabular-nums">68<span style="font-size:13px;color:var(--color-neutral-400)"> lpm</span></span>
      ${etq("Espacio · radios", ";margin-top:6px")}
      <div style="display:flex;align-items:flex-end;gap:8px">
        ${[["1", "3px"], ["2", "6px"], ["3", "8px"], ["4", "11px"], ["6", "17px"], ["8", "22px"]].map(([k, v]) => h`<div style="display:flex;flex-direction:column;align-items:center;gap:4px"><div style="width:${v};height:${v};background:var(--color-accent-700);border-radius:2px"></div><span style="${MONO};font-size:10px;color:var(--color-neutral-400)">${k}</span></div>`)}
        <div style="width:1px;height:28px;background:var(--color-divider);margin:0 6px"></div>
        <div style="width:28px;height:28px;border-radius:4px;box-shadow:inset 0 0 0 1px var(--color-neutral-500)"></div>
        <div style="width:28px;height:28px;border-radius:8px;box-shadow:inset 0 0 0 1px var(--color-neutral-500)"></div>
        <div style="width:28px;height:28px;border-radius:14px;box-shadow:inset 0 0 0 1px var(--color-neutral-500)"></div>
      </div>
    </section>
    <section style="${SECC}">
      ${etq("Botones · reposo, foco, deshabilitado")}
      <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
        <button class="btn btn-primary" type="button" style="padding:9px 16px">Primario</button>
        <button class="btn btn-secondary" type="button" style="padding:9px 16px">Secundario</button>
        <button class="btn btn-secondary" type="button" style="padding:9px 16px;border-color:var(--color-accent-600);color:var(--color-accent-200)">Contorno</button>
        <button class="btn btn-ghost" type="button" style="padding:9px 10px">Fantasma</button>
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
        <button class="btn btn-primary" type="button" style="padding:9px 16px;outline:2px solid var(--color-accent);outline-offset:2px">Foco</button>
        <button class="btn btn-primary" type="button" style="padding:9px 16px;background:color-mix(in srgb, var(--color-accent) 22%, transparent)">Activo</button>
        <button class="btn btn-primary" type="button" disabled style="padding:9px 16px">Deshabilitado</button>
        <button class="btn btn-secondary btn-icon" type="button" aria-label="Reiniciar"><i class="ph ph-arrow-counter-clockwise"></i></button>
      </div>
      ${etq("Etiquetas y tooltip", ";margin-top:6px")}
      <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
        ${tagMono("SIMULADO", "tag-outline")}${tagMono("PROVISIONAL")}<span class="tag tag-accent">Línea base</span>
        <span class="con-tip" style="position:relative;display:inline-flex" tabindex="0">
          <i class="ph ph-question" style="font-size:18px;color:var(--color-neutral-300)"></i>
          <span role="tooltip" style="position:absolute;left:50%;bottom:calc(100% + 8px);transform:translateX(-50%);width:220px;padding:8px 10px;border-radius:var(--radius-md);background:var(--color-neutral-900);box-shadow:var(--shadow-md);font-size:12px;line-height:1.45;color:var(--color-neutral-100)">PERCLOS es la fracción del tiempo con los ojos casi cerrados.</span>
        </span>
      </div>
    </section>
    <section style="${SECC}">
      ${etq("Estados de contenido")}
      <div style="display:flex;flex-direction:column;gap:8px">
        <div style="display:flex;flex-direction:column;gap:6px;padding:12px;border-radius:var(--radius-md);background:color-mix(in srgb, var(--color-bg) 50%, transparent)" aria-busy="true">
          <div style="height:10px;width:40%;border-radius:4px;${brillo}"></div>
          <div style="height:22px;width:60%;border-radius:4px;${brillo}"></div>
        </div>
        ${alertas.map(([ic, fg, bg, t, x]) => h`<div role="status" style="display:flex;gap:10px;align-items:flex-start;padding:10px 12px;border-radius:var(--radius-md);background:${bg}">
            <i class="ph ${ic}" style="font-size:17px;color:${fg};flex:none"></i>
            <span style="display:flex;flex-direction:column;gap:1px"><b style="font-weight:500;font-size:13px;color:${fg}">${t}</b><span style="font-size:12px;color:var(--color-neutral-200)">${x}</span></span>
          </div>`)}
      </div>
    </section>
    <section style="${SECC}">
      ${etq("Formularios y progreso")}
      <div class="field"><label for="dsn">Nombre</label><input id="dsn" class="input" data-libre placeholder="bri"></div>
      <div style="display:flex;gap:14px;flex-wrap:wrap">
        <label class="radio"><input type="radio" name="dsr" checked><span class="dot"></span>3 minutos</label>
        <label class="radio"><input type="radio" name="dsr"><span class="dot"></span>1 minuto (demo)</label>
      </div>
      <div style="display:flex;flex-direction:column;gap:6px">
        <div style="display:flex;justify-content:space-between;font-size:12px;color:var(--color-neutral-300)"><span>Adquiriendo datos</span><span style="${MONO}">62 %</span></div>
        <div style="height:4px;border-radius:2px;background:var(--color-neutral-800)"><div style="height:100%;width:62%;border-radius:2px;background:var(--color-accent);box-shadow:0 0 8px color-mix(in srgb, var(--color-accent) 60%, transparent)"></div></div>
      </div>
      <button class="btn btn-secondary" type="button" data-click="abrirModal" style="align-self:flex-start">Abrir modal</button>
    </section>
    <section style="${SECC}">
      ${etq("Tipos de dato")}
      ${Object.values(TIPOS).map((tl) => h`<div style="display:flex;gap:10px;align-items:flex-start"><i class="ph ${tl.icon}" style="font-size:17px;color:${tl.fg};margin-top:1px"></i><span style="display:flex;flex-direction:column;gap:1px"><b style="font-weight:500;font-size:13px">${tl.label}</b><span style="font-size:12px;color:var(--color-neutral-400)">${tl.help}</span></span></div>`)}
    </section>
  </div>
</div>`;
  }

  // ================================================================== arranque
  aplicarTema();
  aplicarPrefs();
  Fondo.iniciar(document.getElementById("fondo"), { claro: () => S.tema === "claro", quieto: reducido });

  const pantallaPedida = params.get("pantalla");
  if (NAV.some(([id]) => id === pantallaPedida)) S.pantalla = pantallaPedida;
  let pasoInicial = params.get("paso") || "";
  if (/^\d+$/.test(pasoInicial)) pasoInicial = PASOS[Number(pasoInicial)] || "";
  if (PASOS.includes(pasoInicial) && pasoInicial !== "inicio") {  // atajo de prueba: sin publicar la sesión
    entrarInicio();
    S.persona = (params.get("persona") || (CFG.tripulacion || [])[0] || "bri").toLowerCase();
    S.tarea = params.get("tarea") || TAREAS[0];
    S.demo = params.get("demo") === "1";
    S.conDsst = params.get("dsst") === "1" || pasoInicial === "simbolos";
    S.sesion = `prueba-${marcaSesion()}-${S.persona}`;
    S.inicio = Date.now();
    S.pantalla = "evaluacion";
    irA(pasoInicial);
  } else {
    entrarInicio();
  }
  if (S.pantalla === "historial") cargarHistorial();
  else if (window.APTO) {  // para el Panel: pulso, KSS y PVT de las evaluaciones de hoy aunque la página se abra después
    fetch("historial.json?dias=1").then((r) => (r.ok ? r.json() : null)).then((j) => { if (j && j.disponible) { completarUltimas(j.filas || []); pedirPintar(); } }).catch(() => {});
  }
  if (S.pantalla === "config") revisarPermisos();
  if (S.splash) {
    setTimeout(() => { S.splashVa = true; pedirPintar(); }, 60);
    setTimeout(() => { S.splashFuera = true; pedirPintar(); }, 2300);
    setTimeout(() => { S.splash = false; pedirPintar(); }, 2900);
  }
  pintar();
})();
