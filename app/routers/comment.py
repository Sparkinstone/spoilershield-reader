from fastapi import APIRouter, Depends, Request, Form
from sqlalchemy.orm import Session
from app.database import get_db, templates
from app.models import Book, Paragraph, Comment
from app.services.embedding import EmbeddingService
from app.services.llm import LLMService
from app.services.spoiler_detector import SpoilerDetector

router = APIRouter()

_embedding_service = None
_llm_service = None


def get_detector():
    global _embedding_service, _llm_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    if _llm_service is None:
        _llm_service = LLMService()
    return SpoilerDetector(_embedding_service, _llm_service)


@router.post("/comment")
def post_comment(
    request: Request,
    book_id: int = Form(...),
    para_index: int = Form(...),
    content: str = Form(...),
    db: Session = Depends(get_db),
):
    paragraph = db.query(Paragraph).filter(
        Paragraph.book_id == book_id, Paragraph.para_index == para_index
    ).first()
    if not paragraph:
        return {"error": "Paragraph not found"}

    all_paragraphs = db.query(Paragraph).filter(Paragraph.book_id == book_id).order_by(Paragraph.para_index).all()
    para_dicts = [{"para_index": p.para_index, "content": p.content} for p in all_paragraphs]

    detector = get_detector()
    result = detector.detect(
        comment=content,
        current_para_index=para_index,
        all_paragraphs=para_dicts,
    )

    comment = Comment(
        paragraph_id=paragraph.id,
        book_id=book_id,
        content=content,
        status=result["status"],
        is_spoiler=result["is_spoiler"],
        confidence=result["confidence"],
        ai_reason=result["reason"],
    )
    db.add(comment)
    db.commit()

    comments = db.query(Comment).filter(Comment.paragraph_id == paragraph.id).all()
    return templates.TemplateResponse("comment_partial.html", {
        "request": request,
        "book_id": book_id,
        "para_index": para_index,
        "comments": comments,
    })
