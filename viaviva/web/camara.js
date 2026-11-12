// VÍA VIVA · cámara en vivo (webcam del PC en /captura, celular en /camara). Necesita contexto seguro:
// http://localhost (la app en el PC) o HTTPS (el celular, por el puerto 8443 con la autoridad local instalada).
// Graba con MediaRecorder en partes de 2 s que se suben en orden a la sesión abierta; la hora de inicio se corrige
// contra el reloj del PC (/api/hora), así el video queda sincronizado con la señal sin destello.
class CamaraVV {
  constructor(video, origen) {
    this.video = video; this.origen = origen || 'pc';
    this.flujo = null; this.grabador = null; this.id = null; this.n = 0; this.cola = Promise.resolve();
    this.alCambiar = () => {}; this.error = null; this.bytes = 0; this.cuadros = null;
  }
  static disponible() { return !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia) && window.isSecureContext; }
  static motivo() {
    if (!window.isSecureContext) return 'Esta página no es segura (http://IP): el navegador no da la cámara. ' +
      'En el PC use la app (http://localhost); en el celular, la dirección https:// del panel de conexión.';
    if (!navigator.mediaDevices) return 'Este navegador no permite usar la cámara.';
    return '';
  }
  async listar() {
    try {
      const d = await navigator.mediaDevices.enumerateDevices();
      return d.filter(x => x.kind === 'videoinput').map((x, i) => ({id: x.deviceId, nombre: x.label || ('Cámara ' + (i + 1))}));
    } catch (e) { return []; }
  }
  async encender(idDispositivo, trasera) {
    this.apagar();
    const video = idDispositivo ? {deviceId: {exact: idDispositivo}} : (trasera ? {facingMode: {ideal: 'environment'}} : {});
    Object.assign(video, {width: {ideal: 1280}, height: {ideal: 720}, frameRate: {ideal: 30}});
    this.flujo = await navigator.mediaDevices.getUserMedia({video, audio: false});
    this.video.srcObject = this.flujo; await this.video.play().catch(() => {});
    this.alCambiar();
  }
  apagar() {
    if (this.grabando()) this.detener();
    if (this.cuadros) { clearInterval(this.cuadros); this.cuadros = null; }
    if (this.flujo) this.flujo.getTracks().forEach(t => t.stop());
    this.flujo = null; this.video.srcObject = null; this.alCambiar();
  }
  grabando() { return !!(this.grabador && this.grabador.state !== 'inactive'); }
  static tipos() {                           // H.264 en MP4 primero (lo abre cualquier reproductor); si no, WebM
    return ['video/mp4;codecs=avc1', 'video/mp4', 'video/webm;codecs=vp9', 'video/webm;codecs=vp8', 'video/webm']
      .filter(t => window.MediaRecorder && MediaRecorder.isTypeSupported(t));
  }
  static tipo() { return CamaraVV.tipos()[0] || ''; }
  async desfaseReloj() {                     // hora del PC − hora de este equipo (s), con la mitad del viaje
    let mejor = null;
    for (let k = 0; k < 3; k++) {
      const t0 = Date.now() / 1000, r = await fetch('/api/hora', {cache: 'no-store'}).then(x => x.json()), t1 = Date.now() / 1000;
      const d = {viaje: t1 - t0, desfase: r.utc - (t0 + t1) / 2};
      if (!mejor || d.viaje < mejor.viaje) mejor = d;
    }
    return mejor.desfase;
  }
  async grabar() {
    if (!this.flujo) throw new Error('Encienda la cámara primero');
    if (!window.MediaRecorder) throw new Error('Este navegador no puede grabar video (MediaRecorder)');
    const desfase = await this.desfaseReloj();
    this.id = 'v' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
    this.n = 0; this.bytes = 0; this.error = null;
    // Algunos equipos dicen que aceptan MP4 y luego no arrancan: se prueba cada formato hasta que uno empiece
    let tipo = '', ultimoError = null;
    for (const t of [...CamaraVV.tipos(), '']) {
      try {
        this.grabador = new MediaRecorder(this.flujo, t ? {mimeType: t, videoBitsPerSecond: 2_500_000} : {});
        this.grabador.start(2000); tipo = t; ultimoError = null; break;
      } catch (e) { ultimoError = e; this.grabador = null; }
    }
    if (!this.grabador) throw new Error('No se pudo grabar video en este navegador: ' + (ultimoError && ultimoError.message));
    const inicio = Date.now() / 1000 + desfase, mime = this.grabador.mimeType || tipo || 'video/webm';
    this.grabador.ondataavailable = (ev) => {
      if (!ev.data || !ev.data.size) return;
      const n = this.n++;
      this.cola = this.cola.then(async () => {
        const q = new URLSearchParams({id: this.id, n, tipo: mime, origen: this.origen});
        if (n === 0) q.set('inicio', inicio.toFixed(3));
        const r = await fetch('/api/camara/parte?' + q, {method: 'POST', body: ev.data, credentials: 'same-origin'});
        if (!r.ok) { const d = await r.json().catch(() => ({})); throw new Error(d.error || ('HTTP ' + r.status)); }
        this.bytes += ev.data.size; this.alCambiar();
      }).catch(e => { this.error = e.message; this.detener(); this.alCambiar(); });
    };
    this.grabador.onstop = () => {
      const id = this.id;
      this.cola = this.cola.then(() => fetch('/api/camara/fin?id=' + encodeURIComponent(id), {method: 'POST'}))
        .catch(() => {}).then(() => this.alCambiar());
    };
    this.alCambiar();
  }
  detener() { if (this.grabando()) this.grabador.stop(); }
  enviarCuadros(cada) {                      // vista previa en el PC: un JPEG pequeño cada `cada` ms
    if (this.cuadros) clearInterval(this.cuadros);
    const cv = document.createElement('canvas');
    this.cuadros = setInterval(() => {
      if (!this.flujo || !this.video.videoWidth) return;
      cv.width = 480; cv.height = Math.round(480 * this.video.videoHeight / this.video.videoWidth);
      cv.getContext('2d').drawImage(this.video, 0, 0, cv.width, cv.height);
      cv.toBlob(b => b && fetch('/api/camara/cuadro?origen=' + this.origen, {method: 'POST', body: b}).catch(() => {}),
                'image/jpeg', 0.6);
    }, cada || 700);
  }
}
