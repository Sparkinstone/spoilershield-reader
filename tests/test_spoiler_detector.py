"""Tests for the retrieval → future-filter → LLM spoiler pipeline."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services.llm import LLMError
from app.services.spoiler_detector import (
    SNIPPET_WINDOW,
    SpoilerDetector,
    _extract_snippet,
    _merge_candidates,
    determine_status,
)


@pytest.fixture
def embedding_service():
    service = MagicMock()
    service.semantic_search.return_value = []
    service.keyword_search.return_value = []
    return service


@pytest.fixture
def llm_service():
    service = MagicMock()
    service.judge_spoiler.return_value = {
        "is_spoiler": True,
        "confidence": 0.85,
        "reason": "泄露了凶手身份",
    }
    return service


def _paragraphs(count: int = 15, size: int = 20) -> list[dict]:
    return [
        {"para_index": index, "content": f"段落{index}。" * (size // 4 + 1)}
        for index in range(count)
    ]


def test_detect_keeps_only_future_paragraphs(embedding_service, llm_service):
    embedding_service.semantic_search.return_value = [
        {"para_index": 5, "content": "未来五", "similarity": 0.85},
        {"para_index": 10, "content": "未来十", "similarity": 0.72},
        {"para_index": 0, "content": "过去零", "similarity": 0.60},
    ]
    embedding_service.keyword_search.return_value = [
        {"para_index": 7, "content": "关键词段落", "similarity": 3.0},
        {"para_index": 5, "content": "未来五", "similarity": 2.0},
    ]

    detector = SpoilerDetector(embedding_service, llm_service)
    result = detector.detect("管家是凶手", current_para_index=2, all_paragraphs=_paragraphs())

    assert result["status"] == "HIDDEN"
    kwargs = llm_service.judge_spoiler.call_args.kwargs
    assert kwargs["current_paragraph"].startswith("段落2")
    assert kwargs["future_paragraphs"] == ["未来五", "关键词段落", "未来十"]
    assert kwargs["no_context"] is False


def test_low_similarity_vector_hits_are_dropped(embedding_service, llm_service):
    embedding_service.semantic_search.return_value = [
        {"para_index": 9, "content": "低相关", "similarity": 0.20},
    ]

    detector = SpoilerDetector(embedding_service, llm_service)
    detector.detect("随便说说", current_para_index=2, all_paragraphs=_paragraphs())

    kwargs = llm_service.judge_spoiler.call_args.kwargs
    assert kwargs["no_context"] is True
    assert kwargs["future_paragraphs"] == []


def test_no_future_paragraphs_sets_no_context(embedding_service, llm_service):
    embedding_service.semantic_search.return_value = [
        {"para_index": 0, "content": "开头", "similarity": 0.9},
        {"para_index": 1, "content": "第二段", "similarity": 0.8},
    ]

    detector = SpoilerDetector(embedding_service, llm_service)
    detector.detect("开头不错", current_para_index=5, all_paragraphs=_paragraphs())

    kwargs = llm_service.judge_spoiler.call_args.kwargs
    assert kwargs["no_context"] is True
    assert kwargs["future_paragraphs"] == []


def test_long_context_is_snipped(embedding_service, llm_service):
    long_text = "关键词" * 1000  # 3000 chars
    embedding_service.semantic_search.return_value = [
        {"para_index": index, "content": long_text, "similarity": 0.9} for index in (5, 6)
    ]

    detector = SpoilerDetector(embedding_service, llm_service)
    detector.detect("关键词", current_para_index=1, all_paragraphs=_paragraphs(20, 3000))

    kwargs = llm_service.judge_spoiler.call_args.kwargs
    for content in kwargs["future_paragraphs"]:
        assert len(content) <= SNIPPET_WINDOW + 6
        assert "..." in content


def test_detect_rejects_unknown_paragraph(embedding_service, llm_service):
    detector = SpoilerDetector(embedding_service, llm_service)
    with pytest.raises(ValueError):
        detector.detect("x", current_para_index=99, all_paragraphs=_paragraphs())


def test_detect_rejects_empty_book(embedding_service, llm_service):
    detector = SpoilerDetector(embedding_service, llm_service)
    with pytest.raises(ValueError):
        detector.detect("x", current_para_index=0, all_paragraphs=[])


def test_llm_errors_propagate(embedding_service, llm_service):
    llm_service.judge_spoiler.side_effect = LLMError("down", kind="connection")
    detector = SpoilerDetector(embedding_service, llm_service)

    with pytest.raises(LLMError):
        detector.detect("x", current_para_index=1, all_paragraphs=_paragraphs())


def test_merge_candidates_dedupes_and_sorts():
    merged = _merge_candidates(
        [
            {"para_index": 5, "content": "a", "similarity": 0.9},
            {"para_index": 2, "content": "b", "similarity": 0.1},
        ],
        [
            {"para_index": 5, "content": "a", "similarity": 2.0},
            {"para_index": 3, "content": "c", "similarity": 1.0},
        ],
    )
    assert [item["para_index"] for item in merged] == [3, 5]


def test_extract_snippet_returns_short_content_unchanged():
    assert _extract_snippet("短文本", "查询") == "短文本"


def test_extract_snippet_centers_on_query():
    content = "开头" + "填充" * 100 + "目标关键词" + "填充" * 100
    snippet = _extract_snippet(content, "目标关键词", window=60)
    assert "目标关键词" in snippet
    assert len(snippet) <= 66


@pytest.mark.parametrize(
    ("is_spoiler", "confidence", "expected"),
    [
        (True, 0.85, "HIDDEN"),
        (False, 0.85, "PUBLIC"),
        (True, 0.7, "HIDDEN"),
        (True, 0.69, "PENDING_REVIEW"),
        (False, 0.5, "PENDING_REVIEW"),
        (False, 0.0, "PENDING_REVIEW"),
    ],
)
def test_determine_status(is_spoiler, confidence, expected):
    assert determine_status(is_spoiler, confidence) == expected
