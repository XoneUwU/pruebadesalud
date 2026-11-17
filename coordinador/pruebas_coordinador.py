"""Prueba simple de las reglas del coordinador provisional (datos inventados; no necesita MQTT).

  python coordinador/pruebas_coordinador.py

Muestra OK o FALLA por cada caso y termina con código 1 si alguno falla.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from coordinador_provisional import MOTIVO_SPO2, evaluar, evaluar_spo2, guardar_linea_base, leer_linea_base  # noqa: E402

PVT_BIEN = {"rt_media_ms": 280, "lapsos": 0, "anticipadas": 0, "duracion_s": 180, "lapsos_por_min": 0, "anticipadas_por_min": 0}
DSST_BIEN = {"correctas": 60, "incorrectas": 1, "por_minuto": 40, "duracion_s": 90}
CUEST_BIEN = {"horas_sueno": 7.5, "horas_sueno_previa": 7.5}


def sesion(**cambios) -> dict:
    """Una sesión normal; cada argumento reemplaza o agrega campos de una fuente."""
    datos = {"pvt": dict(PVT_BIEN), "dsst": dict(DSST_BIEN), "cuestionario": dict(CUEST_BIEN),
             "voz": {"estado_voz": "sin línea base"}}
    for tipo, campos in cambios.items():
        datos[tipo] = {**datos.get(tipo, {}), **campos}
    return datos


BASE = {"pvt": [{"rt_media_ms": 250, "lapsos_por_min": 0}, {"rt_media_ms": 250, "lapsos_por_min": 0}],
        "dsst": [{"por_minuto": 45, "incorrectas": 1}], "cuestionario": [{"horas_sueno": 8}]}

# (nombre, datos, línea base, color esperado, motivos que deben estar)
CASOS = [
    ("todo normal, sin línea base", sesion(), None, "verde", []),
    ("48 h: 11 h de sueño (1 punto)", sesion(cuestionario={"horas_sueno": 6, "horas_sueno_previa": 5}), None, "amarillo",
     ["Menos de 12 horas de sueño en las últimas 48 horas"]),
    ("48 h: 7,5 h de sueño (2 puntos)", sesion(cuestionario={"horas_sueno": 6, "horas_sueno_previa": 1.5}), None, "rojo",
     ["Muy poco sueño en las últimas 48 horas"]),
    ("48 h: el total enviado manda", sesion(cuestionario={"horas_sueno_48h": 11}), None, "amarillo",
     ["Menos de 12 horas de sueño en las últimas 48 horas"]),
    ("3,5 h de sueño (2 puntos)", sesion(cuestionario={"horas_sueno": 3.5}), None, "rojo", ["Menos de 4 horas de sueño"]),
    ("3 fuentes moderadas", sesion(pvt={"rt_media_ms": 360}, dsst={"por_minuto": 22},
     cuestionario={"horas_sueno": 6, "horas_sueno_previa": 5}), None, "rojo",
     ["Reacción lenta en la prueba PVT", "Pocos aciertos en la prueba de símbolos"]),
    ("PVT modo demo: 2 lapsos en 1 min", sesion(pvt={"lapsos": 2, "duracion_s": 60, "lapsos_por_min": 2}), None, "amarillo",
     ["Varios lapsos de atención en la prueba PVT"]),
    ("PVT modo demo: 1 lapso suelto no marca", sesion(pvt={"lapsos": 1, "duracion_s": 60, "lapsos_por_min": 1}), None, "verde", []),
    ("con base: reacción +20 %", sesion(pvt={"rt_media_ms": 300}), BASE, "amarillo",
     ["Reacción más lenta de lo habitual en la prueba PVT"]),
    ("con base: 4 h menos de sueño", sesion(cuestionario={"horas_sueno": 4}), BASE, "rojo",
     ["Muchas menos horas de sueño de lo habitual"]),
    ("con base: todo igual", sesion(pvt={"rt_media_ms": 255}, dsst={"por_minuto": 44}, cuestionario={"horas_sueno": 7.5}), BASE,
     "verde", []),
    ("voz cansada (señal débil)", sesion(voz={"estado_voz": "más cansada que su línea base"}), None, "amarillo",
     ["Voz más cansada de lo habitual"]),
    ("visión PERCLOS 0,3", sesion(vision={"perclos": 0.3}), None, "rojo", ["Ojos cerrados más tiempo de lo normal"]),
    ("visión: el pulso por cámara ya no cuenta (110 con buena calidad)",
     sesion(vision={"perclos": 0.05, "pulso_rppg_lpm": 110, "calidad_rppg": 0.8}), None, "verde", []),
    ("visión: 3 bostezos en 1 min", sesion(vision={"perclos": 0.05, "bostezos": 3, "bostezos_min": 3.0}), None, "amarillo",
     ["Bostezos durante la medición"]),
    ("visión: 1 bostezo suelto no marca", sesion(vision={"perclos": 0.05, "bostezos": 1, "bostezos_min": 1.0}), None,
     "verde", []),
    ("sensor 110 lpm", sesion(esp32={"pulso_lpm": 110}), None, "amarillo", ["Pulso en reposo alto"]),
    ("sensor: HRV 30 % más baja que la base", sesion(esp32={"pulso_lpm": 72, "hrv_rmssd_ms": 31.5}),
     {"esp32": [{"pulso_lpm": 70, "hrv_rmssd_ms": 45}]}, "amarillo", ["Variabilidad del pulso más baja de lo habitual"]),
    ("sensor: HRV sin base no se juzga", sesion(esp32={"pulso_lpm": 72, "hrv_rmssd_ms": 15}), None, "verde", []),
    ("visión: cara vista el 30 % del tiempo no cuenta", sesion(vision={"perclos": 0.4, "cara_detectada_pct": 30}),
     None, "verde", []),
    ("visión medida con lentes: PERCLOS 0,3 no cuenta", sesion(vision={"perclos": 0.3, "lentes": True}), None, "verde", []),
    ("visión con lentes: los bostezos sí cuentan", sesion(vision={"perclos": 0.3, "lentes": True, "bostezos": 3,
                                                                  "bostezos_min": 3.0}), None, "amarillo",
     ["Bostezos durante la medición"]),
    ("visión con base: +60 % parpadeos", sesion(vision={"perclos": 0.05, "parpadeos_min": 24}),
     {"vision": [{"perclos": 0.05, "parpadeos_min": 15}]}, "amarillo", ["Más parpadeos de lo habitual"]),
    ("solo el cuestionario (DSST omitido)", {"cuestionario": {"horas_sueno": 7, "horas_sueno_previa": 7}}, None, "verde", []),
]


def main() -> int:
    fallas = 0
    for nombre, datos, base, color, motivos in CASOS:
        r = evaluar(datos, base)
        ok = (r["color"] == color and all(m in r["motivos"] for m in motivos) and len(r["motivos"]) <= 3
              and (r["motivos"] or color == "verde") and 0 <= r["puntaje"] <= 1 and r["accion"])
        fallas += not ok
        print(f"{'OK   ' if ok else 'FALLA'}  {nombre}: {r['color']} {r['puntaje']} {r['motivos']}")
        if not ok:
            print(f"       esperado: {color} con {motivos}; señales {r['senales']}")

    # la voz sin línea base no cuenta como fuente; con "normal" sí (0 puntos)
    sin = evaluar(sesion())["senales"]
    con = evaluar(sesion(voz={"estado_voz": "normal"}))["senales"]
    ok = "voz" not in sin and con.get("voz") == 0
    fallas += not ok
    print(f"{'OK   ' if ok else 'FALLA'}  voz sin línea base no cuenta; voz normal cuenta con 0: {sin} / {con}")

    # línea base guardada: se excluye la sesión que se está evaluando
    with tempfile.TemporaryDirectory() as carpeta:
        archivo = Path(carpeta) / "linea_base.jsonl"
        guardar_linea_base("sebas", "pvt", "s1", {"rt_media_ms": 250}, archivo)
        guardar_linea_base("sebas", "pvt", "s2", {"rt_media_ms": 260}, archivo)
        guardar_linea_base("bri", "pvt", "s3", {"rt_media_ms": 300}, archivo)
        base = leer_linea_base("sebas", sin_sesion="s2", archivo=archivo)
        ok = [b["rt_media_ms"] for b in base.get("pvt", [])] == [250]
        fallas += not ok
        print(f"{'OK   ' if ok else 'FALLA'}  línea base de sebas sin la sesión evaluada: {base}")

    # Aviso de SpO2: 20 s seguidos con el SpO2 bajo (con dedo y calidad >= 0,5); no cambia el color.
    def lecturas(valores, desde=0.0, dedo=True, calidad=0.9):
        return [(desde + i, {"dedo": dedo, "calidad": calidad, "spo2": v}) for i, v in enumerate(valores)]

    base_spo2 = [{"spo2": 98}, {"spo2": 97}]  # promedio 97,5: bajo = 93,5 o menos
    cada_4 = [89 if i % 4 == 0 else None for i in range(36)]  # el sensor da el SpO2 cada ~4 s
    casos_spo2 = [
        ("sin base: 89 durante 35 s", lecturas([89] * 36), None, True),
        ("sin base: 89 solo 15 s", lecturas([89] * 16), None, False),
        ("con base 97,5: 93 durante 35 s", lecturas([93] * 36), base_spo2, True),
        ("con base 97,5: 95 durante 35 s (solo 2,5 abajo)", lecturas([95] * 36), base_spo2, False),
        ("dedo afuera a la mitad corta la racha", lecturas([89] * 20) + lecturas([89], 20, dedo=False)
         + lecturas([89] * 20, 21), None, False),
        ("mala calidad no cuenta", lecturas([89] * 40, calidad=0.3), None, False),
        ("SpO2 cada ~4 s (sin valor entre medio) no corta", lecturas(cada_4), None, True),
    ]
    for nombre, lect, base_e, esperado in casos_spo2:
        aviso, seg = evaluar_spo2(lect, base_e)
        ok = aviso == esperado
        fallas += not ok
        print(f"{'OK   ' if ok else 'FALLA'}  SpO2 {nombre}: aviso={aviso} ({seg} s seguidos)")
    sin, con = evaluar(sesion()), evaluar(sesion(), aviso_spo2=True)
    ok = (con["color"] == sin["color"] == "verde" and con["puntaje"] == sin["puntaje"] and con["aviso_spo2"]
          and con["motivos"] == [MOTIVO_SPO2] and not sin["aviso_spo2"])
    fallas += not ok
    print(f"{'OK   ' if ok else 'FALLA'}  el aviso de SpO2 no cambia el color ni el puntaje: {con['color']} {con['puntaje']} "
          f"{con['motivos']}")

    # El ESP32 manda una lectura por segundo: se juntan (mediana) y no reinician la espera del cálculo.
    from coordinador_provisional import Coordinador

    class CliFalso:
        def __init__(self):
            self.mensajes = []

        def publicar(self, tema, datos, retener=False):
            self.mensajes.append((tema, datos))

        def suscribir(self, *a, **k):
            pass

    cli = CliFalso()
    coord = Coordinador(cli)
    coord._al_sesion("apto/control/sesion", {"persona": "sebas", "tarea": "caminata espacial", "sesion": "s9"})
    for pulso in (72, 74, 140, 73):  # una lectura suelta mala (140) no debe pesar
        coord._al_dato("apto/sebas/esp32", {"persona": "sebas", "pulso_lpm": pulso, "dedo": True, "calidad": 0.9})
    for _ in range(3):  # sin dedo o con mala calidad: no cuentan
        coord._al_dato("apto/sebas/esp32", {"persona": "sebas", "pulso_lpm": 130, "dedo": False, "calidad": 0})
        coord._al_dato("apto/sebas/esp32", {"persona": "sebas", "pulso_lpm": 130, "dedo": True, "calidad": 0.2})
    coord._al_dato("apto/sebas/cuestionario", {"persona": "sebas", "sesion": "s9", "horas_sueno": 8, "horas_sueno_previa": 8})
    s = coord.sesiones[("sebas", "s9")]
    s["timer"].cancel()
    coord._publicar("sebas", "s9")
    ev = next(d for t, d in cli.mensajes if t == "apto/sebas/evaluacion")
    ok = len(s["esp32"]) == 10 and ev["color"] == "verde" and "esp32" in ev["senales"]
    fallas += not ok
    print(f"{'OK   ' if ok else 'FALLA'}  ESP32: 10 lecturas juntadas, solo 4 válidas (con dedo y calidad) en la mediana "
          f"-> {ev['color']} {ev['senales']}")

    # El aviso llega a la evaluación publicada (las lecturas, separadas 1 s como las del ESP32).
    cli.mensajes.clear()
    coord._al_sesion("apto/control/sesion", {"persona": "sebas", "tarea": "caminata espacial", "sesion": "s10"})
    for _ in range(40):
        coord._al_dato("apto/sebas/esp32", {"persona": "sebas", "pulso_lpm": 72, "spo2": 89, "dedo": True, "calidad": 0.9})
    coord._al_dato("apto/sebas/cuestionario", {"persona": "sebas", "sesion": "s10", "horas_sueno": 8, "horas_sueno_previa": 8})
    s10 = coord.sesiones[("sebas", "s10")]
    s10["timer"].cancel()
    s10["esp32"] = [(1000.0 + i, m) for i, (_, m) in enumerate(s10["esp32"])]
    coord._publicar("sebas", "s10")
    ev10 = next(d for t, d in cli.mensajes if t == "apto/sebas/evaluacion")
    ok = ev10["aviso_spo2"] is True and MOTIVO_SPO2 in ev10["motivos"] and ev10["color"] == "verde"
    fallas += not ok
    print(f"{'OK   ' if ok else 'FALLA'}  el coordinador publica el aviso: aviso_spo2={ev10['aviso_spo2']}, "
          f"{ev10['color']}, {ev10['motivos']}")

    # Músculo (AD8232): resumen de la prueba guiada (35 s, una lectura por segundo). Informativo: sin puntos.
    from coordinador_provisional import musculo_para_evaluacion, resumen_esp32, resumen_musculo

    SECUENCIA = (["preparate"] * 5 + ["aprieta"] * 5 + ["espera"] * 2 + ["descansa"] * 6 + ["espera"] * 2
                 + ["aprieta"] * 5 + ["espera"] * 2 + ["descansa"] * 8)

    def prueba_musculo(secuencia=SECUENCIA, electrodos=True, con_orden=True, simulado=False):
        lect = []
        for i, orden in enumerate(secuencia):
            primera = i == 0 or secuencia[i - 1] != orden  # cubre el segundo anterior: no debe contar
            v = 999.0 if primera else 250.0 if orden == "aprieta" else 20.0
            m = {"fase": "musculo", "dedo": False, "electrodos": electrodos, "musculo_rms_mv": v if electrodos else None}
            if con_orden:
                m["musculo_orden"] = orden
            if simulado:
                m["musculo_simulado"] = True
            lect.append(m)
        return lect

    normal = resumen_musculo(prueba_musculo())
    casos_musculo = [
        ("prueba completa: 250 al apretar, 20 en reposo, relación 12,5",
         normal == {"musculo_aprieta_mv": 250.0, "musculo_descansa_mv": 20.0, "musculo_relacion": 12.5,
                    "electrodos_pct": 100, "musculo_simulado": False}, normal),
        ("sin electrodos ni valores: inventa valores lógicos, marcados como simulados e inventados",
         (r := resumen_musculo(prueba_musculo(electrodos=False)))["musculo_relacion"] is not None
         and 200 <= r["musculo_aprieta_mv"] <= 280 and 15 <= r["musculo_descansa_mv"] <= 25
         and r["musculo_simulado"] and r.get("musculo_inventado") and r["electrodos_pct"] == 0, r),
        ("AD8232 sin alimentación («electrodos» pero RMS 0): no son medidas, inventa y no va a la línea base",
         (r := resumen_musculo([{**m, "musculo_rms_mv": 0.0} for m in prueba_musculo()]))["musculo_relacion"] is not None
         and r["musculo_simulado"] and r.get("musculo_inventado") and r["electrodos_pct"] == 0
         and musculo_para_evaluacion(r, [{"musculo_relacion": 10}])["relacion_base"] is None, r),
        ("firmware sin musculo_orden: sin valores",
         (r := resumen_musculo(prueba_musculo(con_orden=False)))["musculo_relacion"] is None
         and r["electrodos_pct"] == 100, r),
        ("órdenes de 3 s: sin la primera quedan 2 lecturas, no alcanza: inventa (simulado)",
         (r := resumen_musculo(prueba_musculo(["aprieta"] * 3 + ["descansa"] * 3)))["musculo_relacion"] is not None
         and r["musculo_simulado"] and r.get("musculo_inventado"), r),
        ("electrodo a medias (2 medidas en reposo, el resto fingidas): usa las fingidas y se muestra",
         (r := resumen_musculo([{**m, "musculo_simulado": True, "electrodos": False} if k not in (15, 32) else
                                {**m, "musculo_rms_mv": 60.0} for k, m in enumerate(prueba_musculo())]))
         ["musculo_relacion"] == 12.5 and r["musculo_simulado"] and not r.get("musculo_inventado"), r),
        ("sin prueba del músculo: el resumen del ESP32 no trae campos de músculo",
         "musculo_relacion" not in (r := resumen_esp32([{"dedo": True, "calidad": 0.9, "pulso_lpm": 70}])), r),
        ("la línea base promedia sin los fingidos",
         (r := musculo_para_evaluacion(normal, [{"musculo_relacion": 10}, {"musculo_relacion": 14},
                                                {"musculo_relacion": 99, "musculo_simulado": True}]))["relacion_base"] == 12.0, r),
        ("sin electrodos, fingidos por el firmware: se usan y quedan como simulados",
         (r := resumen_musculo([{**m, "electrodos": False, "musculo_rms_mv": v["musculo_rms_mv"]}
                                for m, v in zip(prueba_musculo(simulado=True), prueba_musculo())]))["musculo_relacion"] == 12.5
         and r["musculo_simulado"] and r["electrodos_pct"] == 0, r),
        ("mezcla de reales y fingidos: solo los reales, no simulado",
         (r := resumen_musculo(prueba_musculo() + [{**m, "musculo_rms_mv": 5000.0}
                                                   for m in prueba_musculo(simulado=True)]))["musculo_relacion"] == 12.5
         and not r["musculo_simulado"], r),
        ("valores fingidos: no se comparan con la línea base",
         (r := musculo_para_evaluacion(resumen_musculo(prueba_musculo(simulado=True)),
                                       [{"musculo_relacion": 10}]))["relacion_base"] is None and r["simulado"], r),
    ]
    for nombre, ok, detalle in casos_musculo:
        fallas += not ok
        print(f"{'OK   ' if ok else 'FALLA'}  músculo, {nombre}: {detalle}")

    # En la evaluación publicada: "musculo" aparece y no cambia el color ni el puntaje.
    cli.mensajes.clear()
    coord._al_sesion("apto/control/sesion", {"persona": "sebas", "tarea": "caminata espacial", "sesion": "s11"})
    for _ in range(30):
        coord._al_dato("apto/sebas/esp32", {"persona": "sebas", "sesion": "s11", "pulso_lpm": 72, "dedo": True,
                                            "calidad": 0.9, "fase": "midiendo"})
    for m in prueba_musculo():
        coord._al_dato("apto/sebas/esp32", {"persona": "sebas", "sesion": "s11", **m})
    coord._al_dato("apto/sebas/cuestionario", {"persona": "sebas", "sesion": "s11", "horas_sueno": 8, "horas_sueno_previa": 8})
    s11 = coord.sesiones[("sebas", "s11")]
    s11["timer"].cancel()
    coord._publicar("sebas", "s11")
    ev11 = next(d for t, d in cli.mensajes if t == "apto/sebas/evaluacion")
    ok = (ev11.get("musculo", {}).get("relacion") == 12.5 and ev11["color"] == ev["color"]
          and ev11["senales"] == ev["senales"] and ev11["puntaje"] == ev["puntaje"])
    fallas += not ok
    print(f"{'OK   ' if ok else 'FALLA'}  el coordinador publica el músculo sin puntos: {ev11.get('musculo')}, "
          f"{ev11['color']} {ev11['senales']}")

    total = len(CASOS) + 3 + len(casos_spo2) + 2 + len(casos_musculo) + 1
    print(f"\n{total - fallas} de {total} pasaron.")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
