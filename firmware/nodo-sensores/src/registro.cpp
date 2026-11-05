// Núcleo 0: registro en la microSD. Una sesión por arranque: crudo_NNN.csv, eventos_NNN.csv, gps_NNN.csv,
// etiquetas_NNN.csv, ambiente_NNN.csv y exp_NNN.csv. El crudo y el GPS son datos de análisis (van a data/raw/,
// no se publican); a la base final solo llegan eventos.
//
// Robustez:
//   * Número de sesión único: contador en la flash (NVS, sobrevive a los reinicios) y además nunca se pisa un archivo
//     que ya exista en la tarjeta (si el contador se borró, se salta al siguiente número libre).
//   * Si la tarjeta no monta al arrancar, se reintenta cada SD_REINTENTO_MS (10 s); lo que llegue mientras tanto se pierde.
//   * Si una escritura falla (tarjeta sacada, contacto flojo), se cierran los archivos, se desmonta y se vuelve a montar;
//     la sesión SIGUE en los mismos archivos (se abren para agregar al final, sin repetir el encabezado).
//   * Corte de energía: los datos se fuerzan a la tarjeta cada SD_FLUSH_MS (1 s). Se pierde como máximo lo escrito
//     desde el último flush (≤ 1 s) más lo que esté esperando en las colas (normalmente < 0,2 s; en el peor caso
//     16 bloques del crudo = 2,5 s). Un corte justo mientras se escribe la FAT puede dañar el último archivo:
//     pasarle chkdsk a la tarjeta en el PC antes de copiar.
//   * Toda operación con la tarjeta toma mutexSD: la página web también la lee (lista y descarga los CSV por Wi-Fi).
#include <Preferences.h>
#include <SD.h>
#include <SPI.h>
#include <stdarg.h>

#include "estado.h"
#include "experimentos.h"
#include "pines.h"

SemaphoreHandle_t mutexSD;
volatile uint32_t sdGeneracion = 0;
volatile bool sdMontada = false;

static SPIClass spiSD(HSPI);     // HSPI (SPI2) por la matriz GPIO, separado del VSPI del acelerómetro
static int sesionActual = 0;

enum Archivo { CRUDO, EVENTOS, GPS, ETIQUETAS, AMBIENTE, EXP, N_ARCHIVOS };
static const char* const PREFIJO[N_ARCHIVOS] = {"crudo", "eventos", "gps", "etiquetas", "ambiente", "exp"};
static const char* const ENCABEZADO[N_ARCHIVOS] = {
    "t_us,ax,ay,az",
    "id,t_us,clase,maniobra,razon_umbral,severidad,confianza,pico_g,rms_g,curtosis,factor_cresta,"
    "jerk_max_gps,gps_valido,lat,lon,vel_kmh,hdop,utc_fix,ms_desde_fix,distancia_mm",
    "t_us,utc,lat,lon,vel_kmh,hdop,satelites",
    "t_us,utc_fix,ms_desde_fix,tipo,origen",
    // utc_fix + ms_desde_fix = hora UTC de la lectura (Colombia = UTC-5); utc vacío si el GPS aún no da hora
    "t_us,utc_fix,ms_desde_fix,gps_valido,lat,lon,sensor_th,temperatura_c,humedad_pct,presion_hpa,lux",
    "t_ms,experimento,condicion,variable,valor",
};

// Monta la tarjeta (llamar con mutexSD tomado, o antes de crear las tareas).
static bool montar() {
    SD.end();   // no hace nada si no estaba montada
    const bool ok = SD.begin(PIN_SD_CS, spiSD, SPI_SD_HZ, "/sd", SD_MAX_ARCHIVOS);
    if (ok) sdGeneracion++;
    sdMontada = ok;
    return ok;
}

// Siguiente número de sesión: contador en NVS + 1, saltando los que ya tengan archivos en la tarjeta.
static int elegirSesion() {
    Preferences nvs;
    nvs.begin("viaviva", false);
    uint32_t s = nvs.getUInt("sesion", 0);
    char crudo[32], eventos[32];
    do {
        s++;
        snprintf(crudo, sizeof(crudo), "/crudo_%03lu.csv", (unsigned long)s);
        snprintf(eventos, sizeof(eventos), "/eventos_%03lu.csv", (unsigned long)s);
    } while ((SD.exists(crudo) || SD.exists(eventos)) && s < 99999);
    nvs.putUInt("sesion", s);   // escribe en la flash: por eso se hace en setup, antes de arrancar la adquisición
    nvs.end();
    return (int)s;
}

bool iniciarSD() {
    mutexSD = xSemaphoreCreateMutex();
    spiSD.begin(PIN_SD_SCK, PIN_SD_MISO, PIN_SD_MOSI, PIN_SD_CS);
    if (montar()) sesionActual = elegirSesion();
    return sdMontada;
}

