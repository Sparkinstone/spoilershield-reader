"""Lazily constructed, FastAPI-injectable service singletons.

Routers depend on these functions instead of importing module-level globals, so
tests can swap in a fake embedding model or a fake LLM with
``app.dependency_overrides`` without downloading models or calling the network.
"""

from __future__ import annotations

import threading

from app.services.embedding import EmbeddingService
from app.services.llm import LLMService

_lock = threading.Lock()
_embedding_service: EmbeddingService | None = None
_llm_service: LLMService | None = None


def get_embedding_service() -> EmbeddingService:
    global _embedding_service
    if _embedding_service is None:
        with _lock:
            if _embedding_service is None:
                _embedding_service = EmbeddingService()
    return _embedding_service


def get_llm_service() -> LLMService:
    global _llm_service
    if _llm_service is None:
        with _lock:
            if _llm_service is None:
                _llm_service = LLMService()
    return _llm_service


def reset_services() -> None:
    """Drop cached services (used by tests and after config changes)."""
    global _embedding_service, _llm_service
    with _lock:
        _embedding_service = None
        _llm_service = None
