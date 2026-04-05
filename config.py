from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator


class AppConfig(BaseModel):
    project_root: Path

    telegram_bot_token: str = ""
    telegram_allowed_user_ids: list[int] = Field(default_factory=list)
    interface_language: str = "ru"

    openai_api_key: str = ""
    openai_model_primary: str = "gpt-5-mini"
    openai_model_secondary: str = "gpt-5.4-mini"
    openai_model_fallback: str = "gpt-4.1-mini"

    allowed_dirs: list[Path] = Field(default_factory=list)
    allowed_apps: dict[str, str] = Field(default_factory=dict)
    allowed_network_hosts: list[str] = Field(default_factory=list)

    file_size_limit_mb: int = 25
    max_files_per_operation: int = 100
    powershell_timeout_sec: int = 20

    logs_dir: Path
    temp_dir: Path
    search_db_path: Path
    log_level: str = "INFO"
    enable_startup_by_default: bool = False
    stt_model_size: str = "small"

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        return value.upper().strip()


def _to_bool(value: str | bool | None, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _get_nested(data: dict[str, Any], path: list[str], default: Any = None) -> Any:
    current: Any = data
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def _parse_allowed_dirs(raw: str | list[str] | None, project_root: Path) -> list[Path]:
    if raw is None:
        raw = [
            "%USERPROFILE%\\Documents",
            "%USERPROFILE%\\Downloads",
            "%USERPROFILE%\\Desktop",
            ".",
        ]

    if isinstance(raw, str):
        parts = [item.strip() for item in raw.split(";") if item.strip()]
    else:
        parts = raw

    resolved: list[Path] = []
    for item in parts:
        expanded = os.path.expandvars(item)
        path = Path(expanded)
        if not path.is_absolute():
            path = (project_root / path).resolve()
        else:
            path = path.resolve()
        resolved.append(path)
    return resolved


def _parse_allowed_apps(raw: str | dict[str, str] | None) -> dict[str, str]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return {k.strip().lower(): os.path.expandvars(v).strip() for k, v in raw.items() if v}

    result: dict[str, str] = {}
    for pair in raw.split(";"):
        if "=" not in pair:
            continue
        key, value = pair.split("=", 1)
        key = key.strip().lower()
        value = os.path.expandvars(value.strip())
        if key and value:
            result[key] = value
    return result


def _parse_int_list(raw: str | list[int] | list[str] | None) -> list[int]:
    if raw is None:
        return []
    if isinstance(raw, list):
        parsed: list[int] = []
        for item in raw:
            try:
                parsed.append(int(item))
            except (TypeError, ValueError):
                continue
        return parsed

    values = [item.strip() for item in raw.split(",") if item.strip()]
    parsed = []
    for value in values:
        try:
            parsed.append(int(value))
        except ValueError:
            continue
    return parsed


def load_config(project_root: Path | None = None) -> AppConfig:
    project_root = (project_root or Path(__file__).resolve().parent).resolve()
    dotenv_path = project_root / ".env"
    if dotenv_path.exists():
        load_dotenv(dotenv_path=dotenv_path)
    else:
        load_dotenv()

    yaml_config: dict[str, Any] = {}
    yaml_path = project_root / "config.yaml"
    if yaml_path.exists():
        with yaml_path.open("r", encoding="utf-8") as f:
            loaded = yaml.safe_load(f) or {}
            if isinstance(loaded, dict):
                yaml_config = loaded

    def pick(env_key: str, yaml_path_parts: list[str], default: Any = None) -> Any:
        env_value = os.getenv(env_key)
        if env_value is not None and env_value != "":
            return env_value
        return _get_nested(yaml_config, yaml_path_parts, default)

    allowed_dirs = _parse_allowed_dirs(
        pick("ALLOWED_DIRS", ["security", "allowed_dirs"], None),
        project_root=project_root,
    )

    allowed_apps = _parse_allowed_apps(pick("ALLOWED_APPS", ["tools", "allowed_apps"], None))

    allowed_hosts = pick("ALLOWED_NETWORK_HOSTS", ["tools", "allowed_network_hosts"], None)
    if isinstance(allowed_hosts, str):
        allowed_network_hosts = [item.strip() for item in allowed_hosts.split(",") if item.strip()]
    elif isinstance(allowed_hosts, list):
        allowed_network_hosts = [str(item).strip() for item in allowed_hosts if str(item).strip()]
    else:
        allowed_network_hosts = ["google.com", "ya.ru", "cloudflare.com"]

    logs_dir = Path(
        os.path.expandvars(str(pick("LOGS_DIR", ["runtime", "logs_dir"], "./logs")))
    )
    if not logs_dir.is_absolute():
        logs_dir = (project_root / logs_dir).resolve()

    temp_dir = Path(
        os.path.expandvars(str(pick("TEMP_DIR", ["runtime", "temp_dir"], "./temp")))
    )
    if not temp_dir.is_absolute():
        temp_dir = (project_root / temp_dir).resolve()

    search_db_path = Path(
        os.path.expandvars(str(pick("SEARCH_DB_PATH", ["runtime", "search_db_path"], "./storage/search_index.db")))
    )
    if not search_db_path.is_absolute():
        search_db_path = (project_root / search_db_path).resolve()

    return AppConfig(
        project_root=project_root,
        telegram_bot_token=str(pick("TELEGRAM_BOT_TOKEN", ["telegram", "bot_token"], "")).strip(),
        telegram_allowed_user_ids=_parse_int_list(
            pick("TELEGRAM_ALLOWED_USER_IDS", ["telegram", "allowed_user_ids"], [])
        ),
        interface_language=str(pick("INTERFACE_LANGUAGE", ["telegram", "interface_language"], "ru")),
        openai_api_key=str(pick("OPENAI_API_KEY", ["openai", "api_key"], "")).strip(),
        openai_model_primary=str(pick("OPENAI_MODEL_PRIMARY", ["openai", "model_primary"], "gpt-5-mini")),
        openai_model_secondary=str(
            pick("OPENAI_MODEL_SECONDARY", ["openai", "model_secondary"], "gpt-5.4-mini")
        ),
        openai_model_fallback=str(pick("OPENAI_MODEL_FALLBACK", ["openai", "model_fallback"], "gpt-4.1-mini")),
        allowed_dirs=allowed_dirs,
        allowed_apps=allowed_apps,
        allowed_network_hosts=allowed_network_hosts,
        file_size_limit_mb=int(pick("FILE_SIZE_LIMIT_MB", ["security", "file_size_limit_mb"], 25)),
        max_files_per_operation=int(
            pick("MAX_FILES_PER_OPERATION", ["security", "max_files_per_operation"], 100)
        ),
        powershell_timeout_sec=int(
            pick("POWERSHELL_TIMEOUT_SEC", ["security", "powershell_timeout_sec"], 20)
        ),
        logs_dir=logs_dir,
        temp_dir=temp_dir,
        search_db_path=search_db_path,
        log_level=str(pick("LOG_LEVEL", ["runtime", "log_level"], "INFO")),
        enable_startup_by_default=_to_bool(
            pick("ENABLE_STARTUP_BY_DEFAULT", ["runtime", "enable_startup_by_default"], False),
            default=False,
        ),
        stt_model_size=str(pick("STT_MODEL_SIZE", ["runtime", "stt_model_size"], "small")),
    )
