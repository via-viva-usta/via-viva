// Actualizaciones seguras del clon de escritorio. El servidor oculta este control en modo Pi/servicio.
(() => {
  const $ = (id) => document.getElementById(id);
  const controles = $('actualizacion');
  const actualizar = $('b-actualizar');
  const revertir = $('b-revertir');
  const mensaje = $('actualizacion-msg');
  if (!controles || !actualizar || !revertir || !mensaje) return;

  let ocupada = false;
  const texto = (valor) => { mensaje.textContent = valor; };
  const mostrarBotones = (estado) => {
    actualizar.classList.toggle('oculto', !estado.disponible);
    revertir.classList.toggle('oculto', !estado.revertible);
    actualizar.disabled = ocupada || !!estado.grabando || !estado.disponible;
    revertir.disabled = ocupada || !!estado.grabando || !estado.revertible;
  };

  async function consultar() {
    if (ocupada) return;
    try {
      const d = await VV.json('/api/actualizacion');
      if (!d.habilitada) { controles.classList.add('oculto'); return; }
      controles.classList.remove('oculto');
      mostrarBotones(d);
      const versiones = d.actual ? ` · instalada ${d.actual}` : '';
      if (d.estado === 'disponible') texto(`Hay una versión lista${versiones}${d.nueva ? ` · nueva ${d.nueva}` : ''}.`);
      else if (d.estado === 'al_dia') texto(`VÍA VIVA está al día${versiones}.`);
      else if (d.estado === 'sin_internet') texto(`Sin internet; se conserva la versión instalada${versiones}.`);
      else if (d.estado === 'grabando') texto(d.mensaje);
      else if (d.estado === 'divergido') texto('Esta copia no sigue el historial de main. Actualización detenida; pide revisión técnica.');
      else texto(d.mensaje || 'Actualización automática no disponible; esta versión sigue funcionando.');
    } catch (e) {
      controles.classList.remove('oculto');
      mostrarBotones({});
      texto('No se pudo comprobar la actualización; la app instalada sigue funcionando.');
    }
  }

  async function ejecutar(ruta, pregunta, textoExito) {
    if (ocupada || !window.confirm(pregunta)) return;
    ocupada = true;
    mostrarBotones({});
    texto('Aplicando cambios. Espera; no cierres VÍA VIVA…');
    try {
      const d = await VV.post(ruta, {});
      if (d.ok) texto(d.mensaje || textoExito);
      else texto(d.mensaje || 'No se pudo completar la operación.');
      if (!d.ok) { ocupada = false; await consultar(); }
    } catch (e) {
      ocupada = false;
      texto(e.message || 'No se pudo completar la operación.');
      await consultar();
    }
  }

  actualizar.addEventListener('click', () => ejecutar('/api/actualizacion/aplicar',
    'Se actualizará VÍA VIVA desde main. La app se reiniciará al terminar; una grabación o video activo bloquearía la operación. ¿Continuar?',
    'Actualización instalada. Reiniciando VÍA VIVA.'));
  revertir.addEventListener('click', () => ejecutar('/api/actualizacion/revertir',
    'Se restaurará la versión anterior de VÍA VIVA y la app se reiniciará. ¿Continuar?',
    'Versión anterior restaurada. Reiniciando VÍA VIVA.'));

  consultar();
  window.setInterval(() => { if (!document.hidden) consultar(); }, 5 * 60 * 1000);
})();
