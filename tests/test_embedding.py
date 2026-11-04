"""Unit tests for embedding search — uses a fake model, never downloads one."""

from __future__ import annotations

import json

import numpy as np
import pytest

from app.services import embedding as embedding_module
from app.services.embedding import EmbeddingService, EmbeddingUnavailableError, _load_model, tokenize


class FakeModel:
    """Deterministic 3-dim encoder so similarity ordering is predictable."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def encode(self, texts):
        single = isinstance(texts, str)
        items = [texts] if single else list(texts)
        self.calls.append(items)
        vectors = []
        for text in items:
            vector = np.zeros(3, dtype=np.float32)
            vector[0] = 1.0 if ("crime" in text or "凶手" in text) else 0.0
            vector[1] = float(len(text) % 7 + 1)
            vector[2] = 0.5
            vectors.append(vector)
        array = np.asarray(vectors, dtype=np.float32)
        return array[0] if single else array


@pytest.fixture
def model():
    return FakeModel()


@pytest.fixture
def service(model):
    return EmbeddingService(model=model)


def test_tokenize_supports_cjk_and_ascii():
    tokens = tokenize("凶手 is the butler")
    assert {"凶", "手", "the", "butler", "is"} <= tokens


def test_encode_batch_encodes_once(service, model):
    vectors = service.encode_batch(["a", "b", "c"])
    assert len(vectors) == 3
    assert all(isinstance(vector, list) for vector in vectors)
    assert len(model.calls) == 1


def test_generate_embedding_returns_floats(service):
    vector = service.generate_embedding("some text")
    assert isinstance(vector, list)
    assert all(isinstance(value, float) for value in vector)


def test_embedding_json_roundtrip(service):
    vector = [0.1, 0.2, 0.3]
    assert json.loads(service.embedding_to_json(vector)) == vector
    assert service.json_to_embedding("[0.1, 0.2]") == [0.1, 0.2]
    assert service.json_to_embedding(None) is None
    assert service.json_to_embedding("not json") is None


def test_keyword_search_ranks_chinese_matches(service):
    paragraphs = [
        {"para_index": 0, "content": "今天天气很好。"},
        {"para_index": 1, "content": "凶手就是管家，他承认了。"},
        {"para_index": 2, "content": "他们喝了茶。"},
    ]

    results = service.keyword_search("凶手是谁", paragraphs, top_k=2)

    assert results
    assert results[0]["para_index"] == 1


def test_keyword_search_handles_english_words(service):
    paragraphs = [
        {"para_index": 0, "content": "It was a rainy day."},
        {"para_index": 1, "content": "The butler confessed at dawn."},
    ]

    results = service.keyword_search("Who is the butler?", paragraphs, top_k=2)

    assert results[0]["para_index"] == 1


def test_keyword_search_is_case_insensitive(service):
    paragraphs = [{"para_index": 0, "content": "The Butler did it."}]

    results = service.keyword_search("butler", paragraphs, top_k=1)

    assert results and results[0]["para_index"] == 0


def test_keyword_search_without_tokens_returns_empty(service):
    assert service.keyword_search("   ", [{"para_index": 0, "content": "x"}]) == []


def test_semantic_search_uses_stored_embeddings(service, model):
    paragraphs = [
        {"para_index": 0, "content": "crime scene", "embedding": [1.0, 6.0, 0.5]},
        {"para_index": 1, "content": "weather", "embedding": [0.0, 1.0, 0.5]},
    ]

    results = service.semantic_search("crime", paragraphs, top_k=2)

    assert [item["para_index"] for item in results] == [0, 1]
    assert results[0]["similarity"] > results[1]["similarity"]
    # Only the query was encoded; stored vectors were reused.
    assert len(model.calls) == 1


def test_semantic_search_encodes_when_embeddings_missing(service, model):
    paragraphs = [
        {"para_index": 0, "content": "crime scene"},
        {"para_index": 1, "content": "weather"},
    ]

    results = service.semantic_search("crime", paragraphs, top_k=1)

    assert len(results) == 1
    assert model.calls[0] == ["crime"]
    assert len(model.calls[-1]) == 2


def test_semantic_search_reencodes_on_dimension_mismatch(service, model):
    paragraphs = [
        {"para_index": 0, "content": "crime scene", "embedding": [1.0, 0.0]},
        {"para_index": 1, "content": "weather", "embedding": [0.0, 1.0]},
    ]

    results = service.semantic_search("crime", paragraphs, top_k=2)

    assert len(results) == 2
    assert len(model.calls[-1]) == 2  # re-encoded both paragraphs
    assert results[0]["para_index"] == 0


def test_semantic_search_empty_book(service):
    assert service.semantic_search("query", [], top_k=3) == []


# ------------------------------------------------------------- offline loading
def test_load_model_prefers_local_cache(monkeypatch):
    calls = []

    def factory(name, **kwargs):
        calls.append((name, kwargs))
        return object()

    monkeypatch.setattr(embedding_module, "SentenceTransformer", factory)

    _load_model("some-model")

    assert calls == [("some-model", {"local_files_only": True})]


def test_load_model_falls_back_to_download(monkeypatch):
    calls = []

    def factory(name, **kwargs):
        calls.append(kwargs)
        if kwargs.get("local_files_only"):
            raise OSError("not cached")
        return object()

    monkeypatch.setattr(embedding_module, "SentenceTransformer", factory)
    monkeypatch.setattr(embedding_module, "_network_available", lambda: True)

    _load_model("some-model")

    assert calls == [{"local_files_only": True}, {}]


def test_load_model_offline_without_cache_fails_fast(monkeypatch):
    def factory(name, **kwargs):
        raise OSError("not cached")

    monkeypatch.setattr(embedding_module, "SentenceTransformer", factory)
    monkeypatch.setattr(embedding_module, "_network_available", lambda: False)

    with pytest.raises(EmbeddingUnavailableError) as excinfo:
        _load_model("some-model")

    assert "缓存" in str(excinfo.value)


def test_load_model_honours_download_disabled(monkeypatch):
    def factory(name, **kwargs):
        raise OSError("not cached")

    monkeypatch.setattr(embedding_module, "SentenceTransformer", factory)
    monkeypatch.setenv("EMBEDDING_ALLOW_DOWNLOAD", "false")

    with pytest.raises(EmbeddingUnavailableError):
        _load_model("some-model")
