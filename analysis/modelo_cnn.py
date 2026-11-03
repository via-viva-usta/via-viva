"""Red 1D pequeña para clasificar ventanas de aceleración, su cuantización int8 y su exportación a C.

Arquitectura (sin relleno):
  entrada 128 muestras (|a| - 1 g, 200 Hz, 0,64 s centrados en el disparo)
  conv1: 1→8 canales, núcleo 7, paso 2 → 61 ; ReLU
  conv2: 8→16 canales, núcleo 5, paso 2 → 29 ; ReLU
  promedio global → 16
  densa: 16 → 4 clases (normal, hueco, resalto, impacto_fuerte)

Cuantización int8 simétrica por tensor (post-entrenamiento):
  pesos:        w_q = round(w / s_w),  s_w = max|w| / 127
  activaciones: x_q = round(x / s_x),  s_x = máximo observado en datos de calibración / 127
  capa:         acc (int32) = Σ w_q·x_q + b_q,  b_q = round(b / (s_w·s_x));  y_q = clamp(round(acc · M)),  M = s_w·s_x / s_y
El redondeo es floor(v + 0,5) tanto aquí como en C, para que Python y el ESP32 den exactamente lo mismo.
"""
from __future__ import annotations

import numpy as np

CLASES = ["normal", "hueco", "resalto", "impacto_fuerte"]
L_ENTRADA = 128
C1, K1, P1 = 8, 7, 2
C2, K2, P2 = 16, 5, 2
L1 = (L_ENTRADA - K1) // P1 + 1
L2 = (L1 - K2) // P2 + 1


def red_torch():
    import torch.nn as nn

    class Red(nn.Module):
        def __init__(self):
            super().__init__()
            self.c1 = nn.Conv1d(1, C1, K1, stride=P1)
            self.c2 = nn.Conv1d(C1, C2, K2, stride=P2)
            self.d = nn.Linear(C2, len(CLASES))

        def forward(self, x):
            x = self.c1(x).relu()
            x = self.c2(x).relu()
            return self.d(x.mean(dim=2))

    return Red()


def entrenar(X: np.ndarray, y: np.ndarray, epocas: int = 80, semilla: int = 0):
    """X: (n, 128) en g; y: índices de clase. Devuelve los pesos en numpy."""
    import torch
    torch.manual_seed(semilla)
    red = red_torch()
    conteo = np.bincount(y, minlength=len(CLASES)).astype(float)
    peso = torch.tensor(np.where(conteo > 0, conteo.sum() / (len(CLASES) * np.maximum(conteo, 1)), 0), dtype=torch.float32)
    opt = torch.optim.Adam(red.parameters(), lr=0.01)
    perdida = torch.nn.CrossEntropyLoss(weight=peso)
    xt = torch.tensor(X[:, None, :], dtype=torch.float32)
    yt = torch.tensor(y, dtype=torch.long)
    rng = np.random.default_rng(semilla)
    for _ in range(epocas):
        orden = rng.permutation(len(X))
        for i in range(0, len(X), 32):
            lote = orden[i:i + 32]
            opt.zero_grad()
            perdida(red(xt[lote]), yt[lote]).backward()
            opt.step()
    return {k: v.detach().numpy().astype(np.float32) for k, v in red.state_dict().items()}


# ---------------------------------------------------------------------------
# Inferencia en numpy (referencia exacta de lo que hace el C)
# ---------------------------------------------------------------------------
def _conv(x, w, b, paso):
    """x: (c_in, L); w: (c_out, c_in, k)."""
    c_out, c_in, k = w.shape
    l_out = (x.shape[1] - k) // paso + 1
    idx = np.arange(k)[None, :] + paso * np.arange(l_out)[:, None]          # (l_out, k)
    parches = x[:, idx]                                                    # (c_in, l_out, k)
    return np.einsum("oik,ilk->ol", w, parches) + b[:, None]


