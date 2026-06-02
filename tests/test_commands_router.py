from __future__ import annotations

import logging
from pathlib import Path

import pytest

from bot.commands_router import CommandsRouter
from config import AppConfig


@pytest.fixture()
def router(tmp_path: Path) -> CommandsRouter:
    downloads = tmp_path / "Downloads"
    documents = tmp_path / "Documents"
    desktop = tmp_path / "Desktop"
    workspace = tmp_path / "workspace"
    for path in (downloads, documents, desktop, workspace):
        path.mkdir(parents=True, exist_ok=True)

    cfg = AppConfig(
        project_root=tmp_path,
        telegram_bot_token="dummy",
        telegram_allowed_user_ids=[1],
        interface_language="ru",
        openai_api_key="",
        openai_model_primary="gpt-5-mini",
        openai_model_secondary="gpt-5.4-mini",
        openai_model_fallback="gpt-4.1-mini",
        allowed_dirs=[downloads, documents, desktop, workspace],
        allowed_apps={"notepad": "C:\\Windows\\System32\\notepad.exe"},
        allowed_network_hosts=["google.com"],
        file_size_limit_mb=25,
        max_files_per_operation=100,
        powershell_timeout_sec=5,
        logs_dir=tmp_path / "logs",
        temp_dir=tmp_path / "temp",
        search_db_path=tmp_path / "storage" / "search.db",
        log_level="INFO",
        enable_startup_by_default=False,
        stt_model_size="small",
    )
    logger = logging.getLogger(f"test-router-{tmp_path}")
    logger.handlers.clear()
    logger.addHandler(logging.NullHandler())

    r = CommandsRouter(config=cfg, logger=logger)
    yield r
    r.shutdown()


def test_keyboard_find_file_button_is_local(router: CommandsRouter, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_llm(*args, **kwargs):
        raise AssertionError("LLM should not be called for this keyboard button")

    monkeypatch.setattr(router, "_handle_with_llm", fail_llm)
    result = router.handle_text(chat_id=1, user_id=1, text="📁 Найти файл")
    assert "Найди файл" in result.message


def test_local_context_lists_allowed_app_aliases(router: CommandsRouter) -> None:
    router.config.allowed_apps["браузер по умолчанию"] = "https://www.google.com"

    message = router._build_local_context_message()

    assert message["role"] == "system"
    assert "браузер по умолчанию" in message["content"]
    assert "exact aliases" in message["content"]


def test_dangerous_clean_downloads_requires_confirmation(router: CommandsRouter) -> None:
    result = router.handle_text(chat_id=1, user_id=1, text="Почисти папку Загрузки")
    assert result.confirmation_id is not None
    assert "Подтвердите действие" in result.message


def test_cancel_confirmation(router: CommandsRouter) -> None:
    first = router.handle_text(chat_id=1, user_id=1, text="Почисти папку Загрузки")
    assert first.confirmation_id is not None

    cancelled = router.confirm_action(chat_id=1, user_id=1, action_id=first.confirmation_id, approve=False)
    assert "отменено" in cancelled.message.lower()
def test_find_in_downloads_and_send_uses_fuzzy_local_search(
    router: CommandsRouter,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_llm(*args, **kwargs):
        raise AssertionError("LLM should not be called for local find-and-send intent")

    monkeypatch.setattr(router, "_handle_with_llm", fail_llm)
    target = router.config.allowed_dirs[0] / "Рисунок 5.png"
    target.write_text("x", encoding="utf-8")

    result = router.handle_text(
        chat_id=1,
        user_id=1,
        text="Привет, найди в загрузках рисунок 5PNG и отправь мне его сюда.",
    )

    assert result.attachment_path == str(target)


def test_cancel_last_scheduled_task_button_returns_human_message(router: CommandsRouter) -> None:
    scheduled = router.scheduler_tools.schedule_callable(lambda: None, minutes=60, job_prefix="test")

    result = router.handle_text(chat_id=1, user_id=1, text="❌ Отмена последней запланированной задачи")

    assert not result.message.strip().startswith("{")
    assert scheduled["job_id"] in result.message


def test_schedule_shutdown_returns_human_message(router: CommandsRouter) -> None:
    result = router._route_result_from_tool(
        "schedule_shutdown",
        {
            "status": "ok",
            "action": "schedule_shutdown",
            "result": {
                "status": "ok",
                "job_id": "shutdown_1780417518",
                "run_at": "2026-06-02T21:25:18.134282",
            },
        },
    )

    assert "ID:" not in result.message
    assert "T21:25" not in result.message
    assert "21:25" in result.message


def test_cancel_shutdown_returns_human_message(router: CommandsRouter) -> None:
    result = router._route_result_from_tool(
        "cancel_shutdown",
        {
            "status": "ok",
            "action": "cancel_shutdown",
            "result": {"status": "ok", "cancelled": 1},
        },
    )

    assert "cancelled" not in result.message
    assert "Отменил" in result.message


def test_blocked_system_path_returns_plain_refusal(router: CommandsRouter) -> None:
    result = router._route_result_from_tool(
        "delete_file",
        {"status": "blocked", "reason": "System path operations are blocked."},
    )

    assert result.message == "Нельзя удалять или изменять системные файлы и папки Windows."


def test_find_site_dump_searches_names_and_folders_locally(
    router: CommandsRouter,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_llm(*args, **kwargs):
        raise AssertionError("LLM should not be called for local find intent")

    monkeypatch.setattr(router, "_handle_with_llm", fail_llm)
    target = router.config.allowed_dirs[3] / "download_steelpro_1766317200_53084"
    target.mkdir(parents=True)

    result = router.handle_text(chat_id=1, user_id=1, text="Найди пожалуйста дамп сайта steelpro")

    assert str(target) in result.message
