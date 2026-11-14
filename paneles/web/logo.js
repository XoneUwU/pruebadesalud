/* Logo animado de Becspace (de «Becspace Logo» de Claude Design): la Tierra gira despacio y el cohete da una vuelta
 * cada 8 s; pasa por detrás del planeta y cruza las letras con un destello verde.
 * Logo.html("full" | "compact", "dark" | "light") devuelve el SVG; un solo bucle anima todos los que haya en la página.
 * Respeta «reducir movimiento» (del sistema o de Configuración: document.documentElement.dataset.quieto). */
(function () {
  "use strict";

  const CX = 300, CY = 200, RX = 250, RY = 50, ROT = (-11 * Math.PI) / 180;
  const TXT = { x0: 110, x1: 530, y0: 178, y1: 258 };
  const DURACION_MS = 8000;
  let uid = 0;

  // Luces de ciudades: siempre las mismas (semilla fija).
  const LUCES = (() => {
    let s = 11;
    const r = () => ((s = (s * 9301 + 49297) % 233280) / 233280);
    const zonas = [[190, 110, 60, 50], [222, 230, 30, 60], [360, 170, 40, 25], [345, 100, 25, 12]];
    const luces = [];
    zonas.forEach(([zx, zy, w, h]) => {
      for (let i = 0; i < 22; i++) {
        luces.push(`<circle cx="${(zx + (r() - 0.5) * w).toFixed(1)}" cy="${(zy + (r() - 0.5) * h).toFixed(1)}" ` +
          `r="${(0.6 + r() * 1.3).toFixed(2)}" style="fill:#d9ff6a;opacity:${(0.45 + r() * 0.5).toFixed(2)}"></circle>`);
      }
    });
    return luces.join("");
  })();

  const TIERRA = (cp) => `<g transform="translate(${cp} 0)">
      <path d="M150 92 C168 74 204 70 222 84 C236 96 230 112 246 122 C258 130 252 148 236 150 C222 152 214 166 220 178 C226 192 212 198 200 190 C190 182 176 186 170 172 C162 156 146 150 148 132 C150 118 140 106 150 92 Z" style="fill:#24503a;opacity:.75"></path>
      <path d="M214 196 C230 192 248 204 252 222 C256 242 246 262 238 282 C232 298 220 312 212 304 C206 296 210 278 204 262 C198 248 192 232 198 216 C202 204 206 198 214 196 Z" style="fill:#24503a;opacity:.75"></path>
      <path d="M330 86 C346 80 366 88 372 102 C376 114 362 118 352 116 C340 114 326 102 330 86 Z" style="fill:#3c6247;opacity:.7"></path>
      <path d="M360 150 C380 144 404 152 410 172 C414 188 400 200 384 198 C368 196 354 182 360 150 Z" style="fill:#2f5b3c;opacity:.6"></path>
      ${LUCES}</g>`;

  const NUBES = (cp, soft) => `<g transform="translate(${cp} 0)" filter="url(#${soft})">
      <ellipse cx="330" cy="140" rx="46" ry="12" style="fill:#e8f2f4"></ellipse>
      <ellipse cx="380" cy="230" rx="38" ry="9" style="fill:#e8f2f4"></ellipse>
      <ellipse cx="250" cy="250" rx="30" ry="8" style="fill:#e8f2f4"></ellipse>
      <ellipse cx="190" cy="120" rx="26" ry="7" style="fill:#e8f2f4"></ellipse></g>`;

  function html(variante, tono) {
    const u = "bx" + ++uid;
    const id = { ocean: u + "o", shade: u + "s", silver: u + "t", trail: u + "r", body: u + "b", flash: u + "f",
      glow: u + "g", soft: u + "q", earth: u + "e", text: u + "x", rocket: u + "k" };
    const claro = tono === "light";
    const tx = claro
      ? { s0: "#F5F7FA", s1: "#E4E9EE", s2: "#C8D2D9", s3: "#9AA7B2", shadow: "#000", edge: "#000000", ew: "6", eo: "1", og: "#1f6b45", ol: "#165a38" }
      : { s0: "#F5F7FA", s1: "#E4E9EE", s2: "#C8D2D9", s3: "#9AA7B2", shadow: "#000", edge: "#F5F7FA", ew: ".6", eo: ".6", og: "#00C896", ol: "#6CFF8F" };
    const viewBox = variante === "compact" ? "30 66 548 272" : "20 40 560 330";
    const texto = 'x="292" y="252" text-anchor="middle" transform="skewX(-12) translate(48 0)"';
    const fuente = "font-family:Inter, system-ui, sans-serif;font-size:96px;font-weight:700;letter-spacing:-1px";
    return `<svg data-logo viewBox="${viewBox}" role="img" aria-label="Becspace" style="display:block;width:100%;height:auto;overflow:visible">
  <defs>
    <radialGradient id="${id.ocean}" cx="36%" cy="30%" r="80%"><stop offset="0" stop-color="#1d6b6a"></stop><stop offset="0.45" stop-color="#0c3b44"></stop><stop offset="1" stop-color="#04141c"></stop></radialGradient>
    <radialGradient id="${id.shade}" cx="30%" cy="28%" r="85%"><stop offset="0.45" stop-color="#000" stop-opacity="0"></stop><stop offset="1" stop-color="#000" stop-opacity="0.65"></stop></radialGradient>
    <linearGradient id="${id.silver}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${tx.s0}"></stop><stop offset="0.5" stop-color="${tx.s1}"></stop><stop offset="0.62" stop-color="${tx.s2}"></stop><stop offset="1" stop-color="${tx.s3}"></stop></linearGradient>
    <linearGradient id="${id.trail}" x1="0" x2="1"><stop offset="0" stop-color="#6CFF8F" stop-opacity="0"></stop><stop offset="0.7" stop-color="#6CFF8F" stop-opacity="0.65"></stop><stop offset="1" stop-color="#E9FFF0" stop-opacity="0.95"></stop></linearGradient>
    <linearGradient id="${id.body}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#F5F7FA"></stop><stop offset="0.55" stop-color="#C8D2D9"></stop><stop offset="1" stop-color="#7d8a95"></stop></linearGradient>
    <radialGradient id="${id.flash}"><stop offset="0" stop-color="#E9FFF0" stop-opacity="1"></stop><stop offset="0.35" stop-color="#6CFF8F" stop-opacity="0.85"></stop><stop offset="1" stop-color="#00C896" stop-opacity="0"></stop></radialGradient>
    <filter id="${id.glow}" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="6"></feGaussianBlur></filter>
    <filter id="${id.soft}" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="2.2"></feGaussianBlur></filter>
    <clipPath id="${id.earth}"><circle cx="300" cy="200" r="128"></circle></clipPath>
    <clipPath id="${id.text}"><text ${texto} style="${fuente}">Becspace</text></clipPath>
    <g id="${id.rocket}">
      <rect x="-64" y="-3.5" width="56" height="7" rx="3.5" fill="url(#${id.trail})" style="filter:blur(1.5px)"></rect>
      <path d="M-10 -3 L-20 0 L-10 3 Z" style="fill:#6CFF8F"></path>
      <path d="M-6 -6 L-14 -14 L-2 -7 Z" style="fill:#C8D2D9"></path>
      <path d="M-6 6 L-14 14 L-2 7 Z" style="fill:#9AA7B2"></path>
      <path d="M22 0 C16 -8 4 -8 -8 -6 L-8 6 C4 8 16 8 22 0 Z" fill="url(#${id.body})"></path>
      <circle cx="7" cy="0" r="3.6" style="fill:#0b2a24;stroke:#6CFF8F;stroke-width:1.4"></circle>
      <path d="M-8 -6 L-8 6" style="stroke:#00C896;stroke-width:1.2"></path>
    </g>
  </defs>
  <g transform="rotate(-11 300 200)">
    <path d="M50 200 A250 50 0 0 1 550 200" style="fill:none;stroke:${tx.og};stroke-width:5;opacity:.35" filter="url(#${id.glow})"></path>
    <path d="M50 200 A250 50 0 0 1 550 200" style="fill:none;stroke:${tx.ol};stroke-width:1.6;opacity:.75"></path>
  </g>
  <g data-k="rocket-back"><use href="#${id.rocket}"></use></g>
  <circle cx="300" cy="200" r="134" style="fill:#00C896;opacity:.38" filter="url(#${id.glow})"></circle>
  <circle cx="300" cy="200" r="128" fill="url(#${id.ocean})"></circle>
  <g clip-path="url(#${id.earth})">
    <g data-k="land">${TIERRA(0)}${TIERRA(300)}</g>
    <g data-k="clouds" style="opacity:.18">${NUBES(0, id.soft)}${NUBES(300, id.soft)}</g>
    <circle cx="300" cy="200" r="128" fill="url(#${id.shade})"></circle>
  </g>
  <path d="M206 108 A128 128 0 0 1 404 124" style="fill:none;stroke:#6CFF8F;stroke-width:3;opacity:.9" filter="url(#${id.soft})"></path>
  <circle cx="300" cy="200" r="128" style="fill:none;stroke:#6CFF8F;stroke-width:1;opacity:.45"></circle>
  <g transform="rotate(-11 300 200)">
    <path d="M550 200 A250 50 0 0 1 50 200" style="fill:none;stroke:${tx.og};stroke-width:6;opacity:.45" filter="url(#${id.glow})"></path>
    <path d="M550 200 A250 50 0 0 1 50 200" style="fill:none;stroke:${tx.ol};stroke-width:2;opacity:.95"></path>
  </g>
  <g data-k="rocket-front"><use href="#${id.rocket}"></use></g>
  <text ${texto} style="${fuente};fill:${tx.shadow};opacity:.45" filter="url(#${id.soft})">Becspace</text>
  <text ${texto} fill="url(#${id.silver})" style="${fuente};stroke:${tx.edge};stroke-width:${tx.ew};stroke-opacity:${tx.eo};paint-order:stroke fill;stroke-linejoin:round">Becspace</text>
  <g clip-path="url(#${id.text})"><circle data-k="flash" cx="-100" cy="-100" r="30" fill="url(#${id.flash})" style="opacity:0"></circle></g>
  <circle data-k="spark" cx="-100" cy="-100" r="14" fill="url(#${id.flash})" style="opacity:0"></circle>
</svg>`;
  }

  function punto(a) {
    const x = RX * Math.cos(a), y = RY * Math.sin(a);
    return [CX + x * Math.cos(ROT) - y * Math.sin(ROT), CY + x * Math.sin(ROT) + y * Math.cos(ROT)];
  }

  function quieto() {
    return document.documentElement.dataset.quieto === "1" ||
      Boolean(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  }

  const inicio = new WeakMap();

  function cuadro(svg, t, reducido) {
    if (!inicio.has(svg)) inicio.set(svg, t);
    const t0 = inicio.get(svg);
    const q = (k) => svg.querySelector(`[data-k="${k}"]`);
    const ph = reducido ? 0.47 : (((t - t0) % DURACION_MS) / DURACION_MS);
    const a = Math.PI - ph * Math.PI * 2;
    const [x, y] = punto(a);
    const [x2, y2] = punto(a - 0.01);
    const ang = (Math.atan2(y2 - y, x2 - x) * 180) / Math.PI;
    const frente = Math.sin(a) > 0;
    const prof = 0.78 + 0.22 * Math.sin(a);
    const tf = `translate(${x.toFixed(2)} ${y.toFixed(2)}) rotate(${ang.toFixed(2)}) scale(${prof.toFixed(3)})`;
    const rf = q("rocket-front"), rb = q("rocket-back");
    if (rf) { rf.setAttribute("transform", tf); rf.style.opacity = frente ? 1 : 0; }
    if (rb) { rb.setAttribute("transform", tf); rb.style.opacity = frente ? 0 : 1; }
    const enTexto = frente && x > TXT.x0 && x < TXT.x1 && y > TXT.y0 && y < TXT.y1;
    const fl = q("flash"), sp = q("spark");
    if (fl) { fl.setAttribute("cx", x); fl.setAttribute("cy", y); fl.style.opacity = enTexto ? 0.9 : 0; }
    if (sp) {
      sp.setAttribute("cx", x + Math.cos((ang * Math.PI) / 180) * 18);
      sp.setAttribute("cy", y + Math.sin((ang * Math.PI) / 180) * 18);
      sp.style.opacity = enTexto ? 0.55 + 0.45 * Math.sin(t / 40) : 0;
    }
    const seg = (t - t0) / 1000;
    const tierra = q("land"), nubes = q("clouds");
    if (tierra) tierra.setAttribute("transform", `translate(${(reducido ? 0 : -((seg * 2.2) % 300)).toFixed(2)} 0)`);
    if (nubes) nubes.setAttribute("transform", `translate(${(reducido ? 0 : -((seg * 3.4) % 300)).toFixed(2)} 0)`);
  }

  function bucle(t) {
    const reducido = quieto();
    document.querySelectorAll("svg[data-logo]").forEach((svg) => cuadro(svg, t, reducido));
    requestAnimationFrame(bucle);
  }
  requestAnimationFrame(bucle);

  window.Logo = { html };
})();
