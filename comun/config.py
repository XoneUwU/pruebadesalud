"""Lee config.env (en la raíz del proyecto), luego config.local.env (si existe) y deja sobrescribir con variables
de entorno.

config.env va en Git con valores de ejemplo y SIN claves. Las claves (MQTT_PASS, MQTT_PASS_LECTURA...) y los valores
de cada laptop (la URL de DroidCam en CAMARA, la IP del broker...) van en config.local.env, que no se sube a Git.
"""
import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
_ARCHIVO = RAIZ / "config.env"
_ARCHIVO_LOCAL = RAIZ / "config.local.env"  # no se sube a Git: claves y valores de esta laptop


def _leer_archivo(ruta: Path) -> dict:
    valores = {}
    if not ruta.exists():
        return valores
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        valores[clave.strip()] = valor.strip()
    return valores


_VALORES = {**_leer_archivo(_ARCHIVO), **_leer_archivo(_ARCHIVO_LOCAL)}


def get(clave: str, defecto: str = "") -> str:
    """Devuelve el valor de la variable de entorno, o el de config.env, o el defecto."""
    valor = os.environ.get(clave)
    if valor is None or valor == "":
        valor = _VALORES.get(clave, "")
    return valor if valor != "" else defecto


def get_int(clave: str, defecto: int) -> int:
    try:
        return int(get(clave, str(defecto)))
    except ValueError:
        return defecto


def get_float(clave: str, defecto: float) -> float:
    """Número con decimales; acepta punto o coma (2.6 o 2,6)."""
    try:
        return float(get(clave, str(defecto)).replace(",", "."))
    except ValueError:
        return defecto


def ruta(clave: str, defecto: str = "") -> Path | None:
    """Ruta relativa a la raíz del proyecto (o absoluta si así se escribió)."""
    valor = get(clave, defecto)
    if not valor:
        return None
    p = Path(valor)
    return p if p.is_absolute() else RAIZ / p
