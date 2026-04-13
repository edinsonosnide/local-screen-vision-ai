# Local Screen Vision AI

A fully local, privacy-first multimodal assistant that can:
- Listen to your microphone in real time (Voice Activity Detection + Whisper STT)
- Watch your screen continuously (configurable frame capture)
- Understand and respond using **Gemma 4 E2B-it** on your GPU
- Speak responses via local TTS (Kokoro / Windows SAPI fallback)

All processing runs **100% locally** — no data leaves your machine after setup.

---

## Current State

| Component | Status | Notes |
|-----------|--------|-------|
| STT (Whisper) | ✅ Working | `faster-whisper` base model, ~5-20ms |
| LLM (Gemma 4 E2B-it) | ✅ Working on GPU | bfloat16, ~25-45s on RTX 2070 SUPER |
| Screen vision | ✅ Working | Model correctly reads and describes screen |
| TTS (SAPI) | ✅ Working | Disabled by default — enable via UI toggle |
| WebSocket stability | ✅ Stable | Two-task reader pattern prevents buffer timeouts |
| GPU acceleration | ✅ Working | Auto-detects CUDA, loads model in bfloat16 |

---

## Architecture

```
Browser (React + TypeScript + Vite)
    │  WebSocket  ws://localhost:8000/ws
    ▼
FastAPI backend (Python)
    ├── VAD    — webrtcvad-wheels (WebRTC Voice Activity Detection)
    ├── STT    — faster-whisper (Whisper base)
    ├── LLM    — Gemma 4 E2B-it (HuggingFace transformers, GPU bfloat16)
    └── TTS    — kokoro-onnx (auto-download) / Windows SAPI fallback
```

---

## Requirements

- Python 3.10+
- Node.js 18+
- 16 GB RAM minimum (model loads to GPU, but CPU RAM is needed during load)
- **NVIDIA GPU with 6+ GB VRAM** (tested on RTX 2070 SUPER 8 GB)
- CUDA 12.x driver

> CPU-only fallback works but expect 3–5 minute response times.

---

## Setup

### 1. Download Gemma 4 E2B-it

```bash
pip install huggingface-hub
huggingface-cli download google/gemma-4-E2B-it \
  --local-dir ./resources/multimodal/gemma-4-E2B-it
```

> Accept the model license at https://huggingface.co/google/gemma-4-E2B-it first.

### 2. Backend — Python environment

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Install CUDA-enabled PyTorch (required for GPU)

The default `pip install torch` installs a CPU-only build. You **must** run this separately:

```powershell
# For CUDA 12.1 (adjust cu121 → cu118 / cu124 for your driver)
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
```

Verify GPU is visible:
```powershell
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

### 4. Frontend

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

### 5. Start the backend

```powershell
# From project root — activates venv automatically:
.\start-backend.ps1    # PowerShell
start-backend.bat      # CMD
```

Or manually:
```powershell
cd backend
.venv\Scripts\activate
python main.py
```

Backend runs at `http://localhost:8000`.

---

## Usage

1. Wait for **LLM (Gemma 4)** to show `idle` in the Models panel (loads in ~15s on GPU)
2. Click **Share Screen** — a frame is captured within 300ms
3. Click **Start Mic** and speak naturally
4. The system detects when you stop talking, sends your speech + screen frame to the model
5. Response appears as text in the **ASSISTANT** panel

> **Tip**: First inference takes ~25-45s on an RTX 2070 SUPER. Subsequent calls are similar — Gemma 4 E2B is a full multimodal model. The UI sends keepalive pings during inference to prevent disconnects.

---

## UI Controls

### Config bar (bottom)

| Control | Default | Description |
|---------|---------|-------------|
| **Whisper STT / Direct Audio** | Whisper STT | Whisper STT: audio → Whisper → text → Gemma 4. Direct Audio: audio straight to Gemma 4 (experimental) |
| **Thinking off / on** | Off | Enables Gemma 4's chain-of-thought reasoning (slower but more accurate) |
| **TTS off / on** | **Off** | Synthesizes and plays the response via Kokoro / Windows SAPI. Off by default for stability |
| **Frame interval** | 1.5s | How often the screen is captured and sent |
| **VAD silence** | 1.2s | Silence duration before ending a speech segment |
| **Clear history** | — | Resets the LLM conversation context |

### Model Status panel

Each model card shows:
- Status dot (green = idle, blue = running, yellow = loading, red = error)
- **CPU / GPU badge** — confirms whether the LLM is on your GPU
- Last inference latency in ms

---

## Configuration (`backend/config.yaml`)

| Key | Default | Description |
|-----|---------|-------------|
| `stt.model` | `base` | Whisper model size (`tiny`, `base`, `small`, `medium`, `large-v3`) |
| `stt.language` | `en` | Transcription language |
| `llm.model_path` | `../resources/multimodal/gemma-4-E2B-it` | Path relative to `backend/` |
| `llm.device` | `auto` | `auto`, `cuda`, or `cpu` |
| `llm.enable_thinking` | `false` | Default thinking mode (overridden per-session via UI) |
| `llm.max_new_tokens` | `512` | Max tokens to generate |
| `llm.image_token_budget` | `280` | Vision resolution (70/140/280/560/1120) |
| `tts.voice` | `af_heart` | Kokoro voice name |
| `tts.speed` | `1.0` | Speech speed multiplier |
| `vision.frame_interval` | `1.5` | Seconds between screen captures |
| `vad.aggressiveness` | `2` | WebRTC VAD aggressiveness (0–3) |
| `vad.silence_duration` | `0.8` | Seconds of silence to trigger end-of-speech |

