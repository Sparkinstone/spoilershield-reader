"""Local sentence-embedding service plus lexical fallback recall."""

from __future__ import annotations

import json
import logging
import os
import re
import socket
from urllib.parse import urlparse

import numpy as np
from sentence_transformers import SentenceTransformer

from app.config import settings

logger = logging.getLogger(__name__)

_CJK_CHAR = re.compile(r"[\u4e00-\u9fff]")
_ASCII_WORD = re.compile(r"[A-Za-z0-9_']+")


class EmbeddingUnavailableError(RuntimeError):
    """The local model is neither cached nor downloadable."""


def _hf_host() -> str:
    endpoint = os.getenv("HF_ENDPOINT", "https://huggingface.co")
    return urlparse(endpoint).hostname or "huggingface.co"


def _network_available(timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((_hf_host(), 443), timeout=timeout):
            return True
    except OSError:
        return False


def _downloads_allowed() -> bool:
    return os.getenv("EMBEDDING_ALLOW_DOWNLOAD", "true").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def _load_model(model_name: str) -> SentenceTransformer:
    """Load from the local cache first, only touching the network as a fallback.

    ``SentenceTransformer(name)`` performs HuggingFace Hub lookups even when the
    weights are already cached. Offline that means five retries with backoff —
    measured at ~184s — which looks like the app has hung. ``local_files_only``
    reads the cache directly (0.2s) and misses are handled explicitly.
    """
    try:
        return SentenceTransformer(model_name, local_files_only=True)
    except Exception as local_error:  # noqa: BLE001 - any load failure means "not cached"
        logger.info("Embedding model %s not fully cached: %s", model_name, local_error)

    if not _downloads_allowed():
        raise EmbeddingUnavailableError(
            f"本地没有 embedding 模型 {model_name} 的完整缓存，且 EMBEDDING_ALLOW_DOWNLOAD=false。"
            " 请预下载模型，或把 EMBEDDING_MODEL 指向本地路径。"
        )
    if not _network_available():
        raise EmbeddingUnavailableError(
            f"本地没有 embedding 模型 {model_name} 的完整缓存，且当前无法访问 HuggingFace。"
            " 请联网首次下载，或把 EMBEDDING_MODEL 指向本地模型目录。"
        )

    logger.warning("Downloading embedding model %s for the first time", model_name)
    return SentenceTransformer(model_name)



def tokenize(query: str) -> set[str]:
    """Split a query into CJK characters + ASCII words.

    The previous implementation only looked at non-ASCII characters, so an
    English comment could never get a lexical match.
    """
    tokens = {match.group(0).lower() for match in _ASCII_WORD.finditer(query)}
    tokens.update(_CJK_CHAR.findall(query))
    return {token for token in tokens if token.strip()}


class EmbeddingService:
    def __init__(self, model_name: str | None = None, model=None) -> None:
        self.model_name = model_name or settings.EMBEDDING_MODEL
        self.model = model if model is not None else _load_model(self.model_name)

    # ------------------------------------------------------------------ encode
    def encode_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self.model.encode(texts)
        return np.asarray(vectors).tolist()

    def generate_embedding(self, text: str) -> list[float]:
        vector = self.model.encode(text)
        return np.asarray(vector).tolist()

    def embedding_to_json(self, vector: list[float]) -> str:
        return json.dumps(vector)

    def json_to_embedding(self, json_str: str | None) -> list[float] | None:
        if not json_str:
            return None
        try:
            return json.loads(json_str)
        except (TypeError, json.JSONDecodeError):
            logger.warning("Ignoring unparsable embedding blob")
            return None

    # ------------------------------------------------------------------ recall
    def keyword_search(self, query: str, paragraphs: list[dict], top_k: int = 3) -> list[dict]:
        """词频检索：统计 query 的字符/单词在段落中出现的次数，取 top_k。"""
        if not paragraphs:
            return []
        tokens = tokenize(query)
        if not tokens:
            return []

        scores = [
            sum(paragraph["content"].lower().count(token) for token in tokens)
            for paragraph in paragraphs
        ]
        top_indices = np.argsort(scores)[::-1][:top_k]
        results = []
        for index in top_indices:
            if scores[index] <= 0:
                continue
            results.append(
                {
                    "para_index": paragraphs[index]["para_index"],
                    "content": paragraphs[index]["content"],
                    "similarity": float(scores[index]),
                }
            )
        return results

    def semantic_search(self, query: str, paragraphs: list[dict], top_k: int = 3) -> list[dict]:
        """向量语义检索，优先使用预计算 embedding。"""
        if not paragraphs:
            return []

        query_embedding = np.asarray(self.model.encode(query), dtype=np.float32)
        query_norm = float(np.linalg.norm(query_embedding)) + 1e-9

        stored = [paragraph.get("embedding") for paragraph in paragraphs]
        if all(vector is not None for vector in stored):
            matrix = np.asarray(stored, dtype=np.float32)
        else:
            matrix = np.asarray(
                self.model.encode([paragraph["content"] for paragraph in paragraphs]),
                dtype=np.float32,
            )
        if matrix.ndim == 1:
            matrix = matrix.reshape(1, -1)

        # A model change (e.g. switching to a Chinese embedding model) leaves
        # old, differently-sized vectors in SQLite. Recompute instead of crashing.
        if matrix.shape[1] != query_embedding.shape[0]:
            logger.warning(
                "Embedding dimension mismatch (%s stored vs %s query); re-encoding paragraphs",
                matrix.shape[1],
                query_embedding.shape[0],
            )
            matrix = np.asarray(
                self.model.encode([paragraph["content"] for paragraph in paragraphs]),
                dtype=np.float32,
            )
            if matrix.ndim == 1:
                matrix = matrix.reshape(1, -1)

        norms = np.linalg.norm(matrix, axis=1) * query_norm + 1e-9
        similarities = (matrix @ query_embedding) / norms

        top_indices = np.argsort(similarities)[::-1][:top_k]
        results = []
        for index in top_indices:
            paragraph = paragraphs[index]
            results.append(
                {
                    "para_index": paragraph["para_index"],
                    "content": paragraph["content"],
                    "similarity": float(similarities[index]),
                }
            )
        return results
