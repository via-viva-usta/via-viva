// Maniobras con el MPU-6050 (pedido del docente): giro a la izquierda, giro a la derecha y frenada brusca.
// Sirven para NO confundir estas maniobras con huecos: un evento del acelerómetro que cae durante una
// maniobra se marca como tal.
//
// Montaje supuesto (docs/montaje.md): eje X del MPU-6050 hacia adelante del carro, eje Z hacia arriba.
// Si se monta distinto, cambiar EJE_* y SIGNO_* en config.h.
//
// Reglas (las mismas de analysis/detector_umbral.py):
//   giro:    |velocidad angular en Z, filtrada| > GIRO_MIN durante >= DUR_GIRO s, con velocidad > V_MIN.
//            Positivo (antihorario visto desde arriba, regla de la mano derecha con Z arriba) = IZQUIERDA.
//   frenada: aceleración longitudinal filtrada < -FRENADA_MIN durante >= DUR_FRENADA s,
//            o caída de la velocidad GPS más rápida que FRENADA_GPS m/s².
#pragma once
#include <math.h>
#include <stdint.h>

enum class Maniobra : uint8_t { NINGUNA = 0, GIRO_IZQUIERDA, GIRO_DERECHA, FRENADA_BRUSCA };

inline const char* nombreManiobra(Maniobra m) {
    switch (m) {
        case Maniobra::GIRO_IZQUIERDA: return "giro_izquierda";
        case Maniobra::GIRO_DERECHA: return "giro_derecha";
        case Maniobra::FRENADA_BRUSCA: return "frenada_brusca";
        default: return "ninguna";
    }
}

struct ParametrosManiobra {
    float giroMinDps = 15.0f;        // °/s
    float durGiroS = 1.0f;
    float frenadaMinG = 0.30f;       // g
    float durFrenadaS = 0.5f;
    float frenadaGpsMs2 = 2.5f;      // m/s²
    float vMinKmh = 5.0f;
    float tauFiltroS = 0.25f;        // pasa-bajos de primer orden sobre giro y aceleración
};

class DetectorManiobras {
public:
    void configurar(const ParametrosManiobra& p, float fsHz) {
        p_ = p;
        fs_ = fsHz;
        alfa_ = 1.0f / (p.tauFiltroS * fsHz + 1.0f);
    }

    // Una muestra del MPU-6050: velocidad angular de giro (°/s, eje vertical) y aceleración longitudinal (g).
    // Devuelve la maniobra que EMPIEZA en esta muestra (o NINGUNA). activa() dice si hay una en curso.
    Maniobra procesar(float giroDps, float aLongG, float velocidadKmh, float decelGpsMs2) {
        giroF_ += alfa_ * (giroDps - giroF_);
        aLongF_ += alfa_ * (aLongG - aLongF_);
        const bool enMovimiento = velocidadKmh > p_.vMinKmh;

        Maniobra candidata = Maniobra::NINGUNA;
        float duracionNecesaria = 0;
        if (enMovimiento && giroF_ > p_.giroMinDps) {
            candidata = Maniobra::GIRO_IZQUIERDA;
            duracionNecesaria = p_.durGiroS;
        } else if (enMovimiento && giroF_ < -p_.giroMinDps) {
            candidata = Maniobra::GIRO_DERECHA;
            duracionNecesaria = p_.durGiroS;
        } else if (aLongF_ < -p_.frenadaMinG || decelGpsMs2 > p_.frenadaGpsMs2) {
            candidata = Maniobra::FRENADA_BRUSCA;
            duracionNecesaria = decelGpsMs2 > p_.frenadaGpsMs2 ? 0.0f : p_.durFrenadaS;
        }

        if (candidata != enCurso_) {
            enCurso_ = candidata;
            muestras_ = 0;
            reportada_ = false;
        } else {
            muestras_++;
        }
        actual_ = (enCurso_ != Maniobra::NINGUNA && muestras_ >= duracionNecesaria * fs_) ? enCurso_ : Maniobra::NINGUNA;
        if (actual_ != Maniobra::NINGUNA && !reportada_) {
            reportada_ = true;
            return actual_;
        }
        return Maniobra::NINGUNA;
    }

    Maniobra activa() const { return actual_; }
    float giroFiltrado() const { return giroF_; }
    float aLongFiltrada() const { return aLongF_; }

private:
    ParametrosManiobra p_;
    float fs_ = 50, alfa_ = 0.07f;
    float giroF_ = 0, aLongF_ = 0;
    Maniobra enCurso_ = Maniobra::NINGUNA, actual_ = Maniobra::NINGUNA;
    uint32_t muestras_ = 0;
    bool reportada_ = false;
};
