# Local Multimodal AI Assistant

## Overview

This project is a fully local, privacy-first multimodal assistant that combines:

- Speech-to-Text (STT)
- Local Large Language Models (LLM)
- Vision understanding
- Text-to-Speech (TTS)

All components run entirely offline, with zero external API calls.

---

## Features

- Microphone input → local transcription
- Screen sharing → optional vision analysis
- Local LLM reasoning
- Voice response via TTS
- Real-time metrics:
  - Token usage
  - Latency per stage
  - Active models
- Modular architecture for swapping models

---

## Architecture

Frontend (React + TypeScript)
        │
        ▼
Backend (FastAPI / Node)
        │
        ▼
Local Models (/resources)
   ├── STT
   ├── TTS
   ├── Vision
   └── LLM

---

## Project Structure

/frontend        → React app
/backend         → API + inference logic
/resources       → All local models
/config          → Model configuration

---

## Resources Folder

/resources
  /stt
  /tts
  /vision
  /llm

You can swap models by replacing folders here.

---

## Configuration

Edit:

/config/models.json

Example:

{
  "stt": "whisper-small",
  "tts": "coqui-tts",
  "vision": "gemma-vision",
  "llm": "llama-3"
}

---

## Pipeline

1. User grants microphone + screen access
2. Audio → STT → text
3. Screen → Vision model (optional)
4. Text + context → LLM
5. LLM → TTS
6. Audio response returned

---

## Requirements

Minimum:
- 16 GB RAM

Recommended:
- 32 GB RAM
- GPU (optional)

---

## Running the Project

Frontend:
cd frontend
npm install
npm run dev

Backend:
cd backend
pip install -r requirements.txt
uvicorn main:app --reload

---

## No Internet Policy

- No API calls
- No telemetry
- No cloud services

All processing happens locally.

---

## License

MIT
