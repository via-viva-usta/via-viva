// Umbrales del detector guardados en la flash (NVS, espacio "viaviva"). Ver ajustes.h.
#include "ajustes.h"

#include <Preferences.h>

#include "config.h"
#include "experimentos.h"

static AjustesDetector actuales = ajustesPorDefecto();
static volatile uint32_t version = 1;
static portMUX_TYPE mux = portMUX_INITIALIZER_UNLOCKED;

AjustesDetector ajustesPorDefecto() {
    return {UMBRAL_K_REL, UMBRAL_P2P_MIN_G, UMBRAL_V_MIN_KMH, UMBRAL_REFRACTARIO_S};
}

static bool dentro(float v, float mn, float mx) { return !isnan(v) && v >= mn && v <= mx; }

bool validarAjustes(const AjustesDetector& a, char* motivo, size_t tam) {
    const char* malo = !dentro(a.kRel, AJ_K_MIN, AJ_K_MAX)           ? "K"
                     : !dentro(a.p2pMinG, AJ_P2P_MIN, AJ_P2P_MAX)     ? "piso p2p"
                     : !dentro(a.vMinKmh, AJ_VMIN_MIN, AJ_VMIN_MAX)   ? "velocidad mínima"
                     : !dentro(a.refractarioS, AJ_REFR_MIN, AJ_REFR_MAX) ? "refractario"
                                                                       : nullptr;
    if (malo) snprintf(motivo, tam, "%s fuera de rango", malo);
    return malo == nullptr;
}

static void publicar(const AjustesDetector& a) {
    portENTER_CRITICAL(&mux);
    actuales = a;
    version = version + 1;
    portEXIT_CRITICAL(&mux);
    // Queda en exp_NNN.csv: así se sabe con qué umbrales se detectó cada tramo de la sesión
    registrarExp("AJU", "detector", "k_rel", a.kRel);
    registrarExp("AJU", "detector", "p2p_min_g", a.p2pMinG);
    registrarExp("AJU", "detector", "v_min_kmh", a.vMinKmh);
    registrarExp("AJU", "detector", "refractario_s", a.refractarioS);
}

void cargarAjustes() {
    const AjustesDetector def = ajustesPorDefecto();
    AjustesDetector a = def;
    Preferences nvs;
    if (nvs.begin("viaviva", true)) {   // solo lectura
        a.kRel = nvs.getFloat("k_rel", def.kRel);
        a.p2pMinG = nvs.getFloat("p2p_g", def.p2pMinG);
        a.vMinKmh = nvs.getFloat("vmin_kmh", def.vMinKmh);
        a.refractarioS = nvs.getFloat("refr_s", def.refractarioS);
        nvs.end();
    }
    char motivo[48];
    if (!validarAjustes(a, motivo, sizeof(motivo))) {   // flash con basura o rangos que cambiaron: por defecto
        Serial.printf("[AJUSTES] %s en la flash: se usan los de config.h\n", motivo);
        a = def;
    }
    Serial.printf("[AJUSTES] K=%.2f · piso=%.3f g · v_min=%.1f km/h · refractario=%.2f s%s\n", a.kRel, a.p2pMinG,
                  a.vMinKmh, a.refractarioS,
                  memcmp(&a, &def, sizeof(a)) == 0 ? " (los de config.h)" : " (CAMBIADOS desde la página)");
    publicar(a);
}

bool guardarAjustes(const AjustesDetector& a, char* motivo, size_t tam) {
    if (!validarAjustes(a, motivo, tam)) return false;
    // [VALIDAR EN PLACA] escribir en la flash detiene la caché unos ms: puede salir un overrun puntual en E1
    Preferences nvs;
    if (!nvs.begin("viaviva", false)) {
        snprintf(motivo, tam, "no se pudo abrir la NVS");
        return false;
    }
    nvs.putFloat("k_rel", a.kRel);
    nvs.putFloat("p2p_g", a.p2pMinG);
    nvs.putFloat("vmin_kmh", a.vMinKmh);
    nvs.putFloat("refr_s", a.refractarioS);
    nvs.end();
    publicar(a);
    Serial.printf("[AJUSTES] guardados: K=%.2f · piso=%.3f g · v_min=%.1f km/h · refractario=%.2f s\n", a.kRel,
                  a.p2pMinG, a.vMinKmh, a.refractarioS);
    return true;
}

AjustesDetector leerAjustes(uint32_t* v) {
    portENTER_CRITICAL(&mux);
    const AjustesDetector a = actuales;
    if (v) *v = version;
    portEXIT_CRITICAL(&mux);
    return a;
}

uint32_t versionAjustes() { return version; }
