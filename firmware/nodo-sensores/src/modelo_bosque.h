// modelo_bosque.h — GENERADO por analysis/entrenar_detector.py el 2026-11-02 con emlearn. NO editar.
// DATOS SINTÉTICOS: este modelo sirve para medir latencia (E2/E3), NO para detectar huecos reales.
// Entradas (float, en este orden): pico_g, rms_g, curtosis, factor_cresta, jerk_max_gps, signo_pico, vel_kmh. Salida: normal, hueco, resalto, impacto_fuerte.
#pragma once
#define BOSQUE_SINTETICO 1



    // !!! This file is generated using emlearn !!!

    #include <stdint.h>
    

static inline int32_t bosque_tree_0(const float *features, int32_t features_length) {
          if (features[0] < 0.236714f) {
              return 0;
          } else {
              if (features[4] < 55.112297f) {
                  return 2;
              } else {
                  if (features[0] < 0.903203f) {
                      return 1;
                  } else {
                      return 3;
                  }
              }
          }
        }
        

static inline int32_t bosque_tree_1(const float *features, int32_t features_length) {
          if (features[2] < 45.597461f) {
              if (features[2] < 6.987072f) {
                  if (features[0] < 0.245408f) {
                      return 0;
                  } else {
                      return 2;
                  }
              } else {
                  return 1;
              }
          } else {
              return 3;
          }
        }
        

static inline int32_t bosque_tree_2(const float *features, int32_t features_length) {
          if (features[3] < 9.601787f) {
              if (features[3] < 5.093645f) {
                  if (features[1] < 0.071808f) {
                      return 0;
                  } else {
                      return 2;
                  }
              } else {
                  return 1;
              }
          } else {
              return 3;
          }
        }
        

static inline int32_t bosque_tree_3(const float *features, int32_t features_length) {
          if (features[4] < 51.270490f) {
              if (features[2] < 3.346814f) {
                  if (features[4] < 20.839127f) {
                      return 0;
                  } else {
                      if (features[4] < 21.110402f) {
                          return 2;
                      } else {
                          return 0;
                      }
                  }
              } else {
                  if (features[5] < 0.000000f) {
                      return 0;
                  } else {
                      if (features[6] < 36.515614f) {
                          return 2;
                      } else {
                          return 0;
                      }
                  }
              }
          } else {
              if (features[3] < 9.386785f) {
                  return 1;
              } else {
                  return 3;
              }
          }
        }
        

static inline int32_t bosque_tree_4(const float *features, int32_t features_length) {
          if (features[0] < 0.244968f) {
              return 0;
          } else {
              if (features[4] < 153.251854f) {
                  if (features[5] < 0.000000f) {
                      return 1;
                  } else {
                      return 2;
                  }
              } else {
                  return 3;
              }
          }
        }
        

static inline int32_t bosque_tree_5(const float *features, int32_t features_length) {
          if (features[4] < 51.083984f) {
              if (features[5] < 0.000000f) {
                  return 0;
              } else {
                  if (features[2] < 3.330798f) {
                      if (features[0] < 0.266758f) {
                          return 0;
                      } else {
                          return 2;
                      }
                  } else {
                      return 2;
                  }
              }
          } else {
              if (features[4] < 151.944229f) {
                  return 1;
              } else {
                  return 3;
              }
          }
        }
        

static inline int32_t bosque_tree_6(const float *features, int32_t features_length) {
          if (features[1] < 0.064684f) {
              return 0;
          } else {
              if (features[5] < 0.000000f) {
                  return 1;
              } else {
                  if (features[3] < 7.277289f) {
                      return 2;
                  } else {
                      return 3;
                  }
              }
          }
        }
        

static inline int32_t bosque_tree_7(const float *features, int32_t features_length) {
          if (features[0] < 0.261969f) {
              return 0;
          } else {
              if (features[4] < 153.251854f) {
                  if (features[2] < 6.987072f) {
                      return 2;
                  } else {
                      return 1;
                  }
              } else {
                  return 3;
              }
          }
        }
        

static inline int32_t bosque_tree_8(const float *features, int32_t features_length) {
          if (features[4] < 51.270490f) {
              if (features[4] < 16.726857f) {
                  if (features[1] < 0.069441f) {
                      return 0;
                  } else {
                      return 2;
                  }
              } else {
                  if (features[2] < 3.359940f) {
                      return 0;
                  } else {
                      if (features[1] < 0.072276f) {
                          return 0;
                      } else {
                          return 2;
                      }
                  }
              }
          } else {
              if (features[0] < 0.891380f) {
                  return 1;
              } else {
                  return 3;
              }
          }
        }
        

static inline int32_t bosque_tree_9(const float *features, int32_t features_length) {
          if (features[2] < 6.987072f) {
              if (features[1] < 0.071142f) {
                  return 0;
              } else {
                  return 2;
              }
          } else {
              if (features[5] < 0.000000f) {
                  return 1;
              } else {
                  return 3;
              }
          }
        }
        

int32_t bosque_predict(const float *features, int32_t features_length) {

        int32_t votes[4] = {0,};
        int32_t _class = -1;

        _class = bosque_tree_0(features, features_length); votes[_class] += 1;
    _class = bosque_tree_1(features, features_length); votes[_class] += 1;
    _class = bosque_tree_2(features, features_length); votes[_class] += 1;
    _class = bosque_tree_3(features, features_length); votes[_class] += 1;
    _class = bosque_tree_4(features, features_length); votes[_class] += 1;
    _class = bosque_tree_5(features, features_length); votes[_class] += 1;
    _class = bosque_tree_6(features, features_length); votes[_class] += 1;
    _class = bosque_tree_7(features, features_length); votes[_class] += 1;
    _class = bosque_tree_8(features, features_length); votes[_class] += 1;
    _class = bosque_tree_9(features, features_length); votes[_class] += 1;
    
        int32_t most_voted_class = -1;
        int32_t most_voted_votes = 0;
        for (int32_t i=0; i<4; i++) {

            if (votes[i] > most_voted_votes) {
                most_voted_class = i;
                most_voted_votes = votes[i];
            }
        }
        return most_voted_class;
    }
    

int bosque_predict_proba(const float *features, int32_t features_length, float *out, int out_length) {

        int32_t _class = -1;

        for (int i=0; i<out_length; i++) {
            out[i] = 0.0f;
        }

        _class = bosque_tree_0(features, features_length); out[_class] += 1.0f;
    _class = bosque_tree_1(features, features_length); out[_class] += 1.0f;
    _class = bosque_tree_2(features, features_length); out[_class] += 1.0f;
    _class = bosque_tree_3(features, features_length); out[_class] += 1.0f;
    _class = bosque_tree_4(features, features_length); out[_class] += 1.0f;
    _class = bosque_tree_5(features, features_length); out[_class] += 1.0f;
    _class = bosque_tree_6(features, features_length); out[_class] += 1.0f;
    _class = bosque_tree_7(features, features_length); out[_class] += 1.0f;
    _class = bosque_tree_8(features, features_length); out[_class] += 1.0f;
    _class = bosque_tree_9(features, features_length); out[_class] += 1.0f;
    
        // compute mean
        for (int i=0; i<out_length; i++) {
            out[i] = out[i] / 10;
        }
        return 0;
    }
    