// Abre los 6 archivos de la sesión. Si ya existen (remontaje), se agrega al final sin repetir el encabezado.
static bool abrirSesion(File f[]) {
    bool todos = true;
    for (int i = 0; i < N_ARCHIVOS; i++) {
        char ruta[32];
        snprintf(ruta, sizeof(ruta), "/%s_%03d.csv", PREFIJO[i], sesionActual);
        if (SD.exists(ruta)) {
            f[i] = SD.open(ruta, FILE_APPEND);
        } else {
            f[i] = SD.open(ruta, FILE_WRITE);
            if (f[i]) f[i].println(ENCABEZADO[i]);
        }
        todos = todos && f[i];
    }
    return todos;
}

static void cerrarSesion(File f[]) {
    for (int i = 0; i < N_ARCHIVOS; i++)
        if (f[i]) f[i].close();
}

// Escritura con formato que avisa si la tarjeta no aceptó todos los bytes.
static bool falloEscritura = false;

static void escribir(File& f, const char* texto, size_t len) {
    if (len && f.write((const uint8_t*)texto, len) != len) falloEscritura = true;
}

static void escribirf(File& f, const char* formato, ...) {
    static char linea[320];
    va_list args;
    va_start(args, formato);
    int len = vsnprintf(linea, sizeof(linea), formato, args);
    va_end(args);
    if (len < 0) return;
    if (len >= (int)sizeof(linea)) len = sizeof(linea) - 1;
    escribir(f, linea, len);
}

static void publicarSD(bool lista, uint32_t fallos) {
    if (xSemaphoreTake(mutexNodo, pdMS_TO_TICKS(5)) == pdTRUE) {
        estadoNodo.sdOk = lista;
        estadoNodo.sesion = sesionActual;
        estadoNodo.sdRemontajes = sdGeneracion > 1 ? sdGeneracion - 1 : 0;
        estadoNodo.sdFallosEscritura = fallos;
        xSemaphoreGive(mutexNodo);
    }
}

