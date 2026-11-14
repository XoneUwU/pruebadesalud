"""Prueba del módulo de visión con señales sintéticas (no necesita cámara ni MQTT).

  python vision/pruebas_vision.py

- Un pulso de 72 lpm metido en el RGB de la piel (con horas irregulares, cambios de luz, ruido y huecos sin cara)
  tiene que dar 72 ± 3 lpm; también 55 y 110. Solo ruido tiene que dar calidad baja (sin número).
- Un EAR con parpadeos conocidos tiene que contarlos bien (los de 1 cuadro no cuentan) y dar el PERCLOS esperado.
- Avisos de luz, cara, fps y pulso; regiones de la cara; la ventana se dibuja sin errores.
Muestra OK o FALLA por cada caso y termina con código 1 si alguno falla.
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import vision as v  # noqa: E402

fallas = 0
total = 0


def revisar(ok, texto, detalle=""):
    global fallas, total
    total += 1
    fallas += not ok
    print(f"{'OK   ' if ok else 'FALLA'}  {texto}")
    if not ok and detalle:
        print(f"       {detalle}")


def horas(segundos=60.0, fps=30.0, semilla=0):
    """Horas de cuadro irregulares, como las de una cámara real."""
    rng = np.random.default_rng(semilla)
    dt = np.clip(1 / fps + rng.normal(0, 0.004, int(segundos * fps * 1.1)), 0.02, None)
    t = np.cumsum(dt)
    return t[t <= segundos]


def piel(lpm, segundos=60.0, semilla=0, amplitud=0.004, ruido=0.5):
    """RGB de la piel con un pulso de `lpm` (firma del volumen sanguíneo), cambios de luz, ruido y huecos."""
    rng = np.random.default_rng(semilla + 1)
    t = horas(segundos, semilla=semilla)
    f = lpm / 60
    pulso = np.sin(2 * np.pi * f * t) + 0.3 * np.sin(2 * np.pi * 2 * f * t + 0.6)
    luz = 1 + 0.06 * np.sin(2 * np.pi * 0.07 * t) + 0.02 * np.sin(2 * np.pi * 0.4 * t + 1)
    firma = np.array([0.33, 0.77, 0.53])
    rgb = np.array([180.0, 125.0, 100.0]) * luz[:, None] * (1 + amplitud * firma * pulso[:, None])
    rgb += rng.normal(0, ruido, rgb.shape)
    for inicio in (300, 1100):  # dos huecos de ~1 s sin cara
        rgb[inicio:inicio + 30] = np.nan
    return t, rgb


def main() -> int:
    print("--- pulso (rPPG, POS) ---")
    # Ruido fuerte (0,5 niveles por cuadro, unas 10 veces más que el del promedio de una región real): la
    # frecuencia tiene que salir bien aunque la calidad sea baja.
    for lpm, semilla in ((72, 1), (55, 2), (110, 3)):
        t, rgb = piel(lpm, semilla=semilla)
        r = v.estimar_pulso(t, rgb)
        revisar(r is not None and abs(r["lpm"] - lpm) <= 3,
                f"con mucho ruido: pulso de {lpm} lpm -> {r['lpm'] if r else None} lpm "
                f"(calidad {r['calidad'] if r else None}, SNR {r['snr_db'] if r else None} dB)")
    # Ruido realista: además, la calidad alcanza para dar el número.
    t, rgb = piel(72, semilla=6, ruido=0.12)
    r = v.estimar_pulso(t, rgb)
    revisar(r is not None and abs(r["lpm"] - 72) <= 3 and r["confiable"],
            f"con ruido realista: 72 lpm -> {r['lpm'] if r else None} lpm, calidad {r['calidad'] if r else None} "
            f"(SNR {r['snr_db'] if r else None} dB): se da el número")
    t, rgb = piel(72, semilla=4, amplitud=0.0, ruido=1.5)  # solo ruido y luz
    r = v.estimar_pulso(t, rgb)
    revisar(r is not None and not r["confiable"], f"solo ruido -> calidad {r['calidad'] if r else None}: sin número")
    revisar(v.estimar_pulso(*piel(72, segundos=4)) is None, "menos de 6 s de datos -> no estima")

    print("\n--- ojos (EAR) ---")
    p1, p4 = np.array([0.0, 0.0]), np.array([10.0, 0.0])
    ojo = np.array([p1, [3, -3], [7, -3], p4, [7, 3], [3, 3]], float)
    revisar(abs(v.ear(ojo) - 0.6) < 1e-9, f"EAR de un ojo de geometría conocida = {v.ear(ojo):.3f} (esperado 0,600)")

    rng = np.random.default_rng(7)
    t = np.arange(0, 60, 1 / 30) + rng.normal(0, 0.002, 1800)
    ears = 0.30 + rng.normal(0, 0.008, len(t))
    parpadeos = [60, 210, 330, 450, 600, 760, 900, 1020, 1300, 1420, 1650, 1740]  # 12, uno dentro de los primeros 5 s
    for i in parpadeos:
        ears[i:i + 4] = 0.07                          # 4 cuadros cerrados
    for i in (500, 950, 1600):
        ears[i] = 0.12                                # 1 solo cuadro bajo: no es parpadeo
    ears[1200:1245] = 0.05                            # cierre largo de 1,5 s: cuenta como 1 parpadeo
    ears[1500:1560] = np.nan                          # 2 s sin cara
    r = v.analizar_ojos(t, ears)
    cerrados, con_cara = 12 * 4 + 45, 1800 - 60
    revisar(r["parpadeos"] == 13, f"parpadeos: {r['parpadeos']} (esperados 13: 12 + el cierre largo; 3 de 1 cuadro no)")
    revisar(abs(r["perclos"] - cerrados / con_cara) < 0.005,
            f"PERCLOS: {r['perclos']} (esperado {cerrados / con_cara:.3f}; sin contar el tiempo sin cara)")
    revisar(abs(r["ear_abierto"] - 0.30) < 0.01, f"EAR de ojo abierto (mediana de 5 s): {r['ear_abierto']}")
    revisar(abs(r["parpadeos_min"] - 13 / (con_cara / 30 / 60)) < 0.2, f"parpadeos por minuto: {r['parpadeos_min']}")
    # Mirar hacia abajo 4 s: la cabeza se inclina 25 grados y el EAR baja como si el ojo se cerrara.
    t2 = np.arange(0, 60, 1 / 30)
    e2 = 0.30 + rng.normal(0, 0.006, len(t2))
    incl = 5 + rng.normal(0, 1, len(t2))
    abajo = (t2 >= 30) & (t2 < 34)
    e2[abajo], incl[abajo] = 0.06, 30
    con_incl, sin_incl = v.analizar_ojos(t2, e2, incl), v.analizar_ojos(t2, e2)
    revisar(con_incl["perclos"] < 0.01 and sin_incl["perclos"] > 0.06 and abs(con_incl["cabeza_inclinada_pct"] - 6.7) < 0.5,
            f"mirar abajo 4 s con la cabeza inclinada: PERCLOS {con_incl['perclos']} (sin descontarlo sería "
            f"{sin_incl['perclos']}); cabeza inclinada {con_incl['cabeza_inclinada_pct']} %")
    cierre = (t2 >= 40) & (t2 < 42)
    e2b = e2.copy()
    e2b[cierre] = 0.05  # ojos cerrados 2 s SIN mover la cabeza: sí cuenta
    revisar(v.analizar_ojos(t2, e2b, incl)["perclos"] > 0.03, "un cierre real (sin mover la cabeza) sí cuenta para el PERCLOS")

    print("\n--- boca (bostezos) ---")
    rng = np.random.default_rng(9)
    t = np.arange(0, 60, 1 / 30)
    mares = 0.03 + np.abs(rng.normal(0, 0.01, len(t)))
    habla = (t >= 10) & (t < 16)
    mares[habla] = 0.27 + 0.18 * np.sin(2 * np.pi * 4 * t[habla])   # hablar: abre y cierra, nunca 1,5 s seguido
    mares[(t >= 20) & (t < 20.6)] = 0.75                             # boca muy abierta 0,6 s: no es bostezo
    for inicio in (30.0, 45.0):                                       # dos bostezos de 3 s (sube, se mantiene, baja)
        en = (t >= inicio) & (t < inicio + 3)
        mares[en] = 0.5 + 0.4 * np.sin(np.pi * (t[en] - inicio) / 3)
    r = v.analizar_boca(t, mares)
    revisar(r["bostezos"] == 2, f"bostezos: {r['bostezos']} (esperados 2; hablar y abrir la boca 0,6 s no cuentan)")
    revisar(abs(r["bostezos_min"] - 2.0) < 0.1, f"bostezos por minuto: {r['bostezos_min']}")
    pts = np.zeros((478, 2))
    pts[78], pts[308] = (100, 200), (160, 200)
    for (a, b), d in zip(v.BOCA_VERTICAL, (30, 24, 24)):
        pts[a], pts[b] = (130, 200 - d / 2), (130, 200 + d / 2)
    revisar(abs(v.mar(pts) - 26 / 60) < 1e-9, f"MAR de una boca de geometría conocida = {v.mar(pts):.3f} (esperado 0,433)")
    reg = v.Registro()  # al bostezar se achican los ojos: no tiene que contar como parpadeo
    reg.t = list(t)
    reg.rgb = [[np.nan] * 3] * len(t)
    reg.mar = list(mares)
    ears_b = 0.30 + rng.normal(0, 0.005, len(t))
    for inicio in (30.0, 45.0):
        ears_b[(t >= inicio + 0.5) & (t < inicio + 2.5)] = 0.10
    reg.ear = list(ears_b)
    res = reg.resultado()
    revisar(res["bostezos"] == 2 and res["parpadeos"] == 0 and res["perclos"] == 0,
            f"ojos achicados durante los bostezos: {res['parpadeos']} parpadeos y PERCLOS {res['perclos']} (esperados 0)")

    print("\n--- avisos ---")
    reg = v.Registro()
    t, rgb = piel(72, semilla=5, amplitud=0.0, ruido=1.5)
    t10 = t[::3]  # ~10 cuadros por segundo
    reg.t, reg.rgb = list(t10), [list(x) for x in rgb[::3]]
    reg.ear = [np.nan if i % 3 == 0 else 0.3 for i in range(len(t10))]  # ~33 % sin cara
    reg.brillo, reg.saturado = [40.0] * len(t10), [0.0] * len(t10)
    res = reg.resultado()
    textos = " ".join(res["avisos"])
    revisar(all(x in textos for x in ("Poca luz", "No se vio la cara", "cuadros por segundo", "no es confiable"))
            and res["pulso_rppg_lpm"] is None,
            f"poca luz, cara perdida, pocos fps y pulso dudoso: {len(res['avisos'])} avisos, sin número de pulso")
    reg.brillo, reg.saturado = [230.0] * len(t10), [0.2] * len(t10)
    revisar("Demasiada luz" in " ".join(reg.resultado()["avisos"]), "demasiada luz o reflejos")

    print("\n--- cámara ---")
    verde = np.zeros((480, 640, 3), np.uint8)
    verde[:, :, 1] = 135                                  # el verde liso de una cámara virtual sin video
    negro = np.zeros((480, 640, 3), np.uint8)
    real = np.random.default_rng(3).integers(40, 200, (480, 640, 3), dtype=np.uint8)
    revisar(v.es_plano(verde) and v.es_plano(negro) and not v.es_plano(real),
            "imagen plana: verde liso y negro sí; una imagen con variación no")
    salida = "List of devices attached\nR5CY73Q2MQA\tdevice\nABC123\tunauthorized\n\n"
    revisar(v.leer_dispositivos(salida) == {"R5CY73Q2MQA": "device", "ABC123": "unauthorized"}
            and v.leer_dispositivos("List of devices attached\n\n") == {},
            "adb devices: celular listo, sin permiso y ninguno")
    revisar(v.es_usb("http://127.0.0.1:4747/video") and not v.es_usb("http://192.168.1.50:4747/video")
            and not v.es_usb("0"), "DroidCam por cable = URL en 127.0.0.1; por Wi-Fi o índice, no")

    class CapFalsa:  # entrega un cuadro cada 20 ms
        def __init__(self):
            self.n = 0

        def read(self):
            import time as _t
            _t.sleep(0.02)
            self.n += 1
            return True, np.full((4, 4, 3), self.n % 255, np.uint8)

        def release(self):
            pass

    cam = v.Camara(CapFalsa())
    horas_vistas = []
    for _ in range(10):
        c, t_c = cam.siguiente(espera=1)
        horas_vistas.append(t_c)
    cam.cerrar()
    revisar(all(b > a for a, b in zip(horas_vistas, horas_vistas[1:])),
            "el hilo de lectura entrega cuadros nuevos con horas crecientes")

    print("\n--- regiones y ventana ---")
    pts = np.zeros((478, 2))
    pts[:] = (320, 260)
    pts[33], pts[263] = (250, 230), (390, 230)       # rabillos de los ojos
    pts[105], pts[334], pts[66], pts[296] = (270, 200), (370, 200), (290, 205), (350, 205)  # cejas
    pts[61], pts[291] = (280, 340), (360, 340)       # comisuras
    cajas = v.regiones(pts, 640, 480)
    frente, mej1, mej2 = cajas if len(cajas) == 3 else (None, None, None)
    revisar(len(cajas) == 3 and frente[3] < 200 and mej1[1] > 230 and mej2[1] > 230
            and all(0 <= x0 < x1 <= 640 and 0 <= y0 < y1 <= 480 for x0, y0, x1, y1 in cajas),
            f"frente sobre las cejas y mejillas bajo los ojos: {cajas}")
    from mediapipe.tasks.python import vision as mpv
    conexiones = np.array([(c.start, c.end) for c in mpv.FaceLandmarksConnections.FACE_LANDMARKS_TESSELATION])
    cuadro = np.full((480, 640, 3), 90, np.uint8)
    try:
        info = {"pulso": {"lpm": 72.0, "calidad": 0.8, "confiable": True}, "ear": 0.29, "parpadeos": 4,
                "quedan": 42, "progreso": 0.3, "avisos": ["POCA LUZ: acerquen una lampara de frente"]}
        v.dibujar(cuadro, pts, conexiones, info)
        v.dibujar(cuadro, None, conexiones, {"pulso": None, "ear": float("nan"), "quedan": None})
        ok = True
    except Exception as e:  # noqa: BLE001
        ok, info = False, e
    revisar(ok, "la ventana se dibuja (malla, regiones, panel, avisos y sin cara)", str(info))

    print(f"\n{total - fallas} de {total} pasaron.")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
