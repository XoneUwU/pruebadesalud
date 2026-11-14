"""Prueba del módulo de visión con señales sintéticas (no necesita cámara ni MQTT).

  python vision/pruebas_vision.py

- Un pulso de 72 lpm metido en el RGB de la piel (con horas irregulares, cambios de luz, ruido y huecos sin cara)
  tiene que dar 72 ± 3 lpm; también 55 y 110. Solo ruido tiene que dar calidad baja (sin número).
- Un EAR con parpadeos conocidos tiene que contarlos bien (los de 1 cuadro no cuentan) y dar el PERCLOS esperado.
- Bostezos tapados con la mano: boca abierta y ojos entrecerrados antes de la mano, o mandíbula que baja con la mano
  encima; la tos, la mano quieta y la mano en el mentón al hablar no cuentan; uno visto y tapado cuenta una vez.
- Lentes: el puente de la montura sube el puntaje (también con la cabeza ladeada); piel lisa o una sombra suave no.
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
    # Guiños: cerrar un solo ojo no es parpadeo ni cierre; los dos a la vez, sí.
    t3 = np.arange(0, 60, 1 / 30)
    der = 0.30 + rng.normal(0, 0.006, len(t3))
    izq = 0.30 + rng.normal(0, 0.006, len(t3))
    for i in (300, 600, 900, 1200):          # 4 guiños de 0,13 s con el ojo derecho
        der[i:i + 4] = 0.05
    izq[1400:1460] = 0.04                     # guiño largo de 2 s con el izquierdo
    for i in (450, 1050, 1650):              # 3 parpadeos de verdad: los dos ojos
        der[i:i + 4], izq[i:i + 4] = 0.06, 0.06
    reg = v.Registro()
    reg.t, reg.rgb = list(t3), [[np.nan] * 3] * len(t3)
    reg.ear_der, reg.ear_izq = list(der), list(izq)
    reg.ear, reg.mar = list((der + izq) / 2), [0.05] * len(t3)
    res = reg.resultado()
    con_promedio = v.analizar_ojos(t3, (der + izq) / 2)
    revisar(res["parpadeos"] == 3 and res["perclos"] < 0.01,
            f"guiños con un ojo no cuentan: {res['parpadeos']} parpadeos (esperados 3) y PERCLOS {res['perclos']} "
            f"(con el promedio de los dos ojos daban {con_promedio['parpadeos']} parpadeos)")

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

    print("\n--- bostezos tapados con la mano ---")
    cara = np.zeros((478, 2))
    for i, xy in {33: (250, 200), 263: (390, 200), 61: (285, 300), 291: (355, 300), 1: (320, 260), 152: (320, 360),
                  168: (320, 190)}.items():
        cara[i] = xy
    zona = v.zona_boca(cara)
    mano_boca = np.column_stack([np.linspace(270, 370, 21), np.linspace(280, 330, 21)])  # palma sobre la boca
    mano_frente = mano_boca - [0, 180]
    tres = np.vstack([mano_frente[:18], [[320, 300]] * 3])                         # solo 3 puntos en la zona
    revisar(v.mano_en_boca(zona, [mano_boca]) and not v.mano_en_boca(zona, [mano_frente])
            and not v.mano_en_boca(zona, [tres]) and v.mano_en_boca(zona, [mano_frente, mano_boca]),
            "mano en la boca: palma sobre la boca sí; en la frente o con 3 puntos no; con 2 manos basta una")
    revisar(abs(v.mandibula(cara) - 170 / 140) < 1e-9, f"mandíbula = raíz de la nariz al mentón / ojos = {v.mandibula(cara):.3f}")

    rng = np.random.default_rng(11)
    t = np.arange(0, 110, 1 / 30)
    en = lambda a, b: (t >= a) & (t < b)  # noqa: E731
    mares = 0.05 + np.abs(rng.normal(0, 0.01, len(t)))
    ears_m = 0.30 + rng.normal(0, 0.006, len(t))
    mand = 1.05 + rng.normal(0, 0.005, len(t))
    manos = np.zeros(len(t))
    # A (10 s): abre la boca (0,55) y entrecierra los ojos; después llega la mano. Con la mano encima el MAR no sirve.
    mares[en(9.2, 10.0)], ears_m[en(9.5, 11.0)], manos[en(10.0, 12.5)] = 0.55, 0.16, 1
    mares[en(10.0, 12.5)] = 0.10
    # B (25 s): la mano tapa ANTES de que se vea la boca; la mandíbula baja (+19 %) y los ojos se entrecierran.
    manos[en(25.0, 28.5)], mand[en(26.0, 27.5)], ears_m[en(26.0, 27.5)] = 1, 1.25, 0.16
    # E (33 s): tos tapada: la boca se abre 0,15 s y los ojos se aprietan 0,6 s; no es bostezo.
    mares[en(32.9, 33.05)], manos[en(33.05, 34.3)], ears_m[en(33.0, 33.6)] = 0.6, 1, 0.16
    # C (40 s): mano quieta en la boca, pensando: no es bostezo.
    manos[en(40.0, 45.0)] = 1
    # D (50 s): mano en el mentón mientras habla: la mandíbula sube y baja rápido; los ojos, normales.
    manos[en(50.0, 55.0)] = 1
    mand[en(50.0, 55.0)] = 1.05 + 0.15 * np.abs(np.sin(2 * np.pi * 3 * t[en(50.0, 55.0)]))
    # F (60 s): bostezo con la boca a la vista que a los 2 s se tapa: cuenta una sola vez.
    mares[en(60.0, 63.0)] = 0.5 + 0.4 * np.sin(np.pi * (t[en(60.0, 63.0)] - 60) / 3)
    ears_m[en(60.5, 63.0)], manos[en(62.0, 64.0)] = 0.16, 1
    mares[en(62.0, 64.0)] = 0.10
    # G (66 s): bostezo a la vista, sin mano.
    mares[en(66.0, 69.0)] = 0.5 + 0.4 * np.sin(np.pi * (t[en(66.0, 69.0)] - 66) / 3)
    # H (16 s): alguien que casi no achica los ojos al bostezar: el EAR baja solo al ~82 % del abierto y tiembla
    # alrededor del umbral (con el 75 % y sin suavizar no contaba). La mano tapa primero y la mandíbula baja.
    manos[en(16.0, 19.5)], mand[en(17.0, 18.5)] = 1, 1.22
    ears_m[en(17.0, 18.5)] = 0.245 + rng.normal(0, 0.012, en(17.0, 18.5).sum())
    # Como en las pruebas reales: la mano tapa antes de abrir la boca y, debajo, la malla dibuja la boca cerrada.
    # I (72 s): la mandíbula sube despacio solo +6 a +11 % y los ojos se cierran poco a poco (70 % -> 40 %).
    manos[en(72.0, 78.0)], mares[en(72.0, 78.0)] = 1, 0.01
    mand[en(73.0, 77.0)] = 1.05 * (1.06 + 0.05 * np.sin(np.pi * (t[en(73.0, 77.0)] - 73) / 4))
    ears_m[en(73.0, 77.0)] = np.linspace(0.21, 0.12, en(73.0, 77.0).sum())
    # J (80 s): ojos casi cerrados (10 %) 5 s; la mandíbula apenas se nota (+3 %).
    manos[en(80.0, 87.0)], mares[en(80.0, 87.0)], mand[en(80.0, 87.0)] = 1, 0.01, 1.05 * 1.03
    ears_m[en(81.0, 86.0)] = 0.03
    # K (90 s): mano en la boca 5 s sin bostezar: ojos abiertos y la mandíbula un poco más corta (apoyada).
    manos[en(90.0, 95.0)], mand[en(90.0, 95.0)] = 1, 1.05 * 0.97
    # D2 (100 s): habla y sonríe con la mano en el mentón: ojos al 80 % y la mandíbula sube y baja (+10 %).
    manos[en(100.0, 105.0)], ears_m[en(100.0, 105.0)] = 1, 0.24
    mand[en(100.0, 105.0)] = 1.05 * (1 + 0.10 * np.abs(np.sin(2 * np.pi * 3 * t[en(100.0, 105.0)])))
    mares[en(100.0, 105.0)] = 0.27 + 0.18 * np.sin(2 * np.pi * 4 * t[en(100.0, 105.0)])
    manos[rng.random(len(t)) < 0.05] = np.nan  # a veces no se pudo ver
    tapados = v.bostezos_tapados(t, mares, ears_m, manos, mand)
    inicios = [round(a) for a, _ in tapados]
    revisar(len(tapados) == 6 and inicios[0] in (8, 9) and inicios[1] == 16 and inicios[2] == 25
            and inicios[3] in (60, 61) and inicios[4] == 72 and inicios[5] == 80,
            f"tapados: {[(round(a, 1), round(b, 1)) for a, b in tapados]} (esperados A con la boca abierta antes, H con "
            f"los ojos apenas achicados, B con la mandíbula, F, I con la mandíbula que sube poco y J con los ojos muy "
            f"cerrados; la tos, la mano quieta, la mano en el mentón al hablar (también sonriendo) y K no)")
    r = v.analizar_boca(t, mares, ears_m, manos, mand)
    revisar(r["bostezos"] == 7 and r["bostezos_tapados"] == 6,
            f"en total: {r['bostezos']} bostezos, {r['bostezos_tapados']} tapados (esperados 7 y 6: F se ve y se tapa, "
            f"cuenta una vez)")
    episodios = {round(e["mano_desde"]): e for e in v.episodios_mano(t, mares, ears_m, manos, mand)}
    quieta, tos = episodios.get(40), episodios.get(33)
    revisar(quieta is not None and not quieta["bostezo"] and "los ojos casi no se entrecerraron" in v.texto_episodio(quieta)
            and tos is not None and "no se vio la boca abierta (antes o entre los dedos)" in v.texto_episodio(tos)
            and not episodios[90]["bostezo"] and not episodios[100]["bostezo"]
            and v.texto_episodio(episodios[16], corto=True).endswith("BOSTEZO"),
            f"diagnóstico: dice qué faltó ({v.texto_episodio(quieta) if quieta else 'sin la mano quieta'})")
    sin_manos = v.analizar_boca(t, mares)
    revisar(sin_manos["bostezos"] == 2, f"sin detección de manos solo cuentan los de boca a la vista: {sin_manos['bostezos']} "
                                        f"(esperados 2: F y G)")
    mano_tarde = manos.copy()
    mano_tarde[en(10.0, 12.5)] = 0
    mano_tarde[en(11.2, 12.5)] = 1  # en A la mano llega 1,2 s después de cerrar la boca: ya no es «justo antes»
    revisar(len(v.bostezos_tapados(t, mares, ears_m, mano_tarde, mand)) == 5,
            "si la mano llega 1,2 s después de cerrar la boca (y la mandíbula no bajó), no es «justo antes»: no cuenta")
    # El contador en vivo (se recalcula cada segundo con lo que hay hasta ahí) nunca baja y termina igual que el final.
    cuentas = [v.analizar_boca(t[:k], mares[:k], ears_m[:k], manos[:k], mand[:k])["bostezos"]
               for k in np.searchsorted(t, np.arange(2, t[-1], 1.0))]
    revisar(all(b >= a for a, b in zip(cuentas, cuentas[1:])) and cuentas[-1] == r["bostezos"],
            f"contador en vivo: nunca baja y termina en {cuentas[-1]} como el resultado final ({r['bostezos']})")
    # Cambia la persona a mitad de la sesión (como en --ver con varias): cada mano se compara con el reposo de
    # los 20 s anteriores, no con el promedio de todos.
    t2 = np.arange(0, 100, 1 / 30)
    en2 = lambda a, b: (t2 >= a) & (t2 < b)  # noqa: E731
    otra = t2 >= 60
    mand2 = np.where(otra, 1.05, 1.25) + rng.normal(0, 0.004, len(t2))   # caras distintas
    ears2 = np.where(otra, 0.25, 0.30) + rng.normal(0, 0.005, len(t2))
    mares2, manos2 = 0.05 + np.abs(rng.normal(0, 0.01, len(t2))), np.zeros(len(t2))
    manos2[en2(85, 89)], mand2[en2(86, 88)], ears2[en2(86, 88)] = 1, 1.05 * 1.14, 0.19  # bostezo de la 2.ª persona
    tap2 = v.bostezos_tapados(t2, mares2, ears2, manos2, mand2)
    revisar(len(tap2) == 1 and round(tap2[0][0]) == 85,
            f"otra persona a los 60 s: su bostezo tapado (mandíbula +14 % sobre SU reposo, ojos al 76 %) cuenta: {tap2}")
    # Mandíbula en 3D: girar la cabeza 25 grados o inclinarla 15 cambia la medida plana, no la de 3D.
    cara3d = np.zeros((478, 3))
    for i, xyz in {33: (-45, 0, 10), 263: (45, 0, 10), 168: (0, -5, -5), 152: (0, 110, 5)}.items():
        cara3d[i] = xyz

    def girar3d(p, guinada, cabeceo):
        g, c = np.radians(guinada), np.radians(cabeceo)
        ry = np.array([[np.cos(g), 0, np.sin(g)], [0, 1, 0], [-np.sin(g), 0, np.cos(g)]])
        rx = np.array([[1, 0, 0], [0, np.cos(c), -np.sin(c)], [0, np.sin(c), np.cos(c)]])
        return p @ (rx @ ry).T

    frente = v.mandibula(cara3d[:, :2], cara3d[:, 2])
    cambios = []
    for guinada, cabeceo in ((30, 0), (0, 20)):
        g = girar3d(cara3d, guinada, cabeceo)
        cambios.append((v.mandibula(g[:, :2]) / frente - 1, v.mandibula(g[:, :2], g[:, 2]) / frente - 1))
    revisar(all(abs(plano) > 0.08 and abs(en3d) < 0.01 for plano, en3d in cambios),
            f"girar la cabeza 30° o inclinarla 20°: la mandíbula plana cambia {cambios[0][0]:+.0%} y {cambios[1][0]:+.0%} "
            f"(parecería un bostezo o lo taparía); en 3D, {cambios[0][1]:+.1%} y {cambios[1][1]:+.1%}")
    reg = v.Registro()
    reg.t, reg.rgb, reg.mar, reg.ear = list(t), [[np.nan] * 3] * len(t), list(mares), list(ears_m)
    reg.mano, reg.mandibula = list(manos), list(mand)
    res = reg.resultado()
    revisar(res["bostezos"] == 7 and res["bostezos_tapados"] == 6 and res["parpadeos"] == 1,
            f"en el resultado: {res['bostezos']} bostezos, {res['bostezos_tapados']} tapados y {res['parpadeos']} parpadeo "
            f"(el entrecerrar de los bostezos no cuenta; el de la tos sí, como 1 parpadeo)")

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

    print("\n--- lentes ---")
    import cv2
    puntos = np.zeros((478, 2))
    for i, xy in {33: (250, 200), 263: (390, 200), 168: (320, 190), 6: (320, 215), 61: (280, 300), 291: (360, 300),
                  105: (270, 170), 334: (370, 170), 66: (285, 172), 296: (355, 172)}.items():
        puntos[i] = xy

    def cara_gris(semilla, montura=None, grosor=3, sombra=False):
        g = np.random.default_rng(semilla)
        img = np.clip(150 + g.normal(0, 3, (480, 640)), 0, 255)
        img += np.linspace(-15, 15, 640)[None, :]  # luz de costado
        if sombra:  # sombra suave en la raíz de la nariz (sin lentes): no es un borde de montura
            img[185:200, 300:340] -= np.linspace(0, 20, 15)[:, None]
            img[200:215, 300:340] -= 20 - np.linspace(0, 20, 15)[:, None]
        img = img.astype(np.uint8)
        if montura is not None:
            cv2.line(img, (290, 196), (350, 196), montura, grosor)                 # puente
            cv2.rectangle(img, (225, 180), (295, 230), montura, grosor)            # aros
            cv2.rectangle(img, (345, 180), (415, 230), montura, grosor)
        return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)

    def girar(img, pts, grados):
        m = cv2.getRotationMatrix2D((320, 240), grados, 1.0)
        return cv2.warpAffine(img, m, (640, 480), borderMode=cv2.BORDER_REPLICATE), pts @ m[:, :2].T + m[:, 2]

    sin = v.puntaje_lentes(cara_gris(1), puntos)
    sombra = v.puntaje_lentes(cara_gris(2, sombra=True), puntos)
    gruesa = v.puntaje_lentes(cara_gris(3, montura=40), puntos)
    fina = v.puntaje_lentes(cara_gris(4, montura=100, grosor=1), puntos)
    revisar(sin < v.LENTES_UMBRAL and sombra < v.LENTES_UMBRAL,
            f"sin lentes: puntaje {sin:.1f}; con una sombra suave en la nariz {sombra:.1f} (umbral {v.LENTES_UMBRAL:g})")
    revisar(gruesa > v.LENTES_UMBRAL and fina > v.LENTES_UMBRAL,
            f"con lentes: montura gruesa {gruesa:.1f}; montura fina de 1 píxel {fina:.1f} (umbral {v.LENTES_UMBRAL:g})")
    girada_con = v.puntaje_lentes(*girar(cara_gris(5, montura=40), puntos, 14))
    girada_sin = v.puntaje_lentes(*girar(cara_gris(6), puntos, 14))
    revisar(girada_con > v.LENTES_UMBRAL and girada_sin < v.LENTES_UMBRAL,
            f"cabeza ladeada 14 grados (se endereza): con lentes {girada_con:.1f}, sin lentes {girada_sin:.1f}")
    revisar(v.puntaje_lentes(cara_gris(1), puntos * 0.2) is None, "cara muy chica: no se decide")
    rev = v.RevisionLentes(umbral=4.0)
    decisiones = []
    for k in range(int(5 * 30)):  # 2,5 s con lentes y después sin
        rev.agregar(k / 30, 9.0 if k < 75 else 1.2)
        decisiones.append(rev.fraccion())
    revisar(decisiones[20] is None and decisiones[70] == 1.0 and decisiones[90] > 0.6 and decisiones[-1] == 0.0,
            f"revisión de 2 s: al principio no decide; con lentes 1,0; al quitarlos baja a 0 "
            f"({decisiones[20]}, {decisiones[70]}, {decisiones[90]:.2f}, {decisiones[-1]})")

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
        pts[1], pts[152], pts[168], pts[6] = (320, 290), (320, 400), (320, 215), (320, 240)
        mano = np.column_stack([np.linspace(270, 370, 21), np.linspace(300, 350, 21)])
        conexiones_mano = [(c.start, c.end) for c in mpv.HandLandmarksConnections.HAND_CONNECTIONS]
        v.dibujar(cuadro, pts, conexiones, {"pulso": None, "ear": 0.2, "quedan": None, "mano": True, "manos": [mano],
                                            "conexiones_mano": conexiones_mano, "lentes": (6.3, 0.9),
                                            "mensaje": ["SE VEN LENTES", "Quitatelos para continuar con la medicion",
                                                        "(si no, se mide igual en 25 s)"]})
        ok = True
    except Exception as e:  # noqa: BLE001
        ok, info = False, e
    revisar(ok, "la ventana se dibuja (malla, regiones, panel, avisos, sin cara, manos y aviso de lentes)", str(info))

    print(f"\n{total - fallas} de {total} pasaron.")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
