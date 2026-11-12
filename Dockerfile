# VÍA VIVA · plan B en Docker: SOLO la captura del PC (phyphox) y el tablero local. La Raspberry Pi no usa Docker.
# Imagen multiarquitectura (amd64 para Windows/Linux, arm64 para Mac con chip Apple): se construye en cada PC.
#   docker compose build            (o: docker build -t viaviva .)
#   docker compose run --rm viaviva doctor
#   docker compose up               → http://localhost:8000/captura
# Nada de .env, config.js, datos ni sesiones entra a la imagen (.dockerignore); las sesiones van en un volumen.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    PIP_NO_CACHE_DIR=1 \
    VIAVIVA_EN_DOCKER=1 \
    VIAVIVA_DIR_SESIONES=/sesiones \
    VIAVIVA_PUERTO=8000

# ffmpeg: convertir videos HEVC del iPhone a H.264 (pantalla Revisión)
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY viaviva/requirements-pc.txt viaviva/requirements-pc.txt
RUN pip install -r viaviva/requirements-pc.txt

# Solo lo que usa la app: viaviva/, la capa de base de datos y la configuración del detector
COPY db/ db/
COPY config/ config/
COPY viaviva/ viaviva/
# Leaflet dentro de la imagen: el mapa funciona sin internet en el carro
ADD --chmod=644 https://unpkg.com/leaflet@1.9.4/dist/leaflet.js https://unpkg.com/leaflet@1.9.4/dist/leaflet.css \
    viaviva/web/vendor/leaflet/

RUN useradd --create-home --uid 1000 viaviva \
    && mkdir -p /sesiones /app/data \
    && chown -R viaviva /sesiones /app/data
USER viaviva

EXPOSE 8000
VOLUME ["/sesiones", "/app/data"]
ENTRYPOINT ["python", "-m", "viaviva"]
CMD ["capture"]
