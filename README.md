# Local Screen Vision AI

A fully local, privacy-first multimodal assistant that can:
- Listen to your microphone in real time (Voice Activity Detection + Whisper STT)
- Watch your screen continuously (configurable frame capture)
- Understand and respond using **Gemma 4 E2B-it** via LiteRT-LM (default, optimized) or HF Transformers (GPU fallback)
- **Stream responses word-by-word** as they are generated
- Speak responses via local TTS (Kokoro / Windows SAPI fallback), streamed sentence-by-sentence

All processing runs **100% locally** — no data leaves your machine after setup.

---

## Current State

| Component | Status | Notes |
|-----------|--------|-------|
| STT (Whisper) | ✅ Working | `faster-whisper` base model |
| LLM (Gemma 4 via LiteRT-LM) | ✅ Default | Int4 quantized, XNNPACK CPU accel. ~2.58 GB, auto-downloaded |
| LLM (Gemma 4 via Transformers) | ✅ Fallback | bfloat16 on GPU. Set `llm.backend: transformers` in config |
| LLM streaming | ✅ Working | Token-by-token via LiteRT-LM `send_message_async` or HF `TextIteratorStreamer` |
| Screen vision | ✅ Working | Model correctly reads and describes screen |
| TTS (streaming) | ✅ Working | Sentence-by-sentence during LLM streaming, queued playback |
| Thinking mode | ✅ Working | Chain-of-thought hidden; only final answer streamed |
| Direct Audio | ⚠️ Beta | Full recording (up to 30 s) sent to Gemma 4 natively |
| WebSocket stability | ✅ Stable | Two-task reader pattern + cooldown prevents disconnects |
| GPU acceleration | ⚠️ Partial | Transformers: CUDA bfloat16. LiteRT-LM: XNNPACK CPU only (GPU/Vulkan falls back to software rendering in WSL) |

### Observed Latency (RTX 2070 SUPER 8 GB, Whisper base, Thinking off)

| Step | Audio + Screen ON | Audio ON, Screen OFF |
|------|-------------------|----------------------|
| **STT (Whisper)** | ~4 ms | ~25 ms |
| **LLM (Gemma 4)** | ~53 s | ~5 s |
| **TTS (SAPI)** | ~52 ms | ~123 ms |

> Screen sharing dramatically increases LLM inference time because the model processes the captured image alongside the text prompt. With `image_token_budget` set to 70 (the current default), expect ~53 s per response with screen on vs ~5 s with screen off on an RTX 2070 SUPER.

---

## Architecture

```
Browser (React + TypeScript + Vite)
    │  WebSocket  ws://localhost:8000/ws
    │
    │  ← llm_response_start         (clear display, start streaming)
    │  ← llm_chunk                   (append text delta)
    │  ← tts_audio                   (sentence audio, queued playback)
    │  ← pipeline_state              (idle / transcribing / thinking / streaming / speaking)
    │
    ▼
FastAPI backend (Python)
    ├── VAD    — webrtcvad-wheels (WebRTC Voice Activity Detection)
    ├── STT    — faster-whisper (Whisper base)
    ├── LLM    — configurable backend (llm.backend in config.yaml):
    │            ├── "litert"       → Gemma 4 E2B-it via LiteRT-LM (int4, XNNPACK)
    │            │                    2.58 GB, auto-downloaded from HuggingFace on first run
    │            └── "transformers" → Gemma 4 E2B-it via HF Transformers (bfloat16, GPU)
    │            Both expose: generate_stream(), generate_with_audio(), clear_history()
    └── TTS    — kokoro-onnx (auto-download) / Windows SAPI fallback
```

### Audio pipelines

| Mode | Flow | Streaming | TTS |
|------|------|-----------|-----|
| **Whisper STT** (default) | Mic → VAD → STT → text → `generate_stream()` | ✅ Token-by-token | ✅ Sentence-by-sentence |
| **Direct Audio** (beta) | Mic → accumulate up to 30 s → `generate_with_audio()` | ❌ Full response | One-shot after response |

---

## Requirements

- Python 3.10+
- Node.js 18+
- 16 GB RAM minimum

**LiteRT-LM backend (default):** No GPU required. Runs on CPU with XNNPACK acceleration. Model (~2.58 GB) is auto-downloaded from HuggingFace on first run.

**Transformers backend (fallback):** NVIDIA GPU with 6+ GB VRAM (tested on RTX 2070 SUPER 8 GB) + CUDA 12.x driver.

---

## Setup

### 1. Accept Gemma license on HuggingFace

Visit https://huggingface.co/litert-community/gemma-4-E2B-it-litert-lm and accept the Gemma license. Then log in:

```bash
pip install huggingface-hub
huggingface-cli login
```

> The LiteRT-LM model (~2.58 GB) is **auto-downloaded** on first backend start. No manual download needed.

