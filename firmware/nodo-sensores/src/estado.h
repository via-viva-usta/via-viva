// Tipos compartidos entre tareas y declaración del estado global del nodo.
// Las variables se definen en main.cpp. Todo lo que se comparte entre núcleos va protegido
// por un mutex o viaja por una cola de FreeRTOS.
#pragma once
#include <Arduino.h>

#include "adxl345.h"
#include "caracteristicas.h"
#include "config.h"
#include "maniobras.h"

struct Bloque {                  // una mitad del búfer ping-pong
    int64_t tUltimaUs;           // hora (esp_timer) de la muestra más reciente del bloque
    uint8_t n;
    MuestraAcc m[TAM_BLOQUE + 1];  // +1: la FIFO puede tener 33 datos (32 + registros de salida)
};

struct EstadoGPS {
    bool valido = false;
    double lat = 0, lon = 0;
    float velKmh = 0, hdop = 99;
    float decelMs2 = 0;          // caída de velocidad entre fijaciones (positivo = frenando)
    uint8_t satelites = 0;
    char utc[24] = "";           // hora UTC de la última fijación, ISO 8601
    int64_t tFixUs = 0;          // esp_timer cuando se completó esa fijación
};

struct EstadoI2C {
    bool mpuOk = false, tofOk = false;
    float giroVertDps = 0, aLongG = 0;
    uint16_t distanciaMm = 0;
    uint32_t usLecturaMpu = 0;   // E4: duración de una lectura I2C de 14 bytes
    Maniobra maniobra = Maniobra::NINGUNA;
};

struct Evento {
    uint32_t id;
    int64_t tUs;
    ClaseEvento clase;
    float severidad, confianza;
    Caracteristicas c;
    float razonUmbral;           // p2p / línea base en el disparo
    Maniobra maniobra;           // maniobra activa en ese momento (NINGUNA si no había)
    EstadoGPS gps;               // copia de la última fijación
    int32_t msDesdeFix;          // para interpolar posición y hora en el ETL
    uint16_t distanciaMm;
};

struct Etiqueta {
    int64_t tUs;
    char tipo[12];               // hueco, resalto, otro (página web) o boton (pulsador)
    char origen[8];              // web o boton
};

struct RespuestaFoto {
    uint32_t idEvento;
    char texto[48];
};

// Estado que muestra la página web
struct EstadoNodo {
    bool adxlOk = false, sdOk = false, camOk = false;
    int sesion = 0;
    uint32_t eventos = 0, etiquetas = 0;
    float muestrasPorSegundo = 0;
    Evento ultimo{};
    bool hayUltimo = false;
};

// ---- Estado global (definido en main.cpp) ----
extern ADXL345 adxl;
extern EstadoGPS estadoGPS;
extern EstadoI2C estadoI2C;
extern EstadoNodo estadoNodo;
extern SemaphoreHandle_t mutexGPS, mutexI2C, mutexNodo;

extern Bloque pingPong[2];
extern SemaphoreHandle_t mitadLibre[2];
extern QueueHandle_t colaBloques, colaCrudo, colaEventosSD, colaCamara, colaGpsSD, colaEtiquetas, colaFotosSD;
extern TaskHandle_t hAdquisicion;

// ---- Tareas (cada una en su archivo) ----
void tareaAdquisicion(void*);
void tareaProcesamiento(void*);
void tareaGPS(void*);
void tareaI2C(void*);
void tareaCamara(void*);
void tareaRegistro(void*);
void tareaEstadisticas(void*);
void tareaWeb(void*);
void IRAM_ATTR isrAdxl();
void registrarEtiqueta(int64_t tUs, const char* tipo, const char* origen);
void iniciarMedicionOcio();

// Copias seguras del estado compartido
EstadoGPS copiarGPS();
EstadoI2C copiarI2C();
EstadoNodo copiarNodo();
