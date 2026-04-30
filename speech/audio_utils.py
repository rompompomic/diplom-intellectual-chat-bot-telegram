from __future__ import annotations

import shutil
import uuid
from pathlib import Path


class AudioDependencyError(RuntimeError):
    pass


def build_temp_audio_path(temp_dir: Path, suffix: str) -> Path:
    temp_dir.mkdir(parents=True, exist_ok=True)
    return (temp_dir / f"{uuid.uuid4().hex}{suffix}").resolve()


def convert_to_wav(source_path: Path, target_path: Path) -> Path:
    missing = [tool for tool in ("ffmpeg", "ffprobe") if shutil.which(tool) is None]
    if missing:
        raise AudioDependencyError(
            "Missing audio dependency: "
            + ", ".join(missing)
            + ". Install FFmpeg and make sure its bin folder is in PATH."
        )

    from pydub import AudioSegment

    audio = AudioSegment.from_file(source_path)
    audio.export(target_path, format="wav")
    return target_path


def safe_remove(path: Path) -> None:
    if path.exists():
        path.unlink(missing_ok=True)
