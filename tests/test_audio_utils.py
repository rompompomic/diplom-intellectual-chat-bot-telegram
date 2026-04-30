from __future__ import annotations

from pathlib import Path

import pytest

from speech import audio_utils
from speech.audio_utils import AudioDependencyError, convert_to_wav


def test_convert_to_wav_reports_missing_ffmpeg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "voice.ogg"
    target = tmp_path / "voice.wav"
    source.write_bytes(b"")

    monkeypatch.setattr(audio_utils.shutil, "which", lambda _: None)

    with pytest.raises(AudioDependencyError, match="ffmpeg"):
        convert_to_wav(source, target)
