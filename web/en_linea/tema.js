// Tema ANTES de pintar la página (evita el destello). Por defecto, oscuro («asfalto», la marca de VÍA VIVA); si la
// persona eligió claro con el botón ◐, se respeta. Va en un archivo aparte porque la CSP no permite scripts en línea.
(function () {
  var t = null;
  try { t = localStorage.getItem('vv_tema'); } catch (e) { /* almacenamiento bloqueado: queda el de la marca */ }
  document.documentElement.dataset.theme = t === 'light' ? 'light' : 'dark';
})();
