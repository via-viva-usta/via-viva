---
name: vv-sincronizar-github
description: Revisa cuenta de GitHub, rama, estado local, remotos, PR abiertos, checks y auto-merge de VÍA VIVA antes de traer o subir cambios, respetando las reglas de ramas (nunca main directo ni --force).
disable-model-invocation: true
---

# Sincronizar con GitHub

1. **Cuenta:** `gh auth status`; la activa debe ser `andresscardens`. Si no, detenerse y decirlo.
   - En los comandos, usar `GH_TOKEN=$(gh auth token --user andresscardens)`.
   - Nunca mostrar ni pedir tokens.
2. **Estado local:** `git status -sb`, `git branch -vv`, `git remote -v` y `git fetch --prune`.
   - Si hay cambios sin guardar, conservarlos: listarlos y preguntar antes de cambiar de rama.
   - `web/datos.js` y los datos locales no se suben.
3. **PR:**
   `gh pr list --repo via-viva-usta/via-viva --json number,title,author,reviewDecision,mergeStateStatus,autoMergeRequest`.
   - Para cada uno: checks, aprobación, si está BEHIND y si tiene auto-merge.
4. **Trabajo nuevo:**
   - rama corta `ac/<tarea>` desde `origin/main` (`herramientas\tarea.cmd ac/<tarea>`);
   - commit en español con `Co-Authored-By`;
   - `git push -u origin HEAD`;
   - `gh pr create`.
   - Activar auto-merge solo si AC lo pidió: `gh pr merge <n> --auto --squash`. Espera checks y 1 aprobación de otra
     persona.
5. **Prohibido:** push a `main`, `--force`, reescribir historial, fusionar a mano los PR propios, borrar ramas sin la
   etiqueta `archivo/<rama>`.
   - Con `dismiss_stale_reviews` activo, actualizar una rama BEHIND puede pedir otra aprobación: avisar antes.
6. **Informe:** rama, qué quedó en el PC, qué se subió, el estado de cada PR y lo que falta (quién debe aprobar).
