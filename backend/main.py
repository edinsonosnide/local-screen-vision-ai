"""FastAPI backend — WebSocket hub for screen-vision AI assistant."""

import asyncio
import base64
import json
import logging
import time
from contextlib import asynccontextmanager
from typing import Optional

import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from config import config
from handlers.hardware import get_hardware_info
from handlers.llm import LLMHandler
from handlers.stt import STTHandler
from handlers.tts import TTSHandler
from handlers.vad import VADHandler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Load models and start background tasks on startup."""
    logger.info("Loading STT and TTS models…")
    await asyncio.gather(stt.load(), tts.load())
    asyncio.create_task(_load_llm_safe())    # LLM is large — load in background
    asyncio.create_task(_hardware_loop())
    asyncio.create_task(_status_loop())
    logger.info("Server ready — waiting for connections")
    yield
    # shutdown: nothing critical to clean up


app = FastAPI(title="Local Screen Vision AI", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Global model handlers
# ---------------------------------------------------------------------------

stt = STTHandler(
    model_name=config["stt"]["model"],
    language=config["stt"]["language"],
)
llm = LLMHandler(
    model_path=config["llm"]["model_path"],
    device=config["llm"]["device"],
    enable_thinking=config["llm"]["enable_thinking"],
    max_new_tokens=config["llm"]["max_new_tokens"],
    image_token_budget=config["llm"]["image_token_budget"],
)
tts = TTSHandler(
    voice=config["tts"]["voice"],
    speed=config["tts"]["speed"],
)


# ---------------------------------------------------------------------------
# Connection manager
# ---------------------------------------------------------------------------

class ConnectionManager:
    def __init__(self):
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self._connections.discard(ws) if hasattr(self._connections, "discard") else None
        if ws in self._connections:
            self._connections.remove(ws)

    async def send(self, ws: WebSocket, msg: dict) -> None:
        try:
            await ws.send_text(json.dumps(msg))
        except Exception:
            pass  # client disconnected mid-inference — silently drop

    async def broadcast(self, msg: dict) -> None:
        for ws in list(self._connections):
            await self.send(ws, msg)


manager = ConnectionManager()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def send_log(
    ws: WebSocket,
    level: str,
    message: str,
    latency_ms: Optional[float] = None,
) -> None:
    await manager.send(
        ws,
        {
            "type": "log",
            "data": {
                "level": level,
                "message": message,
                "timestamp": time.time(),
                "latency_ms": latency_ms,
            },
        },
    )


async def send_status(ws: WebSocket) -> None:
    await manager.send(
        ws,
        {
            "type": "model_status",
            "data": {
                "stt": stt.get_status(),
                "llm": llm.get_status(),
                "tts": tts.get_status(),
            },
        },
    )


async def send_pipeline(ws: WebSocket, state: str) -> None:
    await manager.send(ws, {"type": "pipeline_state", "data": state})


async def _thinking_keepalive(ws: WebSocket, interval: float = 8.0) -> None:
    """Send periodic 'thinking' heartbeats so the browser doesn't drop the socket."""
    try:
        while True:
            await asyncio.sleep(interval)
            await manager.send(ws, {"type": "pipeline_state", "data": "thinking"})
    except asyncio.CancelledError:
        pass


# ---------------------------------------------------------------------------
# Background tasks
# ---------------------------------------------------------------------------

async def _load_llm_safe() -> None:
    """Load the LLM in the background; log errors instead of crashing the server."""
    try:
        await llm.load()
    except Exception as exc:
        logger.error(f"LLM background load failed: {exc}", exc_info=True)


async def _hardware_loop() -> None:
    while True:
        try:
            hw = get_hardware_info()
            await manager.broadcast({"type": "hardware", "data": hw})
        except Exception as exc:
            logger.error(f"Hardware loop error: {exc}")
        await asyncio.sleep(2)


