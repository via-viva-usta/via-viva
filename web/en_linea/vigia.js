// VÍA VIVA · tablero. Si app.js o una librería del CDN no cargan en 12 s, se avisa y se ofrece reintentar
// (antes la página se quedaba en «Cargando…» para siempre). app.js pone window.VV_ARRANCO = true al empezar.
(function () {
  setTimeout(function () {
    if (window.VV_ARRANCO) return;
    var t = document.getElementById('t-frescura');
    if (t) t.textContent = 'Sin conexión';
    var aviso = document.createElement('div');
    aviso.className = 'falla-carga';
    aviso.setAttribute('role', 'alert');
    aviso.innerHTML = '<p class="t-etiqueta">No se pudo cargar el tablero</p>' +
      '<p>Revise la conexión a internet. Si sigue igual, puede que una de las librerías del mapa no esté disponible.</p>';
    var boton = document.createElement('button');
    boton.type = 'button';
    boton.className = 'b-marca lleno';
    boton.textContent = 'Reintentar';
    boton.onclick = function () { location.reload(); };
    aviso.appendChild(boton);
    document.body.appendChild(aviso);
    boton.focus();
  }, 12000);
})();
