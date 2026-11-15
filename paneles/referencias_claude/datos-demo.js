/* Datos DEMOSTRATIVOS de «¿Está apto hoy?». Nada de esto viene de un sensor.
 * Siguen el contrato de los temas MQTT del README (sección 4) para que el cambio a datos reales
 * (servicios.js → paneles/web/comun.js) no cambie la interfaz. Todos llevan simulado: true. */
(function () {
  const TRIPULACION = ["bri", "danilo", "sebas", "erick", "adrian"];
  const TAREAS = ["caminata espacial", "maniobra de acoplamiento", "mantenimiento externo"];
  const MODULOS = [
    { id: "voz", nombre: "Voz", activo: true, comando: "python voz\\voz_fatiga.py --servicio" },
    { id: "copiloto", nombre: "Copiloto", activo: true, comando: "python copiloto\\copiloto.py" },
    { id: "vision", nombre: "Visión", activo: true, comando: "python vision\\vision.py --servicio" },
    { id: "coordinador", nombre: "Coordinador", activo: true, comando: "python coordinador\\coordinador_provisional.py", provisional: true },
    { id: "esp32", nombre: "ESP32", activo: false, comando: "enciendan la placa (firmware\\apto_esp32) en la misma red" },
  ];
  const EVALUACIONES = {
    bri: { persona: "bri", color: "amarillo", puntaje: 3, ts: "2026-11-14T08:12:40", tarea: "caminata espacial",
      motivos: ["Menos horas de sueño de lo habitual", "Reacción más lenta que la línea base"],
      accion: "Hacer la tarea en pareja o posponerla", provisional: true, aviso_spo2: true, simulado: true },
    danilo: { persona: "danilo", color: "verde", puntaje: 0, ts: "2026-11-14T07:48:02", tarea: "caminata espacial",
      motivos: [], accion: "Puede hacer la tarea", provisional: true, simulado: true },
    sebas: { persona: "sebas", color: "verde", puntaje: 1, ts: "2026-11-14T07:55:19", tarea: "caminata espacial",
      motivos: ["Más parpadeos que en la línea base"], accion: "Puede hacer la tarea", provisional: true, simulado: true },
    erick: { persona: "erick", color: "rojo", puntaje: 5, ts: "2026-11-14T08:03:51", tarea: "caminata espacial",
      motivos: ["Somnolencia alta según la escala de Karolinska", "Lapsos frecuentes en la prueba de reacción", "Ojos cerrados más tiempo de lo habitual"],
      accion: "No hacer la tarea hoy; descansar y repetir la evaluación", provisional: true, simulado: true },
  };
  const ULTIMAS = {
    bri: { pulso_lpm: 68, hrv_rmssd_ms: 41, spo2: 91, kss: 6, horas_sueno: 5.5, pvt_mediana: 312, lapsos: 4, perclos: 0.08, parpadeos_min: 17 },
    danilo: { pulso_lpm: 61, hrv_rmssd_ms: 58, spo2: 97, kss: 3, horas_sueno: 7.5, pvt_mediana: 254, lapsos: 0, perclos: 0.03, parpadeos_min: 12 },
    sebas: { pulso_lpm: 72, hrv_rmssd_ms: 47, spo2: 98, kss: 4, horas_sueno: 7, pvt_mediana: 268, lapsos: 1, perclos: 0.04, parpadeos_min: 21 },
    erick: { pulso_lpm: 79, hrv_rmssd_ms: 29, spo2: 96, kss: 8, horas_sueno: 4, pvt_mediana: 389, lapsos: 9, perclos: 0.17, parpadeos_min: 24 },
  };
  // Resultado detallado de la sesión de Bri (pantalla Resultados).
  const DETALLE = {
    sesion: "20261114-080940-bri", persona: "bri", tarea: "caminata espacial", modo_demo: true,
    indicadores: [
      { tipo: "medido", nombre: "Pulso", fuente: "ESP32", valor: "68", unidad: "lpm", calidad: 0.82, puntos: 0, nota: "Mediana de las lecturas con el dedo puesto y calidad de 0,5 o más. Manda sobre el pulso de la cámara." },
      { tipo: "medido", nombre: "HRV (RMSSD)", fuente: "ESP32", valor: "41", unidad: "ms", calidad: 0.82, puntos: 0, nota: "Variación entre latidos en 30 s, comparada con la línea base." },
      { tipo: "medido", nombre: "SpO₂", fuente: "ESP32", valor: "91", unidad: "%", calidad: 0.78, puntos: null, aviso: true, nota: "Aviso, no puntaje: estuvo bajo 30 s seguidos. Repetir la medición." },
      { tipo: "medido", nombre: "Reacción PVT-B", fuente: "Estación", valor: "312", unidad: "ms mediana", puntos: 1, nota: "4 lapsos de 355 ms o más en 1 minuto (modo demo)." },
      { tipo: "medido", nombre: "Parpadeos", fuente: "Visión", valor: "17", unidad: "por min", calidad: 0.9, puntos: 0, nota: "EAR por debajo del 60 % del ojo abierto durante 2 cuadros o más." },
      { tipo: "estimado", nombre: "PERCLOS", fuente: "Visión", valor: "0,08", unidad: "fracción", calidad: 0.9, puntos: 0, nota: "Tiempo con los ojos casi cerrados. Aproximación P80, sin validación clínica." },
      { tipo: "estimado", nombre: "Cansancio en la voz", fuente: "Voz", valor: "+0,6", unidad: "índice z", puntos: 0, nota: "Señal débil: pesa como máximo 1 punto." },
      { tipo: "reportado", nombre: "Somnolencia KSS", fuente: "Cuestionario", valor: "6", unidad: "de 9", puntos: 1, nota: "Algunas señales de sueño." },
      { tipo: "reportado", nombre: "Horas de sueño", fuente: "Cuestionario", valor: "5,5", unidad: "h", puntos: 1, nota: "Menos de lo habitual frente a la línea base." },
      { tipo: "no_disponible", nombre: "Pulso sin contacto", fuente: "Visión", valor: "", unidad: "", calidad: 0.41, puntos: null, nota: "No se publica: la calidad fue 0,41 y hace falta 0,5." },
      { tipo: "no_disponible", nombre: "Fatiga por visión", fuente: "Visión", valor: "", unidad: "", puntos: null, nota: "El algoritmo todavía no está validado. No se calcula." },
    ],
    conversacion: [
      { pregunta: "¿Por qué salí en amarillo?", respuesta: "Tu resultado es amarillo. Motivos: menos horas de sueño de lo habitual y reacción más lenta que la línea base. Además, el oxígeno estuvo más bajo de lo habitual: conviene repetir la medición.", modo: "fichas" },
    ],
  };
  // Historial: 30 días, generado de forma determinista.
  const COLORES = ["verde", "verde", "verde", "amarillo", "verde", "amarillo", "rojo"];
  const HISTORIAL = [];
  let semilla = 7;
  const azar = () => ((semilla = (semilla * 9301 + 49297) % 233280) / 233280);
  for (let d = 29; d >= 0; d -= 1) {
    for (const p of TRIPULACION) {
      if (azar() < 0.45) continue;
      const fecha = new Date(2026, 10, 14 - d, 7 + Math.floor(azar() * 3), Math.floor(azar() * 60));
      const color = COLORES[Math.floor(azar() * COLORES.length)];
      const puntaje = color === "verde" ? Math.round(azar()) : color === "amarillo" ? 2 + Math.round(azar()) : 4 + Math.round(azar() * 2);
      HISTORIAL.push({
        id: `${fecha.toISOString().slice(0, 10).replace(/-/g, "")}-${p}`, persona: p, fecha: fecha.getTime(), color, puntaje,
        kss: Math.min(9, 2 + puntaje + Math.round(azar())), horas_sueno: Math.max(4, 8 - puntaje * 0.6 - Math.round(azar() * 2) / 2),
        pvt_mediana: Math.round(245 + puntaje * 22 + azar() * 25), pulso_lpm: Math.round(60 + azar() * 18), perclos: Math.round((0.02 + puntaje * 0.025) * 100) / 100,
        simulado: true,
      });
    }
  }
  window.AptoDemo = { TRIPULACION, TAREAS, MODULOS, EVALUACIONES, ULTIMAS, DETALLE, HISTORIAL, TAREA_ACTUAL: "caminata espacial" };
})();
