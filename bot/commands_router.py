from __future__ import annotations

import json
import logging
import re
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from docx import Document

from config import AppConfig
from llm.context_manager import ContextManager
from llm.openai_client import OpenAIOrchestrator
from llm.prompts import SYSTEM_PROMPT_RU
from llm.tool_schema import get_tool_schemas
from search.indexer import SearchIndexer
from search.search_engine import SearchEngine
from security.policy import CommandPolicy
from security.validators import normalize_filename, normalize_path
from storage.db import StorageDB
from storage.history import ConversationHistory
from tools.doc_tools import DocTools
from tools.file_tools import FileTools
from tools.media_tools import MediaTools
from tools.network_tools import NetworkTools
from tools.scheduler_tools import SchedulerTools
from tools.screenshot_tools import ScreenshotTools
from tools.shell_tools import ShellTools
from tools.startup_tools import StartupTools


@dataclass(slots=True)
class PendingAction:
    action_id: str
    chat_id: int
    user_id: int
    action: str
    args: dict[str, Any]
    summary: str
    created_at: datetime


@dataclass(slots=True)
class RouteResult:
    message: str
    confirmation_id: str | None = None
    confirmation_text: str | None = None
    attachment_path: str | None = None


class CommandsRouter:
    def __init__(self, config: AppConfig, logger: logging.Logger) -> None:
        self.config = config
        self.logger = logger

        for path in self.config.allowed_dirs:
            path.mkdir(parents=True, exist_ok=True)
        self.config.temp_dir.mkdir(parents=True, exist_ok=True)
        self.config.logs_dir.mkdir(parents=True, exist_ok=True)

        storage_db_path = (self.config.project_root / "storage" / "bot_data.db").resolve()
        self.storage_db = StorageDB(storage_db_path)
        self.history = ConversationHistory(max_messages=12, db=self.storage_db)
        self.context_manager = ContextManager(history=self.history)

        self.policy = CommandPolicy(
            allowed_dirs=self.config.allowed_dirs,
            allowed_apps=self.config.allowed_apps,
            allowed_network_hosts=self.config.allowed_network_hosts,
        )

        self.file_tools = FileTools(
            allowed_dirs=self.config.allowed_dirs,
            max_files_per_operation=self.config.max_files_per_operation,
        )
        self.doc_tools = DocTools(allowed_dirs=self.config.allowed_dirs)
        self.network_tools = NetworkTools(timeout_sec=self.config.powershell_timeout_sec)
        self.media_tools = MediaTools()
        self.screenshot_tools = ScreenshotTools(
            allowed_dirs=self.config.allowed_dirs,
            default_dir=self.config.allowed_dirs[0],
        )
        self.shell_tools = ShellTools(timeout_sec=self.config.powershell_timeout_sec)
        self.scheduler_tools = SchedulerTools(timezone="Asia/Yekaterinburg")
        self.startup_tools = StartupTools(project_root=self.config.project_root)

        self.indexer = SearchIndexer(db_path=self.config.search_db_path, allowed_dirs=self.config.allowed_dirs)
        self.search_engine = SearchEngine(indexer=self.indexer)

        self.llm = OpenAIOrchestrator(
            api_key=self.config.openai_api_key,
            primary_model=self.config.openai_model_primary,
            secondary_model=self.config.openai_model_secondary,
            fallback_model=self.config.openai_model_fallback,
            system_prompt=SYSTEM_PROMPT_RU,
        )
        self.tool_schemas = get_tool_schemas()

        self.pending_actions: dict[str, PendingAction] = {}
        self.user_requests: dict[int, deque[datetime]] = defaultdict(lambda: deque(maxlen=40))
        self.generated_scripts_log = self.config.logs_dir / "generated_scripts.log"

    def shutdown(self) -> None:
        self.scheduler_tools.shutdown()

    def handle_text(self, chat_id: int, user_id: int, text: str) -> RouteResult:
        text = (text or "").strip()
        if not text:
            return RouteResult(message="Пустая команда.")

        if not self._check_rate_limit(user_id):
            self._log_security("Rate limit exceeded for user_id=%s", user_id)
            return RouteResult(message="Слишком много команд подряд. Подождите минуту.")

        self._cleanup_expired_pending_actions()

        local_result = self._handle_quick_button(chat_id, user_id, text)
        if local_result is not None:
            return local_result

        parsed_result = self._try_parse_local_text(chat_id, user_id, text)
        if parsed_result is not None:
            return parsed_result

        return self._handle_with_llm(chat_id, user_id, text)

    def confirm_action(self, chat_id: int, user_id: int, action_id: str, approve: bool) -> RouteResult:
        pending = self.pending_actions.get(action_id)
        if pending is None:
            return RouteResult(message="Запрос подтверждения не найден или уже истек.")
        if pending.chat_id != chat_id or pending.user_id != user_id:
            return RouteResult(message="Нельзя подтверждать чужие действия.")

        self.pending_actions.pop(action_id, None)
        if not approve:
            self.logger.info("Action cancelled by user: %s", action_id)
            self.storage_db.add_tool_call(
                chat_id=chat_id,
                user_id=user_id,
                tool_name=pending.action,
                args_json=json.dumps(pending.args, ensure_ascii=False),
                status="cancelled",
                result_json="{}",
            )
            return RouteResult(message="Действие отменено.")

        result = self._execute_action(
            chat_id=chat_id,
            user_id=user_id,
            action=pending.action,
            args=pending.args,
            confirmed=True,
        )
        return self._route_result_from_tool(pending.action, result)

    def _handle_with_llm(self, chat_id: int, user_id: int, text: str) -> RouteResult:
        context = self.context_manager.get_context(chat_id)
        self.context_manager.add_user_message(chat_id=chat_id, user_id=user_id, content=text)
        confirmation_ids: list[str] = []
        attachments: list[str] = []

        def execute_tool(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
            result = self._execute_action(
                chat_id=chat_id,
                user_id=user_id,
                action=tool_name,
                args=args,
                confirmed=False,
            )
            if result.get("status") == "confirmation_required":
                confirmation_ids.append(str(result["action_id"]))
            
            payload = result.get("result", result)
            if tool_name in ("take_screenshot", "send_file_to_chat"):
                path = payload.get("path")
                if path:
                    attachments.append(str(path))

            return result

        response = self.llm.respond(
            chat_context=context,
            user_text=text,
            tools=self.tool_schemas,
            tool_executor=execute_tool,
        )
        if confirmation_ids:
            pending = self.pending_actions[confirmation_ids[-1]]
            return RouteResult(
                message=f"Подтвердите действие: {pending.summary}",
                confirmation_id=pending.action_id,
                confirmation_text=pending.summary,
            )

        assistant_text = response.text or "Готово."
        self.context_manager.add_assistant_message(chat_id=chat_id, user_id=user_id, content=assistant_text)
        if response.errors:
            self.logger.warning("OpenAI fallback errors: %s", "; ".join(response.errors))
        
        attachment_path = attachments[-1] if attachments else None
        return RouteResult(message=assistant_text, attachment_path=attachment_path)

    def _handle_quick_button(self, chat_id: int, user_id: int, text: str) -> RouteResult | None:
        mapping: dict[str, tuple[str, dict[str, Any]]] = {
            "🔉 Убавить звук": ("volume_down", {"step": 5}),
            "🔊 Прибавить звук": ("volume_up", {"step": 5}),
            "🔇 Выключить звук": ("mute_audio", {}),
            "🔈 Включить звук": ("unmute_audio", {}),
            "⏯ Пауза / Пуск": ("media_play_pause", {}),
            "⏭ Следующий трек": ("media_next", {}),
            "⏮ Предыдущий трек": ("media_previous", {}),
            "📸 Скриншот": ("take_screenshot", {}),
            "🧹 Очистить загрузки": ("clean_downloads", {}),
            "🌐 Проверить интернет": ("check_internet", {}),
            "❌ Отмена последней запланированной задачи": ("cancel_scheduled_task", {"job_id": "__last__"}),
        }

        if text == "💻 IP адрес":
            local = self._execute_action(chat_id, user_id, "get_local_ip", {}, confirmed=True)
            public = self._execute_action(chat_id, user_id, "get_public_ip", {}, confirmed=True)
            local_payload = local.get("result", local)
            public_payload = public.get("result", public)
            return RouteResult(
                message=(
                    f"Локальный IP: {local_payload.get('local_ipv4', local_payload)}\n"
                    f"Внешний IP: {public_payload.get('ip', public_payload)}"
                )
            )

        if text == "📁 Найти файл":
            return RouteResult(message="Напишите команду в формате: Найди файл <имя файла>")

        if text not in mapping:
            return None

        action, args = mapping[text]
        if action == "cancel_scheduled_task" and args.get("job_id") == "__last__":
            result = self.scheduler_tools.cancel_last_task()
            return RouteResult(message=self._format_result(action, result))

        result = self._execute_action(chat_id=chat_id, user_id=user_id, action=action, args=args, confirmed=False)
        return self._route_result_from_tool(action, result)

    def _try_parse_local_text(self, chat_id: int, user_id: int, text: str) -> RouteResult | None:
        lowered = text.lower()

        find_and_send_result = self._try_handle_find_and_send_file(chat_id, user_id, text)
        if find_and_send_result is not None:
            return find_and_send_result

        find_match = re.match(r"^\s*найди\s+файл\s+(.+)$", lowered, re.IGNORECASE)
        if find_match:
            query = text.split(maxsplit=2)[-1]
            result = self._execute_action(chat_id, user_id, "find_file_by_name", {"name": query}, confirmed=True)
            return self._route_result_from_tool("find_file_by_name", result)

        shutdown_match = re.search(r"выключи.+через\s+(\d+)\s+мин", lowered, re.IGNORECASE)
        if shutdown_match:
            minutes = int(shutdown_match.group(1))
            result = self._execute_action(
                chat_id,
                user_id,
                "schedule_shutdown",
                {"minutes": minutes},
                confirmed=False,
            )
            return self._route_result_from_tool("schedule_shutdown", result)

        open_app_match = re.search(r"через\s+(\d+)\s+мин.*(?:запусти|открой)\s+(.+)$", lowered, re.IGNORECASE)
        if open_app_match:
            minutes = int(open_app_match.group(1))
            app_name = open_app_match.group(2).strip()
            result = self._execute_action(
                chat_id,
                user_id,
                "schedule_open_app",
                {"app": app_name, "minutes": minutes},
                confirmed=True,
            )
            return self._route_result_from_tool("schedule_open_app", result)

        if "почисти" in lowered and "загруз" in lowered:
            result = self._execute_action(chat_id, user_id, "clean_downloads", {}, confirmed=False)
            return self._route_result_from_tool("clean_downloads", result)

        if "какой у меня ip" in lowered or "мой ip" in lowered:
            local = self._execute_action(chat_id, user_id, "get_local_ip", {}, confirmed=True)
            public = self._execute_action(chat_id, user_id, "get_public_ip", {}, confirmed=True)
            local_payload = local.get("result", local)
            public_payload = public.get("result", public)
            return RouteResult(
                message=(
                    f"Локальный IP: {local_payload.get('local_ipv4', local_payload)}\n"
                    f"Внешний IP: {public_payload.get('ip', public_payload)}"
                )
            )

        if "есть ли интернет" in lowered or "проверь интернет" in lowered:
            result = self._execute_action(chat_id, user_id, "check_internet", {}, confirmed=True)
            return self._route_result_from_tool("check_internet", result)

        ping_match = re.search(r"(?:пингани|ping)\s+([a-zA-Z0-9\.-]+)$", lowered, re.IGNORECASE)
        if ping_match:
            host = ping_match.group(1)
            result = self._execute_action(chat_id, user_id, "ping_host", {"host": host}, confirmed=True)
            return self._route_result_from_tool("ping_host", result)

        if "включи автозапуск" in lowered:
            result = self._execute_action(chat_id, user_id, "enable_startup", {}, confirmed=False)
            return self._route_result_from_tool("enable_startup", result)

        if "выключи автозапуск" in lowered:
            result = self._execute_action(chat_id, user_id, "disable_startup", {}, confirmed=False)
            return self._route_result_from_tool("disable_startup", result)

        if "статус автозапуска" in lowered:
            status = self.startup_tools.startup_status()
            return RouteResult(message=f"Автозапуск: {'включен' if status['enabled'] else 'выключен'}")

        if "пересобери индекс" in lowered or "rebuild index" in lowered:
            result = self._execute_action(chat_id, user_id, "rebuild_index", {}, confirmed=True)
            return self._route_result_from_tool("rebuild_index", result)

        if "список задач" in lowered:
            result = self._execute_action(chat_id, user_id, "list_scheduled_tasks", {}, confirmed=True)
            return self._route_result_from_tool("list_scheduled_tasks", result)

        return None

    def _try_handle_find_and_send_file(self, chat_id: int, user_id: int, text: str) -> RouteResult | None:
        lowered = text.lower()
        wants_find = "найди" in lowered or "найти" in lowered or "отыщи" in lowered
        wants_send = any(word in lowered for word in ("отправ", "пришли", "скинь", "перешли"))
        if not wants_find or not wants_send:
            return None

        query = self._extract_file_search_query(text)
        if not query:
            return None

        scope_dirs = None
        if "загруз" in lowered:
            downloads = self._find_allowed_dir_by_name("downloads")
            if downloads is not None:
                scope_dirs = [str(downloads)]

        find_result = self._execute_action(
            chat_id,
            user_id,
            "find_file_by_name",
            {"name": query, "scope_dirs": scope_dirs},
            confirmed=True,
        )
        if find_result.get("status") != "ok":
            return self._route_result_from_tool("find_file_by_name", find_result)

        payload = find_result.get("result", {})
        files = payload.get("files", [])
        if not files:
            location = "в загрузках" if scope_dirs else "в разрешённых папках"
            return RouteResult(message=f"Не нашёл подходящий файл {location}: {query}")

        path = str(files[0])
        suffix = ""
        if len(files) > 1:
            suffix = f"\nНашёл ещё вариантов: {len(files) - 1}. Отправляю самый похожий."
        return RouteResult(message=f"Нашёл файл: {path}{suffix}", attachment_path=path)

    def _extract_file_search_query(self, text: str) -> str:
        query = re.sub(r"^\s*(привет|здравствуй|добрый день)[,!\s]*", "", text, flags=re.IGNORECASE)
        query = re.sub(r"\b(найди|найти|отыщи)\b", " ", query, count=1, flags=re.IGNORECASE)
        query = re.sub(r"\b(в|из)\s+(папке\s+)?(загрузках|загрузки|downloads)\b", " ", query, flags=re.IGNORECASE)
        query = re.sub(r"\b(и\s+)?(отправь|отправить|пришли|скинь|перешли)\b.*$", " ", query, flags=re.IGNORECASE)
        query = re.sub(r"\b(мне|его|её|ее|сюда|файл|картинку|изображение)\b", " ", query, flags=re.IGNORECASE)
        return " ".join(query.strip(" .,!?:;\"'").split())

    def _find_allowed_dir_by_name(self, name: str) -> Path | None:
        needle = name.lower()
        for path in self.config.allowed_dirs:
            if path.name.lower() == needle:
                return path
        return None

    def _execute_action(
        self,
        chat_id: int,
        user_id: int,
        action: str,
        args: dict[str, Any],
        confirmed: bool,
    ) -> dict[str, Any]:
        decision = self.policy.evaluate(action=action, args=args, confirmed=confirmed)
        if not decision.allowed:
            self._log_security("Blocked action=%s user_id=%s reason=%s", action, user_id, decision.reason)
            result = {"status": "blocked", "reason": decision.reason}
            self._log_tool_call(chat_id, user_id, action, args, "blocked", result)
            return result

        normalized_args = decision.normalized_args or args
        if decision.requires_confirmation:
            action_id = self._register_pending_action(chat_id, user_id, action, normalized_args)
            result = {
                "status": "confirmation_required",
                "action_id": action_id,
                "summary": self.pending_actions[action_id].summary,
            }
            self._log_tool_call(chat_id, user_id, action, args, "confirmation_required", result)
            return result

        try:
            result = self._dispatch_action(action, normalized_args)
            self._log_tool_call(chat_id, user_id, action, normalized_args, "ok", result)
            return {"status": "ok", "action": action, "result": result}
        except Exception as exc:  # noqa: BLE001
            self.logger.exception("Tool execution failed: %s", action)
            result = {"status": "error", "action": action, "error": str(exc)}
            self._log_tool_call(chat_id, user_id, action, normalized_args, "error", result)
            return result

    def _dispatch_action(self, action: str, args: dict[str, Any]) -> dict[str, Any]:
        if action == "volume_up":
            return self.media_tools.volume_up(step=int(args.get("step", 5)))
        if action == "volume_down":
            return self.media_tools.volume_down(step=int(args.get("step", 5)))
        if action == "mute_audio":
            return self.media_tools.mute_audio()
        if action == "unmute_audio":
            return self.media_tools.unmute_audio()
        if action == "toggle_mute":
            return self.media_tools.toggle_mute()
        if action == "media_play_pause":
            return self.media_tools.media_play_pause()
        if action == "media_next":
            return self.media_tools.media_next()
        if action == "media_previous":
            return self.media_tools.media_previous()
        if action == "take_screenshot":
            return self.screenshot_tools.take_screenshot(save_path=args.get("save_path"))
        if action == "send_file_to_chat":
            path_info = self.file_tools.path_exists(str(args["path"]))
            if not path_info["exists"]:
                raise FileNotFoundError(f"File not found: {path_info['path']}")
            return {"status": "ok", "action": "send_file_to_chat", "path": path_info["path"]}
        if action == "find_file_by_name":
            return self.file_tools.find_file_by_name(name=str(args["name"]), scope_dirs=args.get("scope_dirs"))
        if action == "rename_file":
            return self.file_tools.rename_file(path=str(args["path"]), new_name=str(args["new_name"]))
        if action == "move_file":
            return self.file_tools.move_file(src=str(args["src"]), dst=str(args["dst"]))
        if action == "copy_file":
            return self.file_tools.copy_file(src=str(args["src"]), dst=str(args["dst"]))
        if action == "delete_file":
            return self.file_tools.delete_file(path=str(args["path"]), safe_mode=bool(args.get("safe_mode", True)))
        if action == "create_folder":
            return self.file_tools.create_folder(path=str(args["path"]))
        if action == "extract_archive":
            return self.file_tools.extract_archive(path=str(args["path"]), dst=str(args["dst"]))
        if action == "create_archive":
            return self.file_tools.create_archive(
                paths=[str(item) for item in args["paths"]],
                archive_name=str(args["archive_name"]),
            )
        if action == "extract_text_docx":
            return self.doc_tools.extract_text_docx(path=str(args["path"]))
        if action == "extract_text_pdf":
            return self.doc_tools.extract_text_pdf(path=str(args["path"]))
        if action == "summarize_document":
            return self.doc_tools.summarize_document(path=str(args["path"]))
        if action == "open_document":
            return self.doc_tools.open_document(path=str(args["path"]))
        if action == "search_docs_by_keyword":
            return self.search_engine.search_file_content(
                query=str(args["query"]),
                file_types=["txt", "docx", "pdf", "md"],
            )
        if action == "search_filename":
            return self.search_engine.search_filename(query=str(args["query"]))
        if action == "search_file_content":
            return self.search_engine.search_file_content(
                query=str(args["query"]),
                file_types=args.get("file_types"),
            )
        if action == "rebuild_index":
            return self.search_engine.rebuild_index()
        if action == "schedule_shutdown":
            return self.scheduler_tools.schedule_shutdown(minutes=int(args["minutes"]))
        if action == "cancel_shutdown":
            return self.scheduler_tools.cancel_shutdown()
        if action == "schedule_open_app":
            app_name = str(args["app"]).strip().lower()
            app_path = self.config.allowed_apps[app_name]
            return self.scheduler_tools.schedule_open_app(
                app_name=app_name,
                app_path=app_path,
                minutes=int(args["minutes"]),
            )
        if action == "open_app":
            app_name = str(args["app"]).strip().lower()
            app_path = self.config.allowed_apps[app_name]
            return self.scheduler_tools.open_app(app_path=app_path)
        if action == "enable_startup":
            return self.startup_tools.enable_startup()
        if action == "disable_startup":
            return self.startup_tools.disable_startup()
        if action == "get_system_info":
            return self.shell_tools.get_system_info()
        if action == "get_local_ip":
            return self.network_tools.get_local_ip()
        if action == "get_public_ip":
            return self.network_tools.get_public_ip()
        if action == "check_internet":
            return self.network_tools.check_internet()
        if action == "ping_host":
            return self.network_tools.ping_host(host=str(args["host"]))
        if action == "restart_network_adapter":
            return self.network_tools.restart_network_adapter(adapter_name=args.get("adapter_name"))
        if action == "create_txt":
            return self._create_text_file(args["filename"], args["content"], ".txt")
        if action == "create_markdown":
            return self._create_text_file(args["filename"], args["content"], ".md")
        if action == "create_ps1":
            result = self._create_text_file(args["filename"], args["content"], ".ps1")
            self._log_generated_script(str(result["path"]), str(args["content"]))
            return {
                **result,
                "warning": "Перед запуском .ps1 обязательно проверьте содержимое скрипта вручную.",
            }
        if action == "create_email_template":
            return self._create_text_file(args["filename"], args["content"], ".txt")
        if action == "create_docx":
            return self._create_docx(args["filename"], args["content"])
        if action == "clean_downloads":
            return self.file_tools.clean_downloads()
        if action == "cancel_scheduled_task":
            job_id = str(args.get("job_id", "")).strip()
            return self.scheduler_tools.cancel_scheduled_task(job_id)
        if action == "list_scheduled_tasks":
            return self.scheduler_tools.list_scheduled_tasks()
        raise ValueError(f"Unsupported action: {action}")

    def _register_pending_action(
        self,
        chat_id: int,
        user_id: int,
        action: str,
        args: dict[str, Any],
    ) -> str:
        action_id = uuid.uuid4().hex[:12]
        pending = PendingAction(
            action_id=action_id,
            chat_id=chat_id,
            user_id=user_id,
            action=action,
            args=args,
            summary=self._build_confirmation_summary(action, args),
            created_at=datetime.now(timezone.utc),
        )
        self.pending_actions[action_id] = pending
        self.logger.info("Pending confirmation created: %s", pending)
        return action_id

    def _build_confirmation_summary(self, action: str, args: dict[str, Any]) -> str:
        if action == "delete_file":
            return f"удалить: {args.get('path')}"
        if action == "clean_downloads":
            return "очистить папку Downloads"
        if action == "schedule_shutdown":
            return f"выключить компьютер через {args.get('minutes')} минут"
        if action == "restart_network_adapter":
            adapter = args.get("adapter_name") or "активный адаптер"
            return f"перезапустить сетевой адаптер: {adapter}"
        if action == "create_ps1":
            return f"создать .ps1 скрипт: {args.get('filename')}"
        if action == "enable_startup":
            return "включить автозапуск бота"
        if action == "disable_startup":
            return "выключить автозапуск бота"
        return f"выполнить действие {action}"

    def _route_result_from_tool(self, action: str, result: dict[str, Any]) -> RouteResult:
        if result.get("status") == "confirmation_required":
            action_id = str(result["action_id"])
            summary = str(result.get("summary", ""))
            return RouteResult(
                message=f"Подтвердите действие: {summary}",
                confirmation_id=action_id,
                confirmation_text=summary,
            )

        if result.get("status") == "blocked":
            return RouteResult(message=f"Команда заблокирована политикой безопасности: {result.get('reason')}")

        if result.get("status") == "error":
            return RouteResult(message=f"Ошибка выполнения: {result.get('error')}")

        payload = result.get("result", result)
        attachment = None
        if action in ("take_screenshot", "send_file_to_chat"):
            attachment = payload.get("path")
        return RouteResult(
            message=self._format_result(action, payload),
            attachment_path=attachment,
        )

    def _format_result(self, action: str, payload: dict[str, Any]) -> str:
        if action == "mute_audio":
            return "Звук выключен."
        if action == "unmute_audio":
            return "Звук включен."
        if action == "toggle_mute":
            return "Состояние звука переключено."
        if action == "volume_up":
            msg = f"Громкость увеличена (на {payload.get('step', 10)}%)."
            if payload.get("current_volume") is not None:
                msg += f"\nТекущая громкость: {payload.get('current_volume')}%"
            return msg
        if action == "volume_down":
            msg = f"Громкость уменьшена (на {payload.get('step', 10)}%)."
            if payload.get("current_volume") is not None:
                msg += f"\nТекущая громкость: {payload.get('current_volume')}%"
            return msg
        if action == "media_play_pause":
            return "Воспроизведение приостановлено/запущено."
        if action == "media_next":
            return "Включен следующий трек."
        if action == "media_previous":
            return "Включен предыдущий трек."

        if action == "find_file_by_name":
            files = payload.get("files", [])
            if not files:
                return "Ничего не найдено."
            lines = files[:10]
            return "Найдено:\n" + "\n".join(lines)

        if action in {"search_filename", "search_file_content", "search_docs_by_keyword"}:
            results = payload.get("results", [])
            if not results:
                return "Ничего не найдено в индексе."
            lines = []
            for item in results[:8]:
                path = item.get("path")
                fragment = item.get("fragment")
                if fragment:
                    lines.append(f"{path}\n  {fragment}")
                else:
                    lines.append(str(path))
            return "Результаты поиска:\n" + "\n".join(lines)

        if action == "list_scheduled_tasks":
            tasks = payload.get("tasks", [])
            if not tasks:
                return "Запланированных задач нет."
            lines = [f"{t['job_id']} -> {t['next_run_time']}" for t in tasks]
            return "Запланированные задачи:\n" + "\n".join(lines)

        if action == "take_screenshot":
            return f"Скриншот сохранен: {payload.get('path')}"
            
        if action == "send_file_to_chat":
            return f"Файл отправлен: {payload.get('path')}"

        if action == "check_internet":
            online = payload.get("online")
            return "Интернет доступен." if online else f"Интернет недоступен: {payload.get('error', '')}"

        if action == "schedule_shutdown":
            return f"Выключение запланировано. ID: {payload.get('job_id')}, время: {payload.get('run_at')}"

        if action == "schedule_open_app":
            return (
                f"Запуск приложения '{payload.get('app')}' запланирован. "
                f"ID: {payload.get('job_id')}, время: {payload.get('run_at')}"
            )

        if action == "create_ps1":
            return (
                f"Скрипт создан: {payload.get('path')}\n"
                "Перед запуском .ps1 обязательно проверьте содержимое вручную."
            )

        if action == "cancel_scheduled_task":
            if payload.get("status") == "not_found":
                return "Запланированных задач для отмены не найдено."
            job_id = payload.get("job_id")
            if job_id:
                return f"Запланированная задача отменена. ID: {job_id}"
            cancelled = payload.get("cancelled")
            if cancelled is not None:
                return f"Отменено запланированных задач: {cancelled}"
            return "Запланированная задача отменена."

        return json.dumps(payload, ensure_ascii=False, indent=2)

    def _create_text_file(self, filename: str, content: str, extension: str) -> dict[str, Any]:
        out_path = self._resolve_output_path(filename, extension)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content, encoding="utf-8")
        return {"path": str(out_path), "bytes": out_path.stat().st_size}

    def _create_docx(self, filename: str, content: str) -> dict[str, Any]:
        out_path = self._resolve_output_path(filename, ".docx")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        document = Document()
        for line in content.splitlines() or [content]:
            document.add_paragraph(line)
        document.save(str(out_path))
        return {"path": str(out_path), "bytes": out_path.stat().st_size}

    def _resolve_output_path(self, filename: str, default_extension: str) -> Path:
        safe_name = filename.strip()
        if not safe_name:
            safe_name = f"generated_{uuid.uuid4().hex[:8]}{default_extension}"
        candidate = normalize_path(safe_name, default_parent=self.config.allowed_dirs[0])
        if candidate.suffix == "":
            candidate = candidate.with_suffix(default_extension)

        allowed = False
        for base in self.config.allowed_dirs:
            try:
                candidate.resolve().relative_to(base.resolve())
                allowed = True
                break
            except ValueError:
                continue
        if not allowed:
            name_only = normalize_filename(candidate.name)
            candidate = (self.config.allowed_dirs[0] / name_only).resolve()
            if candidate.suffix == "":
                candidate = candidate.with_suffix(default_extension)
        return candidate

    def _log_generated_script(self, path: str, content: str) -> None:
        with self.generated_scripts_log.open("a", encoding="utf-8") as log_file:
            log_file.write(f"{datetime.now().isoformat()} | {path}\n")
            log_file.write(content)
            log_file.write("\n" + "=" * 80 + "\n")

    def _check_rate_limit(self, user_id: int) -> bool:
        now = datetime.now(timezone.utc)
        window = self.user_requests[user_id]
        window.append(now)
        while window and (now - window[0]).total_seconds() > 60:
            window.popleft()
        return len(window) <= 20

    def _cleanup_expired_pending_actions(self) -> None:
        now = datetime.now(timezone.utc)
        expired_ids = [
            action_id
            for action_id, pending in self.pending_actions.items()
            if (now - pending.created_at).total_seconds() > 15 * 60
        ]
        for action_id in expired_ids:
            self.pending_actions.pop(action_id, None)

    def _log_tool_call(
        self,
        chat_id: int,
        user_id: int,
        action: str,
        args: dict[str, Any],
        status: str,
        result: dict[str, Any],
    ) -> None:
        self.storage_db.add_tool_call(
            chat_id=chat_id,
            user_id=user_id,
            tool_name=action,
            args_json=json.dumps(args, ensure_ascii=False),
            status=status,
            result_json=json.dumps(result, ensure_ascii=False),
        )

    def _log_security(self, message: str, *args: Any) -> None:
        log_fn = getattr(self.logger, "security", None)
        if callable(log_fn):
            log_fn(message, *args)
        else:
            self.logger.warning("SECURITY | " + message, *args)
