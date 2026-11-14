/* Fondo animado de la estación (del diseño «Apto Hoy» de Claude Design), dibujado en un <canvas> fijo:
 * oscuro = la Tierra de noche con su atmósfera, estrellas, una órbita y un cohete; claro = un sistema solar en
 * acuarela con constelaciones. Fondo.iniciar(canvas, {claro: () => bool, quieto: () => bool});
 * Fondo.reconstruir() al cambiar el tema y Fondo.despertar() al quitar «reducir movimiento». */
(function () {
  "use strict";

  let ctx = null, cv = null, op = null;
  let W = 0, H = 0, E = null, A = null, stat = null, tw = [], dots = [], L = null, raf = null, lastT = 0;
  let seed = 4;
  const rnd = (a, b) => a + ((seed = (seed * 16807) % 2147483647) / 2147483647) * (b - a);
  const dpr = Math.min(1.5, window.devicePixelRatio || 1);

  function construirClaro() {
    seed = 9; stat = document.createElement("canvas"); stat.width = W * dpr; stat.height = H * dpr;
    const c = stat.getContext("2d"); c.setTransform(dpr, 0, 0, dpr, 0, 0);
    const g0 = c.createLinearGradient(0, 0, 0, H);
    [[0, "#f3efff"], [0.35, "#ece8fb"], [0.7, "#e6ecfa"], [1, "#fdeee3"]].forEach(([o, k]) => g0.addColorStop(o, k));
    c.fillStyle = g0; c.fillRect(0, 0, W, H);
    // halo del sol, abajo a la derecha
    const sx = W * 0.86, sy = H * 0.94;
    const sg = c.createRadialGradient(sx, sy, 0, sx, sy, Math.max(W, H) * 0.55);
    sg.addColorStop(0, "rgba(255,196,140,0.55)"); sg.addColorStop(0.25, "rgba(255,170,190,0.22)"); sg.addColorStop(1, "rgba(255,200,180,0)");
    c.fillStyle = sg; c.fillRect(0, 0, W, H);
    // nebulosas pastel
    [[0.18, 0.2, 0.42, "rgba(150,130,235,0.16)"], [0.62, 0.12, 0.36, "rgba(110,170,255,0.14)"], [0.4, 0.55, 0.4, "rgba(240,150,200,0.10)"]].forEach(([x, y, r, col]) => {
      const g = c.createRadialGradient(x * W, y * H, 0, x * W, y * H, r * Math.max(W, H));
      g.addColorStop(0, col); g.addColorStop(1, "rgba(255,255,255,0)"); c.fillStyle = g; c.fillRect(0, 0, W, H);
    });
    // cuadrícula de plano
    c.strokeStyle = "rgba(106,92,196,0.06)"; c.lineWidth = 1; const step = 48;
    for (let x = 0; x < W; x += step) { c.beginPath(); c.moveTo(x + 0.5, 0); c.lineTo(x + 0.5, H); c.stroke(); }
    for (let y = 0; y < H; y += step) { c.beginPath(); c.moveTo(0, y + 0.5); c.lineTo(W, y + 0.5); c.stroke(); }
    // sistema solar: sol y órbitas
    L = { sx, sy, orbits: [0.16, 0.27, 0.4, 0.55, 0.72].map((k) => k * Math.max(W, H)) };
    L.orbits.forEach((r, i) => {
      c.beginPath(); c.arc(sx, sy, r, Math.PI, Math.PI * 1.5); c.setLineDash(i % 2 ? [3, 6] : []);
      c.strokeStyle = "rgba(106,92,196," + (0.22 - i * 0.03) + ")"; c.lineWidth = 1; c.stroke();
    });
    c.setLineDash([]);
    c.beginPath(); c.arc(sx, sy, 34, 0, 7);
    const sun = c.createRadialGradient(sx, sy, 0, sx, sy, 34); sun.addColorStop(0, "#fff4dc"); sun.addColorStop(1, "#ffb98a");
    c.fillStyle = sun; c.fill();
    // constelaciones
    const cons = [[[0.08, 0.12], [0.13, 0.08], [0.19, 0.11], [0.23, 0.06], [0.28, 0.1]], [[0.42, 0.3], [0.46, 0.25], [0.51, 0.28], [0.48, 0.35], [0.42, 0.3]],
      [[0.06, 0.62], [0.1, 0.55], [0.15, 0.6], [0.13, 0.7]], [[0.7, 0.08], [0.74, 0.16], [0.8, 0.12], [0.86, 0.18]]];
    cons.forEach((pts) => {
      c.beginPath(); pts.forEach(([x, y], i) => (i ? c.lineTo(x * W, y * H) : c.moveTo(x * W, y * H)));
      c.strokeStyle = "rgba(80,70,170,0.22)"; c.lineWidth = 1; c.stroke();
      pts.forEach(([x, y]) => { c.beginPath(); c.arc(x * W, y * H, 2.2, 0, 7); c.fillStyle = "rgba(80,70,170,0.55)"; c.fill(); });
    });
    for (let i = 0; i < 160; i++) {
      const x = rnd(0, W), y = rnd(0, H); c.beginPath(); c.arc(x, y, rnd(0.4, 1.2), 0, 7);
      c.fillStyle = "rgba(90,80,180," + rnd(0.1, 0.35) + ")"; c.fill();
    }
    tw = Array.from({ length: 40 }, () => ({ x: rnd(0, W), y: rnd(0, H * 0.8), r: rnd(1, 2), p: rnd(0, 6.28), s: rnd(0.3, 0.8), big: rnd(0, 1) < 0.35 }));
    L.planets = [["#7f9cf5", 6, 0.05], ["#f0a6c8", 9, 0.032], ["#9a86e6", 7, 0.022], ["#80c7c0", 12, 0.015, true], ["#c7b4f5", 5, 0.01]]
      .map(([col, r, sp, ring], i) => ({ col, r, sp, ring, a: rnd(0, 1), orb: L.orbits[i] }));
  }

  function construir() {
    if (op.claro()) { construirClaro(); return; }
    L = null;
    seed = 4; stat = document.createElement("canvas"); stat.width = W * dpr; stat.height = H * dpr;
    const c = stat.getContext("2d"); c.setTransform(dpr, 0, 0, dpr, 0, 0);
    const g0 = c.createLinearGradient(0, 0, 0, H);
    [[0, "#060913"], [0.28, "#0B1430"], [0.53, "#111D3D"], [0.76, "#192D56"], [1, "#243B6A"]].forEach(([o, k]) => g0.addColorStop(o, k));
    c.fillStyle = g0; c.fillRect(0, 0, W, H);
    c.globalCompositeOperation = "lighter";
    for (let i = 0; i < 170; i++) {
      const u = rnd(-0.1, 1.1); const x = u * W, y = (0.04 + u * 0.34 + rnd(-0.12, 0.12)) * H; const r = rnd(30, 190); const pur = rnd(0, 1) < 0.6;
      const g = c.createRadialGradient(x, y, 0, x, y, r);
      g.addColorStop(0, pur ? "rgba(128,102,217," + rnd(0.02, 0.06) + ")" : "rgba(69,110,220," + rnd(0.015, 0.045) + ")"); g.addColorStop(1, "rgba(0,0,0,0)");
      c.fillStyle = g; c.fillRect(x - r, y - r, r * 2, r * 2);
    }
    for (let i = 0; i < 900; i++) {
      const u = rnd(0, 1); const x = u * W, y = (0.04 + u * 0.34 + rnd(-0.1, 0.1)) * H;
      c.fillStyle = "rgba(220,215,255," + rnd(0.05, 0.35) + ")"; c.fillRect(x, y, rnd(0.4, 1.1), rnd(0.4, 1.1));
    }
    c.globalCompositeOperation = "source-over";
    for (let i = 0; i < 380; i++) {
      const y = Math.pow(rnd(0, 1), 1.5) * H * 0.85, x = rnd(0, W); const a = rnd(0.15, 0.8) * (1 - y / H * 0.8);
      c.beginPath(); c.arc(x, y, rnd(0.3, 0.9), 0, 7); c.fillStyle = "rgba(244,246,255," + a + ")"; c.fill();
    }
    tw = Array.from({ length: 70 }, () => ({ x: rnd(0, W), y: Math.pow(rnd(0, 1), 1.4) * H * 0.75, r: rnd(0.8, 1.6), p: rnd(0, 6.28), s: rnd(0.3, 0.9), big: rnd(0, 1) < 0.18 }));
    // arco orbital
    c.save(); c.beginPath(); c.ellipse(A.cx, A.cy, A.rx, A.ry, 0, Math.PI * 1.12, Math.PI * 1.88);
    const ga = c.createLinearGradient(A.cx - A.rx, 0, A.cx + A.rx, 0);
    ga.addColorStop(0, "rgba(69,143,255,0)"); ga.addColorStop(0.5, "rgba(150,190,255,0.55)"); ga.addColorStop(1, "rgba(69,143,255,0)");
    c.strokeStyle = ga; c.lineWidth = 1.2; c.shadowColor = "rgba(69,143,255,0.8)"; c.shadowBlur = 10; c.stroke(); c.restore();
    [1.08, 1.2].forEach((k, i) => {
      c.beginPath(); c.ellipse(A.cx, A.cy, A.rx * k, A.ry * k, 0, Math.PI * 1.15, Math.PI * 1.85);
      c.strokeStyle = "rgba(150,165,235," + (0.1 - i * 0.04) + ")"; c.lineWidth = 1; c.stroke();
    });
    // la Tierra
    const { cx, cy, R } = E; const top = cy - R;
    const glow = c.createRadialGradient(cx, top, 0, cx, top, W * 0.55);
    glow.addColorStop(0, "rgba(69,143,255,0.38)"); glow.addColorStop(0.35, "rgba(100,110,230,0.14)"); glow.addColorStop(1, "rgba(69,143,255,0)");
    c.save(); c.translate(cx, top); c.scale(1, 0.42); c.translate(-cx, -top); c.fillStyle = glow; c.fillRect(0, top - W * 0.6, W, W * 1.2); c.restore();
    c.save(); c.beginPath(); c.arc(cx, cy, R, 0, Math.PI * 2); c.clip();
    const gs = c.createLinearGradient(0, top, 0, top + H * 0.2);
    gs.addColorStop(0, "#0e2550"); gs.addColorStop(0.25, "#071433"); gs.addColorStop(1, "#02050d"); c.fillStyle = gs; c.fillRect(0, top, W, H);
    for (let i = 0; i < 60; i++) {
      const x = rnd(0, W), y = top + rnd(6, H * 0.15); const r = rnd(20, 90);
      const g = c.createRadialGradient(x, y, 0, x, y, r); g.addColorStop(0, "rgba(40,70,120," + rnd(0.05, 0.15) + ")"); g.addColorStop(1, "rgba(0,0,0,0)");
      c.fillStyle = g; c.fillRect(x - r, y - r, r * 2, r * 2);
    }
    const surf = (x) => cy - Math.sqrt(Math.max(0, R * R - (x - cx) * (x - cx)));
    for (let k = 0; k < 34; k++) {
      const x0 = rnd(0, W); const d0 = rnd(8, H * 0.13); const n = Math.floor(rnd(15, 60)); const spread = rnd(14, 60);
      for (let i = 0; i < n; i++) {
        const x = x0 + rnd(-spread, spread) * rnd(0.2, 1); const y = surf(x) + d0 + rnd(-spread, spread) * 0.35; const r = rnd(0.4, 1.3);
        const a = rnd(0.35, 0.95) * Math.max(0.2, 1 - d0 / (H * 0.16));
        c.beginPath(); c.arc(x, y, r, 0, 7); c.fillStyle = "rgba(255,196,120," + a + ")"; c.fill();
        if (r > 1.05) { c.beginPath(); c.arc(x, y, r * 3.5, 0, 7); c.fillStyle = "rgba(255,170,90," + a * 0.12 + ")"; c.fill(); }
      }
    }
    const lim = c.createRadialGradient(cx, cy, R - 90, cx, cy, R);
    lim.addColorStop(0, "rgba(69,143,255,0)"); lim.addColorStop(1, "rgba(69,143,255,0.32)"); c.fillStyle = lim; c.fillRect(0, top, W, H);
    c.restore();
    [[40, "rgba(128,102,217,0.10)", 50], [14, "rgba(69,143,255,0.30)", 26], [4, "rgba(110,170,255,0.75)", 12], [1.4, "rgba(225,240,255,0.95)", 4]].forEach(([lw, col, bl]) => {
      c.beginPath(); c.arc(cx, cy, R + lw * 0.3, Math.PI * 1.02, Math.PI * 1.98); c.strokeStyle = col; c.lineWidth = lw;
      c.shadowColor = "rgba(69,143,255,0.9)"; c.shadowBlur = bl; c.stroke();
    });
    c.shadowBlur = 0;
    dots = Array.from({ length: 16 }, () => ({ a: rnd(1.2, 1.8) * Math.PI, sp: rnd(0.006, 0.016), k: [1, 1.08, 1.2][Math.floor(rnd(0, 3))] }));
  }

  function medir() {
    W = window.innerWidth; H = window.innerHeight; cv.width = W * dpr; cv.height = H * dpr; ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const R = Math.max(W * 0.9, (0.25 * W * W) / (0.2 * H)); E = { cx: W * 0.52, cy: H * 0.905 + R, R };
    A = { cx: W * 0.47, cy: H * 0.95, rx: W * 0.36, ry: H * 0.62 };
    construir();
    despertar();
  }

  const cohete = (u) => {
    const p = [[0.6, -0.04], [0.74, 0.04], [0.83, 0.15], [0.85, 0.3]]; const m = 1 - u; const b = [m * m * m, 3 * m * m * u, 3 * m * u * u, u * u * u];
    return [b.reduce((s, k, i) => s + k * p[i][0], 0) * W, b.reduce((s, k, i) => s + k * p[i][1], 0) * H];
  };

  function dibujar(t) {
    const quieto = op.quieto();
    if (!quieto && t - lastT < 32) { raf = requestAnimationFrame(dibujar); return; }
    lastT = t; const T = quieto ? 0 : t / 1000;
    ctx.drawImage(stat, 0, 0, W, H);
    if (L) {
      tw.forEach((s) => {
        const a = 0.2 + 0.8 * (0.5 + 0.5 * Math.sin(T * s.s + s.p)); const k = s.r * (s.big ? 3.2 : 1.6) * a;
        ctx.fillStyle = "rgba(106,92,196," + (0.25 + a * 0.5) + ")"; ctx.beginPath(); ctx.moveTo(s.x, s.y - k);
        ctx.quadraticCurveTo(s.x, s.y, s.x + k, s.y); ctx.quadraticCurveTo(s.x, s.y, s.x, s.y + k); ctx.quadraticCurveTo(s.x, s.y, s.x - k, s.y);
        ctx.quadraticCurveTo(s.x, s.y, s.x, s.y - k); ctx.fill();
      });
      L.planets.forEach((p) => {
        const ang = Math.PI + ((p.a + T * p.sp) % 1) * (Math.PI / 2) * 1.0; const x = L.sx + Math.cos(ang) * p.orb, y = L.sy + Math.sin(ang) * p.orb;
        ctx.beginPath(); ctx.arc(x + 2, y + 3, p.r, 0, 7); ctx.fillStyle = "rgba(80,70,170,0.12)"; ctx.fill();
        const g = ctx.createRadialGradient(x - p.r * 0.4, y - p.r * 0.4, 0, x, y, p.r); g.addColorStop(0, "#ffffff"); g.addColorStop(1, p.col);
        ctx.beginPath(); ctx.arc(x, y, p.r, 0, 7); ctx.fillStyle = g; ctx.fill();
        if (p.ring) { ctx.beginPath(); ctx.ellipse(x, y, p.r * 2, p.r * 0.55, -0.4, 0, 7); ctx.strokeStyle = "rgba(106,92,196,0.55)"; ctx.lineWidth = 1.4; ctx.stroke(); }
      });
      const cyc = 18, q = quieto ? 0.5 : (T % cyc) / cyc; const ox = W * (0.05 + q * 0.75), oy = H * (0.42 - Math.sin(q * Math.PI) * 0.22);
      const al = Math.min(1, q * 8, (1 - q) * 8);
      ctx.save(); ctx.globalAlpha = al;
      for (let i = 1; i <= 28; i++) {
        const qq = Math.max(0, q - i * 0.006); const tx = W * (0.05 + qq * 0.75), ty = H * (0.42 - Math.sin(qq * Math.PI) * 0.22);
        ctx.beginPath(); ctx.arc(tx, ty, 2.6 * (1 - i / 28), 0, 7); ctx.fillStyle = "rgba(240,150,190," + (0.5 * (1 - i / 28)) + ")"; ctx.fill();
      }
      const nx = W * (0.05 + Math.min(1, q + 0.004) * 0.75), ny = H * (0.42 - Math.sin(Math.min(1, q + 0.004) * Math.PI) * 0.22);
      ctx.translate(ox, oy); ctx.rotate(Math.atan2(ny - oy, nx - ox));
      ctx.beginPath(); ctx.moveTo(14, 0); ctx.bezierCurveTo(10, -5, 2, -5, -12, -4); ctx.lineTo(-12, 4); ctx.bezierCurveTo(2, 5, 10, 5, 14, 0); ctx.fillStyle = "#4a3f99"; ctx.fill();
      ctx.beginPath(); ctx.moveTo(-6, -4); ctx.lineTo(-14, -9); ctx.lineTo(-12, -4); ctx.closePath(); ctx.moveTo(-6, 4); ctx.lineTo(-14, 9); ctx.lineTo(-12, 4); ctx.closePath();
      ctx.fillStyle = "#8a7ed6"; ctx.fill();
      ctx.beginPath(); ctx.arc(4, 0, 1.8, 0, 7); ctx.fillStyle = "#ffd9a8"; ctx.fill(); ctx.restore();
      raf = quieto ? null : requestAnimationFrame(dibujar); return;
    }
    tw.forEach((s) => {
      const a = 0.25 + 0.75 * (0.5 + 0.5 * Math.sin(T * s.s + s.p)); ctx.beginPath(); ctx.arc(s.x, s.y, s.r, 0, 7); ctx.fillStyle = "rgba(244,246,255," + a + ")"; ctx.fill();
      if (s.big) {
        ctx.strokeStyle = "rgba(200,210,255," + a * 0.35 + ")"; ctx.lineWidth = 0.6; ctx.beginPath();
        ctx.moveTo(s.x - 6 * a, s.y); ctx.lineTo(s.x + 6 * a, s.y); ctx.moveTo(s.x, s.y - 6 * a); ctx.lineTo(s.x, s.y + 6 * a); ctx.stroke();
      }
    });
    dots.forEach((d) => {
      const ang = d.a + T * d.sp; const x = A.cx + Math.cos(ang) * A.rx * d.k, y = A.cy + Math.sin(ang) * A.ry * d.k;
      if (y > H * 0.9 || x < 0 || x > W) return; ctx.beginPath(); ctx.arc(x, y, 1.4, 0, 7); ctx.fillStyle = "rgba(170,205,255,0.8)"; ctx.fill();
    });
    const { cx, cy, R } = E; const pul = 0.5 + 0.5 * Math.sin(T * 0.5);
    ctx.beginPath(); ctx.arc(cx, cy, R + 3, Math.PI * 1.1, Math.PI * 1.9); ctx.strokeStyle = "rgba(69,143,255," + (0.1 + 0.12 * pul) + ")"; ctx.lineWidth = 10;
    ctx.shadowColor = "rgba(69,143,255,0.9)"; ctx.shadowBlur = 24; ctx.stroke(); ctx.shadowBlur = 0;
    const cyc = 26, ph = quieto ? 1 : Math.min(1, ((T % cyc) / 20)); const fade = quieto ? 1 : Math.min(1, (T % cyc) / 1.5, Math.max(0, (cyc - (T % cyc)) / 2.5));
    const u1 = 0.35 + ph * 0.65, u0 = Math.max(0, u1 - 0.55);
    const N = 60; let prev = cohete(u0);
    for (let i = 1; i <= N; i++) {
      const u = u0 + (u1 - u0) * (i / N); const p = cohete(u); const f = i / N;
      const col = f > 0.75 ? [255, 150, 80] : f > 0.45 ? [235, 105, 165] : [128, 102, 217];
      ctx.beginPath(); ctx.moveTo(prev[0], prev[1]); ctx.lineTo(p[0], p[1]); ctx.strokeStyle = "rgba(" + col.join(",") + "," + (f * f * 0.75 * fade) + ")";
      ctx.lineWidth = 0.6 + f * 3.2; ctx.lineCap = "round"; ctx.shadowColor = "rgba(" + col.join(",") + ",0.9)"; ctx.shadowBlur = 8 * f; ctx.stroke(); prev = p;
    }
    ctx.shadowBlur = 0;
    const [x, y] = cohete(u1), [x2, y2] = cohete(Math.min(1, u1 + 0.004)); const ang = Math.atan2(y2 - y, x2 - x) || 1.4;
    const gw = ctx.createRadialGradient(x, y, 0, x, y, 34); gw.addColorStop(0, "rgba(255,170,110," + 0.4 * fade + ")"); gw.addColorStop(1, "rgba(255,170,110,0)");
    ctx.fillStyle = gw; ctx.fillRect(x - 34, y - 34, 68, 68);
    ctx.save(); ctx.translate(x, y); ctx.rotate(ang); ctx.globalAlpha = fade;
    ctx.beginPath(); ctx.moveTo(-15, 0); ctx.lineTo(-26, -3); ctx.lineTo(-30, 0); ctx.lineTo(-26, 3); ctx.closePath(); ctx.fillStyle = "rgba(255,190,120,0.9)"; ctx.fill();
    ctx.beginPath(); ctx.moveTo(14, 0); ctx.bezierCurveTo(10, -5, 2, -5, -12, -4); ctx.lineTo(-12, 4); ctx.bezierCurveTo(2, 5, 10, 5, 14, 0); ctx.closePath();
    const bd = ctx.createLinearGradient(0, -5, 0, 5); bd.addColorStop(0, "#F4F6FF"); bd.addColorStop(1, "#8f9ab8"); ctx.fillStyle = bd; ctx.fill();
    ctx.beginPath(); ctx.moveTo(-6, -4); ctx.lineTo(-14, -9); ctx.lineTo(-12, -4); ctx.closePath(); ctx.moveTo(-6, 4); ctx.lineTo(-14, 9); ctx.lineTo(-12, 4); ctx.closePath();
    ctx.fillStyle = "#c4cbe0"; ctx.fill();
    ctx.beginPath(); ctx.arc(4, 0, 1.8, 0, 7); ctx.fillStyle = "#458FFF"; ctx.fill(); ctx.restore();
    raf = quieto ? null : requestAnimationFrame(dibujar);
  }

  function despertar() {
    if (!raf && ctx) raf = requestAnimationFrame(dibujar);
  }

  function iniciar(canvas, opciones) {
    cv = canvas; op = opciones; ctx = cv.getContext("2d");
    window.addEventListener("resize", medir);
    medir();
  }

  window.Fondo = { iniciar, reconstruir: () => { if (ctx) medir(); }, despertar };
})();