async def _status_loop() -> None:
    while True:
        try:
            await manager.broadcast(
                {
                    "type": "model_status",
                    "data": {
                        "stt": stt.get_status(),
                        "llm": llm.get_status(),
                        "tts": tts.get_status(),
                    },
                }
            )
        except Exception as exc:
            logger.error(f"Status loop error: {exc}")
        await asyncio.sleep(1)


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await manager.connect(websocket)
    vad = VADHandler(
        aggressiveness=config["vad"]["aggressiveness"],
        silence_duration=config["vad"]["silence_duration"],
    )
    vad.load()
    latest_frame: Optional[str] = None   # base64 JPEG
    audio_mode: str = "whisper"           # "whisper" | "direct"
    tts_enabled: bool = False             # off by default
    thinking_enabled: bool = False        # off by default
    llm_busy: bool = False                # drop audio chunks while LLM is running

    # ── Dedicated reader task ────────────────────────────────────────────────
    # Always keeps an active receive_text() call so WebSocket protocol-level
    # frames are handled immediately and the TCP receive buffer never fills up
    # while the LLM is running in a thread pool.
    msg_queue: asyncio.Queue = asyncio.Queue()

    async def _reader() -> None:
        try:
            while True:
                raw = await websocket.receive_text()
                await msg_queue.put(json.loads(raw))
        except (WebSocketDisconnect, RuntimeError):
            pass
        except Exception as exc:
            logger.debug(f"WS reader: {exc}")
        finally:
            await msg_queue.put(None)   # sentinel → stop processor loop

    reader_task = asyncio.create_task(_reader())
    # ────────────────────────────────────────────────────────────────────────

    await send_log(websocket, "info", "Client connected")
    await send_status(websocket)

    try:
        while True:
            msg = await msg_queue.get()
            if msg is None:
                break   # reader finished → client disconnected

            msg_type: str = msg.get("type", "")

            # ---------------------------------------------------------------
            # Audio chunk from microphone
            # ---------------------------------------------------------------
            if msg_type == "audio_chunk":
                # Drop audio silently while the LLM is still generating —
                # prevents a burst of queued-up speech from triggering a
                # second inference the moment the first one finishes.
                if llm_busy:
                    continue

                audio_bytes = base64.b64decode(msg["data"])
                audio_int16 = np.frombuffer(audio_bytes, dtype=np.int16)
                speech = vad.process_chunk(audio_int16)

                if speech is not None and len(speech) > 3200:  # >200ms
                    audio_f32 = speech.astype(np.float32) / 32768.0
                    dur = len(speech) / 16000
                    llm_busy = True

                    try:
                        if audio_mode == "direct":
                            # ── Direct: audio straight to Gemma 4 ──────────
                            await send_pipeline(websocket, "thinking")
                            await send_log(websocket, "info", f"Speech ({dur:.1f}s) → Gemma 4 directly…")
                            t0 = time.perf_counter()
                            _ka = asyncio.create_task(_thinking_keepalive(websocket))
                            try:
                                transcript, response = await llm.generate_with_audio(
                                    audio_f32, 16000, latest_frame,
                                    enable_thinking=thinking_enabled,
                                )
                            finally:
                                _ka.cancel()
                            llm_ms = (time.perf_counter() - t0) * 1000

                            if transcript:
                                await manager.send(
                                    websocket,
                                    {"type": "transcript", "data": {"text": transcript, "is_final": True}},
                                )
                            if not response.strip():
                                continue

                        else:
                            # ── Whisper: STT → LLM ─────────────────────────
                            await send_pipeline(websocket, "transcribing")
                            await send_log(websocket, "info", f"Speech ({dur:.1f}s), transcribing…")
                            t0 = time.perf_counter()
                            transcript = await stt.transcribe(audio_f32)
                            stt_ms = (time.perf_counter() - t0) * 1000

                            if not transcript.strip():
                                continue

                            await manager.send(
                                websocket,
                                {"type": "transcript", "data": {"text": transcript, "is_final": True}},
                            )
                            await send_log(websocket, "info", f"Transcript: {transcript}", stt_ms)

                            await send_pipeline(websocket, "thinking")
                            t1 = time.perf_counter()
                            _ka = asyncio.create_task(_thinking_keepalive(websocket))
                            try:
                                response = await llm.generate(
                                    transcript, latest_frame,
                                    enable_thinking=thinking_enabled,
                                )
                            finally:
                                _ka.cancel()
                            llm_ms = (time.perf_counter() - t1) * 1000

                        await manager.send(
                            websocket,
                            {"type": "llm_response", "data": {"text": response}},
                        )
                        await send_log(websocket, "info", f"LLM: {response[:100]}", llm_ms)

                        if tts_enabled:
                            await send_pipeline(websocket, "speaking")
                            t2 = time.perf_counter()
                            wav = await tts.synthesize(response)
                            tts_ms = (time.perf_counter() - t2) * 1000
                            if wav:
                                await manager.send(
                                    websocket,
                                    {"type": "tts_audio", "data": base64.b64encode(wav).decode()},
                                )
                                await send_log(websocket, "info", "TTS audio sent", tts_ms)

                    finally:
                        llm_busy = False
                        await send_pipeline(websocket, "idle")

            # ---------------------------------------------------------------
            # Screen frame from display capture
            # ---------------------------------------------------------------
            elif msg_type == "screen_frame":
                latest_frame = msg.get("data")

            # ---------------------------------------------------------------
            # Config update
            # ---------------------------------------------------------------
            elif msg_type == "config_update":
                data = msg.get("data", {})
                if "frame_interval" in data:
                    config["vision"]["frame_interval"] = float(data["frame_interval"])
                if "vad_silence" in data:
                    vad._silence_threshold = int(
                        float(data["vad_silence"]) * 1000 / 30
                    )
                if "audio_mode" in data:
                    audio_mode = str(data["audio_mode"])
                    await send_log(websocket, "info", f"Audio mode → {audio_mode}")
                if "tts_enabled" in data:
                    tts_enabled = bool(data["tts_enabled"])
                    await send_log(websocket, "info", f"TTS → {'enabled' if tts_enabled else 'disabled'}")
                if "thinking_enabled" in data:
                    thinking_enabled = bool(data["thinking_enabled"])
                    await send_log(websocket, "info", f"Thinking → {'enabled' if thinking_enabled else 'disabled'}")
                if not any(k in data for k in ("audio_mode", "tts_enabled", "thinking_enabled")):
                    await send_log(websocket, "info", "Configuration updated")

            # ---------------------------------------------------------------
            # Clear conversation history
            # ---------------------------------------------------------------
            elif msg_type == "clear_history":
                llm.clear_history()
                await send_log(websocket, "info", "Conversation history cleared")

            # ---------------------------------------------------------------
            # Ping / keepalive
            # ---------------------------------------------------------------
            elif msg_type == "ping":
                await manager.send(websocket, {"type": "pong"})

    except Exception as exc:
        logger.error(f"WebSocket processor error: {exc}", exc_info=True)
    finally:
        reader_task.cancel()
        manager.disconnect(websocket)
        logger.info("Client disconnected")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=config["server"]["host"],
        port=config["server"]["port"],
        log_level="info",
    )
