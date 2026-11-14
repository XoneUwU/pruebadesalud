"""Vuelve a publicar una sesión guardada en MongoDB, respetando los tiempos. Es el respaldo de la demo.

  python registrador/reproducir.py --persona bri --sesiones          lista las sesiones guardadas de bri
  python registrador/reproducir.py --persona bri --desde "2026-11-13 20:47" --hasta "2026-11-13 20:52"
  python registrador/reproducir.py --persona bri --sesion 20261113-204746-bri
  python registrador/reproducir.py ... --listar        solo muestra qué publicaría
  python registrador/reproducir.py ... --velocidad 2   el doble de rápido
  python registrador/reproducir.py ... --max-espera 5  nunca espera más de 5 s entre dos mensajes

Cada mensaje sale con "reproducido": true, "ts" de ahora y "ts_original" (la hora en que pasó). Se
reproducen los datos de la persona (esp32, visión, voz, pvt, dsst, cuestionario), su evaluación y semáforo
(con retain, como el coordinador), las respuestas del copiloto y el inicio de sesión. NO se reproducen
órdenes (orden_voz, orden_vision, pregunta) ni avisos de estado o de módulos: harían grabar o responder
de verdad a los módulos abiertos. El coordinador ignora los mensajes reproducidos (no recalcula).
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from almacen import conectar, fecha_local, hora_local  # noqa: E402

from comun.mqtt_cliente import ClienteMQTT, ahora_iso  # noqa: E402

CONTROL_PERMITIDO = {"control/sesion"}
CON_RETAIN = {"evaluacion", "semaforo"}


def consulta(args) -> dict:
    q = {"persona": args.persona.lower(), "reproducido": False}  # nunca se reproduce una reproducción
    if args.sesion:
        q["datos.sesion"] = args.sesion
    if args.desde or args.hasta:
        q["recibido"] = {}
        if args.desde:
            q["recibido"]["$gte"] = fecha_local(args.desde)
        if args.hasta:
            q["recibido"]["$lte"] = fecha_local(args.hasta)
    return q


def se_reproduce(tipo: str) -> bool:
    return not tipo.startswith("control/") or tipo in CONTROL_PERMITIDO


def listar_sesiones(col, persona: str):
    filas = col.aggregate([
        {"$match": {"persona": persona, "reproducido": False, "datos.sesion": {"$exists": True}}},
        {"$group": {"_id": "$datos.sesion", "desde": {"$min": "$recibido"}, "hasta": {"$max": "$recibido"},
                    "mensajes": {"$sum": 1}, "tipos": {"$addToSet": "$tipo"}}},
        {"$sort": {"desde": 1}},
    ])
    vacio = True
    for f in filas:
        vacio = False
        print(f"{f['_id']:32} {hora_local(f['desde'])} -> {hora_local(f['hasta'])[11:]}  "
              f"{f['mensajes']:4} mensajes  ({', '.join(sorted(f['tipos']))})")
    if vacio:
        print(f"No hay sesiones guardadas de {persona}.")


def main():
    ap = argparse.ArgumentParser(description="Reproduce una sesión guardada en MongoDB")
    ap.add_argument("--persona", required=True)
    ap.add_argument("--desde", help='"2026-11-13 20:47" (hora de esta PC)')
    ap.add_argument("--hasta")
    ap.add_argument("--sesion", help="id de sesión de la estación (ver --sesiones)")
    ap.add_argument("--sesiones", action="store_true", help="lista las sesiones guardadas de la persona")
    ap.add_argument("--listar", action="store_true", help="solo muestra qué publicaría")
    ap.add_argument("--velocidad", type=float, default=1.0)
    ap.add_argument("--max-espera", type=float, default=0, help="segundos; 0 = sin límite")
    args = ap.parse_args()

    cliente, col = conectar(timeout_ms=3000)
    try:
        cliente.admin.command("ping")
    except Exception as e:
        print(f"MongoDB no responde ({type(e).__name__}). ¿Está abierto registrador\\mongo_local.py?")
        return
    if args.sesiones:
        listar_sesiones(col, args.persona.lower())
        return
    if not (args.sesion or args.desde or args.hasta):
        print("Indiquen --sesion o un rango con --desde/--hasta (vean las sesiones con --sesiones).")
        return
    docs = [d for d in col.find(consulta(args)).sort("recibido", 1) if se_reproduce(d["tipo"])]
    if not docs:
        print("No hay mensajes para reproducir con ese filtro.")
        return
    duracion = (docs[-1]["recibido"] - docs[0]["recibido"]).total_seconds()
    print(f"{len(docs)} mensajes de {args.persona}, de {hora_local(docs[0]['recibido'])} a "
          f"{hora_local(docs[-1]['recibido'])[11:]} ({duracion:.1f} s a velocidad 1).")
    if args.listar:
        for d in docs:
            print(f"  {hora_local(d['recibido'])[11:]}  {d['tema']}")
        return

    cli = ClienteMQTT("reproductor")
    if not cli.conectar():
        print("Hace falta MQTT para reproducir. Revisen que Mosquitto esté corriendo.")
        return
    inicio = time.time()
    anterior = docs[0]["recibido"]
    try:
        for d in docs:
            espera = (d["recibido"] - anterior).total_seconds() / max(args.velocidad, 0.01)
            if args.max_espera:
                espera = min(espera, args.max_espera)
            if espera > 0:
                time.sleep(espera)
            anterior = d["recibido"]
            datos = dict(d["datos"])
            datos["ts_original"] = datos.get("ts")
            datos["ts"] = ahora_iso()
            datos["reproducido"] = True
            cli.publicar(d["tema"], datos, retener=d["tipo"] in CON_RETAIN)
            print(f"  +{time.time() - inicio:6.1f} s  {d['tema']}")
    except KeyboardInterrupt:
        print("\nReproducción interrumpida.")
    time.sleep(0.5)  # que salga el último mensaje
    cli.cerrar()
    print(f"Listo: {len(docs)} mensajes en {time.time() - inicio:.1f} s.")


if __name__ == "__main__":
    main()
