# Cómo trabajar en VÍA VIVA (ramas y Pull Requests)

Andrés opera Claude Code y revisa; Dany y el resto trabajan en ramas y proponen cambios con Pull Requests (PR).
`main` siempre debe compilar y tener la documentación al día.

## Una vez

1. Aceptar la invitación a la organización **via-viva-usta** en GitHub.
2. Pedirle a Andrés permiso de **escritura (Write)** en el repositorio `via-viva`: con permiso de solo lectura no se pueden
   subir ramas. (Andrés: *Settings → Collaborators and teams → Add people → Write*.)
3. Clonar e instalar lo necesario según el área (ver el README de cada carpeta):

```powershell
gh repo clone via-viva-usta/via-viva
cd via-viva
copy .env.example .env          # y llenar lo que haga falta; .env NUNCA se sube
```

## Flujo de cada cambio

```powershell
git switch main
git pull
git switch -c firmware/prueba-adxl345        # una rama por tarea: <area>/<descripcion-corta>
# ... cambios ...
git add <archivos>
git commit -m "feat(firmware): prueba del ADXL345 por SPI"
git push -u origin firmware/prueba-adxl345
gh pr create --fill --base main               # o desde la página de GitHub
```

- **Prefijos de rama:** `firmware/`, `analisis/`, `etl/`, `riesgo/`, `bot/`, `web/`, `tablero/`, `docs/`.
- **Commits pequeños en español** con prefijo: `feat(etl): ...`, `fix(firmware): ...`, `docs: ...`, `chore: ...`.
- **Un PR por tarea**, enlazando el issue (`Cierra #12`). Andrés revisa y hace *Squash and merge*.
- Antes de pedir revisión: que compile (`pio run` / `ant jar`) o que el script corra, y actualizar el README del módulo.
- Si `main` cambió mientras trabajabas: `git pull origin main` en tu rama y resolver conflictos.

## Reglas (resumen de `CLAUDE.md`, sección 4)

- **Nunca** subir `.env`, tokens, claves (`include/secretos.h` del firmware), datos crudos (`data/raw/`), datos de la Alcaldía
  (`data/alcaldia/`) ni fotos. Ya están en `.gitignore`; si `git status` los muestra, algo anda mal.
- No inventar resultados: todo número del informe sale de código o de una medición, y lo que no se probó en hardware se dice.
- Recorridos: celular fijo, máx. 30 km/h, el copiloto etiqueta (protocolo en `analysis/README.md`).

## Estado y tareas

- Estado general: `docs/ESTADO.md`.
- Tareas: *Issues* de GitHub, con etiqueta de área (`area:A-hardware`, `area:B-senales-ia`, `area:C-datos-plataforma`,
  `area:D-gestion`), responsable y fecha (hito).
