/* Houston (control de misión en Tierra): la vista, con el diseño Becspace/Nocturne de la estación.
 * Usa las mismas piezas que paneles/web/estacion.js (nocturne.css, app.css, Plantilla, Logo, Fondo, íconos Phosphor)
 * y la misma forma de pintar: h`...` escapa todo lo interpolado y morph() cambia solo lo distinto.
 * Solo lee: pide los datos a la API de Houston (api/*.json) cada 5 s. No se conecta al broker. */
(function () {
  "use strict";

  const { h, si, morph } = Plantilla;
  const raiz = document.getElementById("app");
  const CADA_MS = 2000;
  const PASOS_VIVO = [["esp32", "Dispositivo", "ph-heartbeat"], ["vision", "Cámara", "ph-webcam"], ["voz", "Voz", "ph-microphone"],
    ["pvt", "Reacción", "ph-timer"], ["dsst", "Símbolos", "ph-shapes"], ["cuestionario", "Cuestionario", "ph-list-checks"]];

  // ================================================================== constantes del diseño (las de la estación)
  const ST = {
    verde: { fg: "var(--st-verde)", bg: "var(--st-verde-bg)", icon: "ph-check-circle", word: "VERDE", label: "Condición favorable para la tarea" },
    amarillo: { fg: "var(--st-amarillo)", bg: "var(--st-amarillo-bg)", icon: "ph-warning-circle", word: "AMARILLO", label: "Precaución: en pareja o posponer" },
    rojo: { fg: "var(--st-rojo)", bg: "var(--st-rojo-bg)", icon: "ph-x-circle", word: "ROJO", label: "No recomendado hoy" },
    sin: { fg: "var(--color-neutral-400)", bg: "var(--color-neutral-900)", icon: "ph-minus-circle", word: "SIN EVALUAR", label: "Falta la evaluación" },
  };
  const TIPOS = {
    medido: { label: "Medido", icon: "ph-target", fg: "var(--color-accent-300)" },
    estimado: { label: "Estimado", icon: "ph-approximate-equals", fg: "var(--color-neutral-300)" },
    reportado: { label: "Reportado", icon: "ph-chat-centered-text", fg: "var(--color-neutral-300)" },
    no_disponible: { label: "No disponible", icon: "ph-prohibit", fg: "var(--color-neutral-500)" },
  };
  const THEME_DARK = { "--color-bg": "#060913", "--color-surface": "rgba(22,28,48,0.82)", "--color-text": "#F4F6FF", "--color-neutral-300": "#A7B3CC", "--color-divider": "rgba(125,145,210,0.16)", "--nav-bg": "rgba(8,14,34,0.74)", "--card-edge": "rgba(125,145,210,0.18)", "--shadow-sm": "0 0 0 1px rgba(125,145,210,0.18), 0 12px 36px rgba(0,0,0,0.22)", "--st-verde": "oklch(0.80 0.10 160)", "--st-verde-bg": "oklch(0.32 0.045 160)", "--st-amarillo": "oklch(0.85 0.10 85)", "--st-amarillo-bg": "oklch(0.34 0.05 80)", "--st-rojo": "oklch(0.76 0.11 25)", "--st-rojo-bg": "oklch(0.32 0.06 22)", "--ink": "black" };
  const THEME_LIGHT = {
    "--color-bg": "#e9ebf5", "--color-surface": "#f7f7fc", "--color-text": "#1c1e2b", "--color-accent": "#6a5cc4", "--color-divider": "color-mix(in srgb, #1c1e2b 14%, transparent)",
    "--color-neutral-100": "#1f2129", "--color-neutral-200": "#2f3240", "--color-neutral-300": "#454857", "--color-neutral-400": "#5a5e6e", "--color-neutral-500": "#6e7285", "--color-neutral-600": "#9397ab", "--color-neutral-700": "#b2b6ca", "--color-neutral-800": "#d3d6e4", "--color-neutral-900": "#e2e4ef",
    "--color-accent-100": "#1e1a3a", "--color-accent-200": "#2b2560", "--color-accent-300": "#4a3f99", "--color-accent-400": "#5d50b5", "--color-accent-500": "#6a5cc4", "--color-accent-600": "#8a7ed6", "--color-accent-700": "#c4bdf5", "--color-accent-800": "#ddd8fb", "--color-accent-900": "#ecebfd",
    "--shadow-sm": "0 0 0 1px #d3d6e4, 0 1px 3px rgba(30,30,70,0.06)", "--shadow-md": "0 0 0 1px #c9cde0, 0 6px 18px rgba(30,30,70,0.12)", "--shadow-lg": "0 0 0 1px #b2b6ca, 0 16px 40px rgba(30,30,70,0.18)",
    "--st-verde": "oklch(0.45 0.10 160)", "--st-verde-bg": "oklch(0.92 0.04 160)", "--st-amarillo": "oklch(0.48 0.09 70)", "--st-amarillo-bg": "oklch(0.93 0.05 85)", "--st-rojo": "oklch(0.50 0.14 25)", "--st-rojo-bg": "oklch(0.93 0.035 22)", "--ink": "#d9dcea", "--nav-bg": "rgba(240,242,250,0.78)", "--card-edge": "rgba(90,100,160,0.16)",
  };
  const ICONOS_DEF = { bri: "ph-star-four", danilo: "ph-rocket-launch", sebas: "ph-triangle", erick: "ph-moon-stars", adrian: "ph-diamond" };
  const NAV = [
    ["panel", "Panel", "ph-squares-four", "Control de misión · Tierra", "Panel de Houston"],
    ["historial", "Evaluaciones", "ph-chart-line-up", "Base de Houston", "Evaluaciones recibidas"],
    ["resultado", "Resultado", "ph-clipboard-text", "Resultado", "Resultado recibido"],
  ];
  const POR_PAGINA = 20;

  const MONO = "font-family:ui-monospace,Menlo,monospace";
  const ETQ = `font-size:11px;letter-spacing:0.12em;text-transform:uppercase;color:var(--color-neutral-400);${MONO}`;
  const TARJ = "border-radius:var(--radius-md);background:var(--color-surface);box-shadow:inset 0 0 0 1px var(--card-edge)";
  const SECC = "display:flex;flex-direction:column;gap:12px;padding:18px;border-radius:var(--radius-lg);background:var(--color-surface);box-shadow:var(--shadow-sm);backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px)";

  // ================================================================== utilidades
  const cap = (s) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : "");
  const nombre = (p) => (p ? cap(p) : "–");
  const num = (x) => (x === null || x === undefined || x === "" || !Number.isFinite(Number(x)) ? null : Number(x));
  const fmt = (x, c = 2) => (num(x) === null ? "–" : Number(x).toFixed(c).replace(".", ","));
  const entero = (x) => (num(x) === null ? "–" : String(Math.round(Number(x))));
  const dd = (n) => String(n).padStart(2, "0");
  const fechaCorta = (ms) => { const d = new Date(ms); return `${dd(d.getDate())}/${dd(d.getMonth() + 1)}`; };
  const horaCorta = (ms) => { const d = new Date(ms); return Number.isNaN(d.getTime()) ? "--:--" : `${dd(d.getHours())}:${dd(d.getMinutes())}`; };
  const horaLarga = (ms) => { const d = new Date(ms); return Number.isNaN(d.getTime()) ? "--:--:--" : `${horaCorta(ms)}:${dd(d.getSeconds())}`; };
  const esHoy = (ms) => new Date(ms).toDateString() === new Date().toDateString();
  const cuando = (ms) => (!ms ? "" : esHoy(ms) ? `hoy ${horaCorta(ms)}` : `${fechaCorta(ms)} ${horaCorta(ms)}`);
  const hace = (ms) => {
    if (!ms) return "–";
    const s = Math.max(0, Math.round((Date.now() - ms) / 1000));
    if (s < 60) return `hace ${s} s`;
    if (s < 3600) return `hace ${Math.round(s / 60)} min`;
    if (s < 86400) return `hace ${Math.round(s / 3600)} h`;
    return `hace ${Math.round(s / 86400)} d`;
  };
  const reducido = () => Boolean(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  const icono = (p) => ICONOS_DEF[p] || "ph-user";
  function leer(clave, defecto) {
    try { const v = localStorage.getItem(clave); return v === null ? defecto : JSON.parse(v); } catch (e) { return defecto; }
  }
  function guardar(clave, valor) {
    try { localStorage.setItem(clave, JSON.stringify(valor)); } catch (e) { /* sin almacenamiento */ }
  }

  // ================================================================== estado
  const params = new URLSearchParams(location.search);
  const S = {
    pantalla: NAV.some(([id]) => id === params.get("pantalla")) ? params.get("pantalla") : "panel",
    w: window.innerWidth,
    tema: leer("houston-tema", "oscuro"),
    api: "cargando", motivo: "",       // estado de /api/tablero.json
    t: null,                           // último tablero
    hist: { estado: "nada", filas: [], motivo: "" },
    periodo: "7", hPersona: "todos", serie: "puntaje", hSel: null, hPag: 0,
    sel: params.get("sesion") || "",   // sesión que se ve en Resultado
    sesiones: {},                      // id -> respuesta de /api/sesion.json
  };
  const logos = new Map();
  function logo(lugar, variante, tono) {
    const k = `${lugar}-${variante}-${tono}`;
    if (!logos.has(k)) logos.set(k, Plantilla.crudo(Logo.html(variante, tono)));
    return logos.get(k);
  }
  const tripulacion = () => (S.t ? S.t.tripulacion.map((x) => x.persona) : []);
  const filaDe = (id) => (S.hist.filas.find((f) => f.id === id)
    || (S.t ? S.t.evaluaciones.find((f) => f.id === id) : null) || null);

  // ================================================================== pintar
  let pedido = false;
  let ultimaVista = "";
  function pintar() {
    pedido = false;
    morph(raiz, vistaApp());
    if (S.pantalla !== ultimaVista) { ultimaVista = S.pantalla; animarEntrada(); }
  }
  function pedirPintar() {
    if (pedido) return;
    pedido = true;
    // requestAnimationFrame no corre con la pestaña oculta: el setTimeout asegura que los datos se pinten igual.
    const una = () => { if (pedido) pintar(); };
    requestAnimationFrame(una);
    setTimeout(una, 250);
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

  // ================================================================== datos
  async function pedir(ruta) {
    const r = await fetch(ruta, { cache: "no-store" });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.json();
  }
  async function cargarTablero() {
    try {
      const t = await pedir("api/tablero.json");
      if (t.disponible) { S.t = t; S.api = "ok"; S.motivo = ""; } else { S.api = "error"; S.motivo = t.motivo; }
    } catch (e) {
      S.api = "error"; S.motivo = `No responde el servidor de Houston (${e.message}).`;
    }
    pedirPintar();
  }
  async function cargarHistorial() {
    if (S.hist.estado === "nada") S.hist.estado = "cargando";
    const dias = S.periodo === "todo" ? 0 : Number(S.periodo);
    try {
      const r = await pedir(`api/evaluaciones.json?dias=${dias}`);
      S.hist = r.disponible ? { estado: "ok", filas: r.filas, motivo: "" } : { estado: "error", filas: [], motivo: r.motivo };
    } catch (e) {
      S.hist = { estado: "error", filas: [], motivo: e.message };
    }
    pedirPintar();
  }
  async function cargarSesion(id) {
    if (!id) return;
    try {
      S.sesiones[id] = await pedir(`api/sesion.json?sesion=${encodeURIComponent(id)}`);
    } catch (e) {
      S.sesiones[id] = { disponible: false, motivo: e.message };
    }
    pedirPintar();
  }
  function actualizar() {
    cargarTablero();
    if (S.pantalla === "historial") cargarHistorial();
    if (S.pantalla === "resultado" && S.sel) cargarSesion(S.sel);
  }
  function abrirResultado(id) {
    if (!id) return;
    S.sel = id;
    S.pantalla = "resultado";
    window.scrollTo(0, 0);
    cargarSesion(id);
    pedirPintar();
  }
  function ultimoResultado() {
    const ev = S.t && S.t.evaluaciones[0];
    return ev ? ev.id : "";
  }

  // ================================================================== acciones
  Plantilla.acciones({
    ir: (p) => {
      S.pantalla = p;
      if (p === "historial") cargarHistorial();
      if (p === "resultado") { if (!S.sel) S.sel = ultimoResultado(); if (S.sel) cargarSesion(S.sel); }
      window.scrollTo(0, 0);
      pedirPintar();
    },
    abrir: (id) => abrirResultado(id),
    periodo: (v) => { S.periodo = v; S.hPag = 0; S.hist.estado = "cargando"; cargarHistorial(); pedirPintar(); },
    hPersona: (v) => { S.hPersona = v; S.hPag = 0; pedirPintar(); },
    serie: (k) => { S.serie = k; pedirPintar(); },
    hSel: (id) => { S.hSel = S.hSel === id ? null : id; pedirPintar(); },
    hPag: (n) => { S.hPag = Math.max(0, Number(n) || 0); pedirPintar(); },
    tema: () => { S.tema = S.tema === "claro" ? "oscuro" : "claro"; guardar("houston-tema", S.tema); aplicarTema(); try { Fondo.reconstruir(); } catch (e) { /* decoración */ } pedirPintar(); },
    recargar: () => actualizar(),
  });
  window.addEventListener("resize", () => { S.w = window.innerWidth; pedirPintar(); });

  // ================================================================== piezas comunes
  const etq = (texto, extra = "") => h`<span style="${ETQ}${extra}">${texto}</span>`;
  const pildora = (st, texto, extra = "") => h`<span style="display:inline-flex;align-items:center;gap:6px;padding:3px 9px;border-radius:5px;background:${st.bg};color:${st.fg};${MONO};font-size:12px;font-weight:600;letter-spacing:0.06em;white-space:nowrap;${extra}"><i class="ph-fill ${st.icon}"></i>${texto || st.word}</span>`;
  const tagMono = (texto, clase = "tag-neutral") => h`<span class="tag ${clase}" style="${MONO};font-size:10px">${texto}</span>`;
  const nota = (ic, texto) => h`<div style="display:flex;gap:10px;align-items:center;padding:14px 16px;border-radius:var(--radius-md);box-shadow:inset 0 0 0 1px var(--color-neutral-800)"><i class="ph ${ic}" style="font-size:18px;color:var(--color-neutral-400);flex:none"></i><span style="font-size:13px;color:var(--color-neutral-300);text-wrap:pretty">${texto}</span></div>`;
  const cmd = (texto) => h`<code style="${MONO};font-size:11px;color:var(--color-neutral-500);word-break:break-all">${texto}</code>`;
  const segOpciones = (nombreGrupo, aria, opciones, accion, extra = "") => h`<div class="seg" role="radiogroup" aria-label="${aria}" style="flex-wrap:wrap;${extra}">
      ${opciones.map(([valor, label, on]) => h`<label class="seg-opt"><input type="radio" name="${nombreGrupo}" ${si(on, "checked")} data-change="${accion}" data-arg="${valor}"><span>${label}</span></label>`)}
    </div>`;
  const marcas = (f) => h`${f.provisional ? tagMono("PROVISIONAL") : ""}${f.simulado ? tagMono("SIMULADO", "tag-outline") : ""}${f.aviso_spo2 ? h`<span class="tag" style="${MONO};font-size:10px;background:${ST.amarillo.bg};color:${ST.amarillo.fg}">SpO₂</span>` : ""}`;

  function estadoEnlace() {
    if (S.api === "cargando") return { st: ST.amarillo, corto: "CARGANDO", largo: "Leyendo la base de Houston…", icon: "ph-satellite" };
    if (S.api === "error") return { st: ST.rojo, corto: "SIN BASE", largo: S.motivo || "La base de Houston no responde", icon: "ph-database" };
    const e = S.t.enlace;
    if (e.con_senal) return { st: ST.verde, corto: "CON SEÑAL", largo: "Recibiendo de la nave por Mosquitto", icon: "ph-satellite" };
    if (e.error) return { st: ST.rojo, corto: "SIN SEÑAL", largo: e.error, icon: "ph-satellite" };
    return { st: ST.amarillo, corto: "ESPERANDO", largo: "Esperando el receptor de Houston", icon: "ph-satellite" };
  }

  // ================================================================== vista: armazón
  function vistaApp() {
    const wide = S.w >= 900;
    const meta = NAV.find((n) => n[0] === S.pantalla) || NAV[0];
    const enl = estadoEnlace();
    let kicker = meta[3];
    if (S.pantalla === "resultado") {
      const f = filaDe(S.sel);
      kicker = f ? `${nombre(f.persona)} · llegó ${cuando(f.llego || f.fecha)}` : "Sin evaluación";
    }
    return h`
<div style="position:relative;z-index:1;display:flex;min-height:100vh;flex-direction:${wide ? "row" : "column"}">
  <nav aria-label="Navegación principal" style="flex:none;display:flex;flex-direction:${wide ? "column" : "row"};align-items:${wide ? "stretch" : "center"};gap:4px;padding:${wide ? "18px 12px" : "8px 12px"};width:${wide ? "232px" : "100%"};background:var(--nav-bg);backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);position:sticky;top:0;z-index:20;overflow-x:auto;box-shadow:${wide ? "inset -1px 0 0 var(--color-neutral-900)" : "inset 0 -1px 0 var(--color-neutral-900)"};height:${wide ? "100vh" : "auto"}">
    <div style="display:flex;align-items:center;gap:10px;padding:${wide ? "10px 8px 26px" : "4px 8px"};flex:none">
      <div style="display:flex;flex-direction:column;gap:10px;padding:6px 0 4px">
        <div style="width:${wide ? 196 : 140}px" data-congelar="logo-compact-${S.tema}">${logo("barra", "compact", S.tema === "claro" ? "light" : "dark")}</div>
        ${wide ? h`<span style="padding-left:6px;font-size:9.5px;letter-spacing:0.16em;text-transform:uppercase;color:var(--color-neutral-400);${MONO}">Houston · Control de misión</span>` : ""}
      </div>
    </div>
    ${NAV.map(([id, label, icon]) => {
      const on = S.pantalla === id;
      return h`<button type="button" class="hv-nav" data-click="ir" data-arg="${id}" aria-current="${on ? "page" : "false"}" style="display:flex;align-items:center;gap:10px;padding:8px 10px;border:0;border-radius:var(--radius-md);background:${on ? "var(--color-accent-900)" : "transparent"};color:${on ? "var(--color-accent-200)" : "var(--color-neutral-300)"};box-shadow:${on ? "inset 2px 0 0 var(--color-accent)" : "none"};cursor:pointer;text-align:left;font-size:14px;white-space:nowrap;flex:none">
        <i class="ph ${icon}" style="font-size:18px"></i><span>${label}</span></button>`;
    })}
    ${wide ? h`<div style="margin-top:auto;padding:12px 10px;display:flex;flex-direction:column;gap:8px;font-size:12px;color:var(--color-neutral-400)">
        <div style="display:flex;align-items:center;gap:8px"><i class="ph ${enl.icon}" style="font-size:15px;color:${enl.st.fg}"></i><span>${enl.largo}</span></div>
        <div style="display:flex;align-items:center;gap:8px"><i class="ph ph-eye" style="font-size:15px;color:var(--color-accent-300)"></i><span>Tierra: solo lectura</span></div>
        <button type="button" class="btn btn-ghost" data-click="tema" style="justify-content:flex-start;padding:4px 0;font-size:12px"><i class="ph ${S.tema === "claro" ? "ph-moon" : "ph-sun"}"></i>${S.tema === "claro" ? "Tema oscuro" : "Tema claro"}</button>
      </div>` : ""}
  </nav>
  <div style="flex:1;min-width:0;display:flex;flex-direction:column">
    <header style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;padding:14px 24px;background:linear-gradient(to right, transparent, var(--color-divider) 48px, var(--color-divider) calc(100% - 48px), transparent) no-repeat bottom / 100% 1px;background-color:color-mix(in srgb, var(--color-bg) 35%, transparent);backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px)">
      <div style="display:flex;flex-direction:column;gap:2px;margin-right:auto;min-width:0">
        <span style="font-size:11px;letter-spacing:0.12em;text-transform:uppercase;color:var(--color-neutral-400);${MONO}">${kicker}</span>
        <h1 style="font-size:22px;margin:0">${meta[4]}</h1>
      </div>
      <span title="Houston no publica nada: solo ve lo que baja de la nave" style="display:inline-flex;align-items:center;gap:6px;padding:3px 9px;border:1px dashed var(--color-accent-500);border-radius:6px;${MONO};font-size:11px;letter-spacing:0.1em;color:var(--color-accent-300)"><i class="ph ph-eye"></i>SOLO LECTURA</span>
      <span title="${enl.largo}" style="display:inline-flex;align-items:center;gap:6px;padding:3px 10px;border-radius:999px;box-shadow:inset 0 0 0 1px var(--color-neutral-700);${MONO};font-size:11px;letter-spacing:0.08em;color:${enl.st.fg}"><i class="ph ${enl.icon}"></i>ENLACE · ${enl.corto}</span>
      <span style="${MONO};font-size:12px;color:var(--color-neutral-400);font-variant-numeric:tabular-nums" title="Hora de Tierra">${horaLarga(Date.now())} · TIERRA</span>
    </header>
    <main id="principal" style="flex:1;padding:24px;display:flex;flex-direction:column;gap:20px;max-width:1360px;width:100%;box-sizing:border-box">
      ${S.api === "error" && !S.t ? vistaSinBase() : { panel: vistaPanel, historial: vistaHistorial, resultado: vistaResultado }[S.pantalla]()}
    </main>
  </div>
</div>`;
  }

  function vistaSinBase() {
    return h`<div data-k="sin-base" style="display:flex;flex-direction:column;align-items:flex-start;gap:10px;padding:48px 0">
      <i class="ph ph-plugs" style="font-size:36px;color:var(--color-neutral-500)"></i>
      <h2 style="font-size:22px;margin:0">No se pudo leer la base de Houston</h2>
      <span style="color:var(--color-neutral-300)">${S.motivo}</span>
      <span style="font-size:13px;color:var(--color-neutral-400)">En la carpeta houston: ${cmd("docker compose up -d")}</span>
      <button class="btn btn-secondary" type="button" data-click="recargar"><i class="ph ph-arrow-clockwise"></i>Reintentar</button>
    </div>`;
  }

  // ================================================================== vista: En vivo (sesiones en curso a bordo)
  function curvaPulso(serie) {
    if (serie.length < 2) return h`<div style="height:56px;display:grid;place-items:center;font-size:12px;color:var(--color-neutral-500)">Esperando lecturas del pulso…</div>`;
    const vals = serie.map((p) => p[1]);
    const lo = Math.min(...vals) - 5, hi = Math.max(...vals) + 5;
    const t0 = serie[0][0], t1 = serie[serie.length - 1][0] || t0 + 1;
    const x = (t) => 4 + ((t - t0) / Math.max(1, t1 - t0)) * 292;
    const y = (v) => 52 - ((v - lo) / Math.max(1, hi - lo)) * 48;
    const pts = serie.map(([t, v]) => `${x(t).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
    const [ut, uv] = serie[serie.length - 1];
    return h`<svg viewBox="0 0 300 56" preserveAspectRatio="none" style="width:100%;height:56px;display:block" role="img" aria-label="Curva del pulso en vivo">
      <polyline points="${pts}" style="fill:none;stroke:var(--st-rojo);stroke-width:1.6;stroke-linejoin:round;vector-effect:non-scaling-stroke"></polyline>
      <circle cx="${x(ut)}" cy="${y(uv)}" r="3" style="fill:var(--st-rojo)"></circle>
    </svg>`;
  }

  function tarjetaVivo(v) {
    const e = v.esp32;
    const ev = v.evaluacion;
    const st = ev ? ST[ev.color] || ST.sin : null;
    const vigente = e && e.vigente && e.dedo;
    const dato = (label, valor, unidad, extra = "") => h`<div style="display:flex;flex-direction:column;gap:2px;min-width:0"><span style="font-size:11px;color:var(--color-neutral-300)">${label}</span><span style="${MONO};font-size:24px;font-variant-numeric:tabular-nums;${extra}">${valor}<span style="font-size:12px;color:var(--color-neutral-400)"> ${unidad}</span></span></div>`;
    return h`<article data-k="vivo-${v.sesion}" style="${SECC};box-shadow:inset 3px 0 0 ${st ? st.fg : "var(--color-accent)"}, var(--shadow-sm)">
      <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
        <span style="display:flex;align-items:center;gap:7px;font-size:17px;font-weight:500"><i class="ph-fill ${icono(v.persona)}" style="color:var(--color-accent-300)"></i>${nombre(v.persona)}</span>
        ${v.tarea ? h`<span class="tag tag-accent">${cap(v.tarea)}</span>` : ""}
        ${ev ? pildora(st) : h`<span style="display:inline-flex;align-items:center;gap:6px;padding:3px 9px;border-radius:5px;background:var(--color-accent-900);color:var(--color-accent-200);${MONO};font-size:12px;font-weight:600;letter-spacing:0.06em"><i class="ph-fill ph-circle" style="font-size:9px;animation:pulso 1.4s ease-in-out infinite"></i>EVALUANDO</span>`}
        ${e && e.simulado ? tagMono("SIMULADO", "tag-outline") : ""}
        <span style="margin-left:auto;${MONO};font-size:11px;color:var(--color-neutral-400)">inició ${horaCorta(v.inicio)} · último dato ${hace(v.ultimo_dato)}</span>
      </div>
      <div style="display:flex;gap:6px;flex-wrap:wrap" aria-label="Pasos que ya llegaron a Tierra">
        ${PASOS_VIVO.map(([k, label, ic]) => { const ok = v.pasos[k]; return h`<span style="display:inline-flex;align-items:center;gap:5px;padding:3px 9px;border-radius:999px;font-size:12px;${ok ? "background:var(--color-accent-900);color:var(--color-accent-200);box-shadow:inset 0 0 0 1px var(--color-accent-700)" : "color:var(--color-neutral-500);box-shadow:inset 0 0 0 1px var(--color-neutral-800)"}"><i class="${ok ? "ph-fill ph-check-circle" : "ph " + ic}"></i>${label}</span>`; })}
        <span style="display:inline-flex;align-items:center;gap:5px;padding:3px 9px;border-radius:999px;font-size:12px;${ev ? `background:${st.bg};color:${st.fg}` : "color:var(--color-neutral-500);box-shadow:inset 0 0 0 1px var(--color-neutral-800)"}"><i class="${ev ? "ph-fill " + st.icon : "ph ph-flag-checkered"}"></i>Resultado</span>
      </div>
      ${e ? h`<div style="display:grid;grid-template-columns:minmax(0,1.4fr) repeat(3,minmax(0,1fr));gap:14px;align-items:end">
          <div style="display:flex;flex-direction:column;gap:4px;min-width:0">
            <span style="display:flex;align-items:center;gap:6px;font-size:11px;color:var(--color-neutral-300)">${vigente ? h`<i class="ph-fill ph-heart" style="color:var(--st-rojo);animation:pulso 1.2s ease-in-out infinite"></i>` : h`<i class="ph ph-heart"></i>`}Pulso ${vigente ? "en vivo" : e.dedo ? "(sin lecturas recientes)" : "· sin dedo en el sensor"}</span>
            ${curvaPulso(v.serie_pulso)}
          </div>
          ${dato("Pulso", entero(e.pulso_lpm), "lpm", vigente ? "" : "color:var(--color-neutral-500)")}
          ${dato("SpO₂", entero(e.spo2), "%", vigente ? "" : "color:var(--color-neutral-500)")}
          ${dato("HRV", entero(e.hrv_rmssd_ms), "ms", vigente ? "" : "color:var(--color-neutral-500)")}
        </div>
        <span style="${MONO};font-size:11px;color:var(--color-neutral-500)">${v.lecturas_esp32} lecturas del ESP32 · calidad ${fmt(e.calidad)} · ${hace(e.fecha)}</span>`
      : h`<span style="font-size:13px;color:var(--color-neutral-400)">Todavía no llegan lecturas del ESP32 de esta sesión.</span>`}
      ${ev ? h`<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
          <span style="font-size:13px;color:var(--color-neutral-200);flex:1;min-width:200px">${(ev.motivos || []).length ? ev.motivos.join(" · ") : "Sin motivos de alerta"}</span>
          <button class="btn btn-primary" type="button" data-click="abrir" data-arg="${v.sesion}"><i class="ph ph-clipboard-text"></i>Ver resultado</button>
        </div>` : ""}
    </article>`;
  }

  function vistaVivo(t) {
    const vivas = t.en_vivo || [];
    const llegan = t.por_llegar || [];
    if (!vivas.length && !llegan.length) return "";
    return h`<section data-k="vivo" style="display:flex;flex-direction:column;gap:10px">
      <div style="display:flex;align-items:baseline;gap:10px;flex-wrap:wrap"><h2 style="font-size:17px;margin:0;display:flex;align-items:center;gap:8px"><i class="ph-fill ph-broadcast" style="color:var(--st-rojo);animation:pulso 1.6s ease-in-out infinite"></i>En vivo · a bordo</h2><span style="font-size:12px;color:var(--color-neutral-400)">Lo que va llegando de cada evaluación en curso (con ${t.enlace.retraso_s} s de retraso)</span></div>
      ${llegan.map((x) => { const s = Math.max(0, Math.ceil((x.llega - Date.now()) / 1000)); return h`<div role="status" style="display:flex;align-items:center;gap:10px;padding:12px 16px;border-radius:var(--radius-md);background:var(--color-accent-900);box-shadow:inset 0 0 0 1px var(--color-accent-700)">
          <i class="ph ph-paper-plane-tilt" style="font-size:18px;color:var(--color-accent-200)"></i>
          <span style="font-size:14px;flex:1">Resultado de <b style="font-weight:500">${nombre(x.persona)}</b> en camino a Tierra</span>
          <span style="${MONO};font-size:20px;font-variant-numeric:tabular-nums;color:var(--color-accent-200)">${s > 0 ? `llega en ${s} s` : "llegando…"}</span>
        </div>`; })}
      ${vivas.map(tarjetaVivo)}
    </section>`;
  }

  // ================================================================== vista: Panel
  function vistaPanel() {
    if (!S.t) return h`<div data-k="panel-cargando">${nota("ph-circle-notch", "Leyendo la base de Houston…")}</div>`;
    const t = S.t;
    const e = t.enlace;
    const enl = estadoEnlace();
    const cnt = { verde: t.conteo.verde, amarillo: t.conteo.amarillo, rojo: t.conteo.rojo, sin: t.conteo.sin_dato };
    const conSpo2 = t.tripulacion.filter((x) => x.ultima && x.ultima.aviso_spo2).map((x) => nombre(x.persona));
    const ultima = t.evaluaciones[0];
    const enCurso = new Set((t.en_vivo || []).filter((v) => !v.evaluacion).map((v) => v.persona));
    return h`<div data-k="panel" style="display:contents">
  <section style="position:relative;overflow:hidden;display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,340px),1fr));gap:20px;padding:22px;border-radius:var(--radius-lg);background:linear-gradient(135deg, var(--color-surface), color-mix(in srgb, var(--color-surface) 40%, var(--color-bg)));box-shadow:var(--shadow-sm)">
    <svg aria-hidden="true" viewBox="0 0 600 300" style="position:absolute;right:-120px;top:-90px;width:560px;opacity:.5;pointer-events:none"><ellipse cx="300" cy="150" rx="280" ry="90" fill="none" stroke="var(--color-accent-800)" stroke-width="1" transform="rotate(-14 300 150)"></ellipse><ellipse cx="300" cy="150" rx="200" ry="60" fill="none" stroke="var(--color-neutral-800)" stroke-width="1" transform="rotate(-14 300 150)"></ellipse><circle cx="528" cy="88" r="3" fill="var(--color-accent)"></circle></svg>
    <div style="position:relative;display:flex;flex-direction:column;gap:12px">
      <span style="font-size:11px;letter-spacing:0.12em;text-transform:uppercase;color:var(--color-accent-300);${MONO}">Enlace nave → Tierra</span>
      <div style="display:flex;align-items:baseline;gap:12px;flex-wrap:wrap">
        <span style="${MONO};font-size:44px;font-variant-numeric:tabular-nums;line-height:1">${e.retraso_s}<span style="font-size:18px;color:var(--color-neutral-400)"> s</span></span>
        <span style="font-size:15px;color:var(--color-neutral-200)">de retraso de comunicación</span>
      </div>
      <p style="margin:0;font-size:15px;line-height:1.55;color:var(--color-neutral-200);max-width:60ch;text-wrap:pretty">Houston ve cada dato cuando llega a Tierra, no cuando ocurre: la tripulación ya decidió a bordo. Retraso real a Marte: de 3 a 22 minutos.</p>
      <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-top:4px">
        ${pildora(enl.st, enl.corto)}
        <span style="font-size:13px;color:var(--color-neutral-300)">${enl.largo}</span>
      </div>
      ${ultima ? h`<div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:4px">
        <button class="btn btn-primary" type="button" data-click="abrir" data-arg="${ultima.id}" style="padding:9px 16px"><i class="ph ph-clipboard-text"></i>Último resultado · ${nombre(ultima.persona)}</button>
        <button class="btn btn-secondary" type="button" data-click="ir" data-arg="historial" style="padding:9px 16px"><i class="ph ph-chart-line-up"></i>Ver evaluaciones</button>
      </div>` : ""}
    </div>
    <div style="position:relative;display:flex;flex-direction:column;gap:10px">
      ${etq("Transmisión")}
      <div style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px">
        ${[["Último dato", hace(e.ultimo_dato_nave), "ph-clock"], ["En Tierra", entero(e.copiados), "ph-database"], ["En camino", entero(e.en_camino), "ph-paper-plane-tilt"]].map(([l, v, ic]) => h`<div style="display:flex;flex-direction:column;gap:2px;padding:10px;border-radius:var(--radius-md);background:color-mix(in srgb, var(--color-bg) 55%, transparent)">
            <span style="display:flex;align-items:center;gap:5px;font-size:11px;color:var(--color-neutral-300)"><i class="ph ${ic}"></i>${l}</span>
            <span style="${MONO};font-size:20px;font-variant-numeric:tabular-nums">${v}</span></div>`)}
      </div>
      <div aria-hidden="true" style="position:relative;height:2px;border-radius:1px;background:var(--color-neutral-800);overflow:hidden;margin:6px 0">
        ${e.en_camino ? h`<div style="position:absolute;inset:0;width:30%;background:linear-gradient(to right, transparent, var(--color-accent), transparent);animation:barridoX 2.4s linear infinite"></div>` : ""}
      </div>
      ${etq("Tripulación")}
      <div style="display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px">
        ${["verde", "amarillo", "rojo", "sin"].map((c) => h`<div style="display:flex;flex-direction:column;gap:2px;padding:10px;border-radius:var(--radius-md);background:color-mix(in srgb, var(--color-bg) 55%, transparent)">
            <span style="display:flex;align-items:center;gap:5px;font-size:11px;color:${ST[c].fg}"><i class="ph-fill ${ST[c].icon}"></i>${c === "sin" ? "Sin dato" : cap(c)}</span>
            <span style="${MONO};font-size:24px;font-variant-numeric:tabular-nums">${cnt[c]}</span></div>`)}
      </div>
    </div>
  </section>

  ${vistaVivo(t)}

  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,420px),1fr));gap:20px;align-items:start">
    <section style="display:flex;flex-direction:column;gap:10px">
      <div style="display:flex;align-items:baseline;gap:10px"><h2 style="font-size:17px;margin:0">Tripulación</h2><span style="font-size:12px;color:var(--color-neutral-400)">Última evaluación que llegó a Tierra</span></div>
      <div style="display:flex;flex-direction:column;gap:8px">
        ${t.tripulacion.length ? t.tripulacion.map(({ persona: p, ultima: f }) => {
          const st = (f && ST[f.color]) || ST.sin;
          return h`<button type="button" class="hv-crew" ${si(!f, "disabled")} data-click="abrir" data-arg="${f ? f.id : ""}" style="display:flex;flex-direction:column;gap:8px;padding:12px 16px;border:0;border-radius:var(--radius-md);background:var(--color-surface);box-shadow:inset 3px 0 0 ${st.fg}, inset 0 0 0 1px var(--card-edge);text-align:left;cursor:${f ? "pointer" : "default"};transition:transform .2s, background-color .2s;width:100%;min-width:0">
            <span style="display:flex;align-items:center;gap:10px 14px;flex-wrap:wrap;width:100%">
              <span style="display:flex;align-items:center;gap:7px;font-size:16px;font-weight:500"><i class="ph-fill ${icono(p)}" style="font-size:18px;color:var(--color-accent-300)"></i>${nombre(p)}</span>
              <span style="${MONO};font-size:11px;color:var(--color-neutral-400)">${f ? `llegó ${cuando(f.llego || f.fecha)}` : "sin evaluación en Tierra"}</span>
              ${pildora(st)}
              ${f ? marcas(f) : ""}
              ${enCurso.has(p) ? h`<span class="tag tag-accent" style="${MONO};font-size:10px;gap:5px"><i class="ph-fill ph-circle" style="font-size:7px;animation:pulso 1.4s ease-in-out infinite"></i>EVALUANDO AHORA</span>` : ""}
              <span style="margin-left:auto;display:flex;gap:16px;flex-wrap:wrap;${MONO};font-size:13px;color:var(--color-neutral-200);font-variant-numeric:tabular-nums">
                <span title="Pulso">${entero(f && f.pulso_lpm)}<span style="color:var(--color-neutral-500);font-size:11px"> lpm</span></span>
                <span title="Somnolencia KSS">KSS ${entero(f && f.kss)}</span>
                <span title="Mediana PVT">${entero(f && f.pvt_mediana)}<span style="color:var(--color-neutral-500);font-size:11px"> ms</span></span>
              </span>
            </span>
            <span style="font-size:13px;line-height:1.45;color:var(--color-neutral-300);text-wrap:pretty;max-width:80ch">${f ? (f.tarea ? cap(f.tarea) + " · " : "") + ((f.motivos || []).length ? f.motivos.join(" · ") : "Sin motivos de alerta") : "Todavía no llegó ninguna evaluación"}</span>
          </button>`;
        }) : nota("ph-users-three", "No hay TRIPULACION en config.env.")}
      </div>
    </section>
    <div style="display:flex;flex-direction:column;gap:20px">
      <section style="display:flex;flex-direction:column;gap:10px;padding:16px;${TARJ}">
        <div style="display:flex;align-items:center;gap:8px"><h2 style="font-size:15px;margin:0;margin-right:auto">Últimas recibidas</h2><button class="btn btn-ghost" type="button" data-click="ir" data-arg="historial" style="font-size:12px">Ver todas</button></div>
        ${t.evaluaciones.length ? t.evaluaciones.slice(0, 6).map((f) => { const st = ST[f.color] || ST.sin; return h`<button type="button" class="hv-acc" data-click="abrir" data-arg="${f.id}" style="display:flex;align-items:center;gap:10px;padding:8px 10px;border:0;border-radius:var(--radius-md);background:transparent;text-align:left;cursor:pointer;width:100%">
            <i class="ph-fill ${st.icon}" style="font-size:16px;color:${st.fg}"></i>
            <span style="display:flex;flex-direction:column;gap:1px;min-width:0;flex:1"><span style="font-size:13px"><b style="font-weight:500">${nombre(f.persona)}</b> <span style="color:var(--color-neutral-400)">${f.tarea ? "· " + f.tarea : ""}</span></span>
            <span style="${MONO};font-size:10px;color:var(--color-neutral-500)">nave ${horaLarga(f.fecha)} · Tierra ${horaLarga(f.llego || f.fecha)}</span></span>
            <span style="${MONO};font-size:11px;color:${st.fg}">${st.word}</span></button>`; })
          : h`<span style="font-size:13px;color:var(--color-neutral-400)">Todavía no llegó ninguna evaluación.</span>`}
      </section>
      ${conSpo2.length ? h`<section role="status" style="display:flex;gap:12px;padding:14px 16px;border-radius:var(--radius-md);background:${ST.amarillo.bg};box-shadow:inset 0 0 0 1px color-mix(in srgb, ${ST.amarillo.fg} 40%, transparent)">
        <i class="ph ph-warning" style="font-size:20px;color:${ST.amarillo.fg};flex:none"></i>
        <div style="display:flex;flex-direction:column;gap:4px">
          <b style="font-weight:500;color:${ST.amarillo.fg}">Oxígeno más bajo de lo habitual en ${conSpo2.join(", ")}</b>
          <span style="font-size:13px;color:var(--color-neutral-200)">Es un aviso, no cambia el color. La nave debería repetir la medición.</span>
        </div>
      </section>` : ""}
      <section style="display:flex;flex-direction:column;gap:10px;padding:16px;${TARJ}">
        <div style="display:flex;align-items:center;gap:8px"><h2 style="font-size:15px;margin:0;margin-right:auto">Becspace AI a bordo</h2><span style="font-size:12px;color:var(--color-neutral-400)">lo que respondió el copiloto</span></div>
        ${t.copiloto.length ? t.copiloto.slice(0, 5).map((d) => h`<div style="display:flex;flex-direction:column;gap:4px;padding:6px 0">
            <span style="${MONO};font-size:10px;color:var(--color-neutral-500)">${nombre(d.persona)} · ${horaLarga(d.fecha)}</span>
            ${d.pregunta ? h`<span style="font-size:13px;color:var(--color-neutral-300)">${d.pregunta === "(resumen automático)" ? "Resumen automático" : `«${d.pregunta}»`}</span>` : ""}
            <span style="font-size:13px;line-height:1.5">${d.respuesta || ""}</span></div>`)
          : h`<span style="font-size:13px;color:var(--color-neutral-400)">Todavía no llegaron respuestas.</span>`}
      </section>
      <section style="display:flex;gap:12px;padding:14px 16px;border-radius:var(--radius-md);box-shadow:inset 0 0 0 1px var(--color-neutral-800)">
        <i class="ph ph-info" style="font-size:20px;color:var(--color-neutral-400);flex:none"></i>
        <span style="font-size:13px;color:var(--color-neutral-300);text-wrap:pretty">Indicadores orientativos para apoyar la decisión. No es un diagnóstico médico ni una certificación de aptitud.</span>
      </section>
    </div>
  </div>
</div>`;
  }

  // ================================================================== vista: Evaluaciones (como el Historial de la estación)
  function serieDe(k, filas) {
    const vals = filas.map((f) => num(f[k])).filter((v) => v !== null);
    const lo = vals.length ? Math.min(...vals) : null, hi = vals.length ? Math.max(...vals) : null;
    if (k === "puntaje") return ["Puntaje", 0, Math.max(1, hi === null ? 1 : Math.ceil(hi)), Math.max(1, hi === null ? 1 : Math.ceil(hi)) > 1 ? 1 : 0.25, ""];
    if (k === "kss") return ["Somnolencia KSS", 1, 9, 2, ""];
    if (k === "pvt_mediana") return ["Reacción mediana", Math.min(200, lo === null ? 200 : Math.floor(lo / 50) * 50), Math.max(450, hi === null ? 450 : Math.ceil(hi / 50) * 50), 50, " ms"];
    return ["Horas de sueño", Math.min(3, lo === null ? 3 : Math.floor(lo)), Math.max(9, hi === null ? 9 : Math.ceil(hi)), 2, " h"];
  }

  function vistaHistorial() {
    const H = S.hist;
    const crew = tripulacion().length ? tripulacion() : Array.from(new Set(H.filas.map((f) => f.persona)));
    const rows = H.filas.filter((f) => S.hPersona === "todos" || f.persona === S.hPersona).sort((a, b) => b.fecha - a.fecha);
    const [sl, mn, mx, stp, un] = serieDe(S.serie, rows);
    const asc = rows.slice().reverse();
    const x0 = 50, x1 = 780;
    const y = (v) => 190 - ((Math.max(mn, Math.min(mx, v)) - mn) / (mx - mn)) * 170;
    const xs = (i) => (asc.length > 1 ? x0 + (i / (asc.length - 1)) * (x1 - x0) : (x0 + x1) / 2);
    const conValor = asc.map((f, i) => [f, i]).filter(([f]) => num(f[S.serie]) !== null);
    const sel = rows.find((f) => f.id === S.hSel);
    const nPag = Math.max(1, Math.ceil(rows.length / POR_PAGINA)); const pag = Math.min(S.hPag, nPag - 1);
    const todos = S.hPersona === "todos";
    const claro = S.tema === "claro";
    const SER = ["puntaje", "pvt_mediana", "kss", "horas_sueno"];
    const grid = Array.from({ length: Math.floor((mx - mn) / stp + 1e-9) + 1 }, (_, i) => mn + i * stp);
    const estadoReg = H.estado === "cargando" ? ["ph-circle-notch", "Cargando…"] : H.estado === "ok" ? ["ph-database", `MongoDB de Houston · ${H.filas.length} evaluaciones`] : ["ph-database", "Base de Houston sin respuesta"];
    const vacio = H.estado === "error" ? h`<div style="display:flex;flex-direction:column;align-items:flex-start;gap:8px;padding:32px 8px"><i class="ph ph-plugs" style="font-size:28px;color:var(--color-neutral-500)"></i><b style="font-weight:500">No se pudo leer la base</b><span style="font-size:13px;color:var(--color-neutral-400)">${H.motivo}</span><button class="btn btn-secondary" type="button" data-click="recargar" style="margin-top:4px"><i class="ph ph-arrow-clockwise"></i>Reintentar</button></div>`
      : h`<div style="display:flex;flex-direction:column;align-items:flex-start;gap:8px;padding:32px 8px"><i class="ph ph-tray" style="font-size:28px;color:var(--color-neutral-500)"></i><b style="font-weight:500">${H.estado === "cargando" ? "Cargando…" : "Sin evaluaciones en este periodo"}</b><span style="font-size:13px;color:var(--color-neutral-400)">${H.estado === "cargando" ? "Leyendo la base de Houston." : "Prueba con un periodo más largo u otra persona."}</span></div>`;
    const csv = `api/evaluaciones.csv?dias=${S.periodo === "todo" ? 0 : S.periodo}${todos ? "" : `&persona=${encodeURIComponent(S.hPersona)}`}`;
    return h`<div data-k="historial" style="display:contents">
  <div style="display:flex;gap:12px;flex-wrap:wrap;align-items:center">
    ${segOpciones("periodo", "Periodo", [["1", "Hoy", S.periodo === "1"], ["7", "7 días", S.periodo === "7"], ["30", "30 días", S.periodo === "30"], ["todo", "Todo", S.periodo === "todo"]], "periodo", "flex-wrap:nowrap")}
    ${segOpciones("hpersona", "Persona", ["todos"].concat(crew).map((p) => [p, p === "todos" ? "Todos" : nombre(p), S.hPersona === p]), "hPersona")}
    <span style="margin-left:auto;display:inline-flex;align-items:center;gap:6px;font-size:12px;color:var(--color-neutral-400)"><i class="ph ${estadoReg[0]}"></i>${estadoReg[1]}
      <button class="btn btn-ghost" type="button" data-click="recargar" aria-label="Volver a cargar" title="Volver a cargar" style="padding:4px 6px"><i class="ph ph-arrow-clockwise"></i></button></span>
  </div>
  <section style="${SECC}">
    <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">
      <h2 style="font-size:15px;margin:0;margin-right:auto">Evolución · ${sl}${todos ? " · toda la tripulación" : " · " + nombre(S.hPersona)}</h2>
      <div role="tablist" aria-label="Indicador" style="display:flex;gap:2px;flex-wrap:wrap">
        ${SER.map((k) => h`<button role="tab" type="button" class="hv-tab" aria-selected="${String(S.serie === k)}" data-click="serie" data-arg="${k}" style="padding:6px 10px;border:0;background:transparent;border-radius:var(--radius-sm);color:${S.serie === k ? "var(--color-accent-200)" : "var(--color-neutral-400)"};box-shadow:${S.serie === k ? "inset 0 -2px 0 var(--color-accent)" : "none"};font-size:13px;cursor:pointer">${serieDe(k, rows)[0]}</button>`)}
      </div>
    </div>
    ${todos ? h`<div style="display:flex;flex-wrap:wrap;gap:6px 16px;align-items:center">
        ${crew.map((p) => h`<span style="display:inline-flex;align-items:center;gap:6px;font-size:13px;color:var(--color-neutral-200)"><i class="ph-fill ${icono(p)}" style="font-size:22px;color:var(--color-neutral-100)"></i>${nombre(p)}</span>`)}
        <span style="font-size:12px;color:var(--color-neutral-400)">El color del icono es el resultado de esa evaluación</span>
      </div>` : ""}
    <div style="position:relative">
      <svg viewBox="0 0 800 220" style="width:100%;height:auto;display:block" role="img" aria-label="Gráfico de evolución">
        ${grid.map((v) => h`<line x1="40" x2="790" y1="${y(v)}" y2="${y(v)}" style="stroke:var(--color-neutral-800);stroke-width:1"></line>`)}
        ${todos ? "" : h`<polyline points="${conValor.map(([f, i]) => xs(i) + "," + y(num(f[S.serie]))).join(" ")}" style="fill:none;stroke:var(--color-accent);stroke-width:1.5;stroke-linejoin:round"></polyline>
          ${conValor.map(([f, i]) => h`<circle cx="${xs(i)}" cy="${y(num(f[S.serie]))}" r="${f.id === S.hSel ? 6 : 4}" style="fill:${(ST[f.color] || ST.sin).fg};stroke:var(--color-surface);stroke-width:1.5"></circle>`)}`}
      </svg>
      ${grid.map((v) => h`<span style="position:absolute;left:0;width:4.5%;top:${(y(v) / 220) * 100}%;transform:translateY(-50%);text-align:right;${MONO};font-size:10px;color:var(--color-neutral-500)">${S.serie === "puntaje" && stp < 1 ? fmt(v) : v}${un}</span>`)}
      ${todos ? conValor.map(([f, i]) => {
        const fg = claro ? { verde: "oklch(0.72 0.15 158)", amarillo: "oklch(0.80 0.15 80)", rojo: "oklch(0.70 0.17 25)" }[f.color] || ST.sin.fg : (ST[f.color] || ST.sin).fg;
        const sombra = claro ? "drop-shadow(0 0 1px rgba(255,255,255,1)) drop-shadow(0 1px 2px rgba(40,40,90,.35))" : "drop-shadow(0 0 1.5px rgba(6,9,19,.95)) drop-shadow(0 1px 2px rgba(6,9,19,.8))";
        const titulo = `${nombre(f.persona)} · ${fechaCorta(f.fecha)} ${horaCorta(f.fecha)} · ${(ST[f.color] || ST.sin).word}`;
        return h`<button type="button" class="hv-icono" data-click="hSel" data-arg="${f.id}" title="${titulo}" aria-label="${titulo}" style="position:absolute;left:${(xs(i) / 800) * 100}%;top:${(y(num(f[S.serie])) / 220) * 100}%;transform:translate(-50%,-50%) scale(${f.id === S.hSel ? "1.35" : "1"});width:28px;height:28px;padding:0;border:0;background:transparent;display:grid;place-items:center;color:${fg};cursor:pointer;filter:${sombra};transition:transform .15s"><i class="ph-fill ${icono(f.persona)}" style="font-size:24px"></i></button>`;
      }) : ""}
      ${asc.filter((_, i) => i % Math.max(1, Math.ceil(asc.length / 8)) === 0).map((f) => h`<span style="position:absolute;bottom:0;left:${(xs(asc.indexOf(f)) / 800) * 100}%;transform:translateX(-50%);${MONO};font-size:10px;color:var(--color-neutral-500)">${fechaCorta(f.fecha)}</span>`)}
    </div>
    <span style="font-size:12px;color:var(--color-neutral-400)">Cada punto es una evaluación que llegó a Tierra, con el color de su resultado.${todos ? " Cada icono es un tripulante: toca uno para ver el detalle." : ""}</span>
  </section>
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,460px),1fr));gap:20px;align-items:start">
    <section style="overflow-x:auto;grid-column:span ${S.w >= 1200 ? 2 : 1}">
      <table class="table" style="min-width:640px">
        <thead><tr><th>Llegó a Tierra</th><th>Persona</th><th>Estado</th><th>Tarea</th><th style="text-align:right">Puntaje</th><th style="text-align:right">KSS</th><th style="text-align:right">PVT</th><th style="text-align:right">Pulso</th></tr></thead>
        <tbody>
          ${rows.slice(pag * POR_PAGINA, pag * POR_PAGINA + POR_PAGINA).map((f) => { const st = ST[f.color] || ST.sin; return h`<tr data-click="hSel" data-arg="${f.id}" style="cursor:pointer;background-color:${f.id === S.hSel ? "color-mix(in srgb, var(--color-accent) 10%, transparent)" : "transparent"}">
              <td style="${MONO};font-size:12px;white-space:nowrap">${fechaCorta(f.llego || f.fecha)} ${horaLarga(f.llego || f.fecha)}</td>
              <td>${nombre(f.persona)}${f.simulado ? h` <span class="tag tag-neutral" style="${MONO};font-size:9px;padding:1px 6px">SIM</span>` : ""}</td>
              <td><span style="display:inline-flex;align-items:center;gap:5px;padding:2px 8px;border-radius:5px;background:${st.bg};color:${st.fg};${MONO};font-size:11px;font-weight:600"><i class="ph-fill ${st.icon}"></i>${st.word}</span></td>
              <td style="font-size:13px;color:var(--color-neutral-300)">${f.tarea ? cap(f.tarea) : "–"}</td>
              <td style="text-align:right;${MONO}">${fmt(f.puntaje)}</td>
              <td style="text-align:right;${MONO}">${entero(f.kss)}</td>
              <td style="text-align:right;${MONO}">${entero(f.pvt_mediana)}</td>
              <td style="text-align:right;${MONO}">${entero(f.pulso_lpm)}</td>
            </tr>`; })}
        </tbody>
      </table>
      ${nPag > 1 ? h`<nav aria-label="Paginación" style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;padding:12px 4px 0">
          <span style="${MONO};font-size:12px;color:var(--color-neutral-400);margin-right:auto">${pag * POR_PAGINA + 1}–${Math.min(rows.length, pag * POR_PAGINA + POR_PAGINA)} de ${rows.length} evaluaciones</span>
          <button class="btn btn-ghost" type="button" data-click="hPag" data-arg="${pag - 1}" ${si(pag === 0, "disabled")} aria-label="Página anterior" style="padding:6px 8px"><i class="ph ph-caret-left"></i></button>
          <span style="${MONO};font-size:12px;color:var(--color-neutral-300)">${pag + 1} / ${nPag}</span>
          <button class="btn btn-ghost" type="button" data-click="hPag" data-arg="${pag + 1}" ${si(pag >= nPag - 1, "disabled")} aria-label="Página siguiente" style="padding:6px 8px"><i class="ph ph-caret-right"></i></button>
        </nav>` : ""}
      ${rows.length ? "" : vacio}
    </section>
    <aside style="${SECC};position:sticky;top:20px">
      ${sel ? h`${etq("Detalle de la evaluación")}
        <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap"><span style="font-size:20px;font-weight:500">${nombre(sel.persona)}</span>${pildora(ST[sel.color] || ST.sin, "", "font-size:11px;padding:2px 8px")}${marcas(sel)}</div>
        <span style="${MONO};font-size:12px;color:var(--color-neutral-400);word-break:break-all">sesión ${sel.id}</span>
        <dl style="display:grid;grid-template-columns:auto 1fr;gap:8px 16px;margin:0;font-size:13px">
          <dt style="color:var(--color-neutral-400)">En la nave</dt><dd style="margin:0;${MONO}">${cuando(sel.fecha)}:${dd(new Date(sel.fecha).getSeconds())}</dd>
          <dt style="color:var(--color-neutral-400)">En Tierra</dt><dd style="margin:0;${MONO}">${cuando(sel.llego || sel.fecha)}:${dd(new Date(sel.llego || sel.fecha).getSeconds())}</dd>
          <dt style="color:var(--color-neutral-400)">Tarea</dt><dd style="margin:0">${sel.tarea ? cap(sel.tarea) : "–"}</dd>
          <dt style="color:var(--color-neutral-400)">Puntaje</dt><dd style="margin:0;${MONO}">${fmt(sel.puntaje)}</dd>
          <dt style="color:var(--color-neutral-400)">KSS</dt><dd style="margin:0;${MONO}">${entero(sel.kss)} de 9</dd>
          <dt style="color:var(--color-neutral-400)">Sueño</dt><dd style="margin:0;${MONO}">${fmt(sel.horas_sueno, 1)} h</dd>
          <dt style="color:var(--color-neutral-400)">PVT mediana</dt><dd style="margin:0;${MONO}">${entero(sel.pvt_mediana)} ms</dd>
          <dt style="color:var(--color-neutral-400)">Pulso</dt><dd style="margin:0;${MONO}">${entero(sel.pulso_lpm)} lpm</dd>
        </dl>
        ${(sel.motivos || []).length ? h`<div style="display:flex;flex-direction:column;gap:4px">${sel.motivos.map((m) => h`<span style="display:flex;gap:6px;font-size:12px;color:var(--color-neutral-300)"><i class="ph ph-caret-right" style="color:var(--color-accent);margin-top:2px"></i>${m}</span>`)}</div>` : ""}
        <div style="display:flex;gap:8px;flex-wrap:wrap"><button class="btn btn-primary" type="button" data-click="abrir" data-arg="${sel.id}" style="font-size:13px"><i class="ph ph-clipboard-text"></i>Ver resultado</button><a class="btn btn-secondary" href="${csv}" download style="font-size:13px"><i class="ph ph-download-simple"></i>Exportar CSV</a></div>`
      : h`<div style="display:flex;flex-direction:column;gap:8px;align-items:flex-start;padding:12px 0"><i class="ph ph-cursor-click" style="font-size:24px;color:var(--color-neutral-500)"></i><b style="font-weight:500">Elige una evaluación</b><span style="font-size:13px;color:var(--color-neutral-400)">El detalle aparece aquí.</span>${rows.length ? h`<a class="btn btn-secondary" href="${csv}" download style="font-size:13px;margin-top:4px"><i class="ph ph-download-simple"></i>Exportar CSV del periodo</a>` : ""}</div>`}
    </aside>
  </div>
