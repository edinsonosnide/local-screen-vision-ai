"""Multimodal LLM handler — Gemma 4 E2B-it via HuggingFace Transformers."""

import asyncio
import base64
import io
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

MAX_HISTORY_TURNS = 10  # keep last N user+assistant pairs

# Gemma 4 thinking-mode delimiters.
# The thinking block opens with a channel marker (e.g. <|channel>thought)
# and the actual response starts right after the <channel|> token.
_RESPONSE_MARKER = "<channel|>"

# Regex that catches every channel-like token variant for cleanup.
_CHANNEL_RE = re.compile(r"<\|?channel\|?>(?:thought|response)?")

_LITERAL_STRIP = (
    "<|channel|>response", "<|channel|>thought",
    "<|channel>thought", "<|channel>response",
    "<channel|>", "<|channel>", "<|channel|>",
    "<turn|>", "<|turn|>", "<end_of_turn>", "<eos>", "<bos>",
)


def _strip_tokens(text: str) -> str:
    """Strip Gemma 4 special / channel tokens from a text fragment."""
    text = _CHANNEL_RE.sub("", text)
    for tok in _LITERAL_STRIP:
        text = text.replace(tok, "")
    return text


def _extract_final_response(raw: str) -> str:
    """Return only the final answer, stripping any Gemma 4 thinking block."""
    if _RESPONSE_MARKER in raw:
        raw = raw.split(_RESPONSE_MARKER, 1)[1]
    return _strip_tokens(raw).strip()


