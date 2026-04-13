"""Voice Activity Detection — WebRTC VAD with energy-based fallback."""

import logging
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16_000
FRAME_MS = 30
FRAME_SIZE = int(SAMPLE_RATE * FRAME_MS / 1000)  # 480 samples per frame


class VADHandler:
    def __init__(self, aggressiveness: int = 2, silence_duration: float = 0.8):
        self.aggressiveness = aggressiveness
        self._silence_threshold = int(silence_duration * 1000 / FRAME_MS)
        self._vad = None
        self._pending: np.ndarray = np.array([], dtype=np.int16)
        self._speech_buf: list[int] = []
        self._silence_count = 0
        self._is_speaking = False

    def load(self) -> None:
        try:
            import webrtcvad  # type: ignore

            self._vad = webrtcvad.Vad(self.aggressiveness)
            logger.info("WebRTC VAD loaded")
        except Exception as exc:
            logger.warning(f"webrtcvad unavailable, using energy VAD: {exc}")
            self._vad = None

    def process_chunk(self, audio_int16: np.ndarray) -> Optional[np.ndarray]:
        """
        Feed an audio chunk.
        Returns a full speech segment (int16 np.ndarray) when end-of-speech is
        detected, otherwise returns None.
        """
        self._pending = np.concatenate([self._pending, audio_int16])
        completed: Optional[np.ndarray] = None

        while len(self._pending) >= FRAME_SIZE:
            frame = self._pending[:FRAME_SIZE]
            self._pending = self._pending[FRAME_SIZE:]
            is_speech = self._detect(frame)

            if is_speech:
                self._is_speaking = True
                self._speech_buf.extend(frame.tolist())
                self._silence_count = 0
            elif self._is_speaking:
                self._speech_buf.extend(frame.tolist())
                self._silence_count += 1
                if self._silence_count >= self._silence_threshold:
                    completed = np.array(self._speech_buf, dtype=np.int16)
                    self._speech_buf = []
                    self._silence_count = 0
                    self._is_speaking = False

        return completed

    def has_speech(self, audio_int16: np.ndarray) -> bool:
        """Check if any frame in the chunk contains speech (stateless — no side-effects)."""
        pos = 0
        while pos + FRAME_SIZE <= len(audio_int16):
            frame = audio_int16[pos : pos + FRAME_SIZE]
            if self._detect(frame):
                return True
            pos += FRAME_SIZE
        return False

    def reset(self) -> None:
        self._pending = np.array([], dtype=np.int16)
        self._speech_buf = []
        self._silence_count = 0
        self._is_speaking = False

    def _detect(self, frame: np.ndarray) -> bool:
        if self._vad is not None:
            try:
                return self._vad.is_speech(frame.tobytes(), SAMPLE_RATE)
            except Exception:
                pass
        rms = float(np.sqrt(np.mean(frame.astype(np.float32) ** 2)))
        return rms > 600
