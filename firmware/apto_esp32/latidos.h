// Tipos de los latidos. Van en un encabezado aparte porque Arduino pone las declaraciones de las funciones
// al principio del .ino, antes de las estructuras, y una función que devuelve Intervalo no compilaría.
#pragma once
#include <stdint.h>

// Intervalo entre latidos aceptado. "contiguo" = el latido anterior también se aceptó, así la diferencia con el
// intervalo anterior sirve para el RMSSD.
struct Intervalo {
  uint32_t t;
  uint16_t ms;
  bool contiguo;
};

// Latido detectado (aceptado o rechazado), para la calidad.
struct Evento {
  uint32_t t;
  bool aceptado;
};
