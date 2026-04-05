from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class TranscriptionResult:
    text: str
    confidence: float
    low_confidence: bool


class SpeechToText:
    def __init__(self, model_size: str = "small") -> None:
        self.model_size = model_size
        self._model = None

    def transcribe(self, audio_path: Path, language: str = "ru") -> TranscriptionResult:
        model = self._get_model()
        segments, info = model.transcribe(
            str(audio_path),
            language=language,
            vad_filter=True,
            beam_size=5,
        )
        texts: list[str] = []
        confidences: list[float] = []
        for segment in segments:
            text = (segment.text or "").strip()
            if text:
                texts.append(text)
            no_speech_prob = getattr(segment, "no_speech_prob", 0.5)
            confidences.append(max(0.0, min(1.0, 1.0 - float(no_speech_prob))))

        full_text = " ".join(texts).strip()
        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
        language_prob = float(getattr(info, "language_probability", 0.0))
        confidence = (avg_conf + language_prob) / 2 if confidences else language_prob
        low_confidence = confidence < 0.45 or not full_text
        return TranscriptionResult(text=full_text, confidence=confidence, low_confidence=low_confidence)

    def _get_model(self):
        if self._model is not None:
            return self._model
        try:
            from faster_whisper import WhisperModel
        except Exception as exc:
            raise RuntimeError(
                "faster-whisper is not installed or failed to import. "
                "Install dependencies from requirements.txt."
            ) from exc

        self._model = WhisperModel(self.model_size, device="cpu", compute_type="int8")
        return self._model
