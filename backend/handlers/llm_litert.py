"""Multimodal LLM handler — Gemma 3n via LiteRT-LM runtime."""

import asyncio
import base64
import io
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

MAX_HISTORY_TURNS = 10

SYSTEM_PROMPT = (
    "You are a helpful, concise assistant that can see the "
    "user's screen. Respond clearly and briefly."
)
SYSTEM_PROMPT_AUDIO = (
    "You are a helpful, concise assistant that can hear the user "
    "and optionally see their screen."
)


def _save_image_temp(image_b64: str) -> str:
    """Decode a base64 JPEG and write it to a temp file. Returns the path."""
    data = base64.b64decode(image_b64)
    fd, path = tempfile.mkstemp(suffix=".jpg")
    try:
        os.write(fd, data)
    finally:
        os.close(fd)
    return path


def _save_audio_temp(audio_f32: np.ndarray, sample_rate: int = 16000) -> str:
    """Write float32 audio to a temp WAV file. Returns the path."""
    import soundfile as sf  # type: ignore

    fd, path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    sf.write(path, audio_f32, sample_rate)
    return path


def _cleanup(*paths: str) -> None:
    for p in paths:
        try:
            os.unlink(p)
        except OSError:
            pass


class LiteRTLMHandler:
    """LLM handler using LiteRT-LM for fast on-device inference."""

    def __init__(
        self,
        model_repo: str = "litert-community/gemma-4-E2B-it-litert-lm",
        model_file: str = "gemma-4-E2B-it.litertlm",
        max_new_tokens: int = 512,
        enable_thinking: bool = False,
    ):
        self.model_repo = model_repo
        self.model_file = model_file
        self.max_new_tokens = max_new_tokens
        self.enable_thinking = enable_thinking
        self._engine = None
        self._conversation = None
        self._model_path: Optional[str] = None
        self._vision_available: bool = False
        self.status = "not_loaded"
        self.error: Optional[str] = None
        self._last_latency_ms: Optional[float] = None
        self._history: List[Dict] = []

    async def load(self) -> None:
        self.status = "loading"
        try:
            loop = asyncio.get_event_loop()

            def _download_and_init():
                from huggingface_hub import hf_hub_download  # type: ignore

                logger.info(
                    f"Downloading {self.model_file} from {self.model_repo}…"
                )
                local_path = hf_hub_download(
                    repo_id=self.model_repo,
                    filename=self.model_file,
                )
                logger.info(f"Model cached at: {local_path}")
                return local_path

            self._model_path = await loop.run_in_executor(None, _download_and_init)

            def _start_engine():
                import litert_lm  # type: ignore

                litert_lm.set_min_log_severity(litert_lm.LogSeverity.WARNING)

                # Try with vision+audio first, fall back to audio-only
                vision_ok = False
                try:
                    engine = litert_lm.Engine(
                        self._model_path,
                        backend=litert_lm.Backend.CPU,
                        audio_backend=litert_lm.Backend.CPU,
                        vision_backend=litert_lm.Backend.CPU,
                    )
                    engine.__enter__()
                    vision_ok = True
                except Exception as ve:
                    logger.warning(f"Vision backend not available ({ve}), loading without vision")
                    engine = litert_lm.Engine(
                        self._model_path,
                        backend=litert_lm.Backend.CPU,
                        audio_backend=litert_lm.Backend.CPU,
                    )
                    engine.__enter__()

                return engine, vision_ok

            self._engine, self._vision_available = await loop.run_in_executor(
                None, _start_engine
            )
            self._new_conversation()
            self.status = "idle"
            vision_str = "with vision" if self._vision_available else "text+audio only (no vision on CPU)"
            logger.info(f"LiteRT-LM loaded: {self.model_file} — {vision_str}")
        except Exception as exc:
            self.status = "error"
            self.error = str(exc)
            logger.error(f"LiteRT-LM load failed: {exc}")

    def _new_conversation(self) -> None:
        """Create a fresh conversation with the system prompt."""
        if self._conversation is not None:
            try:
                self._conversation.__exit__(None, None, None)
            except Exception:
                pass
        messages = [
            {
                "role": "system",
                "content": [{"type": "text", "text": SYSTEM_PROMPT}],
            }
        ]
        self._conversation = self._engine.create_conversation(messages=messages)
        self._conversation.__enter__()
        self._history = []

    async def generate(
        self,
        user_text: str,
        image_b64: Optional[str] = None,
        enable_thinking: Optional[bool] = None,
    ) -> str:
        if self._engine is None:
            return "(LLM not loaded — check config)"
        self.status = "running"
        t0 = time.perf_counter()
        tmp_paths: list[str] = []
        try:
            content: List[Dict] = []
            if image_b64 and self._vision_available:
                img_path = _save_image_temp(image_b64)
                tmp_paths.append(img_path)
                content.append({"type": "image", "path": img_path})
            content.append({"type": "text", "text": user_text})

            msg = {"role": "user", "content": content}
            loop = asyncio.get_event_loop()

            def _infer():
                return self._conversation.send_message(msg)

            response_obj = await loop.run_in_executor(None, _infer)
            response = self._extract_text(response_obj)

            self._history.append({"role": "user", "text": user_text})
            self._history.append({"role": "assistant", "text": response})
            self._trim_history()

            self._last_latency_ms = (time.perf_counter() - t0) * 1000
            logger.info(f"LiteRT-LM {self._last_latency_ms:.0f}ms: {response}")
            return response

        except Exception as exc:
            self.error = str(exc)
            logger.error(f"LiteRT-LM generate error: {exc}")
            return f"Error: {exc}"
        finally:
            self.status = "idle"
            _cleanup(*tmp_paths)

    async def generate_stream(
        self,
        user_text: str,
        image_b64: Optional[str] = None,
        enable_thinking: Optional[bool] = None,
    ):
        """Async generator yielding response chunks as they are produced."""
        if self._engine is None:
            yield "(LLM not loaded — check config)"
            return

        self.status = "running"
        t0 = time.perf_counter()
        full_response = ""
        tmp_paths: list[str] = []

        try:
            content: List[Dict] = []
            if image_b64 and self._vision_available:
                img_path = _save_image_temp(image_b64)
                tmp_paths.append(img_path)
                content.append({"type": "image", "path": img_path})
            content.append({"type": "text", "text": user_text})

            msg = {"role": "user", "content": content}
            loop = asyncio.get_event_loop()
            token_queue: asyncio.Queue = asyncio.Queue()

            def _stream():
                """Run the blocking streaming iterator, forward chunks to async queue."""
                try:
                    for chunk in self._conversation.send_message_async(msg):
                        text = ""
                        for item in chunk.get("content", []):
                            if item.get("type") == "text":
                                text += item["text"]
                        if text:
                            loop.call_soon_threadsafe(token_queue.put_nowait, text)
                except Exception as exc:
                    loop.call_soon_threadsafe(token_queue.put_nowait, exc)
                finally:
                    loop.call_soon_threadsafe(token_queue.put_nowait, None)

            executor_task = loop.run_in_executor(None, _stream)

            while True:
                item = await token_queue.get()
                if item is None:
                    break
                if isinstance(item, Exception):
                    raise item
                full_response += item
                yield item

            await executor_task

            self._history.append({"role": "user", "text": user_text})
            self._history.append({"role": "assistant", "text": full_response})
            self._trim_history()

            self._last_latency_ms = (time.perf_counter() - t0) * 1000
            logger.info(
                f"LiteRT-LM stream {self._last_latency_ms:.0f}ms: {full_response}"
            )

        except Exception as exc:
            self.error = str(exc)
            logger.error(f"LiteRT-LM stream error: {exc}")
            yield f"Error: {exc}"
        finally:
            self.status = "idle"
            _cleanup(*tmp_paths)

    async def generate_with_audio(
        self,
        audio_float32: np.ndarray,
        sample_rate: int = 16000,
        image_b64: Optional[str] = None,
        enable_thinking: Optional[bool] = None,
    ) -> tuple[str, str]:
        """
        Send audio (and optionally a screen frame) directly to the model.
        Returns (transcript, response).
        """
        if self._engine is None:
            return "", "(LLM not loaded)"
        self.status = "running"
        t0 = time.perf_counter()
        tmp_paths: list[str] = []
        try:
            content: List[Dict] = []

            audio_path = _save_audio_temp(audio_float32, sample_rate)
            tmp_paths.append(audio_path)
            content.append({"type": "audio", "path": audio_path})

            use_image = image_b64 and self._vision_available
            if use_image:
                img_path = _save_image_temp(image_b64)
                tmp_paths.append(img_path)
                content.append({"type": "image", "path": img_path})

            content.append({
                "type": "text",
                "text": (
                    "Listen to the audio. "
                    "First output a single line starting with 'You said: ' containing "
                    "the verbatim transcription. "
                    "Then on a new line respond helpfully and concisely as an AI assistant"
                    + (" that can also see the user's screen." if use_image else ".")
                ),
            })

            msg = {"role": "user", "content": content}
            loop = asyncio.get_event_loop()

            def _infer():
                return self._conversation.send_message(msg)

            response_obj = await loop.run_in_executor(None, _infer)
            full_response = self._extract_text(response_obj)

            transcript = ""
            reply_lines = []
            for line in full_response.splitlines():
                if line.lower().startswith("you said:"):
                    transcript = line[len("you said:"):].strip()
                else:
                    reply_lines.append(line)
            response = "\n".join(reply_lines).strip()

            self._history.append({"role": "user", "text": f"[audio] {transcript}"})
            self._history.append({"role": "assistant", "text": response})
            self._trim_history()

            self._last_latency_ms = (time.perf_counter() - t0) * 1000
            logger.info(
                f"LiteRT-LM(audio) {self._last_latency_ms:.0f}ms | transcript: {transcript}"
            )
            return transcript, response

        except Exception as exc:
            self.error = str(exc)
            logger.error(f"LiteRT-LM generate_with_audio error: {exc}")
            return "", f"Error: {exc}"
        finally:
            self.status = "idle"
            _cleanup(*tmp_paths)

    def clear_history(self) -> None:
        self._new_conversation()
        logger.info("Conversation history cleared (new LiteRT-LM conversation)")

    def get_status(self) -> Dict[str, Any]:
        return {
            "name": "LLM (Gemma 4 LiteRT)",
            "status": self.status,
            "model": self.model_file,
            "device": "cpu (LiteRT-LM)",
            "error": self.error,
            "latency_ms": self._last_latency_ms,
        }

    def _trim_history(self) -> None:
        max_msgs = MAX_HISTORY_TURNS * 2
        if len(self._history) > max_msgs:
            self._history = self._history[-max_msgs:]

    @staticmethod
    def _extract_text(response_obj) -> str:
        """Pull the text string out of a LiteRT-LM response dict."""
        if isinstance(response_obj, str):
            return response_obj
        if isinstance(response_obj, dict):
            parts = []
            for item in response_obj.get("content", []):
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(item["text"])
            return "".join(parts)
        return str(response_obj)
