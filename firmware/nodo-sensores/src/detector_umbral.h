// Detector por umbrales (línea base pedida por el docente de Arquitectura).
//
// Regla, muestra a muestra (la MISMA que analysis/detector_umbral.py, que se usa para pre-etiquetar recorridos):
//   1. a[n]      = aceleración vertical dinámica (g)
//   2. p2p[n]    = max(a) - min(a) en las últimas N_P2P muestras (cambio de aceleración en ~50 ms)
//   3. rms[n]    = raíz de un promedio exponencial de a² con constante de tiempo TAU_BASE (vibración "normal")
//   4. EVENTO si  velocidad GPS > V_MIN
//              y p2p[n] > K_REL × rms[n-1]     (umbral RELATIVO a la vibración de esa calle)
//              y p2p[n] > P2P_MIN              (piso absoluto: evita disparos con el carro casi quieto)
//              y pasó REFRACTARIO desde el último evento
//   La línea base usa rms[n-1] (antes de agregar la muestra actual) para que el golpe no suba su propio umbral.
#pragma once
#include <math.h>
#include <stdint.h>

struct ParametrosUmbral {
    float vMinKmh = 5.0f;        // por debajo de esto no se detecta (carro detenido o maniobrando en parqueo)
    float kRel = 6.0f;           // veces la vibración de fondo
    float p2pMinG = 0.30f;       // piso absoluto del cambio de aceleración
    float tauBaseS = 2.0f;       // memoria de la línea base
    float ventanaP2PS = 0.05f;   // ventana del cambio de aceleración
    float refractarioS = 1.0f;   // separación mínima entre eventos
};

class DetectorUmbral {
public:
    static constexpr int MAX_P2P = 64;

    void configurar(const ParametrosUmbral& p, float fsHz) {
        p_ = p;
        fs_ = fsHz;
        nP2P_ = (int)lroundf(p.ventanaP2PS * fsHz);
        if (nP2P_ < 2) nP2P_ = 2;
        if (nP2P_ > MAX_P2P) nP2P_ = MAX_P2P;
        alfa_ = 1.0f / (p.tauBaseS * fsHz);
        refractarioMuestras_ = (uint32_t)(p.refractarioS * fsHz);
        reiniciar();
    }

    void reiniciar() {
        cuenta_ = 0;
        llenas_ = 0;
        cabeza_ = 0;
        ms2_ = 0;
        ultimoEvento_ = 0;
        hayEvento_ = false;
    }

    // Procesa una muestra. Devuelve true si dispara un evento en ella.
    bool procesar(float aG, float velocidadKmh) {
        ventana_[cabeza_] = aG;
        cabeza_ = (cabeza_ + 1) % nP2P_;
        if (llenas_ < nP2P_) llenas_++;
        float mx = ventana_[0], mn = ventana_[0];
        for (int i = 1; i < llenas_; i++) {
            if (ventana_[i] > mx) mx = ventana_[i];
            if (ventana_[i] < mn) mn = ventana_[i];
        }
        p2p_ = mx - mn;
        const float rmsAnterior = sqrtf(ms2_);
        const bool calentando = cuenta_ < (uint32_t)(p_.tauBaseS * fs_);   // la línea base aún no es confiable
        bool evento = !calentando && velocidadKmh > p_.vMinKmh && p2p_ > p_.kRel * rmsAnterior &&
                      p2p_ > p_.p2pMinG && (!hayEvento_ || cuenta_ - ultimoEvento_ >= refractarioMuestras_);
        ms2_ += alfa_ * (aG * aG - ms2_);
        if (evento) {
            ultimoEvento_ = cuenta_;
            hayEvento_ = true;
            razon_ = rmsAnterior > 1e-6f ? p2p_ / rmsAnterior : 0.0f;
        }
        cuenta_++;
        return evento;
    }

    float ultimoP2P() const { return p2p_; }
    float lineaBase() const { return sqrtf(ms2_); }
    float razonUltimoEvento() const { return razon_; }   // p2p / rms en el disparo (para la severidad)
    const ParametrosUmbral& parametros() const { return p_; }

private:
    ParametrosUmbral p_;
    float fs_ = 200;
    int nP2P_ = 10;
    float alfa_ = 0.0025f;
    uint32_t refractarioMuestras_ = 200;
    float ventana_[MAX_P2P] = {};
    int cabeza_ = 0, llenas_ = 0;
    float ms2_ = 0, p2p_ = 0, razon_ = 0;
    uint32_t cuenta_ = 0, ultimoEvento_ = 0;
    bool hayEvento_ = false;
};
