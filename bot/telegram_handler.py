from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from bot.commands_router import CommandsRouter, RouteResult
from bot.keyboards import build_confirmation_keyboard, build_main_keyboard
from config import AppConfig
from speech.audio_utils import build_temp_audio_path, convert_to_wav, safe_remove
from speech.speech_to_text import SpeechToText


class TelegramBotService:
    def __init__(self, config: AppConfig, logger: logging.Logger) -> None:
        self.config = config
        self.logger = logger
        self.router = CommandsRouter(config=config, logger=logger.getChild("router"))
        self.speech = SpeechToText(model_size=config.stt_model_size)
        self._warned_open_access = False

        self.application = Application.builder().token(config.telegram_bot_token).build()
        self._register_handlers()

    def run(self) -> None:
        self.logger.info("Bot is polling updates...")
        self.application.run_polling(drop_pending_updates=True)

    def _register_handlers(self) -> None:
        self.application.add_handler(CommandHandler("start", self.handle_start))
        self.application.add_handler(CommandHandler("help", self.handle_help))
        self.application.add_handler(CallbackQueryHandler(self.handle_confirmation, pattern=r"^(confirm|cancel):"))
        self.application.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, self.handle_voice))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))

    async def handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorize(update):
            return
        message = (
            "Бот запущен.\n"
            "Доступны голосовые и текстовые команды.\n"
            "Опасные операции выполняются только после подтверждения."
        )
        await update.effective_message.reply_text(message, reply_markup=build_main_keyboard())

    async def handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorize(update):
            return
        await update.effective_message.reply_text(
            "Примеры:\n"
            "- Найди файл Курсы.docx\n"
            "- Выключи компьютер через 30 минут\n"
            "- Через 10 минут запусти notepad\n"
            "- Пингани google.com\n"
            "- Создай markdown файл report.md с текстом ...",
            reply_markup=build_main_keyboard(),
        )

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorize(update):
            return
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        text = update.effective_message.text or ""

        result = await asyncio.to_thread(self.router.handle_text, chat_id, user_id, text)
        await self._send_route_result(update, result)

    async def handle_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorize(update):
            return

        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        message = update.effective_message
        file_id = None
        suffix = ".ogg"

        if message.voice:
            file_id = message.voice.file_id
            suffix = ".ogg"
        elif message.audio:
            file_id = message.audio.file_id
            suffix = ".mp3"

        if not file_id:
            await message.reply_text("Не удалось получить голосовой файл.")
            return

        source_path = build_temp_audio_path(self.config.temp_dir, suffix=suffix)
        wav_path = build_temp_audio_path(self.config.temp_dir, suffix=".wav")
        try:
            tg_file = await context.bot.get_file(file_id)
            await tg_file.download_to_drive(custom_path=str(source_path))
            if source_path.suffix.lower() != ".wav":
                await asyncio.to_thread(convert_to_wav, source_path, wav_path)
                audio_for_stt = wav_path
            else:
                audio_for_stt = source_path

            transcription = await asyncio.to_thread(self.speech.transcribe, audio_for_stt, self.config.interface_language)
            if not transcription.text:
                await message.reply_text("Речь не распознана. Попробуйте еще раз.")
                return

            confidence_pct = round(transcription.confidence * 100, 1)
            await message.reply_text(
                f"Распознано: \"{transcription.text}\"\nУверенность: {confidence_pct}%"
            )

            if transcription.low_confidence:
                await message.reply_text(
                    "Низкая уверенность распознавания. Повторите голосовое или отправьте команду текстом."
                )
                return

            result = await asyncio.to_thread(self.router.handle_text, chat_id, user_id, transcription.text)
            await self._send_route_result(update, result)
        except Exception as exc:  # noqa: BLE001
            self.logger.exception("Voice command processing failed.")
            await message.reply_text(f"Ошибка обработки голосового сообщения: {exc}")
        finally:
            safe_remove(source_path)
            safe_remove(wav_path)

    async def handle_confirmation(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorize(update):
            return
        query = update.callback_query
        await query.answer()
        if not query.data:
            return

        decision, action_id = query.data.split(":", 1)
        approve = decision == "confirm"
        chat_id = query.message.chat_id
        user_id = query.from_user.id

        result = await asyncio.to_thread(self.router.confirm_action, chat_id, user_id, action_id, approve)
        await query.edit_message_text(result.message)

        if result.attachment_path:
            path = Path(result.attachment_path)
            if path.exists():
                is_image = path.suffix.lower() in [".png", ".jpg", ".jpeg"]
                with path.open("rb") as f:
                    if is_image:
                        await context.bot.send_photo(chat_id=chat_id, photo=f, caption="Результат действия")
                    else:
                        await context.bot.send_document(chat_id=chat_id, document=f, caption="Результат действия")

    async def _send_route_result(self, update: Update, result: RouteResult) -> None:
        message = update.effective_message
        chat_id = update.effective_chat.id
        if result.confirmation_id:
            await message.reply_text(
                result.message,
                reply_markup=build_confirmation_keyboard(result.confirmation_id),
            )
            return

        if result.attachment_path:
            path = Path(result.attachment_path)
            if path.exists():
                is_image = path.suffix.lower() in [".png", ".jpg", ".jpeg"]
                with path.open("rb") as f:
                    if is_image:
                        await update.get_bot().send_photo(chat_id=chat_id, photo=f, caption=result.message)
                    else:
                        await update.get_bot().send_document(chat_id=chat_id, document=f, caption=result.message)
                return

        await message.reply_text(result.message)

    async def _authorize(self, update: Update) -> bool:
        user = update.effective_user
        if user is None:
            return False
        if not self.config.telegram_allowed_user_ids:
            if not self._warned_open_access:
                self.logger.warning("TELEGRAM_ALLOWED_USER_IDS is empty. Access is currently open to all users.")
                self._warned_open_access = True
            return True
        if user.id in self.config.telegram_allowed_user_ids:
            return True

        log_fn = getattr(self.logger, "security", None)
        if callable(log_fn):
            log_fn("Unauthorized telegram user blocked: id=%s", user.id)
        else:
            self.logger.warning("SECURITY | Unauthorized telegram user blocked: id=%s", user.id)
        await update.effective_message.reply_text("Доступ запрещен: ваш Telegram ID не в белом списке.")
        return False
