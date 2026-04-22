import pytest
import json
from app.services.embedding import EmbeddingService


@pytest.fixture
def embedding_service():
    return EmbeddingService()


def test_generate_embedding(embedding_service):
    text = "This is a test paragraph."
    vector = embedding_service.generate_embedding(text)
    assert isinstance(vector, list)
    assert len(vector) > 0
    assert all(isinstance(v, float) for v in vector)


def test_embedding_to_json(embedding_service):
    vector = [0.1, 0.2, 0.3]
    json_str = embedding_service.embedding_to_json(vector)
    assert isinstance(json_str, str)
    parsed = json.loads(json_str)
    assert parsed == vector


def test_json_to_embedding(embedding_service):
    json_str = "[0.1, 0.2, 0.3]"
    vector = embedding_service.json_to_embedding(json_str)
    assert vector == [0.1, 0.2, 0.3]


def test_semantic_search(embedding_service):
    paragraphs = [
        {"para_index": 0, "content": "The detective arrived at the crime scene."},
        {"para_index": 1, "content": "It was a rainy day in the city."},
        {"para_index": 2, "content": "The murderer was revealed to be the butler."},
    ]
    query = "Who committed the crime?"
    results = embedding_service.semantic_search(query, paragraphs, top_k=2)
    assert len(results) <= 2
    assert isinstance(results[0], dict)
    assert "para_index" in results[0]