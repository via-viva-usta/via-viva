// Umbrales del detector que se pueden cambiar desde la página web y quedan guardados en la flash (NVS).
// Por defecto valen lo de include/config.h (UMBRAL_*). Solo se ajustan los 4 que tiene sentido calibrar en campo;
// τ de la línea base y la ventana del pico a pico se quedan fijos (cambiarlos obliga a reiniciar el detector).
//
// Entre núcleos: la tarea web (núcleo 0) escribe la copia compartida dentro de un spinlock y sube la versión;
// tareaProcesamiento (núcleo 1) ve la versión nueva entre dos bloques, copia los valores y los aplica sin borrar
// la línea base. Así un cambio nunca cae a mitad de una muestra.
#pragma once
#include <Arduino.h>

struct AjustesDetector {
    float kRel, p2pMinG, vMinKmh, refractarioS;
};

AjustesDetector ajustesPorDefecto();
// Revisa los rangos AJ_* de config.h. Si algo está fuera, escribe el motivo y devuelve false.
bool validarAjustes(const AjustesDetector& a, char* motivo, size_t tam);
void cargarAjustes();                              // NVS → memoria (en setup, antes de crear las tareas)
bool guardarAjustes(const AjustesDetector& a, char* motivo, size_t tam);   // valida, guarda en NVS y publica
AjustesDetector leerAjustes(uint32_t* version = nullptr);                  // copia segura desde cualquier núcleo
uint32_t versionAjustes();
