// Tipos compartidos entre tareas y declaración del estado global del nodo.
// Las variables se definen en main.cpp. Todo lo que se comparte entre núcleos va protegido
// por un mutex o viaja por una cola de FreeRTOS.
#pragma once
#include <Arduino.h>

#include "adxl345.h"
#include "esp_task_wdt.h"
#include "esp_timer.h"
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

// Temperatura, humedad, presión y luz (include/ambiente.h). NAN = sin dato.
struct EstadoAmbiente {
    char sensorTH[8] = "ninguno";   // bme280, bmp280 (sin humedad), dht22 o ninguno
    bool luxOk = false;             // hay BH1750
    float tempC = NAN, humPct = NAN, presHpa = NAN, lux = NAN;
    int64_t tUs = 0;                // esp_timer de la última lectura
};

struct FilaAmbiente {               // una línea de ambiente_NNN.csv
    EstadoAmbiente a;
    EstadoGPS g;                    // última fijación: da la hora UTC y el lugar
};

struct EstadoI2C {
    bool mpuOk = false, tofOk = false;
    float giroVertDps = 0, aLongG = 0;
    uint16_t distanciaMm = 0;
    uint32_t usLecturaMpu = 0;   // E4: duración de una lectura I2C de 14 bytes
    Maniobra maniobra = Maniobra::NINGUNA;
    EstadoAmbiente amb;
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

// Estado que muestra la página web
struct EstadoNodo {
    bool adxlOk = false, sdOk = false;
    int sesion = 0;
    uint32_t eventos = 0, etiquetas = 0;
    float muestrasPorSegundo = 0;
    Evento ultimo{};
    bool hayUltimo = false;
    uint32_t sdRemontajes = 0;       // veces que se volvió a montar la microSD tras una falla
    uint32_t sdFallosEscritura = 0;  // escrituras que no se completaron
    uint32_t crudoPerdido = 0;       // bloques que no cupieron en la cola del registro crudo
    int causaReinicio = 0;           // esp_reset_reason() del último arranque
};

// ---- Estado global (definido en main.cpp) ----
extern ADXL345 adxl;
extern EstadoGPS estadoGPS;
extern EstadoI2C estadoI2C;
extern EstadoNodo estadoNodo;
extern SemaphoreHandle_t mutexGPS, mutexI2C, mutexNodo;

// microSD (registro.cpp). TODO acceso a la tarjeta (registro, listado y descarga por la página) toma mutexSD.
// sdGeneracion sube en cada montaje: si cambia, los archivos abiertos antes ya no sirven.
extern SemaphoreHandle_t mutexSD;
extern volatile uint32_t sdGeneracion;
extern volatile bool sdMontada;
bool iniciarSD();                 // primer montaje y elección de la sesión (en setup, antes de crear las tareas)

// Salud del GPS (perifericos.cpp): las escribe solo tareaGPS; enteros de 32 bits = lectura atómica
extern volatile uint32_t gpsBytes, gpsReinicios, gpsUltimoByteMs;

extern Bloque pingPong[2];
extern SemaphoreHandle_t mitadLibre[2];
extern QueueHandle_t colaBloques, colaCrudo, colaEventosSD, colaGpsSD, colaEtiquetas, colaAmbienteSD;
extern TaskHandle_t hAdquisicion;

// ---- Tareas (cada una en su archivo) ----
void tareaAdquisicion(void*);
void tareaProcesamiento(void*);
void tareaGPS(void*);
void tareaI2C(void*);
void tareaRegistro(void*);
void tareaEstadisticas(void*);
void tareaWeb(void*);
void tareaLED(void*);
void IRAM_ATTR isrAdxl();
void registrarEtiqueta(int64_t tUs, const char* tipo, const char* origen);
void iniciarMedicionOcio();

// Watchdog de tareas (esp_task_wdt): cada tarea crítica se suscribe y avisa en cada vuelta de su ciclo.
// Se avisa como máximo una vez cada 500 ms: es barato, pero no gratis (y en e1_polling el ciclo es de 5 ms).
inline void avisarWdt(int64_t& ultimoUs) {
    const int64_t t = esp_timer_get_time();
    if (t - ultimoUs >= 500000) {
        esp_task_wdt_reset();
        ultimoUs = t;
    }
}

// Copias seguras del estado compartido
EstadoGPS copiarGPS();
EstadoI2C copiarI2C();
EstadoNodo copiarNodo();
