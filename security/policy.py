from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from security.allowlists import (
    ALLOWED_TOOL_ACTIONS,
    BLOCKED_PATTERNS,
    BLOCKED_WINDOWS_PATH_PARTS,
    DANGEROUS_ACTIONS,
    PATH_ACTION_ARGS,
)
from security.validators import is_safe_hostname, normalize_path


@dataclass(slots=True)
class PolicyDecision:
    allowed: bool
    requires_confirmation: bool = False
    reason: str = ""
    normalized_args: dict[str, Any] = field(default_factory=dict)


class CommandPolicy:
    def __init__(
        self,
        allowed_dirs: list[Path],
        allowed_apps: dict[str, str],
        allowed_network_hosts: list[str],
        allowed_actions: set[str] | None = None,
    ) -> None:
        self.allowed_dirs = [path.resolve() for path in allowed_dirs]
        self.allowed_apps = {k.lower(): v for k, v in allowed_apps.items()}
        self.allowed_network_hosts = {host.lower() for host in allowed_network_hosts}
        self.allowed_actions = allowed_actions or set(ALLOWED_TOOL_ACTIONS)

    def evaluate(self, action: str, args: dict[str, Any] | None, confirmed: bool = False) -> PolicyDecision:
        args = args or {}
        normalized_args = self._normalize_args(args)
        action = action.strip()

        if action not in self.allowed_actions:
            return PolicyDecision(False, reason=f"Action '{action}' is not in allowlist.")

        serialized = json.dumps(normalized_args, ensure_ascii=False)
        for pattern in BLOCKED_PATTERNS:
            if pattern.search(serialized):
                return PolicyDecision(False, reason="Blocked by security pattern.")

        path_check = self._validate_paths(action, normalized_args)
        if path_check is not None:
            return path_check

        if action in {"open_app", "schedule_open_app"}:
            app = str(normalized_args.get("app", "")).strip().lower()
            if app not in self.allowed_apps:
                return PolicyDecision(False, reason=f"App '{app}' is not in allowlist.")

        if action == "ping_host":
            host = str(normalized_args.get("host", "")).strip()
            if not host or not is_safe_hostname(host):
                return PolicyDecision(False, reason="Unsafe host format.")
            if self.allowed_network_hosts and host.lower() not in self.allowed_network_hosts:
                return PolicyDecision(False, reason=f"Host '{host}' is not in allowlist.")

        if action in DANGEROUS_ACTIONS and not confirmed:
            return PolicyDecision(
                allowed=True,
                requires_confirmation=True,
                reason=f"Action '{action}' requires user confirmation.",
                normalized_args=normalized_args,
            )

        return PolicyDecision(True, normalized_args=normalized_args)

    def _normalize_args(self, args: dict[str, Any]) -> dict[str, Any]:
        normalized: dict[str, Any] = {}
        for key, value in args.items():
            if isinstance(value, str):
                normalized[key] = value.strip()
            elif isinstance(value, list):
                normalized[key] = [item.strip() if isinstance(item, str) else item for item in value]
            else:
                normalized[key] = value
        return normalized

    def _validate_paths(self, action: str, args: dict[str, Any]) -> PolicyDecision | None:
        path_arg_names = PATH_ACTION_ARGS.get(action, [])
        for arg_name in path_arg_names:
            value = args.get(arg_name)
            if value is None:
                continue

            values = value if isinstance(value, list) else [value]
            for path_value in values:
                if not isinstance(path_value, str):
                    continue

                try:
                    candidate = normalize_path(path_value, default_parent=self.allowed_dirs[0])
                except OSError:
                    return PolicyDecision(False, reason=f"Invalid path in '{arg_name}'.")

                lower_candidate = str(candidate).lower()
                if any(part in lower_candidate for part in BLOCKED_WINDOWS_PATH_PARTS):
                    return PolicyDecision(False, reason="System path operations are blocked.")

                if not self._is_allowed_path(candidate):
                    return PolicyDecision(False, reason=f"Path is outside allowed directories: {candidate}")
        return None

    def _is_allowed_path(self, path: Path) -> bool:
        for allowed in self.allowed_dirs:
            try:
                path.resolve().relative_to(allowed.resolve())
                return True
            except ValueError:
                continue
        return False
