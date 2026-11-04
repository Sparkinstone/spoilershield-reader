"""Shared pytest fixtures: isolated DB, fake AI services, HTTP client."""

from __future__ import annotations

import json
import re
import shutil
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.services.providers import get_embedding_service, get_llm_service

# Pytest's own tmpdir creates its base directory with mode 0o700, which the
# Windows sandbox can turn into an unreadable, protected folder. This fixture
# keeps temp data inside the workspace with default (inherited) permissions.
_TMP_ROOT = Path(__file__).resolve().parent.parent / ".test_tmp"


def pytest_configure(config):
    shutil.rmtree(_TMP_ROOT, ignore_errors=True)


@pytest.fixture
def tmp_path(request):
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", request.node.nodeid)[-80:]
    path = _TMP_ROOT / f"{safe_name}-{uuid.uuid4().hex[:8]}"
    path.mkdir(parents=True, exist_ok=True)
    return path


class FakeEmbeddingService:
    """Deterministic stand-in for sentence-transformers (no model download)."""

    def __init__(self) -> None:
        self.semantic_results: list[dict] | None = None
        self.keyword_results: list[dict] | None = None
        self.batch_calls = 0

    def encode_batch(self, texts: list[str]) -> list[list[float]]:
        self.batch_calls += 1
        return [[0.1, 0.2, 0.3, 0.4] for _ in texts]

    def generate_embedding(self, text: str) -> list[float]:
        return [0.1, 0.2, 0.3, 0.4]

    def embedding_to_json(self, vector: list[float]) -> str:
        return json.dumps(vector)

    def json_to_embedding(self, blob: str | None) -> list[float] | None:
        if not blob:
            return None
        return json.loads(blob)

    def semantic_search(self, query: str, paragraphs: list[dict], top_k: int = 3) -> list[dict]:
        if self.semantic_results is None:
            return []
        return self.semantic_results[:top_k]

    def keyword_search(self, query: str, paragraphs: list[dict], top_k: int = 3) -> list[dict]:
        if self.keyword_results is None:
            return []
        return self.keyword_results[:top_k]


class FakeLLMService:
    def __init__(self) -> None:
        self.result = {
            "is_spoiler": False,
            "confidence": 0.95,
            "reason": "对当前段落的感受，没有剧透。",
        }
        self.error: Exception | None = None
        self.calls: list[dict] = []

    def judge_spoiler(self, **kwargs) -> dict:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return dict(self.result)


@pytest.fixture
def engine(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(engine):
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture
def fake_embedding():
    return FakeEmbeddingService()


@pytest.fixture
def fake_llm():
    return FakeLLMService()


@pytest.fixture
def client(engine, fake_embedding, fake_llm, tmp_path, monkeypatch):
    Session = sessionmaker(bind=engine)

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_embedding_service] = lambda: fake_embedding
    app.dependency_overrides[get_llm_service] = lambda: fake_llm

    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setattr(settings, "MAX_UPLOAD_MB", 20.0)
    monkeypatch.setattr(settings, "MAX_PARAGRAPHS", 5000)
    monkeypatch.setattr(settings, "MAX_COMMENT_CHARS", 500)
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", None)

    test_client = TestClient(app)
    yield test_client
    test_client.close()
    app.dependency_overrides.clear()


@pytest.fixture
def upload_book(client):
    def _upload(content: str = "第一段。\n\n第二段。\n\n第三段。", title: str = "测试书"):
        return client.post(
            "/upload",
            files={"file": ("book.txt", content.encode("utf-8"), "text/plain")},
            data={"title": title},
            follow_redirects=False,
        )

    return _upload


@pytest.fixture
def book_and_paragraphs(db_session):
    from app.models import Book, Paragraph

    book = Book(title="已有书", filename="seed.txt", file_type="txt", total_paragraphs=3)
    db_session.add(book)
    db_session.flush()
    paragraphs = [
        Paragraph(book_id=book.id, para_index=index, content=f"第 {index} 段内容。")
        for index in range(3)
    ]
    db_session.add_all(paragraphs)
    db_session.commit()
    for paragraph in paragraphs:
        db_session.refresh(paragraph)
    return book, paragraphs
