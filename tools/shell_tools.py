from __future__ import annotations

import subprocess
from dataclasses import dataclass, field


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
        }
    )

    def get_system_info(self) -> dict:
        return self.run_template("get_system_info")

    def run_template(self, template_name: str) -> dict:
        script = self.templates.get(template_name)
        if script is None:
            raise ValueError(f"Template '{template_name}' is not registered.")
        return self._run_powershell(script)

    def _run_powershell(self, script: str) -> dict:
        process = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=self.timeout_sec,
            check=False,
        )
        return {
            "returncode": process.returncode,
            "stdout": (process.stdout or "")[: self.stdout_limit],
            "stderr": (process.stderr or "")[: self.stderr_limit],
        }