void tareaRegistro(void*) {
    esp_task_wdt_add(nullptr);
    int64_t wdt = 0;
    File f[N_ARCHIVOS];
    bool lista = false;                  // montada y con los archivos de la sesión abiertos
    uint32_t fallos = 0;
    uint32_t ultimoIntento = millis() - SD_REINTENTO_MS;   // el primer intento es de una vez
    uint32_t ultimoFlush = millis();

    static Bloque b;
    static char bloqueTexto[TAM_BLOQUE * 40 + 40];   // un bloque del crudo se escribe de una sola vez
    Evento ev;
    EstadoGPS g;
    Etiqueta et;
    FilaAmbiente fa;
    FilaExp fe;

    for (;;) {
        avisarWdt(wdt);

        // ---- Montaje (al arrancar sin tarjeta, o después de una falla) ----
        if (!lista && millis() - ultimoIntento >= SD_REINTENTO_MS) {
            ultimoIntento = millis();
            if (xSemaphoreTake(mutexSD, pdMS_TO_TICKS(1000)) == pdTRUE) {
                if (sdMontada || montar()) {
                    if (sesionActual == 0) sesionActual = elegirSesion();
                    lista = abrirSesion(f);
                    if (!lista) {
                        cerrarSesion(f);
                        SD.end();
                        sdMontada = false;
                    }
                }
                xSemaphoreGive(mutexSD);
            }
            if (lista) Serial.printf("[SD] sesión %03d (montaje #%lu)\n", sesionActual, (unsigned long)sdGeneracion);
            else Serial.printf("[SD] no monta; reintento en %lu s\n", (unsigned long)(SD_REINTENTO_MS / 1000));
            publicarSD(lista, fallos);
            avisarWdt(wdt);
        }

        // Si la página está leyendo la tarjeta, los datos esperan en las colas (crudo: 16 bloques = 2,5 s)
        const bool conSD = lista && xSemaphoreTake(mutexSD, pdMS_TO_TICKS(100)) == pdTRUE;
        if (lista && !conSD) {
            vTaskDelay(pdMS_TO_TICKS(10));
            continue;
        }
        falloEscritura = false;

        while (xQueueReceive(colaCrudo, &b, 0) == pdTRUE) {
            size_t len = 0;
            for (int k = 0; conSD && k < b.n; k++) {
                const int64_t t = b.tUltimaUs - (int64_t)(b.n - 1 - k) * PERIODO_US;
                len += snprintf(bloqueTexto + len, sizeof(bloqueTexto) - len, "%lld,%d,%d,%d\n",
                                (long long)t, b.m[k].x, b.m[k].y, b.m[k].z);
                if (len >= sizeof(bloqueTexto)) len = sizeof(bloqueTexto) - 1;
            }
            if (conSD) escribir(f[CRUDO], bloqueTexto, len);
        }
        while (xQueueReceive(colaEventosSD, &ev, 0) == pdTRUE) {
            Serial.printf("[EVENTO] #%lu %s pico=%.2f g razón=%.1f maniobra=%s gps=%s\n", (unsigned long)ev.id,
                          nombreClase(ev.clase), ev.c.pico, ev.razonUmbral, nombreManiobra(ev.maniobra),
                          ev.gps.valido ? "sí" : "no");
            if (conSD) {
                escribirf(f[EVENTOS],
                          "%lu,%lld,%s,%s,%.2f,%.3f,%.3f,%.4f,%.4f,%.3f,%.3f,%.1f,%d,%.7f,%.7f,%.1f,%.1f,%s,%ld,%u\n",
                          (unsigned long)ev.id, (long long)ev.tUs, nombreClase(ev.clase), nombreManiobra(ev.maniobra),
                          ev.razonUmbral, ev.severidad, ev.confianza, ev.c.pico, ev.c.rms, ev.c.curtosis,
                          ev.c.factorCresta, ev.c.jerkMax, ev.gps.valido, ev.gps.lat, ev.gps.lon, ev.gps.velKmh,
                          ev.gps.hdop, ev.gps.utc, (long)ev.msDesdeFix, ev.distanciaMm);
            }
        }
        while (xQueueReceive(colaGpsSD, &g, 0) == pdTRUE) {
            if (conSD) escribirf(f[GPS], "%lld,%s,%.7f,%.7f,%.1f,%.1f,%u\n", (long long)g.tFixUs, g.utc, g.lat, g.lon,
                                 g.velKmh, g.hdop, g.satelites);
        }
        while (xQueueReceive(colaEtiquetas, &et, 0) == pdTRUE) {
            const EstadoGPS copia = copiarGPS();
            const long ms = copia.tFixUs ? (long)((et.tUs - copia.tFixUs) / 1000) : 0;
            Serial.printf("[ETIQUETA] %s (%s) t=%lld us\n", et.tipo, et.origen, (long long)et.tUs);
            if (conSD) escribirf(f[ETIQUETAS], "%lld,%s,%ld,%s,%s\n", (long long)et.tUs, copia.utc, ms, et.tipo,
                                 et.origen);
            if (xSemaphoreTake(mutexNodo, pdMS_TO_TICKS(5)) == pdTRUE) {
                estadoNodo.etiquetas++;
                xSemaphoreGive(mutexNodo);
            }
        }
        while (xQueueReceive(colaAmbienteSD, &fa, 0) == pdTRUE) {
            const long ms = fa.g.tFixUs ? (long)((fa.a.tUs - fa.g.tFixUs) / 1000) : 0;
            // NAN va como celda vacía para que pandas lea el CSV sin errores
            char t[12] = "", h[12] = "", p[12] = "", l[12] = "";
            if (!isnan(fa.a.tempC)) snprintf(t, sizeof(t), "%.2f", fa.a.tempC);
            if (!isnan(fa.a.humPct)) snprintf(h, sizeof(h), "%.1f", fa.a.humPct);
            if (!isnan(fa.a.presHpa)) snprintf(p, sizeof(p), "%.2f", fa.a.presHpa);
            if (!isnan(fa.a.lux)) snprintf(l, sizeof(l), "%.1f", fa.a.lux);
            if (conSD) escribirf(f[AMBIENTE], "%lld,%s,%ld,%d,%.7f,%.7f,%s,%s,%s,%s,%s\n", (long long)fa.a.tUs,
                                 fa.g.utc, ms, fa.g.valido, fa.g.lat, fa.g.lon, fa.a.sensorTH, t, h, p, l);
        }
        while (xQueueReceive(colaExp, &fe, 0) == pdTRUE) {
            if (conSD) escribirf(f[EXP], "%lu,%s,%s,%s,%.4f\n", (unsigned long)fe.tMs, fe.experimento, fe.condicion,
                                 fe.variable, fe.valor);
        }
        if (conSD && millis() - ultimoFlush >= SD_FLUSH_MS) {   // como máximo se pierde ~1 s si se corta la energía
            for (int i = 0; i < N_ARCHIVOS; i++) f[i].flush();
            ultimoFlush = millis();
            publicarSD(lista, fallos);
        }
        if (conSD) {
            if (falloEscritura) {   // tarjeta sacada o con mal contacto: desmontar y volver a montar enseguida
                fallos++;
                cerrarSesion(f);
                SD.end();
                sdMontada = false;
                lista = false;
                ultimoIntento = millis() - SD_REINTENTO_MS;
                Serial.println("[SD] FALLÓ una escritura: se desmonta y se vuelve a montar");
            }
            xSemaphoreGive(mutexSD);
            if (!lista) publicarSD(lista, fallos);
        }
        vTaskDelay(pdMS_TO_TICKS(10));
    }
}
