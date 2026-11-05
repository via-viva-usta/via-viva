"""Etiquetador local de fotos: una página en el navegador con botones (y atajos de teclado) que guarda en metadatos.csv.

Pensado para etiquetar rápido (Pipe y Juan Diego). No necesita internet ni instalar nada más que el venv del dataset:
usa el servidor HTTP de la biblioteca estándar de Python y solo escucha en este PC (127.0.0.1).

Uso (desde via-viva/, después de dataset.ingesta):
  dataset\\.venv\\Scripts\\python -m dataset.etiquetador                 abre http://127.0.0.1:8765
  dataset\\.venv\\Scripts\\python -m dataset.etiquetador --autor pipe    solo las fotos de esa persona
  dataset\\.venv\\Scripts\\python -m dataset.etiquetador --sintetico     prueba con las fotos SINTÉTICAS

Cada clic en "Guardar" reescribe SOLO esa fila del CSV (escritura atómica). Cerrar con Ctrl+C en la consola.
Instrucciones completas en dataset/README.md.
"""
from __future__ import annotations

import argparse
import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pandas as pd

from dataset.comun import (ANGULOS, CLASES, CLASES_DANO, COLUMNAS, LUCES, PROCESADO, PROCESADO_SINTETICO, SEVERIDADES,
                           SUPERFICIES, guardar_csv, leer_metadatos)

EDITABLES = {"clase": CLASES, "severidad": SEVERIDADES, "angulo": ANGULOS, "superficie": SUPERFICIES, "luz": LUCES,
             "superficie_mojada": ["si", "no"]}
LIBRES = ["distancia_m", "notas", "largo_regla_cm", "ancho_regla_cm", "temperatura", "humedad"]
NUMERICOS = {"distancia_m", "largo_regla_cm", "ancho_regla_cm", "temperatura", "humedad"}

