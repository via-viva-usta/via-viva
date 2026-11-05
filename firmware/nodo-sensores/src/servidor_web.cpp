// Núcleo 0: punto de acceso Wi-Fi y página web para el celular del copiloto.
//   http://192.168.4.1/           página (estado cada 1 s, gráfica cada 0,5 s). Sin librerías externas: en la red
//                                 del nodo el celular no tiene internet
//   GET  /estado                  JSON: último evento, velocidad, sensores, ambiente, microSD y GPS
//   GET  /senal?desde=N           JSON: puntos de |a| - 1 g (mg, 20 Hz) con número de orden > N (senal_vivo.h)
//   GET  /ajustes                 JSON: umbrales del detector (valor, por defecto, mínimo y máximo)
//   POST /ajustes?k=6&p2p=0.3&vmin=5&refr=1   guarda en la flash y aplica (o ?restaurar=1 = los de config.h)
//   GET  /archivos                JSON: CSV de la microSD con su tamaño
//   GET  /descargar?f=crudo_001.csv   descarga un CSV por partes, sin sacar la tarjeta
//   POST /etiqueta?tipo=hueco     guarda una etiqueta (hueco, resalto, otro) con la hora en la microSD
//   POST /mesa?activo=1           "modo mesa": ignora la velocidad GPS para probar el detector sin carro
// El Wi-Fi de la ESP32 corre en el núcleo 0 (configuración de ESP-IDF); la adquisición no se toca.
#include <SD.h>
#include <WebServer.h>
#include <WiFi.h>
#include <dirent.h>
#include <sys/stat.h>

