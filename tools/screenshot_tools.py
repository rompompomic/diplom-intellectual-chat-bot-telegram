from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PIL import ImageGrab

from security.validators import normalize_path


@dataclass(slots=True)
class ScreenshotTools:
    allowed_dirs: list[Path]
    default_dir: Path

    def take_screenshot(self, save_path: str | None = None) -> dict:
        if save_path:
            output_path = normalize_path(save_path, default_parent=self.default_dir)
        else:
            name = datetime.now().strftime("screenshot_%Y%m%d_%H%M%S.png")
            output_path = (self.default_dir / name).resolve()

        if not self._is_allowed(output_path):
            raise PermissionError(f"Path is outside allowed dirs: {output_path}")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        image = ImageGrab.grab()
        image.save(output_path)
        return {"status": "ok", "path": str(output_path)}

    def _is_allowed(self, path: Path) -> bool:
        target = path.resolve()
        for allowed in self.allowed_dirs:
            try:
                target.relative_to(allowed.resolve())
                return True
            except ValueError:
                continue
        return False