PAGINA = r"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>VÍA VIVA · etiquetador</title>
<style>
:root{--asfalto:#2f2f2f;--senal:#f2c230;--ok:#2a9d8f;--mal:#b3261e;--fondo:#f4f3ef}
*{box-sizing:border-box}body{margin:0;font-family:system-ui,sans-serif;background:var(--fondo);color:var(--asfalto)}
header{background:var(--asfalto);color:#fff;padding:8px 14px;display:flex;gap:14px;align-items:center;flex-wrap:wrap}
header b{color:var(--senal)}header select,header button{font-size:.9rem}
main{display:grid;grid-template-columns:minmax(0,1fr) 400px;gap:12px;padding:12px}
@media(max-width:900px){main{grid-template-columns:1fr}}
#foto{width:100%;max-height:80vh;object-fit:contain;background:#000;border-radius:8px}
.info{font-size:.85rem;margin-top:6px;line-height:1.5}
.grupo{background:#fff;border-radius:10px;padding:8px 10px;margin-bottom:8px;box-shadow:0 1px 3px #0002}
.grupo h3{margin:0 0 6px;font-size:.85rem;text-transform:uppercase;letter-spacing:.03em}
.grupo h3 small{font-weight:400;text-transform:none;color:#777}
.bts{display:flex;flex-wrap:wrap;gap:5px}
.bts button{border:1px solid #bbb;background:#fafafa;border-radius:8px;padding:7px 9px;font-size:.88rem;cursor:pointer}
.bts button.sel{background:var(--asfalto);color:#fff;border-color:var(--asfalto)}
.bts button:disabled{opacity:.35;cursor:default}
.bts button kbd{font-size:.7rem;color:#999;margin-left:4px}.bts button.sel kbd{color:var(--senal)}
input[type=text],input[type=number]{width:100%;padding:6px;border:1px solid #bbb;border-radius:6px;font-size:.9rem}
.fila{display:grid;grid-template-columns:1fr 1fr;gap:6px}
.acciones{display:flex;gap:8px;margin-top:4px}
.acciones button{flex:1;padding:12px;border:0;border-radius:10px;font-size:1rem;font-weight:700;cursor:pointer}
#guardar{background:var(--ok);color:#fff}#excluir{background:#ddd}#estado{min-height:1.3em;font-weight:600}
.sintetico{background:var(--mal);color:#fff;padding:2px 8px;border-radius:6px}
</style></head><body>
<header><span><b>VÍA VIVA</b> · etiquetador de fotos</span><span id="aviso"></span>
<span id="progreso"></span>
<label>Mostrar <select id="filtro"><option value="sin">sin etiquetar</option><option value="todas">todas</option></select></label>
<button id="ant">← anterior</button><button id="sig">siguiente →</button><span id="pos"></span></header>
<main><section><img id="foto" alt="foto"><div class="info" id="info"></div></section>
<aside>
<div class="grupo"><h3>Clase <small>teclas 1–9</small></h3><div class="bts" data-campo="clase"></div></div>
<div class="grupo"><h3>Severidad <small>Q W E · solo daños</small></h3><div class="bts" data-campo="severidad"></div></div>
<div class="grupo"><h3>Ángulo <small>A S D F</small></h3><div class="bts" data-campo="angulo"></div></div>
<div class="grupo"><h3>Luz <small>Z X C V</small></h3><div class="bts" data-campo="luz"></div></div>
<div class="grupo"><h3>Superficie mojada <small>M</small></h3><div class="bts" data-campo="superficie_mojada"></div></div>
<div class="grupo"><h3>Superficie <small>asfalto, concreto, adoquín o destapada (la planilla la llena si existe)</small></h3><div class="bts" data-campo="superficie"></div></div>
<div class="grupo"><h3>Opcional</h3>
<div class="fila"><label>Distancia al daño (m)<input type="number" step="0.1" min="0" id="distancia_m"></label>
<label>Notas<input type="text" id="notas"></label></div>
<div class="fila"><label>Largo con regla (cm)<input type="number" step="0.5" min="0" id="largo_regla_cm"></label>
<label>Ancho con regla (cm)<input type="number" step="0.5" min="0" id="ancho_regla_cm"></label></div>
<div class="fila"><label>Termohigrómetro °C<input type="number" step="0.1" id="temperatura"></label>
<label>Termohigrómetro % HR<input type="number" step="1" id="humedad"></label></div></div>
<div class="acciones"><button id="excluir" title="persona o placa visible, foto mala">Excluir</button>
<button id="guardar">Guardar y seguir ⏎</button></div><div id="estado"></div>
</aside></main>
<script>
const OPC=__OPCIONES__, DANO=new Set(__DANO__);
const TECLAS={clase:'123456789',severidad:'qwe',angulo:'asdf',luz:'zxcv'};
let lista=[],i=0,fila=null,sel={},termoOriginal={};
const $=id=>document.getElementById(id);
function botones(){for(const div of document.querySelectorAll('.bts')){const c=div.dataset.campo;
div.innerHTML=OPC[c].map((v,k)=>`<button data-v="${v}">${v.replace('_',' ')}${TECLAS[c]?'<kbd>'+TECLAS[c][k].toUpperCase()+'</kbd>':''}</button>`).join('');
div.onclick=e=>{const b=e.target.closest('button');if(b&&!b.disabled)elegir(c,b.dataset.v)}}}
function elegir(c,v){sel[c]=sel[c]===v&&c!=='clase'?'':v;if(c==='clase'&&!DANO.has(sel.clase))sel.severidad='';pintar()}
function pintar(){for(const div of document.querySelectorAll('.bts')){const c=div.dataset.campo;
for(const b of div.children){b.classList.toggle('sel',sel[c]===b.dataset.v);
if(c==='severidad')b.disabled=!DANO.has(sel.clase)}}}
async function cargarLista(){const r=await fetch('/api/lista?filtro='+$('filtro').value);const d=await r.json();
lista=d.ids;$('progreso').textContent=d.etiquetadas+' / '+d.total+' etiquetadas';
$('aviso').innerHTML=d.sintetico?'<span class="sintetico">SINTÉTICO: solo prueba</span>':'';
if(i>=lista.length)i=Math.max(0,lista.length-1);mostrar()}
async function mostrar(){if(!lista.length){$('foto').removeAttribute('src');$('info').textContent='No hay fotos en esta vista.';$('pos').textContent='';return}
const id=lista[i];const r=await fetch('/api/foto?id='+id);fila=await r.json();
$('foto').src='/img/'+id+'.jpg';$('pos').textContent=(i+1)+' / '+lista.length;
sel={};for(const c in OPC)sel[c]=fila[c]||'';
for(const c of ['distancia_m','notas','largo_regla_cm','ancho_regla_cm'])$(c).value=fila[c]||'';
const termo=fila.fuente_clima==='termohigrometro';$('temperatura').value=termo?fila.temperatura:'';$('humedad').value=termo?fila.humedad:'';
termoOriginal={t:$('temperatura').value,h:$('humedad').value};
$('info').innerHTML=`<b>${id}</b> · ${fila.autor||'?'} · ${fila.fecha||'sin fecha'} ${fila.hora||''} (${fila.momento_dia||'?'}) · `+
`${fila.lat?fila.lat+', '+fila.lon:'<b style="color:#b3261e">sin GPS</b>'} · tramo ${fila.id_tramo||'–'} (${fila.tipo_via||'–'}, OSM) · ${fila.barrio||'–'}<br>`+
`Clima: ${fila.temperatura||'–'} °C, ${fila.humedad||'–'} % (${fila.fuente_clima||'sin fuente'}) · lluvia IDEAM del día: ${fila.lluvia_ideam||'–'} mm`+
(fila.notas?' · notas: '+fila.notas:'');pintar();$('estado').textContent=''}
async function guardar(excluir){const campos={...sel};
for(const c of ['distancia_m','notas','largo_regla_cm','ancho_regla_cm'])campos[c]=$(c).value.trim();
if($('temperatura').value!==termoOriginal.t||$('humedad').value!==termoOriginal.h){campos.temperatura=$('temperatura').value;campos.humedad=$('humedad').value}
if(excluir){campos.notas=('EXCLUIR '+campos.notas.replace(/^EXCLUIR\s*/,'')).trim()}
else if(!campos.clase){$('estado').textContent='Falta la clase';return}
const r=await fetch('/api/guardar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:lista[i],campos})});
const d=await r.json();if(!r.ok){$('estado').textContent='No se guardó: '+d.error;return}
$('estado').textContent=excluir?'Excluida':'Guardada';$('progreso').textContent=d.etiquetadas+' / '+d.total+' etiquetadas';
if($('filtro').value==='sin'){lista.splice(i,1);if(i>=lista.length)i=Math.max(0,lista.length-1)}else if(i<lista.length-1)i++;
setTimeout(mostrar,250)}
document.addEventListener('keydown',e=>{if(e.target.tagName==='INPUT'){if(e.key==='Enter')guardar(false);return}
const k=e.key.toLowerCase();for(const c in TECLAS){const p=TECLAS[c].indexOf(k);if(p>=0&&p<OPC[c].length){
if(c==='severidad'&&!DANO.has(sel.clase))return;elegir(c,OPC[c][p]);return}}
if(k==='m')elegir('superficie_mojada',sel.superficie_mojada==='si'?'no':'si');
else if(e.key==='Enter')guardar(false);else if(e.key==='ArrowRight')$('sig').click();else if(e.key==='ArrowLeft')$('ant').click()});
$('sig').onclick=()=>{if(i<lista.length-1){i++;mostrar()}};$('ant').onclick=()=>{if(i>0){i--;mostrar()}};
$('guardar').onclick=()=>guardar(false);$('excluir').onclick=()=>guardar(true);$('filtro').onchange=()=>{i=0;cargarLista()};
botones();cargarLista();
</script></body></html>"""


class Etiquetador:
    def __init__(self, salida: Path, autor: str | None, sintetico: bool):
        self.ruta = salida / "metadatos.csv"
        self.fotos = salida / "fotos"
        self.autor = autor
        self.sintetico = sintetico
        self.candado = threading.Lock()
        if not self.ruta.exists():
            raise SystemExit(f"No existe {self.ruta}: correr primero dataset.ingesta")

    def tabla(self) -> pd.DataFrame:
        df = leer_metadatos(self.ruta)
        return df[df["autor"] == self.autor] if self.autor else df

    def lista(self, filtro: str) -> dict:
        df = self.tabla()
        hechas = (df["clase"] != "") | df["notas"].str.contains("EXCLUIR")
        ids = df["id"] if filtro == "todas" else df.loc[~hechas, "id"]
        return {"ids": ids.tolist(), "total": len(df), "etiquetadas": int(hechas.sum()), "sintetico": self.sintetico}

    def guardar(self, id_: str, campos: dict) -> dict:
        for c, v in campos.items():
            v = str(v).strip()
            if c in EDITABLES and v and v not in EDITABLES[c]:
                raise ValueError(f"{c} = {v!r} no es válido")
            if c not in EDITABLES and c not in LIBRES:
                raise ValueError(f"campo {c} no editable")
            if c in NUMERICOS and v:
                float(v)
            campos[c] = v
        if campos.get("clase") not in CLASES_DANO:
            campos["severidad"] = ""
        with self.candado:                     # lee, cambia una fila y escribe: nunca dos guardados a la vez
            df = leer_metadatos(self.ruta)
            fila = df.index[df["id"] == id_]
            if len(fila) != 1:
                raise ValueError(f"id {id_} no existe")
            k = fila[0]
            for c, v in campos.items():
                if c in ("temperatura", "humedad"):
                    continue
                df.at[k, c] = v
            if "temperatura" in campos or "humedad" in campos:   # lectura del termohigrómetro: manda sobre nodo y API
                if campos.get("temperatura"):
                    df.at[k, "temperatura"], df.at[k, "humedad"] = campos["temperatura"], campos.get("humedad", "")
                    df.at[k, "fuente_clima"], df.at[k, "lux"] = "termohigrometro", ""
                elif df.at[k, "fuente_clima"] == "termohigrometro":   # la borraron: la próxima ingesta la rellena
                    df.at[k, "temperatura"] = df.at[k, "humedad"] = df.at[k, "fuente_clima"] = ""
            guardar_csv(df[COLUMNAS], self.ruta)
        return self.lista("sin") | {"ids": []}


def servidor(et: Etiquetador):
    opciones = json.dumps(EDITABLES)
    pagina = PAGINA.replace("__OPCIONES__", opciones).replace("__DANO__", json.dumps(sorted(CLASES_DANO))).encode()

    class Manejador(BaseHTTPRequestHandler):
        def log_message(self, *a):               # consola limpia
            pass

        def responder(self, codigo, cuerpo: bytes, tipo="application/json"):
            self.send_response(codigo)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(cuerpo)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(cuerpo)

        def json(self, codigo, obj):
            self.responder(codigo, json.dumps(obj, ensure_ascii=False).encode())

        def do_GET(self):
            u = urlparse(self.path)
            q = parse_qs(u.query)
            if u.path == "/":
                self.responder(200, pagina, "text/html; charset=utf-8")
            elif u.path == "/api/lista":
                self.json(200, et.lista(q.get("filtro", ["sin"])[0]))
            elif u.path == "/api/foto":
                df = et.tabla()
                f = df[df["id"] == q.get("id", [""])[0]]
                self.json(200, f.iloc[0].to_dict()) if len(f) else self.json(404, {"error": "no existe"})
            elif u.path.startswith("/img/"):
                nombre = Path(u.path).name      # solo el nombre: no se puede salir de la carpeta de fotos
                p = et.fotos / nombre
                if p.suffix == ".jpg" and p.exists():
                    self.responder(200, p.read_bytes(), "image/jpeg")
                else:
                    self.json(404, {"error": "no existe"})
            else:
                self.json(404, {"error": "no existe"})

        def do_POST(self):
            if urlparse(self.path).path != "/api/guardar":
                return self.json(404, {"error": "no existe"})
            try:
                d = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                self.json(200, et.guardar(d["id"], dict(d["campos"])))
            except (ValueError, KeyError, json.JSONDecodeError) as e:
                self.json(400, {"error": str(e)})

    return Manejador


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--salida", type=Path, default=None, help="carpeta con metadatos.csv y fotos/ (data/procesado)")
    ap.add_argument("--autor", default=None, help="mostrar solo las fotos de esta persona (nombre de la carpeta)")
    ap.add_argument("--sintetico", action="store_true")
    ap.add_argument("--puerto", type=int, default=8765)
    ap.add_argument("--sin-navegador", action="store_true")
    a = ap.parse_args()
    salida = a.salida or (PROCESADO_SINTETICO if a.sintetico else PROCESADO)
    et = Etiquetador(salida, a.autor, a.sintetico)
    srv = ThreadingHTTPServer(("127.0.0.1", a.puerto), servidor(et))
    url = f"http://127.0.0.1:{a.puerto}/"
    print(f"Etiquetador en {url}  (metadatos: {et.ruta})  · Ctrl+C para cerrar")
    if not a.sin_navegador:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nCerrado. Las etiquetas ya están guardadas en el CSV.")


if __name__ == "__main__":
    main()
