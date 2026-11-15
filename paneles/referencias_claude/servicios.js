/* Servicios REALES de «¿Está apto hoy?» — todavía sin conectar en este prototipo.
 * Para conectarlo: cargar paneles/web/config.js, vendor/mqtt.min.js y comun.js, suscribirse a apto/# y
 * publicar las órdenes (apto/control/sesion, orden_vision, orden_voz…). Mientras conectado sea false,
 * la interfaz usa datos-demo.js y lo muestra con la etiqueta DEMO. */
window.AptoServicios = {
  conectado: false,
  broker: { host: "localhost", ws: 9001 },
  temas: {
    sesion: "apto/control/sesion", modulos: "apto/control/modulos/+", ordenVision: "apto/control/orden_vision",
    estadoVision: "apto/control/estado_vision", ordenVoz: "apto/control/orden_voz", estadoVoz: "apto/control/estado_voz",
    pregunta: "apto/control/pregunta", evaluacion: "apto/{persona}/evaluacion", esp32: "apto/{persona}/esp32", vision: "apto/{persona}/vision",
  },
};
