// VÍA VIVA — proyecto para wokwi.com (ESP32 + MPU-6050 + microSD + botón + LED).
// Usa los MISMOS pines que el nodo real (include/pines.h). Sirve para practicar sin hardware:
//   * lee el MPU-6050 por I2C y detecta giros con la regla de src/maniobras.h
//     (en Wokwi: clic en el MPU-6050 y mover el deslizador de giro Z por encima de 15 °/s);
//   * escribe en la microSD simulada;
//   * el botón guarda una etiqueta y el LED parpadea.
// No simula: ADXL345, VL53L0X, GPS NEO-6M ni la ESP32-CAM (Wokwi no tiene esas piezas).
#include <SD.h>
#include <SPI.h>
#include <Wire.h>

#define PIN_I2C_SDA 21
#define PIN_I2C_SCL 22
#define PIN_SD_SCK 14
#define PIN_SD_MISO 27
#define PIN_SD_MOSI 13
#define PIN_SD_CS 32
#define PIN_PULSADOR 26
#define PIN_LED 33

const float GIRO_MIN_DPS = 15.0;   // igual que MANIOBRA_GIRO_MIN_DPS en include/config.h
const float DUR_GIRO_S = 1.0;
const float FS_HZ = 50.0;

SPIClass spiSD(HSPI);
bool sdOk = false;

int16_t leer16(uint8_t reg) {
  Wire.beginTransmission(0x68);
  Wire.write(reg);
  Wire.endTransmission(false);
  Wire.requestFrom(0x68, 2);
  return (int16_t)((Wire.read() << 8) | Wire.read());
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_LED, OUTPUT);
  pinMode(PIN_PULSADOR, INPUT_PULLUP);
  Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL);
  Wire.beginTransmission(0x68);
  Wire.write(0x6B);
  Wire.write(0x00);                       // despierta el MPU-6050
  const bool mpuOk = Wire.endTransmission() == 0;
  Wire.beginTransmission(0x68);
  Wire.write(0x1B);
  Wire.write(0x08);                       // giroscopio ±500 °/s
  Wire.endTransmission();
  spiSD.begin(PIN_SD_SCK, PIN_SD_MISO, PIN_SD_MOSI, PIN_SD_CS);
  sdOk = SD.begin(PIN_SD_CS, spiSD);
  Serial.printf("MPU-6050: %s\nmicroSD: %s\n", mpuOk ? "PASA" : "FALLA", sdOk ? "PASA" : "FALLA");
  if (sdOk) {
    File f = SD.open("/wokwi.csv", FILE_WRITE);
    f.println("t_ms,giro_z_dps,evento");
    f.close();
  }
}

void loop() {
  static float filtrado = 0;
  static int muestras = 0;
  static bool reportado = false;
  static bool botonAntes = true;

  const float giroZ = leer16(0x47) / 65.5f;          // °/s
  filtrado += (giroZ - filtrado) / (0.25f * FS_HZ + 1.0f);
  const int signo = filtrado > GIRO_MIN_DPS ? 1 : filtrado < -GIRO_MIN_DPS ? -1 : 0;
  muestras = signo ? muestras + 1 : 0;
  String evento = "";
  if (signo && muestras >= DUR_GIRO_S * FS_HZ && !reportado) {
    evento = signo > 0 ? "giro_izquierda" : "giro_derecha";
    reportado = true;
  }
  if (!signo) reportado = false;

  const bool boton = digitalRead(PIN_PULSADOR);
  if (botonAntes && !boton) evento = "etiqueta_boton";
  botonAntes = boton;

  if (evento.length()) {
    Serial.printf("%lu ms: %s (giro filtrado %.1f °/s)\n", millis(), evento.c_str(), filtrado);
    digitalWrite(PIN_LED, HIGH);
    if (sdOk) {
      File f = SD.open("/wokwi.csv", FILE_APPEND);
      f.printf("%lu,%.1f,%s\n", millis(), filtrado, evento.c_str());
      f.close();
    }
  } else {
    digitalWrite(PIN_LED, LOW);
  }
  delay(1000 / FS_HZ);
}