def inferir_f32(P: dict, x: np.ndarray) -> np.ndarray:
    h = np.maximum(_conv(x[None, :].astype(np.float32), P["c1.weight"], P["c1.bias"], P1), 0)
    h = np.maximum(_conv(h, P["c2.weight"], P["c2.bias"], P2), 0)
    return P["d.weight"] @ h.mean(axis=1) + P["d.bias"]


def _redondear(v):
    return np.floor(v + 0.5)


def cuantizar(P: dict, X_calib: np.ndarray) -> dict:
    """Escalas de pesos y activaciones a partir de datos de calibración (las ventanas de entrenamiento)."""
    a0 = np.abs(X_calib).max()
    h1 = [np.maximum(_conv(x[None, :], P["c1.weight"], P["c1.bias"], P1), 0) for x in X_calib]
    a1 = max(np.abs(h).max() for h in h1)
    h2 = [np.maximum(_conv(h, P["c2.weight"], P["c2.bias"], P2), 0) for h in h1]
    a2 = max(np.abs(h).max() for h in h2)
    g = max(np.abs(h.mean(axis=1)).max() for h in h2)
    Q = {"s_x": max(a0, 1e-6) / 127, "s_1": max(a1, 1e-6) / 127, "s_2": max(a2, 1e-6) / 127, "s_g": max(g, 1e-6) / 127}
    for nombre, capa in (("w1", "c1"), ("w2", "c2"), ("w3", "d")):
        w = P[f"{capa}.weight"]
        Q[f"s_{nombre}"] = max(np.abs(w).max(), 1e-8) / 127
        Q[nombre] = np.clip(_redondear(w / Q[f"s_{nombre}"]), -127, 127).astype(np.int8)
    Q["b1"] = _redondear(P["c1.bias"] / (Q["s_w1"] * Q["s_x"])).astype(np.int32)
    Q["b2"] = _redondear(P["c2.bias"] / (Q["s_w2"] * Q["s_1"])).astype(np.int32)
    Q["b3"] = _redondear(P["d.bias"] / (Q["s_w3"] * Q["s_g"])).astype(np.int32)
    Q["m1"] = np.float32(Q["s_w1"] * Q["s_x"] / Q["s_1"])
    Q["m2"] = np.float32(Q["s_w2"] * Q["s_1"] / Q["s_2"])
    Q["mg"] = np.float32(Q["s_2"] / Q["s_g"])
    Q["mg_l2"] = np.float32(Q["mg"] / np.float32(L2))   # el promedio incluye la división por L2
    Q["m3"] = np.float32(Q["s_w3"] * Q["s_g"])
    Q["inv_sx"] = np.float32(1.0 / Q["s_x"])
    return Q


def inferir_i8(Q: dict, x: np.ndarray) -> np.ndarray:
    """Misma aritmética que cnn_inferir_i8 en C: MACs en enteros, recuantización con un multiplicador float."""
    xq = np.clip(_redondear(x.astype(np.float32) * Q["inv_sx"]), -127, 127).astype(np.int32)
    a1 = _conv(xq[None, :], Q["w1"].astype(np.int32), Q["b1"], P1)
    h1 = np.clip(_redondear(a1.astype(np.float32) * Q["m1"]), 0, 127).astype(np.int32)
    a2 = _conv(h1, Q["w2"].astype(np.int32), Q["b2"], P2)
    h2 = np.clip(_redondear(a2.astype(np.float32) * Q["m2"]), 0, 127).astype(np.int32)
    gq = np.clip(_redondear(h2.sum(axis=1).astype(np.float32) * Q["mg_l2"]), 0, 127).astype(np.int32)
    acc = Q["w3"].astype(np.int32) @ gq + Q["b3"]
    return acc.astype(np.float32) * Q["m3"]


