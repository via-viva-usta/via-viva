# Seguridad y protección de datos

## Secretos

- Solo en `.env` (ignorado por Git; `chmod 600` en la Pi): `SUPABASE_CLAVE` (secreta, solo la Pi/PC que sincroniza),
  `SOCRATA_APP_TOKEN`, `PI_AP_CLAVE`, tokens del bot (pospuesto). `.env.example` lleva solo los nombres.
- La clave **pública** de Supabase va a la página (es pública por diseño); sin sesión no lee nada (RLS).
  `viaviva nube preparar` se niega a publicar si la clave pública es igual a la secreta.
- Contraseñas: cada persona escribe la suya en la consola (`viaviva usuarios crear`), PBKDF2-SHA256 con 200 000
  iteraciones; en Supabase las maneja Supabase Auth. Nunca por chat, nunca en el repositorio.
- `herramientas/buscar_secretos.py` revisa todo el historial de Git (sin imprimir valores).

## Ley 1581 de 2012 (protección de datos personales) y Decreto 1377 de 2013

| Principio | Cómo se cumple |
|---|---|
| Finalidad | Los datos se usan solo para detectar y priorizar daños de la vía (proyecto académico; no multas, no placas) |
| Libertad | Quien participa (equipo, conductor voluntario) lo hace con su consentimiento; no se recogen datos de terceros |
| Circulación restringida | Las sesiones (que contienen la trayectoria del carro) viven en `06_CAMPO` y el Drive restringido del equipo; **nunca** en Git ni en la nube. A la nube solo van eventos/huecos (puntos de la vía) y riesgo por tramo |
| Seguridad | Roles (editor / Alcaldía / docente), RLS, cookies HttpOnly y SameSite=Strict, límite de intentos, apagado seguro |
| Acceso y supresión | Un usuario se desactiva con `viaviva usuarios desactivar` o en Supabase; las sesiones se pueden borrar del Drive |
| Datos sensibles | No se capturan: sin cámara en el nodo; las fotos del dataset se difuminan (caras y placas) antes de procesarlas |

## Qué NO se publica

Datos crudos de sensores y trayectorias · videos y fotos de campo (sin difuminar) · datos entregados por la Alcaldía ·
nombres o correos de quien maneja o etiqueta · notas de texto libre · usuarios de la base local · cualquier dato DEMO o
simulado presentado como real.

## Red

En campo, el PC y los celulares están en el hotspot del iPhone (WPA2). El tablero local escucha en el puerto 8000;
Windows pregunta por el Firewall la primera vez: permitir **solo en redes privadas**. HTTPS en la red local: pendiente
(el tablero en línea sí va por HTTPS en Netlify y Supabase).