</div>`;
  }

  // ================================================================== vista: Resultado
  function indicadoresDe(s) {
    const ult = {};
    for (const m of s.mensajes) ult[m.tipo] = m.datos;
    const nd = (nombreInd, fuente, notaTxt) => ({ tipo: "no_disponible", nombre: nombreInd, fuente, valor: "", unidad: "", nota: notaTxt });
    const out = [];
    const e = s.esp32;
    if (e && e.validas) {
      out.push(num(e.pulso_lpm) !== null ? { tipo: "medido", nombre: "Pulso", fuente: "ESP32", valor: entero(e.pulso_lpm), unidad: "lpm", nota: `Mediana de ${e.validas} lecturas con el dedo puesto y calidad de 0,5 o más.` } : nd("Pulso", "ESP32", "Sin pulso en las lecturas válidas."));
      out.push(num(e.hrv_rmssd_ms) !== null ? { tipo: "medido", nombre: "HRV (RMSSD)", fuente: "ESP32", valor: entero(e.hrv_rmssd_ms), unidad: "ms", nota: "Variación entre latidos en 30 s." } : nd("HRV (RMSSD)", "ESP32", "Sin HRV en las lecturas válidas."));
      out.push(num(e.spo2) !== null ? { tipo: "medido", nombre: "SpO₂", fuente: "ESP32", valor: entero(e.spo2), unidad: "%", nota: `Mediana; mínimo ${entero(e.spo2_min)} %. Es un aviso, no puntaje.` } : nd("SpO₂", "ESP32", "Sin SpO₂ en las lecturas válidas."));
    } else {
      const motivo = e ? `Ninguna de las ${e.lecturas} lecturas tuvo el dedo puesto y calidad de 0,5 o más.` : "No llegaron lecturas del sensor de esta sesión.";
      out.push(nd("Pulso", "ESP32", motivo), nd("HRV (RMSSD)", "ESP32", motivo));
    }
    const pv = ult.pvt;
    if (pv) {
      const min = Math.max(1, Math.round((num(pv.duracion_s) || 0) / 60));
      out.push({ tipo: "medido", nombre: "Reacción PVT-B", fuente: "Estación", valor: entero(pv.rt_mediana_ms), unidad: "ms mediana", nota: `${pv.lapsos ?? 0} lapsos y ${pv.anticipadas ?? 0} anticipadas${num(pv.duracion_s) !== null ? ` en ${min} ${min === 1 ? "minuto" : "minutos"}` : ""}${pv.modo_demo ? " (modo demo)" : ""}.` });
    } else out.push(nd("Reacción PVT-B", "Estación", "No llegó a Tierra."));
    if (ult.dsst) out.push({ tipo: "medido", nombre: "Símbolos DSST", fuente: "Estación", valor: fmt(ult.dsst.por_minuto, 1), unidad: "correctas por min", nota: `${ult.dsst.correctas ?? 0} correctas y ${ult.dsst.incorrectas ?? 0} errores.` });
    const vi = ult.vision;
    if (vi) {
      out.push({ tipo: "medido", nombre: "Parpadeos", fuente: "Visión", valor: fmt(vi.parpadeos_min, 1), unidad: "por min", nota: vi.lentes ? "Medido con lentes: los ojos no cuentan." : "EAR por debajo del 60 % del ojo abierto." });
      const pc = num(vi.perclos) !== null && num(vi.perclos) > 1 ? num(vi.perclos) / 100 : vi.perclos;
      out.push({ tipo: "estimado", nombre: "PERCLOS", fuente: "Visión", valor: fmt(pc), unidad: "fracción", nota: "Tiempo con los ojos casi cerrados (aproximación P80)." });
      out.push({ tipo: "medido", nombre: "Bostezos", fuente: "Visión", valor: entero(vi.bostezos), unidad: "en la medición", nota: `${entero(vi.bostezos_tapados)} tapados con la mano.` });
      const cal = num(vi.calidad_rppg);
      out.push(num(vi.pulso_rppg_lpm) !== null && cal !== null && cal >= 0.5
        ? { tipo: "estimado", nombre: "Pulso sin contacto", fuente: "Visión", valor: entero(vi.pulso_rppg_lpm), unidad: "lpm", nota: `Por cámara (rPPG), calidad ${fmt(cal)}.` }
        : nd("Pulso sin contacto", "Visión", cal !== null ? `Calidad ${fmt(cal)}: hace falta 0,5.` : "Sin calidad suficiente."));
    } else out.push(nd("Visión", "Visión", "No llegó a Tierra."));
    const vz = ult.voz;
    if (vz && num(vz.indice_cansancio) !== null) {
      const v = num(vz.indice_cansancio);
      out.push({ tipo: "estimado", nombre: "Cansancio en la voz", fuente: "Voz", valor: (v > 0 ? "+" : "") + fmt(v, 1), unidad: "índice z", nota: `Señal débil.${vz.estado_voz ? " " + cap(vz.estado_voz) + "." : ""}` });
    } else out.push(nd("Cansancio en la voz", "Voz", vz ? "Sin línea base de voz." : "No llegó a Tierra."));
    const cu = ult.cuestionario;
    if (cu) {
      out.push({ tipo: "reportado", nombre: "Somnolencia KSS", fuente: "Cuestionario", valor: entero(cu.kss), unidad: "de 9", nota: cu.kss_texto ? `${cu.kss_texto}.` : "Escala de Karolinska." });
      out.push({ tipo: "reportado", nombre: "Horas de sueño", fuente: "Cuestionario", valor: fmt(cu.horas_sueno, 1), unidad: "h", nota: "Reportado por la persona." });
    } else out.push(nd("Cuestionario", "Cuestionario", "No llegó a Tierra."));
    return out;
  }

  function vistaResultado() {
    const f = filaDe(S.sel);
    const s = S.sesiones[S.sel];
    if (!S.sel || !f) {
      return h`<div data-k="res-vacio" style="display:flex;flex-direction:column;align-items:flex-start;gap:12px;padding:48px 0">
        <i class="ph ph-clipboard-text" style="font-size:36px;color:var(--color-neutral-500)"></i>
        <h2 style="font-size:22px;margin:0">Todavía no hay resultados en Tierra</h2>
        <span style="color:var(--color-neutral-300)">Las evaluaciones llegan desde la nave con el retraso de la comunicación.</span>
        <button class="btn btn-secondary" type="button" data-click="ir" data-arg="historial" style="padding:9px 16px"><i class="ph ph-chart-line-up"></i>Ver evaluaciones</button>
      </div>`;
    }
    const st = ST[f.color] || ST.sin;
    const p = Math.max(0, Math.min(1, num(f.puntaje) ?? 0));
    const esAvisoSpo2 = (m) => f.aviso_spo2 && /^ox[ií]geno m[aá]s bajo/i.test(m);
    const propios = (f.motivos || []).filter((m) => !esAvisoSpo2(m));
    const motivos = propios.length ? propios : ["Señales en el rango habitual."];
    const indicadores = s && s.disponible ? indicadoresDe(s) : [];
    const retraso = f.llego && f.fecha ? Math.round((f.llego - f.fecha) / 1000) : null;
    return h`<div data-k="res-${f.id}" style="display:contents">
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,300px),1fr));gap:20px;align-items:stretch">
    <section style="position:relative;overflow:hidden;display:flex;flex-direction:column;align-items:flex-start;gap:14px;padding:22px;border-radius:var(--radius-lg);background:var(--color-surface);box-shadow:var(--shadow-sm);backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px)">
      <div style="position:relative;width:140px;height:140px">
        <svg viewBox="0 0 140 140" width="140" height="140"><circle cx="70" cy="70" r="62" fill="none" stroke="var(--color-neutral-800)" stroke-width="1"></circle><circle cx="70" cy="70" r="50" fill="${st.bg}" stroke="${st.fg}" stroke-width="2"></circle><circle cx="70" cy="70" r="62" fill="none" stroke="${st.fg}" stroke-width="3" stroke-linecap="round" stroke-dasharray="${p * 389.6} 389.6" transform="rotate(-90 70 70)"></circle></svg>
        <i class="ph-fill ${st.icon}" style="position:absolute;inset:0;display:grid;place-items:center;font-size:44px;color:${st.fg}"></i>
      </div>
      <span style="${MONO};font-size:30px;font-weight:600;letter-spacing:0.08em;color:${st.fg}">${st.word}</span>
      <span style="font-size:15px;color:var(--color-neutral-200)">${st.label}</span>
      <div style="display:flex;gap:6px;flex-wrap:wrap">${marcas(f)}</div>
      <span style="${MONO};font-size:12px;color:var(--color-neutral-400)">Puntaje ${fmt(f.puntaje)} · sesión ${f.id}</span>
    </section>
    <section style="display:flex;flex-direction:column;gap:14px;padding:22px;border-radius:var(--radius-lg);background:var(--color-surface);grid-column:span ${S.w >= 1100 ? 2 : 1};box-shadow:var(--shadow-sm);backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px)">
      <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
        <span style="display:flex;align-items:center;gap:7px;font-size:18px;font-weight:500"><i class="ph-fill ${icono(f.persona)}" style="color:var(--color-accent-300)"></i>${nombre(f.persona)}</span>
        ${f.tarea ? h`<span class="tag tag-accent">${cap(f.tarea)}</span>` : ""}
      </div>
      <div style="display:flex;flex-direction:column;gap:6px">
        ${etq("Recomendación a bordo")}
        <p style="margin:0;font-size:20px;line-height:1.35;font-weight:500;text-wrap:pretty">${f.accion || "–"}</p>
      </div>
      <div style="display:flex;flex-direction:column;gap:6px">
        ${etq("Motivos")}
        ${motivos.map((m) => h`<span style="display:flex;gap:8px;align-items:flex-start;font-size:15px"><i class="ph ph-caret-right" style="color:var(--color-accent);margin-top:3px"></i>${m}</span>`)}
      </div>
      ${f.aviso_spo2 ? h`<div role="status" style="display:flex;gap:10px;align-items:flex-start;padding:10px 14px;border-radius:var(--radius-md);background:${ST.amarillo.bg}">
        <i class="ph ph-drop" style="font-size:18px;color:${ST.amarillo.fg}"></i>
        <span style="display:flex;flex-direction:column;gap:2px"><b style="font-weight:500;color:${ST.amarillo.fg}">Oxígeno más bajo de lo habitual</b><span style="font-size:13px;color:var(--color-neutral-200)">Es un aviso y no cambia el color del resultado.</span></span>
      </div>` : ""}
      <div style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin-top:auto">
        ${[["En la nave", horaLarga(f.fecha), cuando(f.fecha)], ["En Tierra", horaLarga(f.llego || f.fecha), cuando(f.llego || f.fecha)], ["Retraso", retraso === null ? "–" : `${retraso} s`, "de la comunicación"]].map(([l, v, sub]) => h`<div style="display:flex;flex-direction:column;gap:2px;padding:10px;${TARJ}"><span style="font-size:11px;color:var(--color-neutral-300)">${l}</span><span style="${MONO};font-size:18px;font-variant-numeric:tabular-nums">${v}</span><span style="font-size:11px;color:var(--color-neutral-400)">${sub}</span></div>`)}
      </div>
    </section>
  </div>

  <section style="display:flex;flex-direction:column;gap:12px">
    <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">
      <h2 style="font-size:17px;margin:0;margin-right:auto">Indicadores recibidos</h2>
      ${Object.values(TIPOS).map((tl) => h`<span style="display:inline-flex;align-items:center;gap:5px;font-size:12px;color:${tl.fg}"><i class="ph ${tl.icon}"></i>${tl.label}</span>`)}
    </div>
    ${!s ? nota("ph-circle-notch", "Leyendo la sesión…") : !s.disponible ? nota("ph-plugs", s.motivo || "No se pudo leer la sesión.") : h`<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,240px),1fr));gap:10px">
      ${indicadores.map((it) => {
        const T = TIPOS[it.tipo]; const nada = it.tipo === "no_disponible";
        return h`<article class="hv-sube" style="display:flex;flex-direction:column;gap:6px;padding:14px;border-radius:var(--radius-md);background:${nada ? "transparent" : "var(--color-surface)"};box-shadow:${nada ? "inset 0 0 0 1px var(--color-neutral-800)" : "none"};transition:transform .2s">
          <div style="display:flex;align-items:center;gap:6px">
            <span style="font-size:13px;font-weight:500">${it.nombre}</span>
            <span style="margin-left:auto;display:inline-flex;align-items:center;gap:4px;font-size:11px;color:${T.fg}"><i class="ph ${T.icon}"></i>${T.label}</span>
          </div>
          <div style="display:flex;align-items:baseline;gap:6px;min-height:34px">
            <span style="${MONO};font-size:${nada ? 22 : 28}px;font-variant-numeric:tabular-nums;color:${nada ? "var(--color-neutral-500)" : "var(--color-text)"}">${nada ? "No disponible" : it.valor}</span>
            <span style="font-size:12px;color:var(--color-neutral-400)">${it.unidad}</span>
          </div>
          <p style="margin:0;font-size:12px;line-height:1.45;color:var(--color-neutral-300);text-wrap:pretty">${it.nota}</p>
          <span style="font-size:11px;color:var(--color-neutral-500);${MONO}">Fuente · ${it.fuente}</span>
        </article>`;
      })}
    </div>`}
  </section>

  <div style="display:flex;gap:8px;flex-wrap:wrap">
    <button class="btn btn-secondary" type="button" data-click="ir" data-arg="historial" style="padding:9px 16px"><i class="ph ph-chart-line-up"></i>Ver evaluaciones</button>
    <button class="btn btn-ghost" type="button" data-click="ir" data-arg="panel" style="padding:9px 16px"><i class="ph ph-squares-four"></i>Volver al panel</button>
  </div>
</div>`;
  }

  // ================================================================== arranque
  aplicarTema();
  pintar();
  actualizar();
  // El fondo es decoración: si falla (por ejemplo, la ventana mide 0 porque la pestaña está oculta), los datos se
  // siguen viendo, y se vuelve a intentar cuando la ventana tenga tamaño.
  let fondoListo = false;
  function iniciarFondo() {
    if (fondoListo || !window.innerWidth || !window.innerHeight) return;
    try {
      Fondo.iniciar(document.getElementById("fondo"), { claro: () => S.tema === "claro", quieto: reducido });
      fondoListo = true;
    } catch (e) { /* se reintenta al cambiar el tamaño */ }
  }
  iniciarFondo();
  window.addEventListener("resize", iniciarFondo);
  if (S.pantalla === "historial") cargarHistorial();
  setInterval(actualizar, CADA_MS);
  setInterval(pedirPintar, 1000);  // el reloj de Tierra y los «hace … s»
})();
