from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class StartupTools:
    project_root: Path
    entry_file: str = "app.py"
    startup_filename: str = "telegram_pc_bot_startup.bat"

    def enable_startup(self) -> dict:
        startup_file = self._startup_file_path()
        startup_file.parent.mkdir(parents=True, exist_ok=True)
        python_exe = Path(sys.executable).resolve()
        app_path = (self.project_root / self.entry_file).resolve()

        startup_script = (
            "@echo off\n"
            f"cd /d \"{self.project_root}\"\n"
            f"\"{python_exe}\" \"{app_path}\"\n"
        )
        startup_file.write_text(startup_script, encoding="utf-8")
        return {"status": "ok", "startup_file": str(startup_file)}

    def disable_startup(self) -> dict:
        startup_file = self._startup_file_path()
        if startup_file.exists():
            startup_file.unlink()
            return {"status": "ok", "startup_file": str(startup_file), "removed": True}
        return {"status": "ok", "startup_file": str(startup_file), "removed": False}

    def startup_status(self) -> dict:
        startup_file = self._startup_file_path()
        return {"enabled": startup_file.exists(), "startup_file": str(startup_file)}

    def _startup_file_path(self) -> Path:
        appdata = os.environ.get("APPDATA")
        if not appdata:
            raise EnvironmentError("APPDATA environment variable is missing.")
        return (
            Path(appdata)
            / "Microsoft"
            / "Windows"
            / "Start Menu"
            / "Programs"
            / "Startup"
            / self.startup_filename
        )
