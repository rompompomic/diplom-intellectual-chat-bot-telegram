from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

from security.allowlists import SAFE_HOST_PATTERN


def normalize_path(path_value: str | Path, default_parent: Path | None = None) -> Path:
    path = Path(os.path.expandvars(str(path_value).strip().strip('"')))
    if not path.is_absolute():
        if default_parent is None:
            default_parent = Path.cwd()
        path = default_parent / path
    return path.resolve()


def is_within_allowed_dirs(path: Path, allowed_dirs: Iterable[Path]) -> bool:
    target = path.resolve()
    for allowed in allowed_dirs:
        try:
            target.relative_to(allowed.resolve())
            return True
        except ValueError:
            continue
    return False


def is_safe_hostname(hostname: str) -> bool:
    return bool(SAFE_HOST_PATTERN.match(hostname.strip()))


def normalize_filename(filename: str) -> str:
    cleaned = filename.strip().replace("/", "_").replace("\\", "_").replace(":", "_")
    cleaned = cleaned.replace("*", "_").replace("?", "_").replace('"', "_")
    cleaned = cleaned.replace("<", "_").replace(">", "_").replace("|", "_")
    return cleaned or "untitled"
