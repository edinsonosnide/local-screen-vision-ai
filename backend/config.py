import os
from typing import Any, Dict

import yaml

DEFAULT_CONFIG: Dict[str, Any] = {
    "server": {"host": "0.0.0.0", "port": 8000},
    "stt": {"model": "base", "language": "en"},
    "llm": {
        "model_path": "./resources/multimodal/gemma-4-E4B-it",
        "device": "auto",
        "enable_thinking": False,
        "max_new_tokens": 512,
        "image_token_budget": 280,
    },
    "tts": {
        "voice": "af_heart",
        "speed": 1.0,
    },
    "vision": {
        "frame_interval": 2.0,
        "max_frames_in_context": 1,
    },
    "vad": {
        "aggressiveness": 2,
        "silence_duration": 0.8,
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    result = base.copy()
    for k, v in override.items():
        if isinstance(v, dict) and k in result and isinstance(result[k], dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def load_config(path: str = "config.yaml") -> Dict[str, Any]:
    cfg = DEFAULT_CONFIG.copy()
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            user_cfg = yaml.safe_load(f) or {}
        cfg = _deep_merge(cfg, user_cfg)
    return cfg


config = load_config()
