"""Bot ciudadano de VÍA VIVA en Telegram.

Flujo de /reportar: tipo (botones) → foto → ubicación (botón "Enviar ubicación") → nota opcional → número de reporte.
/estado <número> consulta el estado (nuevo, confirmado, en reparación, reparado). /mis_reportes lista los propios.

Uso (desde via-viva/, con TELEGRAM_BOT_TOKEN y BOT_SAL_HASH en .env):
  bot\\.venv\\Scripts\\python bot\\bot.py
"""
from __future__ import annotations

import logging
import warnings
import os
import sys
import uuid
from pathlib import Path

from telegram import (InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup,
                      ReplyKeyboardRemove, Update)
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler, ContextTypes, ConversationHandler,
                          MessageHandler, filters)

sys.path.insert(0, str(Path(__file__).resolve().parent))
import reportes  # noqa: E402

# Aviso inofensivo de python-telegram-bot sobre per_message (los botones solo se usan en el primer paso)
warnings.filterwarnings("ignore", message=".*per_message.*")
logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)   # no escribir el token en los registros (va en la URL)
log = logging.getLogger("bot")

TIPO, FOTO, UBICACION, NOTA = range(4)

BIENVENIDA = (
    "Hola. Soy el bot de *VÍA VIVA*: reporta huecos, resaltos y obstáculos en las vías de Tunja.\n\n"
    "/reportar — nuevo reporte (foto + ubicación)\n"
    "/estado <número> — estado de un reporte tuyo\n"
    "/mis_reportes — tus últimos reportes\n\n"
    "Privacidad: no guardamos tu nombre ni tu número de Telegram (solo un código anónimo). "
    "Evita que en la foto salgan rostros o placas. VÍA VIVA no genera multas."
)


async def inicio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(BIENVENIDA, parse_mode="Markdown")


async def reportar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    botones = [[InlineKeyboardButton(nombre, callback_data=clave)] for clave, nombre in reportes.TIPOS.items()]
    await update.message.reply_text("¿Qué quieres reportar?", reply_markup=InlineKeyboardMarkup(botones))
    return TIPO


async def elegir_tipo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    consulta = update.callback_query
    await consulta.answer()
    context.user_data["tipo"] = consulta.data
    await consulta.edit_message_text(f"Tipo: {reportes.TIPOS[consulta.data]}.\n\nAhora envía una *foto* "
                                     "(sin rostros ni placas). Si no puedes, escribe /omitir.", parse_mode="Markdown")
    return FOTO


async def recibir_foto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    foto = update.message.photo[-1]                     # la de mayor resolución
    reportes.CARPETA_FOTOS.mkdir(parents=True, exist_ok=True)
    ruta = reportes.CARPETA_FOTOS / f"{uuid.uuid4().hex}.jpg"   # nombre al azar: no revela al usuario
    archivo = await foto.get_file()
    await archivo.download_to_drive(ruta)
    context.user_data["foto"] = str(ruta.relative_to(reportes.RAIZ))
    return await pedir_ubicacion(update)


async def omitir_foto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["foto"] = None
    return await pedir_ubicacion(update)


async def pedir_ubicacion(update: Update):
    teclado = ReplyKeyboardMarkup([[KeyboardButton("📍 Enviar ubicación", request_location=True)]],
                                  resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text("Comparte la *ubicación* del lugar (botón de abajo). Hazlo estando ahí.",
                                    parse_mode="Markdown", reply_markup=teclado)
    return UBICACION


async def recibir_ubicacion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    loc = update.message.location
    if not reportes.ubicacion_valida(loc.latitude, loc.longitude):
        await update.message.reply_text("Esa ubicación está fuera de Tunja. Envía la ubicación del lugar del reporte.")
        return UBICACION
    context.user_data["lat"], context.user_data["lon"] = loc.latitude, loc.longitude
    await update.message.reply_text("¿Algún detalle? (por ejemplo: \"ocupa medio carril\"). Si no, escribe /omitir.",
                                    reply_markup=ReplyKeyboardRemove())
    return NOTA


async def recibir_nota(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await terminar(update, context, update.message.text[:500])


async def omitir_nota(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await terminar(update, context, None)


async def terminar(update: Update, context: ContextTypes.DEFAULT_TYPE, nota):
    d = context.user_data
    try:
        numero = reportes.guardar_reporte(reportes.hash_usuario(update.effective_user.id), d["tipo"], d["lat"],
                                          d["lon"], d.get("foto"), nota)
    except Exception:
        log.exception("No se pudo guardar el reporte")
        await update.message.reply_text("No pude guardar el reporte. Intenta de nuevo más tarde.")
        return ConversationHandler.END
    log.info("Reporte %s guardado (%s)", numero, d["tipo"])
    await update.message.reply_text(f"✅ Reporte *#{numero}* registrado. Estado: *nuevo*.\n"
                                    f"Consúltalo con /estado {numero}", parse_mode="Markdown")
    d.clear()
    return ConversationHandler.END


async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Reporte cancelado.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


async def estado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or not context.args[0].lstrip("#").isdigit():
        await update.message.reply_text("Uso: /estado <número de reporte>, por ejemplo /estado 12")
        return
    r = reportes.consultar(int(context.args[0].lstrip("#")), reportes.hash_usuario(update.effective_user.id))
    if r is None:
        await update.message.reply_text("No encontré ese reporte entre los tuyos.")
        return
    await update.message.reply_text(f"Reporte #{r['id']} ({reportes.TIPOS[r['tipo']]}): "
                                    f"*{reportes.NOMBRE_ESTADO[r['estado']]}*.", parse_mode="Markdown")


async def mis_reportes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lista = reportes.mis_reportes(reportes.hash_usuario(update.effective_user.id))
    if not lista:
        await update.message.reply_text("Aún no tienes reportes. Usa /reportar.")
        return
    texto = "\n".join(f"#{r['id']} · {reportes.TIPOS[r['tipo']]} · {reportes.NOMBRE_ESTADO[r['estado']]}"
                      for r in lista)
    await update.message.reply_text("Tus reportes:\n" + texto)


def construir(token: str) -> Application:
    app = Application.builder().token(token).build()
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("reportar", reportar)],
        states={
            TIPO: [CallbackQueryHandler(elegir_tipo, pattern="^(" + "|".join(reportes.TIPOS) + ")$")],
            FOTO: [MessageHandler(filters.PHOTO, recibir_foto), CommandHandler("omitir", omitir_foto)],
            UBICACION: [MessageHandler(filters.LOCATION, recibir_ubicacion)],
            NOTA: [CommandHandler("omitir", omitir_nota), MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_nota)],
        },
        fallbacks=[CommandHandler("cancelar", cancelar)],
    ))
    app.add_handler(CommandHandler(["start", "ayuda"], inicio))
    app.add_handler(CommandHandler("estado", estado))
    app.add_handler(CommandHandler("mis_reportes", mis_reportes))
    return app


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit("Falta TELEGRAM_BOT_TOKEN en .env (ver bot/README.md)")
    reportes.hash_usuario(0)   # falla temprano si falta BOT_SAL_HASH
    log.info("Bot VÍA VIVA iniciado. Ctrl+C para detener.")
    construir(token).run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
