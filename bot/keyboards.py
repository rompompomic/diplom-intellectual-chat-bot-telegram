from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup


MAIN_BUTTONS = [
    ["🔉 Убавить звук", "🔊 Прибавить звук", "🔇 Выключить звук", "🔈 Включить звук"],
    ["⏯ Пауза / Пуск", "⏭ Следующий трек", "⏮ Предыдущий трек"],
    ["📸 Скриншот", "🧹 Очистить загрузки"],
    ["🌐 Проверить интернет", "💻 IP адрес", "📁 Найти файл"],
    ["❌ Отмена последней запланированной задачи"],
]


def build_main_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [[KeyboardButton(text=item) for item in row] for row in MAIN_BUTTONS]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def build_confirmation_keyboard(action_id: str) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="Подтвердить", callback_data=f"confirm:{action_id}"),
            InlineKeyboardButton(text="Отмена", callback_data=f"cancel:{action_id}"),
        ]
    ]
    return InlineKeyboardMarkup(buttons)
