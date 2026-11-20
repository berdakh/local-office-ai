"""faster-whisper wrapper. Imported lazily so the app runs without the optional extra."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

import numpy as np


@dataclass
class Segment:
    start: float
    end: float
    text: str


@dataclass
class Transcription:
    segments: list[Segment]
    duration: float


def model_files_present(path: Path) -> bool:
    return all((path / name).is_file() for name in ("config.json", "model.bin", "tokenizer.json"))


def transcription_available(model_path: Path) -> bool:
    if not model_files_present(model_path):
        return False
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        return False
    return True


class Transcriber:
    def __init__(self, model_path: Path, device: str = "auto", compute_type: str = "auto"):
        self.model_path = model_path
        self.device = device
        self.compute_type = compute_type
        self._model = None
        self._load_lock = Lock()

    def _load(self):
        with self._load_lock:
            if self._model is None:
                if not transcription_available(self.model_path):
                    raise RuntimeError("The local transcription model or package is missing.")
                from faster_whisper import WhisperModel

                self._model = WhisperModel(
                    str(self.model_path),
                    device=self.device,
                    compute_type=self.compute_type,
                    local_files_only=True,
                )
            return self._model

    def transcribe(
        self, path: Path, progress: Callable[[float], None] | None = None
    ) -> Transcription:
        model = self._load()
        segments, info = model.transcribe(str(path), vad_filter=True, beam_size=5)
        total = info.duration or 0.0
        out: list[Segment] = []
        for s in segments:
            out.append(Segment(start=s.start, end=s.end, text=s.text.strip()))
            if progress and total:
                progress(min(1.0, s.end / total))
        return Transcription(out, total)

    def preview(self, pcm: bytes) -> str:
        audio = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768
        segments, _ = self._load().transcribe(
            audio, beam_size=1, vad_filter=True, condition_on_previous_text=False
        )
        return "\n".join(segment.text.strip() for segment in segments if segment.text.strip())


def segments_to_text(segments: list[Segment]) -> str:
    return "\n".join(s.text for s in segments if s.text)
