import pytest
from unittest.mock import MagicMock
from app.services.spoiler_detector import SpoilerDetector, determine_status


@pytest.fixture
def mock_embedding_service():
    service = MagicMock()
    service.semantic_search.return_value = [
        {"para_index": 5, "content": "The butler was the murderer.", "similarity": 0.85},
        {"para_index": 10, "content": "The detective solved the case.", "similarity": 0.72},
        {"para_index": 0, "content": "A crime was committed.", "similarity": 0.60},
    ]
    return service


@pytest.fixture
def mock_llm_service():
    service = MagicMock()
    service.judge_spoiler.return_value = {
        "is_spoiler": True,
        "confidence": 0.85,
        "reason": "Comment reveals the killer's identity from page 50.",
    }
    return service


def test_detect_spoiler_with_future_paragraphs(mock_embedding_service, mock_llm_service):
    detector = SpoilerDetector(mock_embedding_service, mock_llm_service)
    result = detector.detect(
        comment="The butler did it!",
        current_para_index=2,
        all_paragraphs=[{"para_index": i, "content": f"Para {i}"} for i in range(15)],
    )
    assert result["is_spoiler"] is True
    assert result["confidence"] == 0.85


def test_detect_no_future_paragraphs(mock_embedding_service, mock_llm_service):
    mock_embedding_service.semantic_search.return_value = [
        {"para_index": 0, "content": "A crime was committed.", "similarity": 0.60},
        {"para_index": 1, "content": "The detective arrived.", "similarity": 0.55},
    ]
    detector = SpoilerDetector(mock_embedding_service, mock_llm_service)
    result = detector.detect(
        comment="Interesting start!",
        current_para_index=5,
        all_paragraphs=[{"para_index": i, "content": f"Para {i}"} for i in range(15)],
    )
    mock_llm_service.judge_spoiler.assert_called_once()


def test_determine_status_high_confidence_spoiler():
    assert determine_status(True, 0.85) == "HIDDEN"


def test_determine_status_high_confidence_non_spoiler():
    assert determine_status(False, 0.85) == "PUBLIC"


def test_determine_status_low_confidence():
    assert determine_status(True, 0.5) == "PENDING_REVIEW"
    assert determine_status(False, 0.5) == "PENDING_REVIEW"
