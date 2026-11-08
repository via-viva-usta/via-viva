# bot/ — Bot ciudadano de Telegram

El ciudadano reporta huecos, resaltos y obstáculos con **foto + ubicación + tipo**. Cada reporte queda en la tabla
`reportes` con estado `nuevo`, y el bot responde con el **número de reporte**. Para la demo corre en el portátil
(sin servidor): mientras `bot.py` esté corriendo, el bot responde.

## Comandos

| Comando | Qué hace |
|---|---|
| `/start`, `/ayuda` | Bienvenida, comandos y aviso de privacidad |
| `/reportar` | Tipo (botones: Hueco, Resalto, Obstáculo, Otro) → foto (o `/omitir`) → ubicación (botón "Enviar ubicación") → detalle opcional → **"Reporte #N registrado"** |
| `/estado N` | Estado del reporte N: nuevo, confirmado, en reparación, reparado (o descartado). Solo los reportes propios |
| `/mis_reportes` | Últimos 10 reportes del usuario |
| `/cancelar` | Cancela un reporte a medias |

El operador (en la demo, el equipo) cambia el estado con:

```powershell
bot\.venv\Scripts\python bot\cambiar_estado.py --listar
bot\.venv\Scripts\python bot\cambiar_estado.py 12 confirmado
```

## Privacidad

- Del usuario solo se guarda `hash_usuario` = SHA-256 de (sal + id de Telegram). La sal (`BOT_SAL_HASH`) está en `.env`;
  sin ella no se puede volver al id. Por eso el bot **no puede avisar** al ciudadano cuando cambia el estado: él lo consulta.
- Las fotos se guardan en `data/fotos_bot/` con un nombre al azar. Esa carpeta está en `.gitignore` y las fotos **no**
  se publican en el mapa web. El bot pide que no salgan rostros ni placas. Pendiente: difuminado automático antes de
  usarlas como evidencia.
- Se rechazan ubicaciones a más de 25 km del centro de Tunja.

## Poner a andar (una vez)

1. En Telegram, hablar con **@BotFather** → `/newbot` → nombre (p. ej. "VÍA VIVA Tunja") → usuario (termina en `bot`).
   Copiar el token que entrega.
2. Pegar el token en `.env` (raíz de `via-viva/`), en `TELEGRAM_BOT_TOKEN=`. **No** compartirlo por chat ni subirlo
   al repositorio (`.env` está en `.gitignore`). `BOT_SAL_HASH` ya quedó generada al crear `.env`; no cambiarla.
3. Entorno e inicio, desde `via-viva/`:

```powershell
py -3.11 -m venv bot\.venv
bot\.venv\Scripts\python -m pip install -r bot\requirements.txt
bot\.venv\Scripts\python bot\bot.py
```

Si el token se filtra: @BotFather → `/revoke` y pegar el nuevo en `.env`.

## Archivos

| Archivo | Qué hace |
|---|---|
| `bot.py` | Manejadores de Telegram (`python-telegram-bot` 22) y conversación de `/reportar` |
| `reportes.py` | Lógica sin Telegram: hash del usuario, validar ubicación, guardar, consultar, cambiar estado |
| `cambiar_estado.py` | Herramienta del operador para cambiar el estado de un reporte |

La base se abre por `db/acceso.py`. El tramo de cada reporte lo asigna después el ETL (`risk_model.variables`);
el bot guarda lat/lon y el geohash.

## Estado (2-nov-2026)

- **Probado sin Telegram** (base temporal): guarda reportes, el hash no contiene el id, un usuario no ve los reportes de
  otro, los estados cambian y se rechaza una ubicación de Bogotá. La aplicación se construye con un token falso.
- **No probado con Telegram real**: falta el token en `.env`. Cuando esté, probar `/reportar` de punta a punta con un
  celular (foto, ubicación, número de reporte, `/estado`).
