"""Reader pages: book list, reader view, per-paragraph comment panel."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db, templates
from app.models import Book, Comment, Paragraph
from app.services.parser import parse_epub_toc

router = APIRouter()
logger = logging.getLogger(__name__)

VISIBLE_COMMENT_STATUSES = ("PUBLIC", "HIDDEN")


@router.get("/")
def home(request: Request, db: Session = Depends(get_db)):
    books = db.query(Book).order_by(Book.id.desc()).all()
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "books": books,
            "allow_uploads": settings.ALLOW_UPLOADS,
        },
    )


@router.get("/book/{book_id}")
def read_book(request: Request, book_id: int, db: Session = Depends(get_db)):
    book = db.query(Book).filter(Book.id == book_id).first()
    if book is None:
        raise HTTPException(status_code=404, detail="书籍不存在")

    paragraphs = (
        db.query(Paragraph)
        .filter(Paragraph.book_id == book_id)
        .order_by(Paragraph.para_index)
        .all()
    )

    # Only comments a reader can actually see are counted; pending comments are
    # still in moderation and must not leak a count into the reading UI.
    comment_counts_rows = (
        db.query(Comment.paragraph_id, func.count(Comment.id))
        .filter(
            Comment.book_id == book_id,
            Comment.status.in_(VISIBLE_COMMENT_STATUSES),
        )
        .group_by(Comment.paragraph_id)
        .all()
    )
    comment_counts = {row[0]: row[1] for row in comment_counts_rows}

    toc: list[dict] = []
    if book.file_type == "epub":
        file_path = settings.upload_dir / book.filename
        if file_path.exists():
            try:
                toc = parse_epub_toc(str(file_path))
            except Exception:  # a broken TOC must not break reading
                logger.exception("Failed to parse EPUB TOC for book %s", book.id)

    return templates.TemplateResponse(
        "reader.html",
        {
            "request": request,
            "book": book,
            "paragraphs": paragraphs,
            "comment_counts": comment_counts,
            "toc": toc,
        },
    )


@router.get("/book/{book_id}/comments/{para_index}")
def get_comments(
    request: Request,
    book_id: int,
    para_index: int,
    db: Session = Depends(get_db),
):
    paragraph = (
        db.query(Paragraph)
        .filter(Paragraph.book_id == book_id, Paragraph.para_index == para_index)
        .first()
    )
    if paragraph is None:
        raise HTTPException(status_code=404, detail="段落不存在")

    comments = (
        db.query(Comment)
        .filter(Comment.paragraph_id == paragraph.id)
        .order_by(Comment.id)
        .all()
    )
    return templates.TemplateResponse(
        "comment_partial.html",
        {
            "request": request,
            "book_id": book_id,
            "para_index": para_index,
            "comments": comments,
            "ai_error": None,
            "max_comment_chars": settings.MAX_COMMENT_CHARS,
        },
    )
