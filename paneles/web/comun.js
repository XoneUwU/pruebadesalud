/* Conexión al broker por WebSocket, indicador de conexión y utilidades de pantalla (las 3 páginas).
 * Necesita, antes que este archivo: config.js (window.APTO), vendor/mqtt.min.js y logica.js. */
(function () {
  "use strict";

  const CFG = window.APTO || {};

  /** el("p", {class: "x"}, "texto", otroNodo) -> elemento. Los textos se insertan como texto, nunca como HTML. */
  function el(etiqueta, atributos, ...hijos) {
    const nodo = document.createElement(etiqueta);
    for (const [clave, valor] of Object.entries(atributos || {})) {
      if (valor === null || valor === undefined || valor === false) continue;
      if (clave === "dataset") Object.assign(nodo.dataset, valor);
      else if (clave.startsWith("on")) nodo.addEventListener(clave.slice(2), valor);
      else nodo.setAttribute(clave, valor === true ? "" : valor);
    }
    for (const hijo of hijos.flat()) {
      if (hijo === null || hijo === undefined || hijo === false) continue;
      nodo.append(hijo instanceof Node ? hijo : document.createTextNode(String(hijo)));
    }
    return nodo;
  }

  /** Etiqueta pequeña para los mensajes con "simulado": true. */
  function etiquetaSimulado(datos) {
    return datos && datos.simulado ? el("span", { class: "simulado", title: "Dato del simulador" }, "SIMULADO") : null;
  }

  /** Etiqueta para las evaluaciones del coordinador provisional ("provisional": true). */
  function etiquetaProvisional(datos) {
    return datos && datos.provisional
      ? el("span", { class: "simulado provisional", title: "Calculado por el coordinador provisional" }, "PROVISIONAL") : null;
  }

  /** Palabra del color, para no depender solo del color: "verde" -> "VERDE". */
  function palabraColor(color) {
    return { verde: "VERDE", amarillo: "AMARILLO", rojo: "ROJO" }[color] || "SIN EVALUAR";
  }

  /** "apto/bri/evaluacion" -> ["bri", "evaluacion"]. */
  function partesTema(tema) {
    const p = tema.split("/");
    return [p[1] || "", p.slice(2).join("/")];
  }

  /** Conecta al broker en el mismo host desde el que se abrió la página.
   *  alMensaje(tema, datos, retenido) recibe cada mensaje JSON de los temas indicados. */
  function conectar(pagina, temas, alMensaje) {
    const indicador = document.getElementById("conexion");
    const poner = (estado, texto) => {
      if (!indicador) return;
      indicador.dataset.estado = estado;
      indicador.querySelector(".texto").textContent = texto;
    };
    const falso = { cliente: null, publicar: () => false };
    if (!window.APTO) {
      poner("error", "Falta config.js: abran la página desde paneles/servidor.py");
      return falso;
    }
    if (typeof mqtt === "undefined") {
      poner("error", "Falta vendor/mqtt.min.js");
      return falso;
    }
    const protocolo = location.protocol === "https:" ? "wss" : "ws";
    const url = `${protocolo}://${location.hostname || "localhost"}:${CFG.mqtt_puerto_ws || 9001}`;
    const opciones = {
      clientId: `panel-${pagina}-${Math.random().toString(16).slice(2, 8)}`,
      reconnectPeriod: 2000,
      connectTimeout: 5000,
      clean: true,
    };
    if (CFG.mqtt_usuario) {
      opciones.username = CFG.mqtt_usuario;
      opciones.password = CFG.mqtt_clave || "";
    }

    poner("conectando", "Conectando…");
    const cliente = mqtt.connect(url, opciones);
    let suscrito = false;
    cliente.on("connect", () => {
      poner("ok", "Conectado");
      if (!suscrito) {  // al reconectar, mqtt.js vuelve a suscribirse solo
        cliente.subscribe(temas, { qos: 1 });
        suscrito = true;
      }
    });
    cliente.on("reconnect", () => poner("reconectando", "Reconectando…"));
    cliente.on("offline", () => poner("reconectando", "Reconectando…"));
    cliente.on("error", (e) => {
      if (/auth|password|usuario/i.test(e && e.message)) poner("error", "Sin permiso: revisen usuario y clave");
    });
    cliente.on("message", (tema, carga, paquete) => {
      let datos;
      try {
        datos = JSON.parse(carga.toString());
      } catch (e) {
        return;  // no es JSON
      }
      if (!datos || typeof datos !== "object") return;
      try {
        alMensaje(tema, datos, Boolean(paquete && paquete.retain));
      } catch (e) {
        console.error("[paneles] Error con", tema, e);
      }
    });

    /** Publica JSON con ts y fuente, como comun/mqtt_cliente.py. */
    function publicar(tema, datos, retener) {
      const mensaje = { ...datos, ts: Logica.ahoraIso(), fuente: `panel-${pagina}` };
      cliente.publish(tema, JSON.stringify(mensaje), { qos: 1, retain: Boolean(retener) });
      return true;
    }

    return { cliente, publicar };
  }

  /** Pantalla completa (si el navegador lo permite); no pasa nada si no se puede. */
  function pantallaCompleta(activar) {
    try {
      if (activar && !document.fullscreenElement && document.documentElement.requestFullscreen) {
        document.documentElement.requestFullscreen().catch(() => {});
      } else if (!activar && document.fullscreenElement) {
        document.exitFullscreen().catch(() => {});
      }
    } catch (e) {
      /* sin pantalla completa */
    }
  }

  window.Comun = { CFG, el, etiquetaSimulado, etiquetaProvisional, palabraColor, partesTema, conectar, pantallaCompleta };
})();
