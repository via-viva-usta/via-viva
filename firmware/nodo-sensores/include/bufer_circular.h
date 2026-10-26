// Búfer circular de tamaño fijo (estructura de datos del nodo).
// Insertar es O(1) y nunca pide memoria: cuando se llena, la muestra nueva pisa la más vieja.
// Se usa para la ventana deslizante de 2 s de aceleración.
#pragma once
#include <stddef.h>

template <typename T, size_t N>
class BuferCircular {
public:
    void agregar(const T& valor) {
        datos_[cabeza_] = valor;
        cabeza_ = (cabeza_ + 1) % N;
        if (cantidad_ < N) cantidad_++;
    }

    // i = 0 es la muestra más vieja; i = cantidad() - 1 la más reciente
    const T& operator[](size_t i) const {
        size_t inicio = (cabeza_ + N - cantidad_) % N;
        return datos_[(inicio + i) % N];
    }

    size_t cantidad() const { return cantidad_; }
    bool lleno() const { return cantidad_ == N; }
    static constexpr size_t capacidad() { return N; }
    void vaciar() { cabeza_ = 0; cantidad_ = 0; }

private:
    T datos_[N];
    size_t cabeza_ = 0;     // posición donde va la próxima muestra
    size_t cantidad_ = 0;
};