### 2. Backend — Python environment

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 3. (Optional) Transformers backend — CUDA PyTorch + Gemma 4

Only needed if you set `llm.backend: transformers` in `config.yaml`:

```powershell
# Download Gemma 4 E2B-it model files
huggingface-cli download google/gemma-4-E2B-it --local-dir ./resources/multimodal/gemma-4-E2B-it

# Install CUDA-enabled PyTorch (CPU-only ships by default)
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
5. Response **streams word-by-word** in the ASSISTANT panel with a blinking cursor
6. If TTS is enabled, audio plays sentence-by-sentence as text streams — you hear the answer while it's still being generated

> **Tip**: With screen sharing **off**, inference takes ~5 s on an RTX 2070 SUPER. With screen sharing **on**, expect ~53 s because the model also processes the captured frame. The UI shows a "Generating…" badge and blinking cursor during output.

---

## UI Controls

### Config bar (bottom)

| Control | Default | Description |
|---------|---------|-------------|
| **Whisper STT / Direct Audio** | Whisper STT | Whisper: fast transcription + streaming LLM. Direct Audio (beta): records up to 30 s and sends to Gemma 4 natively — experimental, may echo or repeat |
| **Thinking off / on** | Off | Enables Gemma 4's chain-of-thought reasoning. Thinking tokens are hidden; only the final answer is streamed. Better quality but slower |
| **TTS off / on** | **Off** | Streams audio sentence-by-sentence as text generates. Use headphones to avoid mic echo triggering repeated answers |
| **Frame interval** | 1.5s | How often a screenshot is sent. Lower = better screen awareness, more GPU load |
| **VAD silence** | 0.8s | Whisper mode: silence needed to end speech. Too low = cuts you off. Too high = long wait. Direct Audio uses a fixed 2 s threshold |
| **Clear history** | — | Resets the LLM conversation context |

### Indicators

- **Pipeline badge**: Idle → Transcribing → Thinking → Generating → Speaking
- **TTS indicator**: Lights up orange when audio is actively playing (tracked client-side via audio queue events, independent of backend state)
- **GPU/CPU badge**: Confirms whether the LLM is running on your GPU

---

## Configuration (`backend/config.yaml`)

| Key | Default | Description |
|-----|---------|-------------|
| `stt.model` | `base` | Whisper model size (`tiny`, `base`, `small`, `medium`, `large-v3`) |
| `stt.language` | `en` | Transcription language |
| **`llm.backend`** | **`litert`** | **`litert` (LiteRT-LM, optimized) or `transformers` (HF, GPU)** |
| `llm.litert_model_repo` | `litert-community/gemma-4-E2B-it-litert-lm` | HuggingFace repo for LiteRT-LM model (auto-downloaded) |
| `llm.litert_model_file` | `gemma-4-E2B-it.litertlm` | Model filename within the repo |
| `llm.model_path` | `../resources/multimodal/gemma-4-E2B-it` | Path for Transformers backend (relative to `backend/`) |
| `llm.device` | `auto` | Transformers backend: `auto`, `cuda`, or `cpu` |
| `llm.enable_thinking` | `false` | Default thinking mode (overridden per-session via UI) |
| `llm.max_new_tokens` | `512` | Max tokens to generate |
| `llm.image_token_budget` | `70` | Transformers backend: vision resolution (70/140/280/560/1120 tokens) |
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
│       ├── llm_litert.py    # Gemma 4 via LiteRT-LM (int4 XNNPACK, default)
│       ├── llm.py           # Gemma 4 via HF Transformers (bfloat16 GPU, fallback)
│       ├── tts.py           # kokoro-onnx (auto-download) + Windows SAPI fallback
│       ├── hardware.py      # CPU / RAM / GPU monitoring (nvidia-ml-py)
│       └── vad.py           # WebRTC VAD + energy fallback + stateless has_speech()
├── frontend/
│   ├── src/
│   │   ├── App.tsx          # Main component, TTS queue, WebSocket orchestration
│   │   ├── hooks/
│   │   │   ├── useWebSocket.ts     # Auto-reconnect, stable callback refs
│   │   │   ├── useMicrophone.ts    # AudioWorklet 16kHz capture
│   │   │   └── useScreenCapture.ts # getDisplayMedia + interval JPEG capture
│   │   ├── components/
│   │   │   ├── ModelStatusPanel.tsx  # Per-model status + CPU/GPU badge
│   │   │   ├── HardwarePanel.tsx     # CPU/RAM/VRAM meters
│   │   │   ├── RealTimeIndicators.tsx # Pipeline + TTS playback indicators
│   │   │   ├── SystemDisplay.tsx     # Transcript + streaming LLM response + pipeline viz
│   │   │   ├── DebugLog.tsx          # Filterable timestamped logs
│   │   │   └── ConfigPanel.tsx       # Toggles, sliders, hints, Direct Audio warning
│   │   └── types/index.ts
│   └── public/
│       └── audio-processor.js   # AudioWorklet: mic → 16kHz PCM16
├── resources/
│   └── multimodal/              # Place gemma-4-E2B-it here
├── start-backend.ps1            # PowerShell launcher (activates venv)
├── start-backend.bat            # CMD launcher
└── start-backend-wsl.bat        # WSL launcher (LiteRT-LM via Ubuntu venv)
```

