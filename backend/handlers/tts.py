"""
Text-to-Speech handler.

Priority order:
  1. kokoro-onnx   — neural TTS, auto-downloads model files on first run
  2. Windows SAPI  — built-in Windows voices via pywin32, zero model files needed
"""

import asyncio
import io
import logging
import os
import time
import wave
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np

logger = logging.getLogger(__name__)

# kokoro model files are downloaded next to this file's parent (backend/)
_BACKEND_DIR = Path(__file__).resolve().parent.parent
_KOKORO_ONNX = _BACKEND_DIR / "kokoro-v1_0.onnx"
_KOKORO_VOICES = _BACKEND_DIR / "voices-v1_0.bin"


class TTSHandler:
    def __init__(self, voice: str = "af_heart", speed: float = 1.0):
        self.voice = voice
        self.speed = speed
        self._kokoro = None
        self._backend: str = "none"
        self.status = "not_loaded"
        self.error: Optional[str] = None
        self._last_latency_ms: Optional[float] = None

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------

    async def load(self) -> None:
        self.status = "loading"
        loop = asyncio.get_event_loop()

        # ── 1. kokoro-onnx ────────────────────────────────────────────
        try:
            from kokoro_onnx import Kokoro  # type: ignore

            # Auto-download model files if missing
            if not _KOKORO_ONNX.exists() or not _KOKORO_VOICES.exists():
                logger.info("Downloading kokoro model files from HuggingFace…")
                await loop.run_in_executor(None, _download_kokoro)

            self._kokoro = await loop.run_in_executor(
                None, lambda: Kokoro(str(_KOKORO_ONNX), str(_KOKORO_VOICES))
            )
            self._backend = "kokoro"
            self.status = "idle"
            logger.info("TTS loaded: kokoro-onnx")
            return
        except Exception as exc:
            logger.warning(f"kokoro-onnx unavailable: {exc}")

        # ── 2. Windows SAPI fallback ──────────────────────────────────
        try:
            import win32com.client  # type: ignore  # noqa: F401

            # Smoke-test: can we create the voice object?
            await loop.run_in_executor(None, _sapi_smoke_test)
            self._backend = "sapi"
            self.status = "idle"
            logger.info("TTS loaded: Windows SAPI")
        except Exception as exc:
            self._backend = "none"
            self.status = "error"
            self.error = str(exc)
            logger.error(f"TTS load failed: {exc}")

    # ------------------------------------------------------------------
    # Synthesize
    # ------------------------------------------------------------------

    async def synthesize(self, text: str) -> bytes:
        if self._backend == "none":
            return b""
        self.status = "running"
        t0 = time.perf_counter()
        try:
            loop = asyncio.get_event_loop()

            if self._backend == "kokoro":
                samples, sr = await loop.run_in_executor(
                    None,
                    lambda: self._kokoro.create(
                        text, voice=self.voice, speed=self.speed, lang="en-us"
                    ),
                )
                wav_bytes = _float32_to_wav(samples, sr)

            else:  # sapi
                wav_bytes = await loop.run_in_executor(
                    None, lambda: _sapi_synth(text)
                )

            self._last_latency_ms = (time.perf_counter() - t0) * 1000
            logger.info(f"TTS {self._last_latency_ms:.0f}ms, {len(wav_bytes)} bytes")
            return wav_bytes

        except Exception as exc:
            self.error = str(exc)
            logger.error(f"TTS synthesize error: {exc}")
            return b""
        finally:
            self.status = "idle"

    def get_status(self) -> Dict[str, Any]:
        return {
            "name": f"TTS ({self._backend})",
            "status": self.status,
            "model": self.voice if self._backend == "kokoro" else self._backend,
            "error": self.error,
            "latency_ms": self._last_latency_ms,
        }


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def _download_kokoro() -> None:
    """Download kokoro model files from HuggingFace Hub."""
    from huggingface_hub import hf_hub_download  # type: ignore

    repo = "hexgrad/Kokoro-82M"
    for filename, dest in [
        ("kokoro-v1_0.onnx", _KOKORO_ONNX),
        ("voices-v1_0.bin", _KOKORO_VOICES),
    ]:
        if not dest.exists():
            logger.info(f"Downloading {filename}…")
            path = hf_hub_download(repo_id=repo, filename=filename)
            import shutil
            shutil.copy(path, dest)
            logger.info(f"Saved {filename} → {dest}")


def _sapi_smoke_test() -> None:
    import pythoncom       # type: ignore
    import win32com.client  # type: ignore

    pythoncom.CoInitialize()
    try:
        v = win32com.client.Dispatch("SAPI.SpVoice")
        _ = v.GetVoices()
    finally:
        pythoncom.CoUninitialize()


def _sapi_synth(text: str) -> bytes:
    """Synthesize via Windows SAPI.

    COM must be initialized per-thread.  We call CoInitialize / CoUninitialize
    around every synthesis so it works correctly in threadpool workers.
    """
    import tempfile

    import pythoncom       # type: ignore
    import win32com.client  # type: ignore

    pythoncom.CoInitialize()
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        tmp = f.name
    try:
        voice = win32com.client.Dispatch("SAPI.SpVoice")
        stream = win32com.client.Dispatch("SAPI.SpFileStream")
        stream.Open(tmp, 3)   # SSFMCreateForWrite = 3
        voice.AudioOutputStream = stream
        voice.Speak(text)
        stream.Close()
        with open(tmp, "rb") as f:
            return f.read()
    finally:
        pythoncom.CoUninitialize()
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _float32_to_wav(samples: np.ndarray, sample_rate: int) -> bytes:
    buf = io.BytesIO()
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16)
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())
    return buf.getvalue()
