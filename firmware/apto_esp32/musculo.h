// AD8232: filtros y secuencia guiada del músculo. Van en un encabezado aparte por lo mismo que latidos.h: Arduino
// pone las declaraciones de las funciones al principio del .ino, antes de las estructuras.
#pragma once
#include <math.h>
#include <stdint.h>

// Filtro de segundo orden (biquad). Se usa como pasa altos (quita la deriva lenta y el movimiento) y como notch
// (quita el zumbido de la red eléctrica, 50 Hz en Bolivia, y su armónico de 100 Hz).
struct Biquad {
  float b0, b1, b2, a1, a2;
  float x1 = 0, x2 = 0, y1 = 0, y2 = 0;
  float paso(float x) {
    float y = b0 * x + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2;
    x2 = x1, x1 = x, y2 = y1, y1 = y;
    return y;
  }
  void reiniciar() { x1 = x2 = y1 = y2 = 0; }
};

inline Biquad normalizar(float b0, float b1, float b2, float a0, float a1, float a2) {
  Biquad f;
  f.b0 = b0 / a0, f.b1 = b1 / a0, f.b2 = b2 / a0, f.a1 = a1 / a0, f.a2 = a2 / a0;
  return f;
}

inline Biquad notch(float f0, float fs, float q) {
  float w = 2 * M_PI * f0 / fs, al = sinf(w) / (2 * q), c = cosf(w);
  return normalizar(1, -2 * c, 1, 1 + al, -2 * c, 1 - al);
}

inline Biquad pasaAltos(float fc, float fs) {  // Butterworth
  float w = 2 * M_PI * fc / fs, al = sinf(w) / sqrtf(2), c = cosf(w);
  return normalizar((1 + c) / 2, -(1 + c), (1 + c) / 2, 1 + al, -2 * c, 1 - al);
}

inline Biquad pasaBajos(float fc, float fs) {  // Butterworth
  float w = 2 * M_PI * fc / fs, al = sinf(w) / sqrtf(2), c = cosf(w);
  return normalizar((1 - c) / 2, 1 - c, (1 - c) / 2, 1 + al, -2 * c, 1 - al);
}

// Secuencia guiada (35 s): entre cada orden hay una pausa de 2 s para que la persona alcance a reaccionar.
struct FaseMusculo {
  const char *nombre, *texto;  // texto: como mucho 14 caracteres (lo que entra al lado del contador en la OLED)
  int s;
  bool aprieta;
};
static const FaseMusculo FASES_MUSCULO[] = {
    {"PREPARATE", "Brazo quieto", 5, false}, {"APRIETA", "Puno fuerte", 5, true}, {"ESPERA", "Suelta", 2, false},
    {"DESCANSA", "Brazo suelto", 6, false},  {"ESPERA", "Atento...", 2, false},   {"APRIETA", "Puno fuerte", 5, true},
    {"ESPERA", "Suelta", 2, false},          {"DESCANSA", "Brazo suelto", 8, false}};
static const int N_FASES_MUSCULO = sizeof(FASES_MUSCULO) / sizeof(FASES_MUSCULO[0]);

// Fase en curso a los ms desde el inicio (-1 = terminó), segundos que le quedan y ms que lleva
inline int faseMusculo(uint32_t ms, int &quedan, uint32_t &enFase) {
  uint32_t acum = 0;
  for (int i = 0; i < N_FASES_MUSCULO; i++) {
    uint32_t fin = acum + FASES_MUSCULO[i].s * 1000UL;
    if (ms < fin) {
      quedan = (fin - ms + 999) / 1000;
      enFase = ms - acum;
      return i;
    }
    acum = fin;
  }
  quedan = 0;
  enFase = ms - acum;
  return -1;
}