class LLMHandler:
    def __init__(
        self,
        model_path: str,
        device: str = "auto",
        enable_thinking: bool = False,
        max_new_tokens: int = 512,
        image_token_budget: int = 280,
    ):
        self.model_path = model_path
        self.device = device
        self.enable_thinking = enable_thinking
        self.max_new_tokens = max_new_tokens
        self.image_token_budget = image_token_budget
        self._model = None
        self._processor = None
        self.status = "not_loaded"
        self.error: Optional[str] = None
        self._last_latency_ms: Optional[float] = None
        self._history: List[Dict] = []

    async def load(self) -> None:
        self.status = "loading"
        try:
            from transformers import AutoModelForMultimodalLM, AutoProcessor  # type: ignore

            # Resolve relative to backend/ (where main.py lives), not CWD.
            # Pass as Path object — HF treats Path instances as local dirs,
            # bypassing the repo-ID string validator that rejects Windows paths.
            _backend_dir = Path(__file__).resolve().parent.parent  # handlers/ -> backend/
            local_path = (_backend_dir / self.model_path).resolve()
            if not local_path.exists():
                raise FileNotFoundError(f"Model directory not found: {local_path}")
            loop = asyncio.get_event_loop()

            def _load():
                import torch  # type: ignore

                has_cuda = torch.cuda.is_available()
                proc = AutoProcessor.from_pretrained(local_path, local_files_only=True)

                if has_cuda:
                    free_vram = torch.cuda.mem_get_info()[0] / 1e9
                    logger.info(f"CUDA detected — {free_vram:.1f} GB VRAM free")

                    # Gemma 4 E2B in bfloat16 ≈ 4 GB — fits in 6 GB+ VRAM cleanly.
                    # Load to CPU first then move, so no meta tensors are created.
                    # This is simpler and more reliable than device_map="auto" + quant.
                    if free_vram >= 5.0:
                        try:
                            model = AutoModelForMultimodalLM.from_pretrained(
                                local_path,
                                dtype=torch.bfloat16,
                                local_files_only=True,
                            ).to("cuda")
                            logger.info("LLM loaded on GPU (bfloat16)")
                        except Exception as gpu_exc:
                            logger.warning(
                                f"bfloat16 GPU load failed ({gpu_exc}), "
                                "trying 4-bit quantization…"
                            )
                            # Patch Params4bit to absorb _is_hf_initialized kwarg
                            # added in transformers 4.48+ but missing in bnb 0.49.
                            try:
                                import bitsandbytes as bnb  # type: ignore
                                _orig_new = bnb.nn.Params4bit.__new__
                                def _p(cls, *a, _is_hf_initialized=None, **kw):
                                    return _orig_new(cls, *a, **kw)
                                bnb.nn.Params4bit.__new__ = _p
                            except Exception:
                                pass
                            from transformers import BitsAndBytesConfig  # type: ignore
                            bnb_cfg = BitsAndBytesConfig(
                                load_in_4bit=True,
                                bnb_4bit_compute_dtype=torch.bfloat16,
                                bnb_4bit_use_double_quant=True,
                                bnb_4bit_quant_type="nf4",
                            )
                            model = AutoModelForMultimodalLM.from_pretrained(
                                local_path,
                                quantization_config=bnb_cfg,
                                device_map="cuda:0",
                                local_files_only=True,
                            )
                            logger.info("LLM loaded with 4-bit NF4 quantization on GPU")
                    else:
                        logger.warning(
                            f"Only {free_vram:.1f} GB VRAM free — loading on CPU"
                        )
                        model = AutoModelForMultimodalLM.from_pretrained(
                            local_path,
                            dtype=torch.float32,
                            local_files_only=True,
                        )
                        logger.info("LLM loaded on CPU (low VRAM)")
                else:
                    model = AutoModelForMultimodalLM.from_pretrained(
                        local_path,
                        dtype=torch.float32,
                        local_files_only=True,
                    )
                    logger.info("LLM loaded on CPU (no CUDA detected)")

                return proc, model

            self._processor, self._model = await loop.run_in_executor(None, _load)
            self.status = "idle"
            logger.info(f"LLM loaded: {self.model_path}")
        except Exception as exc:
            self.status = "error"
            self.error = str(exc)
            logger.error(f"LLM load failed: {exc}")

    async def generate(
        self, user_text: str, image_b64: Optional[str] = None,
        enable_thinking: Optional[bool] = None,
    ) -> str:
        if self._model is None:
            return "(LLM not loaded — check model path in config.yaml)"
        self.status = "running"
        t0 = time.perf_counter()
        try:
            content: List[Dict] = []
            if image_b64:
                from PIL import Image  # type: ignore

                img = Image.open(io.BytesIO(base64.b64decode(image_b64)))
                content.append({"type": "image", "image": img})
            content.append({"type": "text", "text": user_text})

            self._history.append({"role": "user", "content": content})

            messages = [
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "You are a helpful, concise assistant that can see the "
                                "user's screen. Respond clearly and briefly."
                            ),
                        }
                    ],
                },
                *self._history,
            ]

            thinking = enable_thinking if enable_thinking is not None else self.enable_thinking
            loop = asyncio.get_event_loop()

            def _infer():
                import torch  # type: ignore  # noqa: F811

                inputs = self._processor.apply_chat_template(
                    messages,
                    tokenize=True,
                    return_dict=True,
                    return_tensors="pt",
                    add_generation_prompt=True,
                    enable_thinking=thinking,
                ).to(self._model.device)
                input_len = inputs["input_ids"].shape[-1]
                with torch.no_grad():
                    outputs = self._model.generate(
                        **inputs,
                        max_new_tokens=self.max_new_tokens,
                        do_sample=True,
                        temperature=1.0,
                        top_p=0.95,
                        top_k=64,
                    )
                raw = self._processor.decode(
                    outputs[0][input_len:], skip_special_tokens=False
                )
                return _extract_final_response(raw)

            response: str = await loop.run_in_executor(None, _infer)

            # Store only text in history (no image objects)
            self._history[-1] = {
                "role": "user",
                "content": [{"type": "text", "text": user_text}],
            }
            self._history.append(
                {"role": "assistant", "content": [{"type": "text", "text": response}]}
            )

            # Trim history
            max_msgs = MAX_HISTORY_TURNS * 2
            if len(self._history) > max_msgs:
                self._history = self._history[-max_msgs:]

            self._last_latency_ms = (time.perf_counter() - t0) * 1000
            logger.info(f"LLM {self._last_latency_ms:.0f}ms: {response}")
            return response

        except Exception as exc:
            self.error = str(exc)
            logger.error(f"LLM generate error: {exc}")
            return f"Error: {exc}"
        finally:
            self.status = "idle"

    async def generate_stream(
        self,
        user_text: str,
        image_b64: Optional[str] = None,
        enable_thinking: Optional[bool] = None,
    ):
        """
        Async generator yielding response text chunks as they are produced.
        Thinking blocks are buffered silently; only the final answer is streamed.
        """
        if self._model is None:
            yield "(LLM not loaded — check model path in config.yaml)"
            return

        self.status = "running"
        t0 = time.perf_counter()
        full_response = ""

        try:
            import threading as _threading
            import torch  # type: ignore
            from transformers import TextIteratorStreamer  # type: ignore

            content: List[Dict] = []
            if image_b64:
                from PIL import Image  # type: ignore
                img = Image.open(io.BytesIO(base64.b64decode(image_b64)))
                content.append({"type": "image", "image": img})
            content.append({"type": "text", "text": user_text})

            self._history.append({"role": "user", "content": content})

            messages = [
                {
                    "role": "system",
                    "content": [{"type": "text", "text": (
                        "You are a helpful, concise assistant that can see the "
                        "user's screen. Respond clearly and briefly."
                    )}],
                },
                *self._history,
            ]

            thinking = enable_thinking if enable_thinking is not None else self.enable_thinking

            inputs = self._processor.apply_chat_template(
                messages,
                tokenize=True,
                return_dict=True,
                return_tensors="pt",
                add_generation_prompt=True,
                enable_thinking=thinking,
            ).to(self._model.device)

            # Use the underlying tokenizer for the streamer
            tokenizer = getattr(self._processor, "tokenizer", self._processor)
            streamer = TextIteratorStreamer(
                tokenizer,
                skip_prompt=True,
                skip_special_tokens=False,
                timeout=120.0,
            )

            loop = asyncio.get_event_loop()
            token_queue: asyncio.Queue = asyncio.Queue()

            def _run() -> None:
                """Executor thread: runs generation then forwards tokens to asyncio queue."""
                try:
                    gen_thread = _threading.Thread(
                        target=lambda: self._model.generate(
                            **inputs,
                            max_new_tokens=self.max_new_tokens,
                            do_sample=True,
                            temperature=1.0,
                            top_p=0.95,
                            top_k=64,
                            streamer=streamer,
                        ),
                        daemon=True,
                    )
                    gen_thread.start()
                    for token in streamer:
                        loop.call_soon_threadsafe(token_queue.put_nowait, token)
                    gen_thread.join()
                except Exception as exc:
                    loop.call_soon_threadsafe(token_queue.put_nowait, exc)
                finally:
                    loop.call_soon_threadsafe(token_queue.put_nowait, None)

            executor_task = loop.run_in_executor(None, _run)

            # Stream tokens, silently buffering the thinking block.
            # When thinking is on we absorb everything until <channel|>
            # appears — that token marks the start of the actual response.
            raw_buffer = ""
            response_started = not thinking  # yield immediately when thinking is off

            while True:
                item = await token_queue.get()
                if item is None:
                    break
                if isinstance(item, Exception):
                    raise item

                token: str = item
                raw_buffer += token

                if not response_started:
                    if _RESPONSE_MARKER in raw_buffer:
                        response_started = True
                        after = raw_buffer.split(_RESPONSE_MARKER, 1)[1]
                        clean = _strip_tokens(after)
                        if clean:
                            full_response += clean
                            yield clean
                else:
                    clean = _strip_tokens(token)
                    if clean:
                        full_response += clean
                        yield clean

            await executor_task

            # Fallback: if no response marker appeared, extract from buffer
            if not full_response:
                full_response = _extract_final_response(raw_buffer)
                if full_response:
                    yield full_response

            # Update conversation history (text-only, no image objects)
            self._history[-1] = {
                "role": "user",
                "content": [{"type": "text", "text": user_text}],
            }
            self._history.append({
                "role": "assistant",
                "content": [{"type": "text", "text": full_response}],
            })
            max_msgs = MAX_HISTORY_TURNS * 2
            if len(self._history) > max_msgs:
                self._history = self._history[-max_msgs:]

            self._last_latency_ms = (time.perf_counter() - t0) * 1000
            logger.info(f"LLM stream {self._last_latency_ms:.0f}ms: {full_response}")

        except Exception as exc:
            self.error = str(exc)
            logger.error(f"LLM stream error: {exc}")
            yield f"Error: {exc}"
        finally:
            self.status = "idle"

    async def generate_with_audio(
        self,
        audio_float32: np.ndarray,
        sample_rate: int = 16000,
        image_b64: Optional[str] = None,
        enable_thinking: Optional[bool] = None,
    ) -> tuple[str, str]:
        """
        Send audio (and optionally a screen frame) directly to Gemma 4.
        Returns (transcript, response) — Gemma both transcribes and replies.
        Only works when the model was loaded with AutoModelForMultimodalLM.
        """
        if self._model is None:
            return "", "(LLM not loaded)"
        self.status = "running"
        t0 = time.perf_counter()
        try:
            content: List[Dict] = []

            # Audio must come before text per Gemma 4 best-practices
            content.append({"type": "audio", "audio": audio_float32})

            if image_b64:
                from PIL import Image  # type: ignore

                img = Image.open(io.BytesIO(base64.b64decode(image_b64)))
                content.append({"type": "image", "image": img})

            content.append({
                "type": "text",
                "text": (
                    "Listen to the audio. "
                    "First output a single line starting with 'You said: ' containing "
                    "the verbatim transcription. "
                    "Then on a new line respond helpfully and concisely as an AI assistant"
                    + (" that can also see the user's screen." if image_b64 else ".")
                ),
            })

            self._history.append({"role": "user", "content": content})

            messages = [
                {
                    "role": "system",
                    "content": [{"type": "text", "text": (
                        "You are a helpful, concise assistant that can hear the user "
                        "and optionally see their screen."
                    )}],
                },
                *self._history,
            ]

            thinking = enable_thinking if enable_thinking is not None else self.enable_thinking
            loop = asyncio.get_event_loop()

            def _infer():
                import torch  # type: ignore  # noqa: F811

                inputs = self._processor.apply_chat_template(
                    messages,
                    tokenize=True,
                    return_dict=True,
                    return_tensors="pt",
                    add_generation_prompt=True,
                    enable_thinking=thinking,
                ).to(self._model.device)
                input_len = inputs["input_ids"].shape[-1]
                with torch.no_grad():
                    outputs = self._model.generate(
                        **inputs,
                        max_new_tokens=self.max_new_tokens,
                        do_sample=True,
                        temperature=1.0,
                        top_p=0.95,
                        top_k=64,
                    )
                raw = self._processor.decode(
                    outputs[0][input_len:], skip_special_tokens=False
                )
                return _extract_final_response(raw)

            full_response: str = await loop.run_in_executor(None, _infer)

            # Parse transcript line from response
            transcript = ""
            reply_lines = []
            for line in full_response.splitlines():
                if line.lower().startswith("you said:"):
                    transcript = line[len("you said:"):].strip()
                else:
                    reply_lines.append(line)
            response = "\n".join(reply_lines).strip()

            # Store text-only in history
            self._history[-1] = {
                "role": "user",
                "content": [{"type": "text", "text": f"[audio] {transcript}"}],
            }
            self._history.append(
                {"role": "assistant", "content": [{"type": "text", "text": response}]}
            )
            max_msgs = MAX_HISTORY_TURNS * 2
            if len(self._history) > max_msgs:
                self._history = self._history[-max_msgs:]

            self._last_latency_ms = (time.perf_counter() - t0) * 1000
            logger.info(f"LLM(audio) {self._last_latency_ms:.0f}ms | transcript: {transcript}")
            return transcript, response

        except Exception as exc:
            self.error = str(exc)
            logger.error(f"LLM generate_with_audio error: {exc}")
            return "", f"Error: {exc}"
        finally:
            self.status = "idle"

    def clear_history(self) -> None:
        self._history = []
        logger.info("Conversation history cleared")

    def get_status(self) -> Dict[str, Any]:
        device = "unknown"
        if self._model is not None:
            try:
                p = next(self._model.parameters())
                device = str(p.device)
            except Exception:
                pass
        return {
            "name": "LLM (Gemma 4)",
            "status": self.status,
            "model": Path(self.model_path).resolve().name,
            "device": device,
            "error": self.error,
            "latency_ms": self._last_latency_ms,
        }
