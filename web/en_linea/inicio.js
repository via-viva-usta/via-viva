// VÍA VIVA · portada. Sin librerías: hora de Tunja, aparición por partes y cifras que cuentan al verse.
(function () {
  // Los enlaces viejos (?demo=1, ?kiosco=1 en la raíz) siguen llevando al tablero
  if (/[?&](demo|kiosco|rol)\b/.test(location.search)) { location.replace('tablero.html' + location.search + location.hash); return; }

  var quieto = matchMedia('(prefers-reduced-motion: reduce)').matches;

  // Hora local de Tunja (como el «New York 21:33» de la referencia)
  var hora = document.getElementById('hora');
  function reloj() {
    hora.textContent = new Date().toLocaleTimeString('es-CO', {timeZone: 'America/Bogota', hour: '2-digit', minute: '2-digit', hour12: false});
  }
  reloj(); setInterval(reloj, 15000);
  document.getElementById('anio').textContent = new Date().getFullYear();

  // Cifras que cuentan desde 0 cuando se ven (formato es-CO: 5 775 · 537,6)
  function formato(v, dec) { return v.toLocaleString('es-CO', {minimumFractionDigits: dec, maximumFractionDigits: dec}).replace(/\./g, ' '); }
  function contar(el) {
    var fin = parseFloat(el.dataset.contar), dec = parseInt(el.dataset.dec || '0', 10), t0 = null, dur = 1300;
    if (quieto) { el.textContent = formato(fin, dec); return; }
    function paso(t) {
      t0 = t0 || t;
      var p = Math.min(1, (t - t0) / dur), suave = 1 - Math.pow(1 - p, 3);
      el.textContent = formato(fin * suave, dec);
      if (p < 1) requestAnimationFrame(paso);
    }
    requestAnimationFrame(paso);
  }
  for (var c of document.querySelectorAll('[data-contar]')) c.textContent = formato(parseFloat(c.dataset.contar), parseInt(c.dataset.dec || '0', 10));

  // Aparición: la portada al cargar; lo demás al entrar en pantalla
  var partes = document.querySelectorAll('.aparece');
  if (quieto || !('IntersectionObserver' in window)) { partes.forEach(function (e) { e.classList.add('visible'); }); return; }
  var vigia = new IntersectionObserver(function (entradas) {
    entradas.forEach(function (e) {
      if (!e.isIntersecting) return;
      e.target.classList.add('visible');
      e.target.querySelectorAll('[data-contar]').forEach(contar);
      vigia.unobserve(e.target);
    });
  }, {rootMargin: '0px 0px -8% 0px', threshold: 0.12});
  partes.forEach(function (e) { vigia.observe(e); });
})();
