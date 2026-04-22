from sqlalchemy import Column, Integer, String, Float, Boolean, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class Book(Base):
    __tablename__ = "books"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    filename = Column(String(255), nullable=False)
    file_type = Column(String(10), nullable=False)  # pdf, epub, txt
    total_paragraphs = Column(Integer, default=0)

    paragraphs = relationship("Paragraph", back_populates="book", cascade="all, delete-orphan")
    comments = relationship("Comment", back_populates="book", cascade="all, delete-orphan")


class Paragraph(Base):
    __tablename__ = "paragraphs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    book_id = Column(Integer, ForeignKey("books.id"), nullable=False)
    para_index = Column(Integer, nullable=False)
    page_num = Column(Integer, nullable=True)
    content = Column(Text, nullable=False)
    embedding_blob = Column(Text, nullable=True)  # JSON-serialized embedding vector

    book = relationship("Book", back_populates="paragraphs")


class Comment(Base):
    __tablename__ = "comments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    paragraph_id = Column(Integer, ForeignKey("paragraphs.id"), nullable=False)
    book_id = Column(Integer, ForeignKey("books.id"), nullable=False)
    content = Column(Text, nullable=False)
    status = Column(String(20), nullable=False, default="PENDING_REVIEW")  # PENDING_REVIEW, PUBLIC, HIDDEN
    is_spoiler = Column(Boolean, default=None)
    confidence = Column(Float, default=None)
    ai_reason = Column(Text, default=None)

    paragraph = relationship("Paragraph")
    book = relationship("Book", back_populates="comments")