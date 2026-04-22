import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base, init_db
from app.models import Book, Paragraph, Comment


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_create_book(db_session):
    book = Book(title="Test Book", filename="test.pdf", file_type="pdf", total_paragraphs=10)
    db_session.add(book)
    db_session.commit()
    assert book.id is not None
    assert book.title == "Test Book"


def test_create_paragraph(db_session):
    book = Book(title="Test Book", filename="test.pdf", file_type="pdf", total_paragraphs=1)
    db_session.add(book)
    db_session.commit()
    para = Paragraph(book_id=book.id, para_index=0, page_num=1, content="Hello world")
    db_session.add(para)
    db_session.commit()
    assert para.id is not None
    assert para.content == "Hello world"


def test_create_comment(db_session):
    book = Book(title="Test Book", filename="test.pdf", file_type="pdf", total_paragraphs=1)
    db_session.add(book)
    db_session.commit()
    para = Paragraph(book_id=book.id, para_index=0, page_num=1, content="Hello world")
    db_session.add(para)
    db_session.commit()
    comment = Comment(
        paragraph_id=para.id,
        book_id=book.id,
        content="Great paragraph!",
        status="PUBLIC",
        is_spoiler=False,
        confidence=0.95,
        ai_reason="No spoiler content detected."
    )
    db_session.add(comment)
    db_session.commit()
    assert comment.id is not None
    assert comment.status == "PUBLIC"
    assert comment.is_spoiler is False