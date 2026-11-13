# Contribuir a VÍA VIVA

El paso a paso (clonar, rama, probar, PR) está en **[`GUIA_TRABAJO.md`](GUIA_TRABAJO.md)**. Aquí, solo las reglas.

1. **`main` es la versión compartida.** Todo entra por un PR pequeño con los 3 checks en verde (`pytest` con ruff,
   `node-test`, `compilar`) y una aprobación de otra persona. Nadie empuja a `main` directo ni usa `--force`.
2. **Ramas cortas desde `main`:** `ac/<tarea>`, `dani/<tarea>` o `compartida/<tarea>`. Créelas con
   `herramientas\tarea.cmd` (Windows) o `./herramientas/tarea.sh` (Mac). Al fusionar se borran; antes de borrar una
   rama sin fusionar se guarda en una etiqueta `archivo/<rama>`.
3. **Responsables:** Dany → `web/` (interfaz e identidad; `web/en_linea/marca.css` es la única fuente de estilos, que
   también usa la app local). AC → `viaviva/`, `firmware/`, `db/`, `tests/`. Los cambios de Pi, sensores o firmware no
   se mezclan con cambios visuales. `CODEOWNERS` propone revisor por carpeta.
4. **Carril de campo:** la versión de la prueba en el carro está congelada en una etiqueta (`campo-AAAA-MM-DD`) y se usa
   en un clon aparte. No se edita ni se actualiza: el botón **Actualizar** solo funciona en un clon en la rama `main`.
5. **Datos y secretos:** nunca subir `.env`, claves, `06_CAMPO`, `data/raw/`, datos de la Alcaldía, fotos ni videos.
   Las claves de Supabase del sitio en línea van como variables de Netlify, no en el repo.
6. **Resultados:** toda cifra sale de código o medición; lo sintético se marca SINTÉTICO/DEMO; lo no probado en
   hardware real se dice.
