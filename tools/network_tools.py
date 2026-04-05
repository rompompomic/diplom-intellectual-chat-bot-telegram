from __future__ import annotations

import socket
import subprocess
from dataclasses import dataclass

import requests


@dataclass(slots=True)
class NetworkTools:
    timeout_sec: int = 10

    def get_local_ip(self) -> dict:
        hostname = socket.gethostname()
        addresses = socket.getaddrinfo(hostname, None, socket.AF_INET)
        ipv4 = sorted({item[4][0] for item in addresses if item[4]})
        return {"hostname": hostname, "local_ipv4": ipv4}

    def get_public_ip(self) -> dict:
        response = requests.get("https://api.ipify.org?format=json", timeout=self.timeout_sec)
        response.raise_for_status()
        return response.json()

    def check_internet(self) -> dict:
        try:
            response = requests.get("https://clients3.google.com/generate_204", timeout=self.timeout_sec)
            online = response.status_code in {200, 204}
            return {"online": online, "status_code": response.status_code}
        except requests.RequestException as exc:
            return {"online": False, "error": str(exc)}

    def ping_host(self, host: str) -> dict:
        process = subprocess.run(
            ["ping", "-n", "4", host],
            capture_output=True,
            text=True,
            timeout=self.timeout_sec,
            check=False,
        )
        stdout = (process.stdout or "")[:3000]
        stderr = (process.stderr or "")[:1000]
        return {
            "host": host,
            "returncode": process.returncode,
            "stdout": stdout,
            "stderr": stderr,
        }

    def restart_network_adapter(self, adapter_name: str | None = None) -> dict:
        if adapter_name:
            safe_name = adapter_name.replace("'", "''")
            script = (
                f"$name='{safe_name}';"
                "Disable-NetAdapter -Name $name -Confirm:$false;"
                "Start-Sleep -Seconds 2;"
                "Enable-NetAdapter -Name $name -Confirm:$false;"
                "Write-Output \"Adapter restarted: $name\""
            )
        else:
            script = (
                "$name=(Get-NetAdapter | Where-Object {$_.Status -eq 'Up'} | Select-Object -First 1).Name;"
                "if (-not $name) { throw 'No active adapter found.' };"
                "Disable-NetAdapter -Name $name -Confirm:$false;"
                "Start-Sleep -Seconds 2;"
                "Enable-NetAdapter -Name $name -Confirm:$false;"
                "Write-Output \"Adapter restarted: $name\""
            )

        process = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=self.timeout_sec,
            check=False,
        )
        return {
            "returncode": process.returncode,
            "stdout": (process.stdout or "")[:2000],
            "stderr": (process.stderr or "")[:1000],
        }
