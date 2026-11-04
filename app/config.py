"""Application configuration.

Every value is read from the environment (``.env`` is loaded from the project
root) at instantiation time.  Keeping this an ordinary object — instead of
class-level constants evaluated at import time — means tests can build a fresh
``Settings`` or monkeypatch a single field without reloading modules.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


def _get(name: str, default: str = "") -> str:
    value = os.getenv(name)
    return default if value is None else value.strip()


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _get_int(name: str, default: int, minimum: int | None = None) -> int:
    try:
        value = int(_get(name, str(default)))
    except ValueError:
        return default
    if minimum is not None and value < minimum:
        return minimum
    return value


def _get_float(name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(_get(name, str(default)))
    except ValueError:
        return default
    return min(maximum, max(minimum, value))


class Settings:
    def __init__(self) -> None:
        # --- LLM (DeepSeek Flash by default, any OpenAI-compatible endpoint) ---
        # LLM_* wins; OPENAI_* / DEEPSEEK_API_KEY are kept as fallbacks so an
        # existing .env keeps working after the switch away from Anthropic.
        self.LLM_API_KEY = (
            _get("LLM_API_KEY") or _get("DEEPSEEK_API_KEY") or _get("OPENAI_API_KEY")
        )
        self.LLM_BASE_URL = (
            _get("LLM_BASE_URL") or _get("OPENAI_API_BASE") or "https://api.deepseek.com/v1"
        ).rstrip("/")
        self.LLM_MODEL = _get("LLM_MODEL") or "deepseek-flash"
        self.LLM_TIMEOUT = _get_float("LLM_TIMEOUT", 30.0, 1.0, 300.0)
        self.LLM_MAX_RETRIES = _get_int("LLM_MAX_RETRIES", 2, minimum=0)
        self.LLM_TEMPERATURE = _get_float("LLM_TEMPERATURE", 0.0, 0.0, 2.0)
        self.LLM_MAX_TOKENS = _get_int("LLM_MAX_TOKENS", 400, minimum=16)
        # Some private gateways serve an expired/self-signed certificate.
        # Enabled by default; opt out explicitly and knowingly.
        self.LLM_SSL_VERIFY = _get_bool("LLM_SSL_VERIFY", True)

        # Backwards-compatible aliases used by older scripts.
        self.OPENAI_API_KEY = self.LLM_API_KEY
        self.OPENAI_API_BASE = self.LLM_BASE_URL
        self.EMBEDDING_MODEL = _get("EMBEDDING_MODEL") or "all-MiniLM-L6-v2"

        # --- product behaviour ---
        self.SPOILER_CONFIDENCE_THRESHOLD = _get_float(
            "SPOILER_CONFIDENCE_THRESHOLD", 0.7, 0.0, 1.0
        )
        self.MAX_COMMENT_CHARS = _get_int("MAX_COMMENT_CHARS", 500, minimum=1)
        self.MAX_UPLOAD_MB = _get_float("MAX_UPLOAD_MB", 20.0, 0.1, 1024.0)
        self.MAX_PARAGRAPHS = _get_int("MAX_PARAGRAPHS", 5000, minimum=1)
        # Public demo deployments usually pre-seed one book and turn uploads off:
        # each upload runs the embedding model and is an easy resource-abuse path.
        self.ALLOW_UPLOADS = _get_bool("ALLOW_UPLOADS", True)

        # --- infrastructure ---
        self.DATABASE_URL = _get("DATABASE_URL") or "sqlite:///./spoiler_shield.db"
        self.UPLOAD_DIR = _get("UPLOAD_DIR") or "uploads"
        self.ADMIN_USER = _get("ADMIN_USER") or "admin"
        self.ADMIN_PASSWORD = _get("ADMIN_PASSWORD")

    @property
    def llm_configured(self) -> bool:
        return bool(self.LLM_API_KEY)

    @property
    def upload_dir(self) -> Path:
        path = Path(self.UPLOAD_DIR)
        return path if path.is_absolute() else BASE_DIR / path

    def __repr__(self) -> str:  # never leak the key
        return (
            f"Settings(model={self.LLM_MODEL!r}, base_url={self.LLM_BASE_URL!r}, "
            f"key={'set' if self.llm_configured else 'missing'})"
        )


settings = Settings()
