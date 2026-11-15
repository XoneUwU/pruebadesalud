# PANELes NUEVO — Reconciliación de los ZIP

Archivos originales revisados:

- `paneles.zip`: base de funcionamiento, Python + HTML/CSS/JS (Estación, Tripulación y Tierra).
- `Preguntas de diseño pendientes (1).zip`: exportación fuente de Claude Design con las páginas «Apto Hoy», «Becspace Logo» y «Estación Actual».

## Resultado de coincidencias

- `logica.js` y `paneles/web/logica.js` son **idénticos byte a byte** (SHA-256: `fba6f4f477267c23bfcaaf41c68461b9c2e2b14a4502801d58f75aa1fec963df`).
- El resto de archivos de código no son equivalentes directos: Claude Design exporta páginas `.dc.html` ejecutadas con su soporte propio; Paneles usa módulos JS y el servidor Python con MQTT/MongoDB. **No se deben reemplazar por copia directa**.
- `referencias_claude/` conserva los originales de diseño con sus dependencias. El código activo permanece en `web/`.

## Cambios integrados en esta copia

1. La base es el contenido íntegro de `paneles.zip` (no se elimina ninguna de sus pantallas ni scripts).
2. Se incorpora en `web/assets/fondo-luna.png` el recurso lunar de Claude Design.
3. `web/fondo.js` emplea el fondo claro lunar de la exportación más reciente: cielo claro, estrellas, constelaciones, salida de la Tierra, alunizador y horizonte lunar; **el modo oscuro original permanece intacto**.
4. Se conservan los tres archivos `.dc.html`, `support.js`, `datos-demo.js`, `servicios.js`, `logica.js` y el sistema de diseño de Claude en `referencias_claude/`, separadamente de los archivos operativos.
5. Las capturas de pantalla y las imágenes duplicadas de `uploads/` no se duplican en el ZIP consolidado: no contienen código ni son requeridas por la ejecución. Se mantienen los recursos visuales **realmente referenciados por el código**.
6. La paginación del historial ya está implementada en `web/estacion.js` con `POR_PAGINA = 20`; se conserva sin modificar.

## Instrucciones de integración

Coloca la carpeta `paneles/` del ZIP nuevo dentro de la raíz de tu repositorio `pruebadesalud/`, reemplazando **solo** la carpeta `paneles/` tras guardar una copia o crear una rama Git. No copies `referencias_claude/` como si fuera la interfaz activa. El archivo principal de la estación es `paneles/web/estacion.html`.

Desde la **raíz del repositorio completo**, con tus módulos `comun/`, `registrador/`, etc. y los archivos `config.env` correspondientes, ejecuta:

```powershell
python paneles\servidor.py
```

Luego abre: `http://localhost:8080/estacion.html`.

> **Alcance:** Estos dos ZIP NO contienen todo el backend de `pruebadesalud`. Por ejemplo, `paneles/servidor.py` importa `comun.config` del nivel superior y utiliza MongoDB y MQTT cuando están configurados. El ZIP consolidado sí contiene todo el código de los paneles y fuentes de diseño, pero **no sustituye** los módulos externos que no fueron adjuntados.

## Verificaciones realizadas

Se comprobaron la identidad del archivo común, la sintaxis de los JavaScript activos y la compilación sintáctica de los scripts Python. Las pruebas de integración contra dispositivos, broker MQTT y registrador requieren el repositorio principal y sus servicios.
