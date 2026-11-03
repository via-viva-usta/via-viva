// Núcleo 0: punto de acceso Wi-Fi y página web para el celular del copiloto.
//   http://192.168.4.1/           página (se actualiza sola cada segundo)
//   GET  /estado                  JSON con el último evento, velocidad, estado de sensores y ambiente
//   POST /etiqueta?tipo=hueco     guarda una etiqueta (hueco, resalto, otro) con la hora en la microSD
//   POST /mesa?activo=1           "modo mesa": ignora la velocidad GPS para probar el detector sin carro
// El Wi-Fi de la ESP32 corre en el núcleo 0 (configuración de ESP-IDF); la adquisición no se toca.
#include <WebServer.h>
#include <WiFi.h>

#include "esp_timer.h"
#include "estado.h"
#include "experimentos.h"

#if __has_include("secretos.h")
#include "secretos.h"
#define SECRETOS_DE_EJEMPLO 0
#else
#include "secretos.example.h"
#define SECRETOS_DE_EJEMPLO 1
#endif

extern volatile bool modoMesa;   // procesamiento.cpp

static WebServer servidor(80);

static const char PAGINA[] PROGMEM = R"HTML(<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>VÍA VIVA · nodo</title>
<style>
:root{--asfalto:#2f2f2f;--senal:#f2c230;--ok:#2a9d8f;--mal:#b3261e;--fondo:#f4f3ef}
body{font-family:system-ui,sans-serif;margin:0;background:var(--fondo);color:var(--asfalto)}
header{background:var(--asfalto);color:#fff;padding:12px 16px;font-weight:700}
main{padding:12px 16px;max-width:520px;margin:auto}
.tarjeta{background:#fff;border-radius:12px;padding:12px 14px;margin:10px 0;box-shadow:0 1px 3px #0002}
.grande{font-size:2.2rem;font-weight:700}
.botones{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px}
button{font-size:1.15rem;padding:22px 6px;border:0;border-radius:12px;color:#fff;font-weight:700}
.hueco{background:var(--mal)}.resalto{background:#e9672b}.otro{background:#555}
.sens span{display:inline-block;margin:3px 6px 3px 0;padding:3px 8px;border-radius:8px;color:#fff;font-size:.85rem}
.si{background:var(--ok)}.no{background:var(--mal)}
#aviso{min-height:1.2em;font-weight:600}
</style></head><body>
<header>VÍA VIVA · nodo de sensores</header>
<main>
<div class="tarjeta"><div>Velocidad GPS</div><div class="grande"><span id="vel">–</span> km/h</div>
<div id="gps">–</div></div>
<div class="tarjeta"><div><b>Etiquetar ahora</b> (lo oprime el copiloto, nunca el conductor)</div>
<div class="botones" style="margin-top:8px">
<button class="hueco" onclick="etiquetar('hueco')">Hueco</button>
<button class="resalto" onclick="etiquetar('resalto')">Resalto</button>
<button class="otro" onclick="etiquetar('otro')">Otro</button></div>
<div id="aviso"></div></div>
<div class="tarjeta"><div><b>Ambiente</b> <small id="amb_s"></small></div><div id="amb">–</div></div>
<div class="tarjeta"><div><b>Último evento</b></div><div id="evento">ninguno todavía</div></div>
<div class="tarjeta"><div><b>Sensores</b></div><div class="sens" id="sens"></div><div id="extra"></div>
<label><input type="checkbox" id="mesa" onchange="mesa(this.checked)"> Modo mesa (ignora la velocidad para probar)</label></div>
</main>
<script>
function chip(n,v){return '<span class="'+(v?'si':'no')+'">'+n+'</span>'}
async function actualizar(){try{const r=await fetch('/estado');const e=await r.json();
document.getElementById('vel').textContent=e.gps.vel.toFixed(1);
document.getElementById('gps').textContent=e.gps.valido?('Fijación: '+e.gps.sat+' satélites · '+e.gps.utc):'Sin señal GPS (bajo techo no hay)';
document.getElementById('sens').innerHTML=chip('ADXL345',e.adxl)+chip('MPU-6050',e.mpu)+chip('VL53L0X',e.tof)+chip('microSD',e.sd)+chip('GPS',e.gps.valido)+chip(e.amb.sensor_th.toUpperCase(),e.amb.sensor_th!='ninguno')+chip('BH1750',e.amb.lux_ok);
const a=e.amb,f=(v,d,u)=>v===null?'–':v.toFixed(d)+u;
document.getElementById('amb').textContent=f(a.temp,1,' °C')+' · '+f(a.hum,0,' % HR')+' · '+f(a.pres,0,' hPa')+' · '+f(a.lux,0,' lx');
document.getElementById('amb_s').textContent=a.hace_s>=0?('hace '+a.hace_s.toFixed(0)+' s'):'';
document.getElementById('extra').textContent='Sesión '+e.sesion+' · '+e.muestras_s.toFixed(0)+' muestras/s · '+e.eventos+' eventos · '+e.etiquetas+' etiquetas · modo E1: '+e.modo_e1+' · maniobra: '+e.maniobra+' · láser '+e.dist_mm+' mm';
document.getElementById('mesa').checked=e.mesa;
if(e.ultimo){const u=e.ultimo;document.getElementById('evento').textContent='#'+u.id+' '+u.clase+' · pico '+u.pico.toFixed(2)+' g · '+u.vel.toFixed(0)+' km/h · hace '+u.hace_s.toFixed(0)+' s'}
}catch(x){}}
async function etiquetar(t){const r=await fetch('/etiqueta?tipo='+t,{method:'POST'});
document.getElementById('aviso').textContent=r.ok?('Guardado: '+t):'No se pudo guardar';setTimeout(()=>document.getElementById('aviso').textContent='',2500)}
async function mesa(a){await fetch('/mesa?activo='+(a?1:0),{method:'POST'})}
setInterval(actualizar,1000);actualizar();
</script></body></html>)HTML";

static void manejarEstado() {
    const EstadoNodo n = copiarNodo();
    const EstadoGPS g = copiarGPS();
    const EstadoI2C i = copiarI2C();
    char ultimo[220] = "null";
    if (n.hayUltimo) {
        snprintf(ultimo, sizeof(ultimo), "{\"id\":%lu,\"clase\":\"%s\",\"pico\":%.3f,\"vel\":%.1f,\"hace_s\":%.1f}",
                 (unsigned long)n.ultimo.id, nombreClase(n.ultimo.clase), n.ultimo.c.pico, n.ultimo.gps.velKmh,
                 (esp_timer_get_time() - n.ultimo.tUs) / 1e6);
    }
    // Ambiente: NAN → null en el JSON
    const EstadoAmbiente& a = i.amb;
    char t[12] = "null", h[12] = "null", p[12] = "null", l[12] = "null";
    if (!isnan(a.tempC)) snprintf(t, sizeof(t), "%.2f", a.tempC);
    if (!isnan(a.humPct)) snprintf(h, sizeof(h), "%.1f", a.humPct);
    if (!isnan(a.presHpa)) snprintf(p, sizeof(p), "%.1f", a.presHpa);
    if (!isnan(a.lux)) snprintf(l, sizeof(l), "%.1f", a.lux);
    char amb[200];
    snprintf(amb, sizeof(amb),
             "{\"sensor_th\":\"%s\",\"lux_ok\":%s,\"temp\":%s,\"hum\":%s,\"pres\":%s,\"lux\":%s,\"hace_s\":%.1f}",
             a.sensorTH, a.luxOk ? "true" : "false", t, h, p, l,
             a.tUs ? (esp_timer_get_time() - a.tUs) / 1e6 : -1.0);
    char json[900];
    snprintf(json, sizeof(json),
             "{\"adxl\":%s,\"mpu\":%s,\"tof\":%s,\"sd\":%s,\"sesion\":%d,\"muestras_s\":%.1f,"
             "\"eventos\":%lu,\"etiquetas\":%lu,\"maniobra\":\"%s\",\"dist_mm\":%u,\"mesa\":%s,\"modo_e1\":\"%s\","
             "\"gps\":{\"valido\":%s,\"vel\":%.1f,\"sat\":%u,\"utc\":\"%s\"},\"amb\":%s,\"ultimo\":%s}",
             n.adxlOk ? "true" : "false", i.mpuOk ? "true" : "false", i.tofOk ? "true" : "false",
             n.sdOk ? "true" : "false", n.sesion, n.muestrasPorSegundo,
             (unsigned long)n.eventos, (unsigned long)n.etiquetas, nombreManiobra(i.maniobra), i.distanciaMm,
             modoMesa ? "true" : "false", nombreModoAdq(), g.valido ? "true" : "false", g.velKmh, g.satelites, g.utc,
             amb, ultimo);
    servidor.send(200, "application/json", json);
}

static void manejarEtiqueta() {
    const String tipo = servidor.arg("tipo");
    if (tipo != "hueco" && tipo != "resalto" && tipo != "otro") {
        servidor.send(400, "text/plain", "tipo debe ser hueco, resalto u otro");
        return;
    }
    registrarEtiqueta(esp_timer_get_time(), tipo.c_str(), "web");
    servidor.send(200, "text/plain", "ok");
}

static void manejarMesa() {
    modoMesa = servidor.arg("activo") == "1";
    servidor.send(200, "text/plain", modoMesa ? "modo mesa activo" : "modo mesa apagado");
}

void tareaWeb(void*) {
    WiFi.mode(WIFI_AP);
    const bool ok = WiFi.softAP(AP_SSID, AP_CLAVE, AP_CANAL, 0, AP_MAX_CLIENTES);
    Serial.printf("[WEB] Punto de acceso \"%s\" %s · http://%s/%s\n", AP_SSID, ok ? "activo" : "FALLÓ",
                  WiFi.softAPIP().toString().c_str(),
                  SECRETOS_DE_EJEMPLO ? "  (clave de EJEMPLO: crea include/secretos.h)" : "");
    servidor.on("/", HTTP_GET, [] { servidor.send_P(200, "text/html; charset=utf-8", PAGINA); });
    servidor.on("/estado", HTTP_GET, manejarEstado);
    servidor.on("/etiqueta", HTTP_POST, manejarEtiqueta);
    servidor.on("/mesa", HTTP_POST, manejarMesa);
    servidor.onNotFound([] { servidor.send(404, "text/plain", "no existe"); });
    servidor.begin();
    for (;;) {
        servidor.handleClient();
        vTaskDelay(pdMS_TO_TICKS(5));
    }
}
