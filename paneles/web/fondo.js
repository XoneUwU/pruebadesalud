/* Fondo animado de la estación (del diseño «Apto Hoy» de Claude Design), dibujado en un <canvas> fijo:
 * oscuro = la Tierra de noche con su atmósfera, estrellas, una órbita y un cohete; claro = un sistema solar en
 * cielo claro y paisaje lunar exportado de Claude Design. Fondo.iniciar(canvas, {claro: () => bool, quieto: () => bool});
 * Fondo.reconstruir() al cambiar el tema y Fondo.despertar() al quitar «reducir movimiento». */
(function () {
  "use strict";

  let ctx = null, cv = null, op = null;
  let moonImg = null;
  let W = 0, H = 0, E = null, A = null, stat = null, tw = [], dots = [], L = null, raf = null, lastT = 0;
  let seed = 4;
  const rnd = (a, b) => a + ((seed = (seed * 16807) % 2147483647) / 2147483647) * (b - a);
  const dpr = Math.min(1.5, window.devicePixelRatio || 1);

  function construirClaro() {
seed = 9; stat = document.createElement("canvas"); stat.width = W * dpr; stat.height = H * dpr; const c = stat.getContext("2d"); c.setTransform(dpr, 0, 0, dpr, 0, 0);
      const g0 = c.createLinearGradient(0, 0, 0, H); [[0, "#eef2fb"], [0.45, "#f8f9fd"], [1, "#ffffff"]].forEach(([o, k]) => g0.addColorStop(o, k)); c.fillStyle = g0; c.fillRect(0, 0, W, H);
      [[0.85, 0.12, 0.45, "rgba(69,110,200,0.07)"], [0.1, 0.35, 0.4, "rgba(128,102,217,0.05)"]].forEach(([x, y, r, col]) => { const g = c.createRadialGradient(x * W, y * H, 0, x * W, y * H, r * Math.max(W, H)); g.addColorStop(0, col); g.addColorStop(1, "rgba(255,255,255,0)"); c.fillStyle = g; c.fillRect(0, 0, W, H); });
      for (let i = 0; i < 90; i++) { c.beginPath(); c.arc(rnd(0, W), rnd(0, H * 0.75), rnd(0.5, 1.2), 0, 7); c.fillStyle = "rgba(15,42,92," + rnd(0.15, 0.45) + ")"; c.fill(); }
      const img = moonImg; const ok = img && img.complete && img.naturalWidth;
      const sy = 1160, sh = 1448 - sy; const scale = Math.max(W / 1086, (H * 0.2) / sh); const dw = 1086 * scale, dh = sh * scale; const dx = (W - dw) / 2, dy = H - Math.min(dh, Math.max(120, H * 0.22) + (1180 - sy) * scale);
      const half = W / 2, sag = Math.max(8, 48 * scale * Math.min(1, W / dw)); const R = (half * half + sag * sag) / (2 * sag); const top = dy + (1180 - sy) * scale;
      L = { moon: null, top, R, cx: W / 2, cy: top + R };
      if (ok) {
        c.save(); c.globalCompositeOperation = "multiply"; c.globalAlpha = 0.55; c.drawImage(img, 0, sy, 1086, sh, dx, dy, dw, dh); c.restore();
        const by = Math.max(0, Math.floor(top - 4)), bh = Math.ceil(H - by); const m = document.createElement("canvas"); m.width = Math.ceil(W * dpr); m.height = Math.ceil(bh * dpr); const mc = m.getContext("2d");
        mc.drawImage(stat, 0, by * dpr, W * dpr, bh * dpr, 0, 0, W * dpr, bh * dpr);
        mc.globalCompositeOperation = "destination-in"; mc.setTransform(dpr, 0, 0, dpr, 0, 0); mc.beginPath(); mc.arc(W / 2, top + R - by, R, 0, Math.PI * 2); mc.fill();
        L.moon = m; L.by = by; L.bh = bh;
      }
      const base = [[121, 252, 15], [785, 179, 13], [976, 452, 22], [894, 1046, 13], [355, 209, 0], [1005, 73, 0], [66, 675, 0], [986, 834, 0]];
      L.sparks = base.map(([x, y, s]) => ({ x: (x / 1086) * W, y: Math.min((y / 1448) * H * 1.05, top - 40), s, p: rnd(0, 6.28), sp: rnd(0.4, 0.9) }))
        .concat(Array.from({ length: 10 }, () => ({ x: rnd(0, W), y: rnd(20, top - 60), s: rnd(0, 1) < 0.5 ? rnd(6, 10) : 0, p: rnd(0, 6.28), sp: rnd(0.3, 0.8) })));
      const sp = L.sparks.filter((q) => q.s > 0); L.lines = [[sp[0], sp[1]], [sp[1], sp[2]], [sp[2], sp[3]]].filter((l) => l[0] && l[1]);
      tw = [];
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
    // Con la ventana en 0 × 0 (pestaña recién abierta u oculta) los cálculos dan Infinity y el canvas lanza una
    // excepción que corta el arranque de la estación: se espera al siguiente cuadro.
    if (!window.innerWidth || !window.innerHeight) { stat = null; requestAnimationFrame(medir); return; }
    W = window.innerWidth; H = window.innerHeight; cv.width = W * dpr; cv.height = H * dpr; ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const R = Math.max(W * 0.9, (0.25 * W * W) / (0.2 * H)); E = { cx: W * 0.52, cy: H * 0.905 + R, R };
    A = { cx: W * 0.47, cy: H * 0.95, rx: W * 0.36, ry: H * 0.62 };
    construir();
    if (raf !== null) { cancelAnimationFrame(raf); raf = null; }
    despertar();
  }

  const cohete = (u) => {
    const p = [[0.6, -0.04], [0.74, 0.04], [0.83, 0.15], [0.85, 0.3]]; const m = 1 - u; const b = [m * m * m, 3 * m * m * u, 3 * m * u * u, u * u * u];
    return [b.reduce((s, k, i) => s + k * p[i][0], 0) * W, b.reduce((s, k, i) => s + k * p[i][1], 0) * H];
  };

  function dibujar(t) {
    const quieto = op.quieto();
    if (!quieto && t - lastT < (L ? 50 : 32)) { raf = requestAnimationFrame(dibujar); return; }
    if (!stat || !stat.width || !stat.height) { raf = requestAnimationFrame(dibujar); return; }
    lastT = t; const T = quieto ? 0 : t / 1000;
    ctx.drawImage(stat, 0, 0, W, H);
      if (L) {
        const NAVY = "15,42,92";
        const star = (x, y, k, rot, al) => { ctx.save(); ctx.translate(x, y); ctx.rotate(rot); ctx.fillStyle = "rgba(" + NAVY + "," + al + ")"; ctx.beginPath(); ctx.moveTo(0, -k); ctx.quadraticCurveTo(k * 0.12, -k * 0.12, k * 0.62, 0); ctx.quadraticCurveTo(k * 0.12, k * 0.12, 0, k); ctx.quadraticCurveTo(-k * 0.12, k * 0.12, -k * 0.62, 0); ctx.quadraticCurveTo(-k * 0.12, -k * 0.12, 0, -k); ctx.fill(); ctx.restore(); };
        // constellation lines draw in and out
        const cl = quieto ? 1 : 0.5 - 0.5 * Math.cos(T * 0.12);
        L.lines.forEach(([p, q]) => { ctx.beginPath(); ctx.moveTo(p.x, p.y); ctx.lineTo(p.x + (q.x - p.x) * cl, p.y + (q.y - p.y) * cl); ctx.strokeStyle = "rgba(" + NAVY + ",0.14)"; ctx.setLineDash([2, 5]); ctx.lineWidth = 1; ctx.stroke(); });
        ctx.setLineDash([]);
        L.sparks.forEach((s) => { const a = 0.5 + 0.5 * Math.sin(T * s.sp + s.p);
          if (s.s) { star(s.x, s.y, s.s * (0.75 + 0.3 * a), Math.sin(T * 0.2 + s.p) * 0.12, 0.65 + 0.35 * a); if (a > 0.92) { ctx.beginPath(); ctx.arc(s.x, s.y, s.s * 1.4, 0, 7); ctx.fillStyle = "rgba(69,110,200," + (a - 0.92) * 1.5 + ")"; ctx.fill(); } }
          else { ctx.beginPath(); ctx.arc(s.x, s.y, 2 + a * 0.8, 0, 7); ctx.fillStyle = "rgba(" + NAVY + "," + (0.55 + 0.4 * a) + ")"; ctx.fill(); } });
        // satellite crossing with dashed trail
        const sc = 38, sq = quieto ? 0.4 : (T % sc) / sc; const sx = -40 + sq * (W + 80), syy = H * 0.16 + Math.sin(sq * Math.PI) * -H * 0.06;
        ctx.beginPath(); for (let i = 0; i <= 30; i++) { const qq = Math.max(0, sq - i * 0.006); const x = -40 + qq * (W + 80), y = H * 0.16 + Math.sin(qq * Math.PI) * -H * 0.06; i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); }
        ctx.strokeStyle = "rgba(" + NAVY + ",0.18)"; ctx.setLineDash([3, 4]); ctx.stroke(); ctx.setLineDash([]);
        ctx.save(); ctx.translate(sx, syy); ctx.rotate(0.3 + T * 0.15); ctx.fillStyle = "rgba(" + NAVY + ",0.85)"; ctx.fillRect(-3, -3, 6, 6); ctx.fillRect(-15, -2, 9, 4); ctx.fillRect(6, -2, 9, 4); ctx.restore();
        // earthrise behind the lunar horizon
        const ec = 70, eq = quieto ? 0.6 : (T % ec) / ec; const ex = W * 0.2, er = Math.min(46, W * 0.035);
        const hy = L.cy - Math.sqrt(Math.max(0, L.R * L.R - (ex - L.cx) * (ex - L.cx)));
        const ey = hy + er + 6 - Math.min(1, eq / 0.7) * (er * 2 + 70); const ea = Math.min(1, (1 - eq) * 8);
        ctx.save(); ctx.globalAlpha = ea;
        const eg = ctx.createRadialGradient(ex, ey, er, ex, ey, er * 2.2); eg.addColorStop(0, "rgba(69,143,255,0.18)"); eg.addColorStop(1, "rgba(69,143,255,0)"); ctx.fillStyle = eg; ctx.fillRect(ex - er * 2.3, ey - er * 2.3, er * 4.6, er * 4.6);
        ctx.beginPath(); ctx.arc(ex, ey, er, 0, 7); const eb = ctx.createRadialGradient(ex - er * 0.4, ey - er * 0.4, 0, ex, ey, er); eb.addColorStop(0, "#cfe0fa"); eb.addColorStop(1, "#7f9fd6"); ctx.fillStyle = eb; ctx.fill();
        ctx.save(); ctx.beginPath(); ctx.arc(ex, ey, er, 0, 7); ctx.clip(); ctx.fillStyle = "rgba(" + NAVY + ",0.45)"; const rot = (T * 3) % (er * 4);
        [[-0.5, -0.3, 0.42, 0.3], [0.15, 0.25, 0.3, 0.4], [0.5, -0.4, 0.22, 0.18]].forEach(([u, v, rx, ry]) => { for (const off of [0, er * 4]) { ctx.beginPath(); ctx.ellipse(ex + u * er + rot - off * 0.5, ey + v * er, rx * er, ry * er, 0.4, 0, 7); ctx.fill(); } });
        const sh = ctx.createLinearGradient(ex - er, 0, ex + er, 0); sh.addColorStop(0.45, "rgba(15,42,92,0)"); sh.addColorStop(1, "rgba(15,42,92,0.55)"); ctx.fillStyle = sh; ctx.fillRect(ex - er, ey - er, er * 2, er * 2); ctx.restore();
        ctx.beginPath(); ctx.arc(ex, ey, er, 0, 7); ctx.strokeStyle = "rgba(" + NAVY + ",0.7)"; ctx.lineWidth = 1.2; ctx.stroke(); ctx.restore();
        // lunar lander descending
        const lc = 30, lq = quieto ? 0.5 : (T % lc) / lc; const lx = W * 0.72; const lhy = L.cy - Math.sqrt(Math.max(0, L.R * L.R - (lx - L.cx) * (lx - L.cx)));
        const dq = Math.min(1, lq / 0.75); const ease = 1 - Math.pow(1 - dq, 2.4); const ly = -30 + ease * (lhy - 14 + 30); const la = Math.min(1, lq * 10, (1 - lq) * 6);
        ctx.save(); ctx.globalAlpha = la; ctx.translate(lx, ly);
        if (dq < 1) { const fl = 8 + 6 * Math.sin(T * 30); const fg = ctx.createLinearGradient(0, 8, 0, 8 + fl * 2); fg.addColorStop(0, "rgba(255,150,80,0.85)"); fg.addColorStop(1, "rgba(255,150,80,0)"); ctx.fillStyle = fg; ctx.beginPath(); ctx.moveTo(-3, 8); ctx.lineTo(0, 8 + fl * 2); ctx.lineTo(3, 8); ctx.fill(); }
        ctx.fillStyle = "rgba(" + NAVY + ",0.92)"; ctx.beginPath(); ctx.moveTo(0, -12); ctx.lineTo(6, -4); ctx.lineTo(6, 6); ctx.lineTo(-6, 6); ctx.lineTo(-6, -4); ctx.closePath(); ctx.fill();
        ctx.fillRect(-4, 6, 8, 3); ctx.strokeStyle = "rgba(" + NAVY + ",0.92)"; ctx.lineWidth = 1.3; ctx.beginPath(); ctx.moveTo(-5, 6); ctx.lineTo(-10, 14); ctx.moveTo(5, 6); ctx.lineTo(10, 14); ctx.moveTo(-12, 14); ctx.lineTo(-8, 14); ctx.moveTo(8, 14); ctx.lineTo(12, 14); ctx.stroke();
        ctx.beginPath(); ctx.arc(0, -3, 2.2, 0, 7); ctx.fillStyle = "#cfe0fa"; ctx.fill(); ctx.restore();
        if (dq > 0.9 && dq <= 1) { const pd = lq < 0.75 ? (dq - 0.9) / 0.1 : 1 + (lq - 0.75) * 4; ctx.beginPath(); ctx.ellipse(lx, lhy + 1, 10 + pd * 28, 2 + pd * 5, 0, 0, 7); ctx.fillStyle = "rgba(120,135,170," + Math.max(0, 0.35 - pd * 0.18) * la + ")"; ctx.fill(); }
        // shooting star (navy)
        const ss = 14, sq2 = quieto ? 2 : (T % ss) / 1.1; if (sq2 < 1) { const x0 = W * 0.65, y0 = H * 0.05; const x = x0 - sq2 * W * 0.25, y = y0 + sq2 * H * 0.12; const g = ctx.createLinearGradient(x, y, x + W * 0.06, y - H * 0.03); g.addColorStop(0, "rgba(" + NAVY + "," + (1 - sq2) * 0.7 + ")"); g.addColorStop(1, "rgba(" + NAVY + ",0)"); ctx.strokeStyle = g; ctx.lineWidth = 1.4; ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x + W * 0.06, y - H * 0.03); ctx.stroke(); }
        if (L.moon && L.moon.width && L.moon.height && L.bh > 0) { ctx.drawImage(L.moon, 0, L.by, W, L.bh);
          const glint = quieto ? 0.5 : (T * 0.03) % 1.4 - 0.2; const gg = ctx.createLinearGradient((glint - 0.15) * W, 0, (glint + 0.15) * W, 0); gg.addColorStop(0, "rgba(255,255,255,0)"); gg.addColorStop(0.5, "rgba(255,255,255,0.14)"); gg.addColorStop(1, "rgba(255,255,255,0)"); ctx.fillStyle = gg; ctx.fillRect(Math.max(0, (glint - 0.15) * W), L.top, 0.3 * W, H - L.top); }
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
    moonImg = new Image();
    moonImg.onload = () => { if (ctx && op.claro()) medir(); };
    moonImg.onerror = () => { console.warn("[Becspace] No se pudo cargar assets/fondo-luna.png"); };
    moonImg.src = "assets/fondo-luna.png";
    window.addEventListener("resize", medir);
    medir();
  }

  window.Fondo = { iniciar, reconstruir: () => { if (ctx) medir(); }, despertar };
})();
