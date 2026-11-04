"""Comment submission + AI spoiler detection."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db, templates
from app.models import Book, Comment, Paragraph
from app.services.embedding import EmbeddingService
from app.services.llm import LLMError, LLMService
from app.services.providers import get_embedding_service, get_llm_service
from app.services.spoiler_detector import SpoilerDetector

router = APIRouter()
logger = logging.getLogger(__name__)

AI_UNAVAILABLE_REASON = "AI 审核暂不可用，评论已转入人工审核"


def _comments_for(db: Session, paragraph: Paragraph) -> list[Comment]:
    return (
        db.query(Comment)
        .filter(Comment.paragraph_id == paragraph.id)
        .order_by(Comment.id)
        .all()
    )


@router.post("/comment")
def post_comment(
    request: Request,
    book_id: int = Form(...),
    para_index: int = Form(...),
    content: str = Form(...),
    db: Session = Depends(get_db),
    embedding: EmbeddingService = Depends(get_embedding_service),
    llm: LLMService = Depends(get_llm_service),
):
    text = (content or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="评论内容不能为空")
    if len(text) > settings.MAX_COMMENT_CHARS:
        raise HTTPException(
            status_code=400,
            detail=f"评论最多 {settings.MAX_COMMENT_CHARS} 字",
        )

    book = db.query(Book).filter(Book.id == book_id).first()
    if book is None:
        raise HTTPException(status_code=404, detail="书籍不存在")

    paragraph = (
        db.query(Paragraph)
        .filter(Paragraph.book_id == book_id, Paragraph.para_index == para_index)
        .first()
    )
    if paragraph is None:
        raise HTTPException(status_code=404, detail="段落不存在")

    all_paragraphs = (
        db.query(Paragraph)
        .filter(Paragraph.book_id == book_id)
        .order_by(Paragraph.para_index)
        .all()
    )
    paragraph_payload = [
        {
            "para_index": item.para_index,
            "content": item.content,
            "embedding": embedding.json_to_embedding(item.embedding_blob),
        }
        for item in all_paragraphs
    ]

    ai_error = None
    try:
        result = SpoilerDetector(embedding, llm).detect(
            comment=text,
            current_para_index=para_index,
            all_paragraphs=paragraph_payload,
        )
    except LLMError as exc:
        # Losing the reader's comment because a vendor is down is worse than
        # queueing it for a human: keep it, but never auto-publish it.
        logger.warning("Spoiler detection unavailable: %s", exc)
        ai_error = AI_UNAVAILABLE_REASON
        result = {
            "is_spoiler": None,
            "confidence": None,
            "reason": AI_UNAVAILABLE_REASON,
            "status": "PENDING_REVIEW",
        }

    comment = Comment(
        paragraph_id=paragraph.id,
        book_id=book_id,
        content=text,
        status=result["status"],
        is_spoiler=result["is_spoiler"],
        confidence=result["confidence"],
        ai_reason=result["reason"],
    )
    db.add(comment)
    db.commit()

    return templates.TemplateResponse(
        "comment_partial.html",
        {
            "request": request,
            "book_id": book_id,
            "para_index": para_index,
            "comments": _comments_for(db, paragraph),
            "ai_error": ai_error,
            "max_comment_chars": settings.MAX_COMMENT_CHARS,
        },
    )
