"""Speech-to-Text handler using faster-whisper."""

import asyncio
import logging
import time
from typing import Any, Dict, Optional

import numpy as np

logger = logging.getLogger(__name__)


class STTHandler:
    def __init__(self, model_name: str = "base", language: str = "en"):
        self.model_name = model_name
        self.language = language
        self._model = None
        self.status = "not_loaded"
        self.error: Optional[str] = None
        self._last_latency_ms: Optional[float] = None

    async def load(self) -> None:
        self.status = "loading"
        try:
            from faster_whisper import WhisperModel  # type: ignore

            loop = asyncio.get_event_loop()
            self._model = await loop.run_in_executor(
                None,
                lambda: WhisperModel(
                    self.model_name, device="cpu", compute_type="int8"
                ),
            )
            self.status = "idle"
            logger.info(f"STT loaded: whisper/{self.model_name}")
        except Exception as exc:
            self.status = "error"
            self.error = str(exc)
            logger.error(f"STT load failed: {exc}")

    async def transcribe(self, audio_float32: np.ndarray) -> str:
        """Transcribe float32 audio at 16 kHz. Returns text."""
        if self._model is None:
            return ""
        self.status = "running"
        t0 = time.perf_counter()
        try:
            loop = asyncio.get_event_loop()
            segments, _ = await loop.run_in_executor(
                None,
                lambda: self._model.transcribe(
                    audio_float32,
                    language=self.language,
                    beam_size=5,
                    vad_filter=True,
                ),
            )
            text = " ".join(s.text.strip() for s in segments).strip()
            self._last_latency_ms = (time.perf_counter() - t0) * 1000
            logger.info(f"STT {self._last_latency_ms:.0f}ms: {text[:120]}")
            return text
        except Exception as exc:
            self.error = str(exc)
            logger.error(f"STT transcribe error: {exc}")
            return ""
        finally:
            self.status = "idle"

    def get_status(self) -> Dict[str, Any]:
        return {
            "name": "STT (Whisper)",
            "status": self.status,
            "model": self.model_name,
            "error": self.error,
            "latency_ms": self._last_latency_ms,
        }
