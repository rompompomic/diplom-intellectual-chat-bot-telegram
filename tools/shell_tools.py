from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Any


SAFE_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$")


@dataclass(slots=True)
class ShellTools:
    timeout_sec: int = 20
    stdout_limit: int = 4000
    stderr_limit: int = 2000
    templates: dict[str, str] = field(
        default_factory=lambda: {
            "get_system_info": (
                "Get-ComputerInfo | Select-Object "
                "CsName,WindowsProductName,WindowsVersion,OsArchitecture | Format-List"
            ),
            "list_processes": (
                "Get-Process | Select-Object -First 25 ProcessName,Id,CPU,WS | "
                "Format-Table -AutoSize | Out-String -Width 180"
            ),
            "net_status": (
                "Get-NetIPConfiguration | Select-Object InterfaceAlias,IPv4Address,IPv4DefaultGateway | "
                "Format-Table -AutoSize | Out-String -Width 180"
            ),
            "list_ports": (
                "Get-NetTCPConnection | Where-Object {$_.State -eq 'Listen'} | "
                "Select-Object -First 80 LocalAddress,LocalPort,OwningProcess | "
                "Format-Table -AutoSize | Out-String -Width 180"
            ),
            "disk_usage": (
                "Get-PSDrive -PSProvider FileSystem | "
                "Select-Object Name,Used,Free,Root | Format-Table -AutoSize | Out-String -Width 180"
            ),
        }
    )

    def get_system_info(self) -> dict:
        return self.run_template("get_system_info")

    def run_safe_command(self, command: str, args: dict[str, Any] | None = None) -> dict:
        args = args or {}
        command = command.strip()
        if command in {"get_system_info", "list_processes", "net_status", "list_ports", "disk_usage"}:
            return self.run_template(command)

        if command == "docker_ps":
            return self._run_process(["docker", "ps", "-a", "--no-trunc"])
        if command == "docker_stats":
            return self._run_process(["docker", "stats", "--no-stream"])
        if command == "docker_logs":
            container = self._safe_identifier(args.get("container"), "container")
            tail = self._safe_tail(args.get("tail", 200))
            return self._run_process(["docker", "logs", "--tail", str(tail), container])
        if command == "docker_inspect":
            container = self._safe_identifier(args.get("container"), "container")
            return self._run_process(["docker", "inspect", container])
        if command == "docker_top":
            container = self._safe_identifier(args.get("container"), "container")
            return self._run_process(["docker", "top", container])

        raise ValueError(f"Safe command '{command}' is not registered.")

    def run_template(self, template_name: str) -> dict:
        script = self.templates.get(template_name)
        if script is None:
            raise ValueError(f"Template '{template_name}' is not registered.")
        return self._run_powershell(script)

    def _run_process(self, command: list[str]) -> dict:
        executable = shutil.which(command[0])
        if executable is None:
            raise FileNotFoundError(f"Executable not found: {command[0]}")
        process = subprocess.run(
            [executable, *command[1:]],
            capture_output=True,
            text=True,
            timeout=self.timeout_sec,
            check=False,
        )
        return self._process_result(process)

    def _run_powershell(self, script: str) -> dict:
        process = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=self.timeout_sec,
            check=False,
        )
        return self._process_result(process)

    def _process_result(self, process: subprocess.CompletedProcess[str]) -> dict:
        return {
            "returncode": process.returncode,
            "stdout": (process.stdout or "")[: self.stdout_limit],
            "stderr": (process.stderr or "")[: self.stderr_limit],
        }

    @staticmethod
    def _safe_identifier(value: Any, name: str) -> str:
        text = str(value or "").strip()
        if not text or not SAFE_IDENTIFIER_PATTERN.fullmatch(text):
            raise ValueError(f"Invalid {name}.")
        return text

    @staticmethod
    def _safe_tail(value: Any) -> int:
        try:
            tail = int(value)
        except (TypeError, ValueError):
            tail = 200
        return max(1, min(tail, 500))