#include "ajustes.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "estado.h"
#include "experimentos.h"
#include "senal_vivo.h"

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
.sec{background:var(--asfalto);font-size:1rem;padding:10px 14px;margin:6px 6px 0 0}
.sens span{display:inline-block;margin:3px 6px 3px 0;padding:3px 8px;border-radius:8px;color:#fff;font-size:.85rem}
.si{background:var(--ok)}.no{background:var(--mal)}
#aviso{min-height:1.2em;font-weight:600}
canvas{width:100%;height:160px;display:block;background:#fafaf7;border-radius:8px}
.aj label{display:flex;justify-content:space-between;align-items:center;margin:6px 0;gap:8px}
.aj input{width:6.5em;font-size:1rem;padding:4px}
small{color:#666}.linea{margin:3px 0}
#arch a{color:var(--asfalto);font-weight:600}
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
<div class="tarjeta"><div><b>Aceleración vertical</b> <small>|a| − 1 g · últimos 10 s</small></div>
<canvas id="graf"></canvas><small id="graf_t">esperando datos…</small></div>
<div class="tarjeta"><div><b>Último evento</b></div><div id="evento">ninguno todavía</div></div>
<div class="tarjeta"><div><b>Ambiente</b> <small id="amb_s"></small></div><div id="amb">–</div></div>
<div class="tarjeta"><div><b>Estado del nodo</b></div><div class="sens" id="sens"></div>
<div class="linea" id="sd">–</div><div class="linea" id="gpsest">–</div><div class="linea" id="extra"></div>
<label><input type="checkbox" id="mesa" onchange="mesa(this.checked)"> Modo mesa (ignora la velocidad para probar)</label></div>
<div class="tarjeta"><div><b>Umbrales del detector</b> <small>(se guardan en el nodo)</small></div><div class="aj">
<label><span>K (× vibración de fondo) <small id="r_k"></small></span><input id="aj_k" type="number" step="0.1"></label>
<label><span>Piso pico a pico (g) <small id="r_p2p"></small></span><input id="aj_p2p" type="number" step="0.01"></label>
<label><span>Velocidad mínima (km/h) <small id="r_vmin"></small></span><input id="aj_vmin" type="number" step="0.5"></label>
<label><span>Refractario (s) <small id="r_refr"></small></span><input id="aj_refr" type="number" step="0.1"></label></div>
<button class="sec" onclick="guardarAj(0)">Guardar</button><button class="sec" onclick="guardarAj(1)">Valores de fábrica</button>
<div id="aj_aviso"></div></div>
<div class="tarjeta"><div><b>Archivos de la microSD</b></div>
<small>Mientras se descarga, esta página deja de actualizarse; el nodo sigue guardando.</small><br>
<button class="sec" onclick="archivos()">Ver archivos</button><div id="arch"></div></div>
</main>
<script>
const $=id=>document.getElementById(id);let sesion=0;
function chip(n,v){return '<span class="'+(v?'si':'no')+'">'+n+'</span>'}
const pad=n=>String(n).padStart(3,'0');
async function actualizar(){try{const r=await fetch('/estado');const e=await r.json();sesion=e.sesion;
$('vel').textContent=e.gps.vel.toFixed(1);
$('gps').textContent=e.gps.valido?('Fijación: '+e.gps.sat+' satélites · '+e.gps.utc):'Sin señal GPS (bajo techo no hay)';
$('sens').innerHTML=chip('ADXL345',e.adxl)+chip('MPU-6050',e.mpu)+chip('VL53L0X',e.tof)+chip('microSD',e.sd)+chip('GPS',e.gps.valido)+chip(e.amb.sensor_th.toUpperCase(),e.amb.sensor_th!='ninguno')+chip('BH1750',e.amb.lux_ok);
const a=e.amb,f=(v,d,u)=>v===null?'–':v.toFixed(d)+u;
$('amb').textContent=f(a.temp,1,' °C')+' · '+f(a.hum,0,' % HR')+' · '+f(a.pres,0,' hPa')+' · '+f(a.lux,0,' lx');
$('amb_s').textContent=a.hace_s>=0?('hace '+a.hace_s.toFixed(0)+' s'):'';
$('sd').textContent=e.sd?('microSD: guardando la sesión '+pad(e.sesion)+' · '+e.sd_remontajes+' remontajes · '+e.sd_fallos+' fallos de escritura'+(e.crudo_perdido?' · '+e.crudo_perdido+' bloques del crudo perdidos':'')):'microSD: SIN MONTAR, no se está guardando (se reintenta cada 10 s)';
const g=e.gps;$('gpsest').textContent='GPS: '+(g.sin_datos_s<0?'no ha llegado ningún dato':('datos hace '+g.sin_datos_s.toFixed(0)+' s · '+(g.valido?('HDOP '+g.hdop.toFixed(1)):'sin fijación')))+' · UART reiniciada '+g.reinicios+' veces';
$('extra').textContent=e.muestras_s.toFixed(0)+' muestras/s · '+e.eventos+' eventos · '+e.etiquetas+' etiquetas · modo E1: '+e.modo_e1+' · maniobra: '+e.maniobra+' · láser '+e.dist_mm+' mm · último reinicio: '+e.reinicio;
$('mesa').checked=e.mesa;
if(e.ultimo){const u=e.ultimo;$('evento').textContent='#'+u.id+' '+u.clase+' · pico '+u.pico.toFixed(2)+' g · razón '+u.razon.toFixed(1)+' · '+u.vel.toFixed(0)+' km/h · hace '+u.hace_s.toFixed(0)+' s'}
}catch(x){}}
const sen=[];let nSen=0;
async function senal(){try{const r=await fetch('/senal?desde='+nSen);const s=await r.json();
if(s.n<nSen)sen.length=0;for(const v of s.mg)sen.push(v/1000);while(sen.length>200)sen.shift();nSen=s.n;dibujar()}catch(x){}}
function dibujar(){const c=$('graf'),d=window.devicePixelRatio||1,W=c.clientWidth,H=160;c.width=W*d;c.height=H*d;
const g=c.getContext('2d');g.scale(d,d);let m=0;for(const v of sen)m=Math.max(m,Math.abs(v));const esc=Math.max(0.5,m*1.15);
const y=v=>H/2-v/esc*(H/2-6);g.strokeStyle='#ccc';g.beginPath();g.moveTo(0,y(0));g.lineTo(W,y(0));g.stroke();
g.fillStyle='#888';g.font='11px system-ui';g.fillText('+'+esc.toFixed(2)+' g',4,12);g.fillText('−'+esc.toFixed(2)+' g',4,H-4);
g.strokeStyle='#2f2f2f';g.lineWidth=1.5;g.beginPath();const dx=W/199;
sen.forEach((v,i)=>{const x=W-(sen.length-1-i)*dx;i?g.lineTo(x,y(v)):g.moveTo(x,y(v))});g.stroke();
$('graf_t').textContent='Mayor |valor| en la pantalla: '+m.toFixed(2)+' g (cada punto = el valor de mayor magnitud en 50 ms)'}
async function etiquetar(t){const r=await fetch('/etiqueta?tipo='+t,{method:'POST'});
$('aviso').textContent=r.ok?('Guardado: '+t):'No se pudo guardar';setTimeout(()=>$('aviso').textContent='',2500)}
async function mesa(a){await fetch('/mesa?activo='+(a?1:0),{method:'POST'})}
async function cargarAj(){try{const a=await (await fetch('/ajustes')).json();for(const k in a){const i=$('aj_'+k);
i.value=a[k].v;i.min=a[k].min;i.max=a[k].max;$('r_'+k).textContent='('+a[k].min+'–'+a[k].max+'; fábrica '+a[k].def+')'}}catch(x){}}
async function guardarAj(fab){const q=fab?'restaurar=1':['k','p2p','vmin','refr'].map(k=>k+'='+encodeURIComponent($('aj_'+k).value)).join('&');
try{const r=await fetch('/ajustes?'+q,{method:'POST'});$('aj_aviso').textContent=await r.text();if(r.ok)cargarAj()}catch(x){$('aj_aviso').textContent='Sin conexión con el nodo'}}
const tam=b=>b<1048576?(b/1024).toFixed(1)+' KB':(b/1048576).toFixed(1)+' MB';
const ses=f=>parseInt((f.match(/_(\d+)\.csv$/)||[0,'0'])[1]);
async function archivos(){const d=$('arch');d.textContent='Leyendo la tarjeta…';try{const r=await fetch('/archivos');
if(!r.ok){d.textContent=await r.text();return}const l=await r.json();l.sort((a,b)=>ses(b.f)-ses(a.f)||a.f.localeCompare(b.f));
d.innerHTML=l.length?l.map(a=>'<div class="linea"><a href="/descargar?f='+a.f+'" download="'+a.f+'">'+a.f+'</a> <small>'+tam(a.b)+(ses(a.f)==sesion?' · sesión actual':'')+'</small></div>').join(''):'No hay archivos CSV'}
catch(x){d.textContent='No se pudo leer la lista'}}
setInterval(actualizar,1000);setInterval(senal,500);actualizar();senal();cargarAj();
</script></body></html>)HTML";

static const char* nombreReinicio(int causa) {
    switch (causa) {
        case ESP_RST_POWERON: return "encendido";
        case ESP_RST_EXT: return "pin EN";
        case ESP_RST_SW: return "software";
        case ESP_RST_PANIC: return "error (panic)";
        case ESP_RST_INT_WDT:
        case ESP_RST_TASK_WDT:
        case ESP_RST_WDT: return "watchdog";
        case ESP_RST_BROWNOUT: return "bajo voltaje";
        default: return "otro";
    }
}

static void manejarEstado() {
    const EstadoNodo n = copiarNodo();
    const EstadoGPS g = copiarGPS();
    const EstadoI2C i = copiarI2C();
    const int64_t ahoraUs = esp_timer_get_time();
    char ultimo[240] = "null";
    if (n.hayUltimo) {
        snprintf(ultimo, sizeof(ultimo),
                 "{\"id\":%lu,\"clase\":\"%s\",\"pico\":%.3f,\"razon\":%.1f,\"vel\":%.1f,\"hace_s\":%.1f}",
                 (unsigned long)n.ultimo.id, nombreClase(n.ultimo.clase), n.ultimo.c.pico, n.ultimo.razonUmbral,
                 n.ultimo.gps.velKmh, (ahoraUs - n.ultimo.tUs) / 1e6);
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
             a.sensorTH, a.luxOk ? "true" : "false", t, h, p, l, a.tUs ? (ahoraUs - a.tUs) / 1e6 : -1.0);
    // Salud del GPS: segundos desde el último byte NMEA (-1 = nunca llegó nada)
    const float sinDatosS = gpsBytes ? (millis() - gpsUltimoByteMs) / 1000.0f : -1.0f;
    char gps[220];
    snprintf(gps, sizeof(gps),
             "{\"valido\":%s,\"vel\":%.1f,\"sat\":%u,\"hdop\":%.1f,\"utc\":\"%s\",\"bytes\":%lu,\"reinicios\":%lu,"
             "\"sin_datos_s\":%.1f}",
             g.valido ? "true" : "false", g.velKmh, g.satelites, g.hdop, g.utc, (unsigned long)gpsBytes,
             (unsigned long)gpsReinicios, sinDatosS);
    char json[1200];
    snprintf(json, sizeof(json),
             "{\"adxl\":%s,\"mpu\":%s,\"tof\":%s,\"sd\":%s,\"sesion\":%d,\"sd_remontajes\":%lu,\"sd_fallos\":%lu,"
             "\"crudo_perdido\":%lu,\"muestras_s\":%.1f,\"eventos\":%lu,\"etiquetas\":%lu,\"maniobra\":\"%s\","
             "\"dist_mm\":%u,\"mesa\":%s,\"modo_e1\":\"%s\",\"reinicio\":\"%s\",\"gps\":%s,\"amb\":%s,\"ultimo\":%s}",
             n.adxlOk ? "true" : "false", i.mpuOk ? "true" : "false", i.tofOk ? "true" : "false",
             n.sdOk ? "true" : "false", n.sesion, (unsigned long)n.sdRemontajes, (unsigned long)n.sdFallosEscritura,
             (unsigned long)n.crudoPerdido, n.muestrasPorSegundo, (unsigned long)n.eventos,
             (unsigned long)n.etiquetas, nombreManiobra(i.maniobra), i.distanciaMm, modoMesa ? "true" : "false",
             nombreModoAdq(), nombreReinicio(n.causaReinicio), gps, amb, ultimo);
    servidor.send(200, "application/json", json);
}

// ---- Gráfica en vivo ----
static void manejarSenal() {
    static int16_t puntos[SENAL_VIVO_PUNTOS];
    static char json[SENAL_VIVO_PUNTOS * 7 + 64];   // "-32000," = 7 caracteres por punto
    const uint32_t desde = strtoul(servidor.arg("desde").c_str(), nullptr, 10);
    uint32_t total;
    const size_t n = senalVivo.copiarDesde(desde, puntos, total);
    size_t len = snprintf(json, sizeof(json), "{\"fs\":%u,\"n\":%lu,\"mg\":[", SENAL_VIVO_HZ, (unsigned long)total);
    for (size_t j = 0; j < n && len < sizeof(json) - 16; j++)
        len += snprintf(json + len, sizeof(json) - len, j ? ",%d" : "%d", puntos[j]);
    snprintf(json + len, sizeof(json) - len, "]}");
    servidor.send(200, "application/json", json);
}

// ---- Umbrales del detector ----
static void manejarAjustesGet() {
    const AjustesDetector a = leerAjustes();
    const AjustesDetector d = ajustesPorDefecto();
    char json[400];
    snprintf(json, sizeof(json),
             "{\"k\":{\"v\":%.2f,\"def\":%.2f,\"min\":%.2f,\"max\":%.2f},"
             "\"p2p\":{\"v\":%.3f,\"def\":%.3f,\"min\":%.3f,\"max\":%.3f},"
             "\"vmin\":{\"v\":%.1f,\"def\":%.1f,\"min\":%.1f,\"max\":%.1f},"
             "\"refr\":{\"v\":%.2f,\"def\":%.2f,\"min\":%.2f,\"max\":%.2f}}",
             a.kRel, d.kRel, AJ_K_MIN, AJ_K_MAX, a.p2pMinG, d.p2pMinG, AJ_P2P_MIN, AJ_P2P_MAX, a.vMinKmh, d.vMinKmh,
             AJ_VMIN_MIN, AJ_VMIN_MAX, a.refractarioS, d.refractarioS, AJ_REFR_MIN, AJ_REFR_MAX);
    servidor.send(200, "application/json", json);
}

// Lee un número del formulario (acepta coma decimal). Si el campo no viene, deja el valor actual.
static bool leerNumero(const char* nombre, float& destino) {
    if (!servidor.hasArg(nombre)) return true;
    String s = servidor.arg(nombre);
    s.trim();
    s.replace(",", ".");
    char* fin = nullptr;
    const float v = strtof(s.c_str(), &fin);
    if (s.length() == 0 || fin == s.c_str() || *fin != '\0') return false;
    destino = v;
    return true;
}

static void manejarAjustesPost() {
    AjustesDetector a = leerAjustes();
    if (servidor.arg("restaurar") == "1") {
        a = ajustesPorDefecto();
    } else if (!leerNumero("k", a.kRel) || !leerNumero("p2p", a.p2pMinG) || !leerNumero("vmin", a.vMinKmh) ||
               !leerNumero("refr", a.refractarioS)) {
        servidor.send(400, "text/plain; charset=utf-8", "Hay un valor que no es un número");
        return;
    }
    char motivo[64];
    if (!guardarAjustes(a, motivo, sizeof(motivo))) {
        servidor.send(400, "text/plain; charset=utf-8", String("No se guardó: ") + motivo);
        return;
    }
    char ok[120];
    snprintf(ok, sizeof(ok), "Guardado y aplicado: K=%.2f · piso %.3f g · %.1f km/h · refractario %.2f s", a.kRel,
             a.p2pMinG, a.vMinKmh, a.refractarioS);
    servidor.send(200, "text/plain; charset=utf-8", ok);
}

// ---- Archivos de la microSD ----
// Solo se listan y descargan nombres simples terminados en .csv (sin "/" ni ".."): nada fuera de la raíz.
static bool esCsv(const char* nombre) {
    const size_t n = strlen(nombre);
    if (n < 5 || n > 40 || strcmp(nombre + n - 4, ".csv") != 0) return false;
    for (size_t i = 0; i < n; i++) {
        const char c = nombre[i];
        if (!(isalnum((unsigned char)c) || c == '_' || c == '-' || (c == '.' && i == n - 4))) return false;
    }
    return true;
}

// Toma la tarjeta solo si sigue siendo el mismo montaje con el que se empezó (gen).
static bool tomarSD(uint32_t gen) {
    if (xSemaphoreTake(mutexSD, pdMS_TO_TICKS(500)) != pdTRUE) return false;
    if (!sdMontada || sdGeneracion != gen) {
        xSemaphoreGive(mutexSD);
        return false;
    }
    return true;
}

static void manejarArchivos() {
    const uint32_t gen = sdGeneracion;
    DIR* dir = nullptr;
    if (tomarSD(gen)) {
        dir = opendir("/sd");
        xSemaphoreGive(mutexSD);
    }
    if (!dir) {
        servidor.send(503, "text/plain; charset=utf-8", "microSD sin montar u ocupada");
        return;
    }
    servidor.setContentLength(CONTENT_LENGTH_UNKNOWN);   // la lista se manda por partes
    servidor.send(200, "application/json", "");
    servidor.sendContent("[");
    int cuenta = 0;
    bool fin = false, perdida = false;
    while (!fin && cuenta < 500) {
        // La tarjeta se toma por cada archivo: el registro no espera más que eso
        if (!tomarSD(gen)) {
            perdida = sdGeneracion != gen || !sdMontada;
            if (perdida) break;
            continue;   // el registro la estaba usando: se reintenta
        }
        char item[96] = "";
        const struct dirent* e = readdir(dir);
        if (!e) {
            fin = true;
        } else if (e->d_type != DT_DIR && esCsv(e->d_name)) {
            char ruta[64];
            snprintf(ruta, sizeof(ruta), "/sd/%s", e->d_name);
            struct stat st {};
            stat(ruta, &st);
            snprintf(item, sizeof(item), "%s{\"f\":\"%s\",\"b\":%lu}", cuenta ? "," : "", e->d_name,
                     (unsigned long)st.st_size);
        }
        xSemaphoreGive(mutexSD);
        if (item[0]) {
            servidor.sendContent(item);
            cuenta++;
        }
    }
    // Si la tarjeta se remontó a mitad del listado, el directorio viejo NO se cierra: pertenece a un montaje
    // que ya no existe y cerrarlo podría tocar memoria liberada (se pierden unos bytes, solo en ese caso raro).
    for (int intento = 0; intento < 10 && !perdida; intento++) {
        if (tomarSD(gen)) {
            closedir(dir);
            xSemaphoreGive(mutexSD);
            break;
        }
        perdida = sdGeneracion != gen || !sdMontada;
    }
    servidor.sendContent("]");
    servidor.sendContent("");   // fin de la respuesta por partes
}

static void manejarDescarga() {
    const String nombre = servidor.arg("f");
    if (!esCsv(nombre.c_str())) {
        servidor.send(400, "text/plain; charset=utf-8", "Nombre de archivo no válido");
        return;
    }
    char ruta[48];
    snprintf(ruta, sizeof(ruta), "/%s", nombre.c_str());
    const uint32_t gen = sdGeneracion;
    if (!tomarSD(gen)) {
        servidor.send(503, "text/plain; charset=utf-8", "microSD sin montar u ocupada");
        return;
    }
    // En el montón: si la tarjeta se remonta a mitad de la descarga, el archivo viejo se abandona sin cerrarlo
    // (su número de descriptor ya puede ser de un archivo nuevo del registro)
    File* f = new File(SD.open(ruta, FILE_READ));
    const size_t tam = *f ? f->size() : 0;   // si se está escribiendo, se manda hasta el último flush
    const bool existe = (bool)*f;
    if (!existe) delete f;
    xSemaphoreGive(mutexSD);
    if (!existe) {
        servidor.send(404, "text/plain; charset=utf-8", "No existe ese archivo");
        return;
    }
    servidor.sendHeader("Content-Disposition", String("attachment; filename=\"") + nombre + "\"");
    servidor.setContentLength(tam);
    servidor.send(200, "text/csv", "");
    WiFiClient cliente = servidor.client();
    static uint8_t buf[2048];
    size_t enviados = 0;
    bool perdida = false;
    const uint32_t t0 = millis();
    while (enviados < tam && cliente.connected()) {
        // La tarjeta se toma solo para leer un pedazo; el envío por Wi-Fi va sin el mutex
        if (!tomarSD(gen)) {
            perdida = sdGeneracion != gen || !sdMontada;
            if (perdida) break;
            continue;   // el registro la estaba usando: se reintenta
        }
        const size_t n = f->read(buf, min(sizeof(buf), tam - enviados));
        xSemaphoreGive(mutexSD);
        if (n == 0 || cliente.write(buf, n) != n) break;
        enviados += n;
        vTaskDelay(1);   // deja correr a la tarea ociosa del núcleo 0 (la vigila el watchdog)
    }
    for (int intento = 0; intento < 10 && !perdida; intento++) {   // cerrar sí o sí: los archivos abiertos son 8
        if (tomarSD(gen)) {
            f->close();
            xSemaphoreGive(mutexSD);
            delete f;
            break;
        }
        perdida = sdGeneracion != gen || !sdMontada;
    }
    // [VALIDAR EN PLACA] velocidad real de descarga por el punto de acceso con la adquisición corriendo
    Serial.printf("[WEB] descarga %s: %u de %u B en %.1f s%s\n", nombre.c_str(), (unsigned)enviados, (unsigned)tam,
                  (millis() - t0) / 1000.0f, perdida ? " (la microSD se remontó: cortada)" : "");
}

// ---- Etiquetas y modo mesa ----
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
    servidor.on("/senal", HTTP_GET, manejarSenal);
    servidor.on("/ajustes", HTTP_GET, manejarAjustesGet);
    servidor.on("/ajustes", HTTP_POST, manejarAjustesPost);
    servidor.on("/archivos", HTTP_GET, manejarArchivos);
    servidor.on("/descargar", HTTP_GET, manejarDescarga);
    servidor.on("/etiqueta", HTTP_POST, manejarEtiqueta);
    servidor.on("/mesa", HTTP_POST, manejarMesa);
    servidor.onNotFound([] { servidor.send(404, "text/plain", "no existe"); });
    servidor.begin();
    for (;;) {
        servidor.handleClient();
        vTaskDelay(pdMS_TO_TICKS(5));
    }
}