---

## Lessons Learned

### LiteRT-LM backend

- [LiteRT-LM](https://ai.google.dev/edge/litert-lm) is Google's open-source inference framework for edge devices. It runs quantized models (int4) with XNNPACK CPU acceleration — no GPU or CUDA needed.
- The Python API (`litert-lm-api-nightly`) uses `Engine` and `Conversation` context managers. The `Engine` loads the `.litertlm` model file; each `Conversation` manages chat state internally.
- Multimodal inputs (images, audio) are passed as **file paths**, not raw arrays. The handler writes temp files before inference and cleans them up afterward.
- Streaming uses `conversation.send_message_async()` which returns a synchronous chunk iterator. We run it in a thread executor and bridge to asyncio via `Queue` + `call_soon_threadsafe`, identical to the Transformers streaming pattern.
- The model (`gemma-4-E2B-it.litertlm`, ~2.58 GB) is auto-downloaded from HuggingFace via `hf_hub_download()` on first run and cached locally.
- Vision support depends on the backend and model. The CPU backend for `gemma-4-E2B-it.litertlm` does **not** include a vision encoder (`TF_LITE_VISION_ENCODER not found`). The handler probes for vision during load and silently skips image inputs if unsupported, preventing crashes.

### WSL (Windows Subsystem for Linux)

- `litert-lm-api-nightly` only publishes **Linux** wheels — no Windows binaries. Running the backend inside WSL2 (Ubuntu) is the simplest workaround. A `start-backend-wsl.bat` launcher invokes the WSL Python venv from Windows.
- `webrtcvad` depends on `pkg_resources`, which was removed in `setuptools` ≥ 81. Fix: `pip install 'setuptools<81'` inside the WSL venv to restore compatibility.
- `pywin32` (Windows SAPI TTS fallback) is unavailable in Linux/WSL. `kokoro-onnx` is the TTS backend when running in WSL.

### GPU acceleration in WSL

- WSL2 exposes the host NVIDIA GPU for **CUDA** workloads — `nvidia-smi` works and reports the card correctly.
- However, LiteRT-LM's GPU backend uses **WebGPU/Vulkan**, not CUDA. In WSL2, Vulkan falls back to **llvmpipe** (a software renderer), making the "GPU" path ~21× slower than native CPU (24.9 s vs 1.16 s for a single response on an RTX 2070 SUPER).
- Until LiteRT-LM adds a CUDA backend, or WSL gets proper Vulkan GPU passthrough, the **CPU backend with XNNPACK** remains the fastest option.
- Benchmarked (RTX 2070 SUPER, WSL2 Ubuntu, Gemma 4 E2B-it):

| Backend | Engine load | Response time |
|---------|-------------|---------------|
| CPU (XNNPACK) | 0.3 s | **1.16 s** |
| "GPU" (llvmpipe software Vulkan) | 2.1 s | **24.9 s** |

### GPU / PyTorch

- `pip install torch` installs **CPU-only** by default. CUDA torch must be installed separately with the correct `--index-url` for your driver version.
- `device_map="auto"` with quantized models places some layers on `meta` device, causing `Tensor on device meta is not on the expected device cuda:0` during inference. The fix: load the model normally (bfloat16, no device_map), then call `.to("cuda")` — guaranteed zero meta tensors.
- Gemma 4 E2B-it (~2B parameters) in bfloat16 is ~4 GB — fits comfortably in 8 GB VRAM. No quantization needed on a typical gaming GPU.
- `bitsandbytes` 0.49.2 is incompatible with `transformers` 5.x (`Params4bit.__new__() got an unexpected keyword argument '_is_hf_initialized'`). Skip quantization unless you specifically need it for VRAM constraints.

### LLM Streaming

- `TextIteratorStreamer` from `transformers` provides token-by-token output. It must run in a separate thread (`threading.Thread`) since `model.generate()` is blocking.
- An executor thread reads from the streamer iterator and pushes tokens into an `asyncio.Queue` via `loop.call_soon_threadsafe`, bridging the sync/async boundary.
- When Gemma 4's thinking mode is on, tokens are silently buffered until the `<channel|>` response marker appears. Everything before it (the thinking block) is never shown to the user or spoken by TTS.
- The frontend receives `llm_response_start` (clear + switch to "streaming" state) followed by `llm_chunk` deltas, showing a blinking cursor until generation completes.

### Streaming TTS

- TTS synthesis runs concurrently with LLM streaming — each sentence boundary (`.!?\n` or 200+ chars) triggers an `asyncio.create_task` for synthesis.
- The frontend maintains a sequential audio queue (`ttsQueueRef`). Each segment plays to completion before the next starts, preventing overlap.
- Chrome's autoplay policy suspends `AudioContext` until a user gesture. The fix: call `ctx.resume()` before playing if the context is suspended.
- The `ttsPlaying` state is tracked independently from the backend's pipeline state (via `BufferSource.ended` events), so the TTS indicator correctly shows active playback even after the backend goes idle.

### WebSocket stability

- A single-loop WebSocket handler that calls `await receive_text()` once per iteration will **block** while `await llm.generate()` runs. Audio chunks pile up in the TCP buffer; when it fills, the OS applies backpressure, timeouts fire, and the connection drops.
- Fix: **two-task pattern** — a dedicated `_reader` coroutine always has an active `receive_text()` call, continuously draining the socket. The processor reads from an asyncio Queue. This prevents buffer fill regardless of inference time.
- Drop audio chunks with an `llm_busy` flag while the model is generating. Without this, all buffered audio is processed immediately after inference ends, potentially triggering a second LLM call from speech the user uttered while waiting.
- A 2-second cooldown after each inference prevents TTS echo from the speakers being picked up by the microphone and triggering a feedback loop.
- Add a server-side keepalive (send `pipeline_state: thinking` every 8s during inference) as a secondary mechanism to prevent browser-side idle timeouts.

### Direct Audio mode

- Gemma 4's audio encoder accepts up to **30 seconds** at 16 kHz (25 tokens/second). There is no streaming audio API — the model processes audio as a complete batch.
- The old approach reused VAD's short-silence detection (0.8s), sending tiny 1-3s fragments. This caused repeated LLM calls with the same question due to sentence fragments and echo.
- Fix: Direct Audio now **accumulates all audio** (speech + natural pauses) into one continuous buffer. It only sends when: (a) 2 seconds of silence follow detected speech, or (b) the buffer reaches 30 seconds.
- A stateless `vad.has_speech()` method checks each chunk for voice activity without modifying the VAD's internal state or buffers.
- Mode switching resets both the VAD and the direct audio buffer to prevent stale audio from carrying over.

### HuggingFace model loading on Windows

- Passing a Windows absolute path string like `C:\Users\...\gemma-4-E2B-it` to `from_pretrained()` fails because `transformers` validates it as a HuggingFace repo ID (rejects backslashes, colons, etc.).
- Fix: pass a `pathlib.Path` object. HuggingFace's `from_pretrained` detects `Path` instances and bypasses the repo-ID validator.
- Always use `local_files_only=True` with a local model to avoid unnecessary network calls.

### TTS

- `pyttsx3` is not safe for repeated use in a thread pool — internal COM state corrupts between calls. Replaced with direct Windows SAPI via `pywin32`.
- Windows SAPI COM objects require `pythoncom.CoInitialize()` on every thread before use, and `CoUninitialize()` when done.
- Kokoro ONNX (`kokoro-onnx`) provides high-quality neural TTS but the model files must be present. Auto-download from HuggingFace Hub on first run.

### Thinking mode

- Gemma 4's thinking output uses channel markers: `<|channel>thought...thinking...<channel|>actual response`. The `<channel|>` token is the boundary between internal reasoning and the final answer.
- During streaming, all tokens before `<channel|>` are silently absorbed. After the marker, tokens are streamed normally to the frontend.
- A regex-based cleanup (`_CHANNEL_RE`) strips all channel marker variants from both streaming chunks and batch responses, ensuring no raw tokens leak to the UI.

### Screen vision

- `latest_frame` is `None` until the first capture fires. If the user speaks before any frame is captured (e.g., with a 10s interval), the model receives no image and responds as a text-only AI.
- Fix: capture the first frame 300ms after screen sharing starts, independent of the regular interval. Also cap the interval slider at 5s.
- `image_token_budget` controls vision resolution (70/140/280/560/1120 tokens). Lower values (70) trade detail for speed — useful on limited VRAM or when screen content is simple.

### VAD / STT

- `webrtcvad` requires Microsoft Visual C++ Build Tools to compile on Windows. Use `webrtcvad-wheels` instead — pre-compiled binaries, same API.
- Faster-whisper's VAD filter aggressively strips silence. Very short clips (< 200ms of actual speech) produce empty transcripts. The minimum speech gate (`len(speech) > 3200` samples = 200ms at 16kHz) prevents empty LLM calls.

---

## Privacy

- Zero telemetry
- No external API calls during operation (only initial model downloads)
- All audio, video, and inference stay on your machine
- Microphone and screen access require explicit browser permission each session
