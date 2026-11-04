"""Model-level tests for the SQLAlchemy schema."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Book, Comment, Paragraph


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _seed(session):
    book = Book(title="Test Book", filename="test.pdf", file_type="pdf", total_paragraphs=1)
    session.add(book)
    session.commit()
    paragraph = Paragraph(book_id=book.id, para_index=0, page_num=1, content="Hello world")
    session.add(paragraph)
    session.commit()
    comment = Comment(
        paragraph_id=paragraph.id,
        book_id=book.id,
        content="Great paragraph!",
        status="PUBLIC",
        is_spoiler=False,
        confidence=0.95,
        ai_reason="No spoiler content detected.",
    )
    session.add(comment)
    session.commit()
    return book, paragraph, comment


def test_create_book(db_session):
    book = Book(title="Test Book", filename="test.pdf", file_type="pdf", total_paragraphs=10)
    db_session.add(book)
    db_session.commit()

    assert book.id is not None
    assert book.title == "Test Book"


def test_create_paragraph(db_session):
    _, paragraph, _ = _seed(db_session)
    assert paragraph.id is not None
    assert paragraph.content == "Hello world"


def test_create_comment(db_session):
    _, _, comment = _seed(db_session)
    assert comment.id is not None
    assert comment.status == "PUBLIC"
    assert comment.is_spoiler is False


def test_comment_allows_unknown_ai_verdict(db_session):
    _, paragraph, _ = _seed(db_session)
    comment = Comment(
        paragraph_id=paragraph.id,
        book_id=paragraph.book_id,
        content="AI was down",
        status="PENDING_REVIEW",
    )
    db_session.add(comment)
    db_session.commit()

    assert comment.is_spoiler is None
    assert comment.confidence is None


def test_deleting_book_cascades_to_paragraphs_and_comments(db_session):
    book, _, _ = _seed(db_session)

    db_session.delete(book)
    db_session.commit()

    assert db_session.query(Book).count() == 0
    assert db_session.query(Paragraph).count() == 0
    assert db_session.query(Comment).count() == 0
