// Núcleo 0: registro en la microSD. Una sesión por arranque: crudo_NNN.csv, eventos_NNN.csv, gps_NNN.csv,
// etiquetas_NNN.csv y fotos_NNN.csv. El crudo y el GPS son datos de análisis (van a data/raw/, no se publican);
// a la base final solo llegan eventos.
#include <SD.h>

#include "estado.h"

static File abrirSiguiente(const char* prefijo, int sesion, const char* encabezado) {
    char ruta[32];
    snprintf(ruta, sizeof(ruta), "/%s_%03d.csv", prefijo, sesion);
    File f = SD.open(ruta, FILE_WRITE);
    if (f) f.println(encabezado);
    return f;
}

void tareaRegistro(void*) {
    const bool sdOk = copiarNodo().sdOk;
    int sesion = 0;
    File fCrudo, fEventos, fGps, fEtiq, fFotos;
    if (sdOk) {
        char ruta[32];
        do {
            snprintf(ruta, sizeof(ruta), "/crudo_%03d.csv", ++sesion);
        } while (SD.exists(ruta) && sesion < 999);
        Serial.printf("[SD] sesión %03d\n", sesion);
        fCrudo = abrirSiguiente("crudo", sesion, "t_us,ax,ay,az");
        fEventos = abrirSiguiente("eventos", sesion,
            "id,t_us,clase,maniobra,razon_umbral,severidad,confianza,pico_g,rms_g,curtosis,factor_cresta,"
            "jerk_max_gps,gps_valido,lat,lon,vel_kmh,hdop,utc_fix,ms_desde_fix,distancia_mm");
        fGps = abrirSiguiente("gps", sesion, "t_us,utc,lat,lon,vel_kmh,hdop,satelites");
        fEtiq = abrirSiguiente("etiquetas", sesion, "t_us,utc_fix,ms_desde_fix,tipo,origen");
        fFotos = abrirSiguiente("fotos", sesion, "id_evento,respuesta");
        if (xSemaphoreTake(mutexNodo, pdMS_TO_TICKS(5)) == pdTRUE) {
            estadoNodo.sesion = sesion;
            xSemaphoreGive(mutexNodo);
        }
    }

    static Bloque b;
    Evento ev;
    EstadoGPS g;
    Etiqueta et;
    RespuestaFoto rf;
    uint32_t ultimoFlush = millis();
    char linea[64];

    for (;;) {
        while (xQueueReceive(colaCrudo, &b, 0) == pdTRUE) {
            for (int k = 0; sdOk && k < b.n; k++) {
                const int64_t t = b.tUltimaUs - (int64_t)(b.n - 1 - k) * PERIODO_US;
                const int len = snprintf(linea, sizeof(linea), "%lld,%d,%d,%d\n",
                                         (long long)t, b.m[k].x, b.m[k].y, b.m[k].z);
                fCrudo.write((const uint8_t*)linea, len);
            }
        }
        while (xQueueReceive(colaEventosSD, &ev, 0) == pdTRUE) {
            Serial.printf("[EVENTO] #%lu %s pico=%.2f g razón=%.1f maniobra=%s gps=%s\n", (unsigned long)ev.id,
                          nombreClase(ev.clase), ev.c.pico, ev.razonUmbral, nombreManiobra(ev.maniobra),
                          ev.gps.valido ? "sí" : "no");
            if (sdOk) {
                fEventos.printf("%lu,%lld,%s,%s,%.2f,%.3f,%.3f,%.4f,%.4f,%.3f,%.3f,%.1f,%d,%.7f,%.7f,%.1f,%.1f,%s,%ld,%u\n",
                                (unsigned long)ev.id, (long long)ev.tUs, nombreClase(ev.clase),
                                nombreManiobra(ev.maniobra), ev.razonUmbral, ev.severidad, ev.confianza, ev.c.pico,
                                ev.c.rms, ev.c.curtosis, ev.c.factorCresta, ev.c.jerkMax, ev.gps.valido, ev.gps.lat,
                                ev.gps.lon, ev.gps.velKmh, ev.gps.hdop, ev.gps.utc, (long)ev.msDesdeFix,
                                ev.distanciaMm);
            }
        }
        while (xQueueReceive(colaGpsSD, &g, 0) == pdTRUE) {
            if (sdOk) fGps.printf("%lld,%s,%.7f,%.7f,%.1f,%.1f,%u\n", (long long)g.tFixUs, g.utc, g.lat, g.lon,
                                  g.velKmh, g.hdop, g.satelites);
        }
        while (xQueueReceive(colaEtiquetas, &et, 0) == pdTRUE) {
            const EstadoGPS copia = copiarGPS();
            const long ms = copia.tFixUs ? (long)((et.tUs - copia.tFixUs) / 1000) : 0;
            Serial.printf("[ETIQUETA] %s (%s) t=%lld us\n", et.tipo, et.origen, (long long)et.tUs);
            if (sdOk) fEtiq.printf("%lld,%s,%ld,%s,%s\n", (long long)et.tUs, copia.utc, ms, et.tipo, et.origen);
            if (xSemaphoreTake(mutexNodo, pdMS_TO_TICKS(5)) == pdTRUE) {
                estadoNodo.etiquetas++;
                xSemaphoreGive(mutexNodo);
            }
        }
        while (xQueueReceive(colaFotosSD, &rf, 0) == pdTRUE) {
            Serial.printf("[CAM] evento #%lu → %s\n", (unsigned long)rf.idEvento, rf.texto);
            if (sdOk) fFotos.printf("%lu,%s\n", (unsigned long)rf.idEvento, rf.texto);
        }
        if (sdOk && millis() - ultimoFlush > 1000) {   // como máximo se pierde 1 s si se corta la energía
            fCrudo.flush(); fEventos.flush(); fGps.flush(); fEtiq.flush(); fFotos.flush();
            ultimoFlush = millis();
        }
        vTaskDelay(pdMS_TO_TICKS(10));
    }
}
