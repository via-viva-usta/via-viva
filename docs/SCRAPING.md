# Scraping: términos de uso y robots.txt (revisado el 10-nov-2026)

Reglas del proyecto: User-Agent identificable con contacto (`SCRAPER_USER_AGENT` en `.env`), respetar el `Crawl-delay`
más largo de cada sitio, guardar solo **titular, enlace, fecha y un extracto breve** (nunca el artículo completo), citar la
fuente y **nunca** resolver CAPTCHA. Tarea diaria: `etl.scraping.diario` (Programador de tareas del PC, 06:30, o el
temporizador `via-viva-scraping.timer` en la Pi).

| Fuente | Qué se usa | Licencia / términos | robots.txt | Estado |
|---|---|---|---|---|
| Gobernación de Boyacá (`boyaca.gov.co/feed/`) | Titulares RSS (vías departamentales) | Portal oficial; RSS publicado para lectura automática | `etl.scraping.noticias --revisar` (10-nov): permitido | **Habilitada** (6 entradas el 10-nov, 0 relevantes) |
| datos.gov.co, dataset `s54a-sgyg` (Precipitación, IDEAM) | API SODA `/resource/s54a-sgyg.json` | **CC BY-SA 4.0** (citar al IDEAM; redistribuir igual). Términos del portal: uso libre (Ley 1712/2014) | `User-agent: *`, `Crawl-delay: 1`; bloquea `/api/odata/`, `/OData.svc/`, `/login`, `/tiles/`; **no** bloquea `/resource/` | Permitido. Con `SOCRATA_APP_TOKEN` en `.env` no hay límite compartido por IP |
| Boyacá 7 Días (`boyaca7dias.com.co`) | Titulares sobre cierres y accidentes en Tunja | Sin página de términos; el pie dice "prohibida su reproducción total o parcial sin autorización" (protege el contenido, no prohíbe leer) | Permite todo, sin crawl-delay | **Apagada** en `etl/scraping/noticias.py` hasta que el equipo decida (el pie prohíbe la reproducción; se guardaría solo titular, enlace y fecha). `www.boyacasietedias.com` **no existe** (DNS) |
| El Diario de Boyacá (`eldiarioboyaca.com`) | Titulares | Sin página de términos encontrada | Permite todo | Permitido con metadatos. El dominio viejo `periodicoeldiario.com` es una página "Coming Soon" con `Crawl-delay: 10` y `Content-Signal: ai-train=no, use=reference`: **no se usa** |
| Radio Boyacá | — | — | `www.radioboyaca.com` **no existe** (DNS) | **No se usa** hasta que el equipo confirme el dominio |
| Alcaldía de Tunja (`tunja-boyaca.gov.co`) | — | Política de derechos de autor (dic-2025) editorial; no menciona recolección automática | `/robots.txt` devuelve HTML (no hay reglas); usa hCaptcha | **No se raspa** (CAPTCHA). Datos de la Alcaldía solo por entrega oficial, nunca al repo |

Fuentes: https://www.datos.gov.co/robots.txt · https://www.datos.gov.co/api/views/s54a-sgyg.json ·
https://herramientas.datos.gov.co/terminos · https://dev.socrata.com/docs/app-tokens ·
https://boyaca7dias.com.co/robots.txt · https://eldiarioboyaca.com/robots.txt · https://www.periodicoeldiario.com/robots.txt ·
https://www.tunja-boyaca.gov.co/politicas-y-lineamientos/politica-de-derechos-de-autor