# ---------------------------------------------------------------------------
# Exportación a C
# ---------------------------------------------------------------------------
def _arreglo(tipo, nombre, v, por_linea=12):
    v = np.asarray(v).ravel()
    fmt = (lambda a: f"{float(a):.8e}f") if tipo == "float" else (lambda a: str(int(a)))
    filas = [", ".join(fmt(a) for a in v[i:i + por_linea]) for i in range(0, len(v), por_linea)]
    return f"static const {tipo} {nombre}[{len(v)}] = {{\n    " + ",\n    ".join(filas) + "\n};\n"


def exportar_c(P: dict, Q: dict, ruta, encabezado: str):
    partes = [f"// {linea}\n" for linea in encabezado.splitlines()]
    partes.append(f"""#pragma once
#include <math.h>
#include <stdint.h>

#define CNN_ENTRADA {L_ENTRADA}
#define CNN_C1 {C1}
#define CNN_K1 {K1}
#define CNN_P1 {P1}
#define CNN_L1 {L1}
#define CNN_C2 {C2}
#define CNN_K2 {K2}
#define CNN_P2 {P2}
#define CNN_L2 {L2}
#define CNN_CLASES {len(CLASES)}
// Orden de las clases: {", ".join(CLASES)}

// ---- Pesos float32 (const → quedan en FLASH, leídos a través de la caché) ----
""")
    partes += [_arreglo("float", "CNN_W1_F32", P["c1.weight"]), _arreglo("float", "CNN_B1_F32", P["c1.bias"]),
               _arreglo("float", "CNN_W2_F32", P["c2.weight"]), _arreglo("float", "CNN_B2_F32", P["c2.bias"]),
               _arreglo("float", "CNN_W3_F32", P["d.weight"]), _arreglo("float", "CNN_B3_F32", P["d.bias"])]
    partes.append("\n// ---- Pesos int8 y escalas (cuantización simétrica por tensor) ----\n")
    partes += [_arreglo("int8_t", "CNN_W1_Q", Q["w1"]), _arreglo("int32_t", "CNN_B1_Q", Q["b1"]),
               _arreglo("int8_t", "CNN_W2_Q", Q["w2"]), _arreglo("int32_t", "CNN_B2_Q", Q["b2"]),
               _arreglo("int8_t", "CNN_W3_Q", Q["w3"]), _arreglo("int32_t", "CNN_B3_Q", Q["b3"])]
    partes.append(f"""static const float CNN_INV_SX = {float(Q['inv_sx']):.9e}f;
static const float CNN_M1 = {float(Q['m1']):.9e}f;
static const float CNN_M2 = {float(Q['m2']):.9e}f;
static const float CNN_MG = {float(Q['mg_l2']):.9e}f;   // incluye la división por CNN_L2 del promedio
static const float CNN_M3 = {float(Q['m3']):.9e}f;

// Pesos float32 agrupados: el experimento E2 pasa estos punteros (flash) o una copia en SRAM.
struct PesosCnnF32 {{ const float *w1, *b1, *w2, *b2, *w3, *b3; }};
struct PesosCnnQ {{ const int8_t *w1; const int32_t *b1; const int8_t *w2; const int32_t *b2;
                   const int8_t *w3; const int32_t *b3; }};

static inline float cnn_redondear(float v) {{ return floorf(v + 0.5f); }}
static inline int32_t cnn_saturar(float v, int32_t lo, int32_t hi) {{
    const int32_t r = (int32_t)cnn_redondear(v);
    return r < lo ? lo : (r > hi ? hi : r);
}}

// Devuelve la clase de mayor puntaje y deja los puntajes (logits) en salida[CNN_CLASES].
static inline int cnn_inferir_f32(const float* x, const PesosCnnF32& p, float* salida) {{
    static float h1[CNN_C1 * CNN_L1];
    static float h2[CNN_C2 * CNN_L2];
    for (int o = 0; o < CNN_C1; o++)
        for (int l = 0; l < CNN_L1; l++) {{
            float a = p.b1[o];
            for (int k = 0; k < CNN_K1; k++) a += p.w1[o * CNN_K1 + k] * x[l * CNN_P1 + k];
            h1[o * CNN_L1 + l] = a > 0 ? a : 0;
        }}
    float g[CNN_C2];
    for (int o = 0; o < CNN_C2; o++) {{
        float suma = 0;
        for (int l = 0; l < CNN_L2; l++) {{
            float a = p.b2[o];
            for (int i = 0; i < CNN_C1; i++)
                for (int k = 0; k < CNN_K2; k++) a += p.w2[(o * CNN_C1 + i) * CNN_K2 + k] * h1[i * CNN_L1 + l * CNN_P2 + k];
            h2[o * CNN_L2 + l] = a > 0 ? a : 0;
            suma += h2[o * CNN_L2 + l];
        }}
        g[o] = suma / CNN_L2;
    }}
    int mejor = 0;
    for (int c = 0; c < CNN_CLASES; c++) {{
        float a = p.b3[c];
        for (int i = 0; i < CNN_C2; i++) a += p.w3[c * CNN_C2 + i] * g[i];
        salida[c] = a;
        if (a > salida[mejor]) mejor = c;
    }}
    return mejor;
}}

// Misma red en int8: multiplicaciones y sumas en enteros; solo la recuantización usa un multiplicador float.
static inline int cnn_inferir_i8(const float* x, const PesosCnnQ& p, float* salida) {{
    static int8_t xq[CNN_ENTRADA];
    static int8_t h1[CNN_C1 * CNN_L1];
    static int8_t h2[CNN_C2 * CNN_L2];
    for (int i = 0; i < CNN_ENTRADA; i++) xq[i] = (int8_t)cnn_saturar(x[i] * CNN_INV_SX, -127, 127);
    for (int o = 0; o < CNN_C1; o++)
        for (int l = 0; l < CNN_L1; l++) {{
            int32_t a = p.b1[o];
            for (int k = 0; k < CNN_K1; k++) a += (int32_t)p.w1[o * CNN_K1 + k] * xq[l * CNN_P1 + k];
            h1[o * CNN_L1 + l] = (int8_t)cnn_saturar(a * CNN_M1, 0, 127);
        }}
    int8_t g[CNN_C2];
    for (int o = 0; o < CNN_C2; o++) {{
        int32_t suma = 0;
        for (int l = 0; l < CNN_L2; l++) {{
            int32_t a = p.b2[o];
            for (int i = 0; i < CNN_C1; i++)
                for (int k = 0; k < CNN_K2; k++)
                    a += (int32_t)p.w2[(o * CNN_C1 + i) * CNN_K2 + k] * h1[i * CNN_L1 + l * CNN_P2 + k];
            h2[o * CNN_L2 + l] = (int8_t)cnn_saturar(a * CNN_M2, 0, 127);
            suma += h2[o * CNN_L2 + l];
        }}
        g[o] = (int8_t)cnn_saturar(suma * CNN_MG, 0, 127);
    }}
    int mejor = 0;
    for (int c = 0; c < CNN_CLASES; c++) {{
        int32_t a = p.b3[c];
        for (int i = 0; i < CNN_C2; i++) a += (int32_t)p.w3[c * CNN_C2 + i] * g[i];
        salida[c] = a * CNN_M3;
        if (salida[c] > salida[mejor]) mejor = c;
    }}
    return mejor;
}}

static const PesosCnnF32 CNN_PESOS_FLASH = {{CNN_W1_F32, CNN_B1_F32, CNN_W2_F32, CNN_B2_F32, CNN_W3_F32, CNN_B3_F32}};
static const PesosCnnQ CNN_PESOS_Q = {{CNN_W1_Q, CNN_B1_Q, CNN_W2_Q, CNN_B2_Q, CNN_W3_Q, CNN_B3_Q}};
""")
    ruta.write_text("".join(partes), encoding="utf-8")