---

## Project Structure

```
local-screen-vision-ai/
├── backend/
│   ├── main.py              # FastAPI app + WebSocket hub (two-task reader pattern)
│   ├── config.py            # Config loader with defaults
│   ├── config.yaml          # User-editable settings
│   ├── requirements.txt
│   └── handlers/
│       ├── stt.py           # faster-whisper STT
│       ├── llm.py           # Gemma 4 E2B-it (bfloat16 GPU / CPU fallback)
│       ├── tts.py           # kokoro-onnx (auto-download) + Windows SAPI fallback
│       ├── hardware.py      # CPU / RAM / GPU monitoring (nvidia-ml-py)
│       └── vad.py           # WebRTC VAD + energy fallback
├── frontend/
│   ├── src/
│   │   ├── App.tsx          # Main component, config state, WebSocket orchestration
│   │   ├── hooks/
│   │   │   ├── useWebSocket.ts     # Auto-reconnect, stable callback refs
│   │   │   ├── useMicrophone.ts    # AudioWorklet 16kHz capture
│   │   │   └── useScreenCapture.ts # getDisplayMedia + interval JPEG capture
│   │   ├── components/
│   │   │   ├── ModelStatusPanel.tsx  # Per-model status + CPU/GPU badge
│   │   │   ├── HardwarePanel.tsx     # CPU/RAM/VRAM meters
│   │   │   ├── RealTimeIndicators.tsx
│   │   │   ├── SystemDisplay.tsx     # Transcript + LLM response + pipeline
│   │   │   ├── DebugLog.tsx          # Filterable timestamped logs
│   │   │   └── ConfigPanel.tsx       # All runtime toggles and sliders
│   │   └── types/index.ts
│   └── public/
│       └── audio-processor.js   # AudioWorklet: mic → 16kHz PCM16
├── resources/
│   └── multimodal/              # Place gemma-4-E2B-it here
├── start-backend.ps1            # PowerShell launcher (activates venv)
└── start-backend.bat            # CMD launcher
```

---

## Lessons Learned

### GPU / PyTorch

- `pip install torch` installs **CPU-only** by default. CUDA torch must be installed separately with the correct `--index-url` for your driver version.
- `device_map="auto"` with quantized models places some layers on `meta` device, causing `Tensor on device meta is not on the expected device cuda:0` during inference. The fix: load the model normally (bfloat16, no device_map), then call `.to("cuda")` — guaranteed zero meta tensors.
- Gemma 4 E2B-it (~2B parameters) in bfloat16 is ~4 GB — fits comfortably in 8 GB VRAM. No quantization needed on a typical gaming GPU.
- `bitsandbytes` 0.49.2 is incompatible with `transformers` 5.x (`Params4bit.__new__() got an unexpected keyword argument '_is_hf_initialized'`). Skip quantization unless you specifically need it for VRAM constraints.

### WebSocket stability

- A single-loop WebSocket handler that calls `await receive_text()` once per iteration will **block** while `await llm.generate()` runs. Audio chunks pile up in the TCP buffer; when it fills, the OS applies backpressure, timeouts fire, and the connection drops.
- Fix: **two-task pattern** — a dedicated `_reader` coroutine always has an active `receive_text()` call, continuously draining the socket. The processor reads from an asyncio Queue. This prevents buffer fill regardless of inference time.
- Drop audio chunks with an `llm_busy` flag while the model is generating. Without this, all buffered audio is processed immediately after inference ends, potentially triggering a second LLM call from speech the user uttered while waiting.
- Add a server-side keepalive (send `pipeline_state: thinking` every 8s during inference) as a secondary mechanism to prevent browser-side idle timeouts.

### HuggingFace model loading on Windows

- Passing a Windows absolute path string like `C:\Users\...\gemma-4-E2B-it` to `from_pretrained()` fails because `transformers` validates it as a HuggingFace repo ID (rejects backslashes, colons, etc.).
- Fix: pass a `pathlib.Path` object. HuggingFace's `from_pretrained` detects `Path` instances and bypasses the repo-ID validator.
- Always use `local_files_only=True` with a local model to avoid unnecessary network calls.

### TTS

- `pyttsx3` is not safe for repeated use in a thread pool — internal COM state corrupts between calls. Replaced with direct Windows SAPI via `pywin32`.
- Windows SAPI COM objects require `pythoncom.CoInitialize()` on every thread before use, and `CoUninitialize()` when done.
- Kokoro ONNX (`kokoro-onnx`) provides high-quality neural TTS but the model files must be present. Auto-download from HuggingFace Hub on first run.

### Screen vision

- `latest_frame` is `None` until the first capture fires. If the user speaks before any frame is captured (e.g., with a 10s interval), the model receives no image and responds as a text-only AI.
- Fix: capture the first frame 300ms after screen sharing starts, independent of the regular interval. Also cap the interval slider at 5s.

### VAD / STT

- `webrtcvad` requires Microsoft Visual C++ Build Tools to compile on Windows. Use `webrtcvad-wheels` instead — pre-compiled binaries, same API.
- Faster-whisper's VAD filter aggressively strips silence. Very short clips (< 200ms of actual speech) produce empty transcripts. The minimum speech gate (`len(speech) > 3200` samples = 200ms at 16kHz) prevents empty LLM calls.

---

## Privacy

- Zero telemetry
- No external API calls during operation (only initial model downloads)
- All audio, video, and inference stay on your machine
- Microphone and screen access require explicit browser permission each session
