from __future__ import annotations

import logging
import sys

from bot.telegram_handler import TelegramBotService
from config import load_config
from logging_setup import configure_logging


def main() -> int:
    config = load_config()
    logger = configure_logging(config)

    if not config.telegram_bot_token:
        logger.error("TELEGRAM_BOT_TOKEN is not configured. Set it in .env.")
        return 1

    if not config.openai_api_key:
        logger.warning("OPENAI_API_KEY is empty. LLM features will be limited.")

    logger.info("Starting Telegram PC assistant...")
    service = TelegramBotService(config=config, logger=logging.getLogger("bot"))
    service.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
