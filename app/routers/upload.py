import os
import shutil
from fastapi import APIRouter, UploadFile, File, Form, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Book, Paragraph
from app.services.parser import parse_file
from app.services.embedding import EmbeddingService
from app.config import settings

router = APIRouter()
_embedding_service = None


def get_embedding_service():
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service


@router.post("/upload")
async def upload_book(
    file: UploadFile = File(...),
    title: str = Form(...),
    db: Session = Depends(get_db),
):
    filename = file.filename
    file_type = filename.rsplit(".", 1)[-1].lower()
    if file_type not in ("pdf", "epub", "txt"):
        return {"error": f"Unsupported file type: {file_type}"}

    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    file_path = os.path.join(settings.UPLOAD_DIR, filename)
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    paragraphs = parse_file(file_path, file_type)

    book = Book(title=title, filename=filename, file_type=file_type, total_paragraphs=len(paragraphs))
    db.add(book)
    db.commit()
    db.refresh(book)

    emb_service = get_embedding_service()
    for para in paragraphs:
        embedding_vector = emb_service.generate_embedding(para["content"])
        embedding_json = emb_service.embedding_to_json(embedding_vector)
        p = Paragraph(
            book_id=book.id,
            para_index=para["para_index"],
            page_num=para.get("page_num"),
            content=para["content"],
            embedding_blob=embedding_json,
        )
        db.add(p)
    db.commit()

    return {"book_id": book.id, "title": book.title, "total_paragraphs": len(paragraphs)}
